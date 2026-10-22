// Word-level track changes between two versions of a piece. A plain LCS over
// tokens is exact and fast enough at post length; past the budget below it
// falls back to whole lines, which keeps a long document diff responsive.

export type Chunk = { op: "same" | "add" | "del"; text: string };

const CELL_BUDGET = 4_000_000;

const words = (s: string) => s.match(/\s+|[^\s]+/g) ?? [];
const lines = (s: string) => s.match(/[^\n]*\n|[^\n]+$/g) ?? [];

export function diffText(before: string, after: string): Chunk[] {
  let a = words(before);
  let b = words(after);
  if (a.length * b.length > CELL_BUDGET) {
    a = lines(before);
    b = lines(after);
  }
  // Trim the shared head and tail first: edits are usually local.
  let head = 0;
  while (head < a.length && head < b.length && a[head] === b[head]) head++;
  let tail = 0;
  while (tail < a.length - head && tail < b.length - head && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail++;
  const midA = a.slice(head, a.length - tail);
  const midB = b.slice(head, b.length - tail);

  const out: Chunk[] = [];
  const push = (op: Chunk["op"], text: string) => {
    const prev = out[out.length - 1];
    if (prev && prev.op === op) prev.text += text;
    else out.push({ op, text });
  };
  if (head) push("same", a.slice(0, head).join(""));

  if (midA.length * midB.length > CELL_BUDGET) {
    // Still too big after trimming: show it as replaced rather than freeze the page.
    if (midA.length) push("del", midA.join(""));
    if (midB.length) push("add", midB.join(""));
  } else {
    const n = midA.length, m = midB.length;
    // lcs[i * (m + 1) + j] = LCS length of midA[i:] and midB[j:]
    const lcs = new Uint32Array((n + 1) * (m + 1));
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        lcs[i * (m + 1) + j] = midA[i] === midB[j]
          ? lcs[(i + 1) * (m + 1) + j + 1] + 1
          : Math.max(lcs[(i + 1) * (m + 1) + j], lcs[i * (m + 1) + j + 1]);
      }
    }
    let i = 0, j = 0;
    while (i < n && j < m) {
      if (midA[i] === midB[j]) { push("same", midA[i]); i++; j++; }
      else if (lcs[(i + 1) * (m + 1) + j] >= lcs[i * (m + 1) + j + 1]) { push("del", midA[i]); i++; }
      else { push("add", midB[j]); j++; }
    }
    while (i < n) push("del", midA[i++]);
    while (j < m) push("add", midB[j++]);
  }

  if (tail) push("same", a.slice(a.length - tail).join(""));
  return out;
}

export function diffStats(chunks: Chunk[]): { added: number; removed: number } {
  const count = (op: Chunk["op"]) => chunks.filter((c) => c.op === op)
    .reduce((n, c) => n + (c.text.match(/[^\s]+/g)?.length ?? 0), 0);
  return { added: count("add"), removed: count("del") };
}
