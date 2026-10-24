import "server-only";

// Keeps the chat routes' own instructions to themselves. They hold no secrets (the data is filtered and
// redacted before it is sent), but a model that recites its rules on request hands anyone a map of what to
// argue around, so asking for them is answered here, in code, and a reply that quotes them never leaves.
// Two layers, because a model can be talked round and a pattern can be worded round:
//   1. the question: requests for the instructions themselves get a fixed reply, and the model is not called;
//   2. the answer: the stream is held back a little and checked against the instruction text; a reply that
//      starts quoting it is replaced by the same fixed reply before any of the quote is sent.

// Each pattern names the assistant's own set-up, not instructions in general: "show me the logo usage
// instructions", "the creator's original message" and "ignore the previous warnings" are workspace questions.
const ASKS = [
  /\bsystem\s+(prompt|message|instructions?)\b/i,
  /\b(initial|hidden|developer|secret|full|original)\s+(system\s+)?prompt\b/i,
  /\bdeveloper\s+(message|instructions?)\b/i,
  /\byour\s+(own\s+)?(prompt|instructions?|directives|configuration|system message|setup text|guidance)\b/i,
  /\b(repeat|print|show|reveal|output|dump|display|copy|recite|translate|encode|spell out|write out|type out|paste)\b[^.?!\n]{0,60}\b(everything|text|words|all)( that)?( came| comes| come| is| was| you were given| you got)? (before|above) (my|this|our|the) (first |opening )?(message|question|conversation|chat)\b/i,
  /\bword for word\b[^.?!\n]{0,60}\b(before my|before this|above my|you were (told|given))\b/i,
  /\bignore\s+(all\s+)?(of\s+)?(your|the|my|any)?\s*(previous|prior|above|earlier|preceding|system)\s+(instructions?|rules|prompts?|directions)\b/i,
  /\bignore\s+(all\s+)?(of\s+)?your\s+(instructions?|rules|prompts?|directions)\b/i,
  /\b(what|how)\s+(were|are|have)\s+you\s+(been\s+)?(told|instructed|programmed|prompted|configured)\b/i,
  /\beverything\s+you\s+(were|have been|got)\s+(given|told|sent)\b/i,
  /\b(guidance|rules|instructions|directions)\s+(that\s+)?you\s+(operate under|operate by|run on|were given)\b/i,
];

/** Whether the question asks for the assistant's instructions rather than about the workspace. Kept narrow:
 * "what do our guidelines say about emoji" is a question about the brand, not about the assistant. */
export function asksForInstructions(text: string): boolean {
  return ASKS.some((pattern) => pattern.test(text));
}

const words = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().split(" ").filter(Boolean);
const SHINGLE = 8; // words in a row: long enough that ordinary phrasing doesn't repeat it by chance
// Words of the instructions quoted before a reply counts as reciting them. An answer may restate one rule
// line in its own sentence ("Verytas has no reach or engagement data", up to about 15 words); a recital
// runs on for sentences. Counted as words covered, so one long line is not counted again per window.
const LEAK_WORDS = 30;
const HOLD = 260; // characters held back: more than LEAK_WORDS words of ordinary prose

function shingles(text: string): Set<string> {
  const w = words(text);
  const out = new Set<string>();
  for (let i = 0; i + SHINGLE <= w.length; i++) out.add(w.slice(i, i + SHINGLE).join(" "));
  return out;
}

/**
 * The prose of a prompt that also teaches an output syntax: code spans, signatures and examples dropped.
 * A correct answer is written in that syntax and may echo an example line for line, so only the sentences
 * around them are worth matching; a reply reciting those is reciting the prompt.
 */
export function proseOf(prompt: string): string {
  return prompt
    .split("\n")
    .filter((line) => !/[()=]|^\s*[-*]?\s*`/.test(line))
    .map((line) => line.replace(/`[^`]*`/g, " "))
    .join("\n");
}

/** Whether `text` quotes the instructions, given their shingles. */
function quotes(text: string, secret: Set<string>): boolean {
  const w = words(text);
  let covered = 0;
  let reach = 0; // first word not yet counted
  for (let i = 0; i + SHINGLE <= w.length; i++) {
    if (!secret.has(w.slice(i, i + SHINGLE).join(" "))) continue;
    covered += i + SHINGLE - Math.max(i, reach);
    reach = i + SHINGLE;
    if (covered >= LEAK_WORDS) return true;
  }
  return false;
}

const encoder = new TextEncoder();
const event = (content: string) => encoder.encode(`data: ${JSON.stringify({ choices: [{ delta: { content } }] })}\n\n`);
const DONE = encoder.encode("data: [DONE]\n\n");

/** A complete answer in the stream format the pages read (lib/sse.ts), for when the model is not asked. */
export function fixedAnswer(content: string): Response {
  return new Response(new ReadableStream({
    start(c) { c.enqueue(event(content)); c.enqueue(DONE); c.close(); },
  }), { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform" } });
}

/**
 * The model's stream, re-sent in the same format with the last HOLD characters held back. If what has
 * arrived quotes `instructions`, nothing more of it is sent and `refusal` goes instead. Error events pass
 * straight through so the page can say what went wrong.
 */
export function guardedStream(upstream: ReadableStream<Uint8Array>, instructions: string, refusal: string): ReadableStream<Uint8Array> {
  const secret = shingles(instructions);
  const reader = upstream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let text = "";
  let sent = 0;
  let checked = 0;

  return new ReadableStream({
    // Each pull must hand over something or end the stream: a pull that returns empty-handed is not
    // called again, and the page would wait for ever. Text being held back is not enough, so keep reading.
    async pull(c) {
      for (;;) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split("\n");
        buffer = done ? "" : lines.pop() ?? "";
        let passed = false;
        for (const line of lines) {
          const data = line.startsWith("data:") ? line.slice(5).trim() : "";
          if (!data || data === "[DONE]") continue;
          try {
            const parsed = JSON.parse(data) as { error?: unknown; choices?: { delta?: { content?: unknown } }[] };
            if (parsed.error) {
              c.enqueue(encoder.encode(`data: ${data}\n\n`));
              passed = true;
            }
            const delta = parsed.choices?.[0]?.delta?.content;
            if (typeof delta === "string") text += delta;
          } catch {
            // not JSON: a comment or keep-alive, never content
          }
        }
        // Checking costs a pass over the reply, so only once enough has arrived to change the answer.
        if (done || text.length - checked >= 24) {
          checked = text.length;
          if (quotes(text, secret)) {
            await reader.cancel().catch(() => undefined);
            c.enqueue(event(sent ? `\n\n${refusal}` : refusal));
            c.enqueue(DONE);
            c.close();
            return;
          }
        }
        const upto = done ? text.length : text.length - HOLD;
        if (upto > sent) {
          c.enqueue(event(text.slice(sent, upto)));
          sent = upto;
          passed = true;
        }
        if (done) {
          c.enqueue(DONE);
          c.close();
          return;
        }
        if (passed) return;
      }
    },
    cancel(reason) {
      return reader.cancel(reason);
    },
  });
}
