// Where Ask Verytas conversations are kept: the person's account through the
// API (/chats, private to them), or this browser when the console runs on demo
// data with no API behind it.

export type StoredMessage = { role: "user" | "assistant"; content: string; images?: string[] };
export type ThreadSummary = { id: number; title: string; updated_at: string };
export type Thread = ThreadSummary & { messages: StoredMessage[] };

const LOCAL_KEY = "vt-chats";

function readLocal(): Thread[] {
  try {
    const raw = localStorage.getItem(LOCAL_KEY);
    return raw ? (JSON.parse(raw) as Thread[]) : [];
  } catch {
    return [];
  }
}

function writeLocal(threads: Thread[]): boolean {
  try {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(threads.slice(0, 50)));
    return true;
  } catch {
    return false; // storage blocked or full; the conversation still works for this visit
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v/${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!res.ok) throw Object.assign(new Error(`chats: ${res.status}`), { status: res.status });
  return (res.status === 204 ? null : await res.json()) as T;
}

export type ChatStore = {
  where: "account" | "browser";
  list(): Promise<ThreadSummary[]>;
  get(id: number): Promise<Thread | null>;
  save(id: number | null, title: string, messages: StoredMessage[]): Promise<ThreadSummary>;
  remove(id: number): Promise<void>;
};

const accountStore: ChatStore = {
  where: "account",
  list: () => api<ThreadSummary[]>("chats"),
  get: (id) => api<Thread>(`chats/${id}`).catch(() => null),
  save: (id, title, messages) => api<Thread>(id == null ? "chats" : `chats/${id}`, {
    method: id == null ? "POST" : "PUT",
    body: JSON.stringify({ title, messages }),
  }),
  remove: async (id) => { await api(`chats/${id}`, { method: "DELETE" }); },
};

const browserStore: ChatStore = {
  where: "browser",
  list: async () => readLocal().map(({ id, title, updated_at }) => ({ id, title, updated_at })),
  get: async (id) => readLocal().find((t) => t.id === id) ?? null,
  save: async (id, title, messages) => {
    const all = readLocal();
    const thread: Thread = { id: id ?? Date.now(), title, messages, updated_at: new Date().toISOString() };
    writeLocal([thread, ...all.filter((t) => t.id !== thread.id)]);
    return thread;
  },
  remove: async (id) => { writeLocal(readLocal().filter((t) => t.id !== id)); },
};

/** The account store when the API answers, the browser store when it runs in demo mode. */
export async function openChatStore(): Promise<ChatStore> {
  try {
    await accountStore.list();
    return accountStore;
  } catch (err) {
    return (err as { status?: number }).status === 503 ? browserStore : accountStore;
  }
}

/** Downscales an image file to a JPEG data URL small enough to keep with the conversation. */
export async function imageToDataUrl(file: File, maxSide = 1024, maxChars = 580_000): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("This browser can't prepare images.");
  ctx.fillStyle = "#fff"; // JPEG has no transparency
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  for (const quality of [0.85, 0.7, 0.55, 0.4]) {
    const url = canvas.toDataURL("image/jpeg", quality);
    if (url.length <= maxChars) return url;
  }
  throw new Error(`${file.name} is too detailed to attach, even when shrunk.`);
}
