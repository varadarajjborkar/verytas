/** Reads an OpenAI-style SSE stream, calling `onText` with each content delta.
 * Lines are only parsed once complete; an error payload from upstream throws. */
export async function readStream(res: Response, onText: (t: string) => void) {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const handle = (line: string) => {
    const data = line.startsWith("data:") ? line.slice(5).trim() : "";
    if (!data || data === "[DONE]") return;
    let event: { error?: { message?: string } | string; choices?: { delta?: { content?: unknown } }[] };
    try {
      event = JSON.parse(data);
    } catch {
      return; // not JSON (a comment or keep-alive); complete lines are never split
    }
    if (event.error) throw new Error(typeof event.error === "string" ? event.error : event.error.message ?? "The model failed.");
    const delta = event.choices?.[0]?.delta?.content;
    if (typeof delta === "string") onText(delta);
  };
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = done ? "" : lines.pop() ?? "";
    lines.forEach(handle);
    if (done) break;
  }
}
