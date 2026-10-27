// Conversations between a creator and the brand team (backend api/messages.py), through the same proxy.

import { ApiError, api, json } from "./review-client";

export type Party = { id: number; name: string; role: string };
export type Contact = Party & { conversation_id: number | null };
export type SharedFile = {
  id: string;
  kind: "image" | "video" | "document";
  name: string;
  media_type: string;
  bytes: number;
  duration?: number | null;
};

export type ChatMessage = {
  id: number;
  conversation_id: number;
  kind: "text" | "call" | "inki";
  text: string;
  call: { url: string; provider: string } | null;
  files: SharedFile[];
  piece: { id: number; title: string } | null;
  reply_to: { id: number; sender: string; excerpt: string; deleted: boolean } | null;
  /** null: Inki. */
  sender: Party | null;
  asked_by: Party | null;
  created_at: string;
  edited: boolean;
  deleted: boolean;
};

export type ConversationRow = {
  id: number;
  other: Party;
  last: ChatMessage | null;
  unread: number;
  /** The other person spoke last: the ball is in this person's court. */
  needs_reply: boolean;
  topic: { id: number; title: string; status: string } | null;
  last_message_at: string;
};

export type LiveEvent =
  | { type: "message"; message: ChatMessage }
  | { type: "read"; conversation_id: number; last_id: number }
  | { type: "inki"; conversation_id: number; state: "thinking" | "failed" };

export const listContacts = () => api<Contact[]>("conversations/people");
export const listConversations = () => api<ConversationRow[]>("conversations");
export const openConversation = (userId: number) => api<ConversationRow>("conversations", json({ user_id: userId }));
export const unreadMessages = () => api<{ unread: number }>("conversations/unread");

export function listMessages(conversationId: number, cursor: { before?: number; after?: number } = {}) {
  const q = new URLSearchParams();
  if (cursor.before) q.set("before", String(cursor.before));
  if (cursor.after !== undefined) q.set("after", String(cursor.after));
  const s = q.toString();
  return api<ChatMessage[]>(`conversations/${conversationId}/messages${s ? `?${s}` : ""}`);
}

export type Outgoing = {
  text?: string; call_url?: string; content_id?: number | null; files?: string[]; reply_to?: number | null;
  client_id: string;
};
export const sendMessage = (conversationId: number, body: Outgoing) =>
  api<ChatMessage>(`conversations/${conversationId}/messages`, json(body));
export const editMessage = (conversationId: number, id: number, text: string) =>
  api<ChatMessage>(`conversations/${conversationId}/messages/${id}`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
export const deleteMessage = (conversationId: number, id: number) =>
  api<ChatMessage>(`conversations/${conversationId}/messages/${id}`, { method: "DELETE" });
export const markRead = (conversationId: number, lastId: number) =>
  api<null>(`conversations/${conversationId}/read`, json({ last_id: lastId }));

export const inkiConsent = () => api<{ accepted_at: string | null }>("conversations/inki-consent");
export const acceptInki = () => api<{ accepted_at: string }>("conversations/inki-consent", json({ accept: true }));
export const withdrawInki = () => api<null>("conversations/inki-consent", { method: "DELETE" });
/** The API's answer when @Inki is used before agreeing to it reading the conversation. */
export const needsInkiConsent = (e: unknown) =>
  e instanceof ApiError && e.status === 428 && (e.detail as { code?: string })?.code === "inki_consent_required";

export const fileUrl = (conversationId: number, fileId: string) => `/api/v/conversations/${conversationId}/files/${fileId}`;
export const posterUrl = (conversationId: number, fileId: string) => `${fileUrl(conversationId, fileId)}/poster`;

/** A fresh id per message, so a resend after a dropped connection is stored once. */
export const newClientId = () =>
  (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`).replace(/[^A-Za-z0-9_-]/g, "").slice(0, 40);

export const CONVERSATIONS_SEEN_EVENT = "vt:conversations-seen";

/** Meeting services the API accepts for a call card, with where to start a new meeting on each. */
export const CALL_STARTERS = [
  { name: "Google Meet", start: "https://meet.new" },
  { name: "Microsoft Teams", start: "https://teams.microsoft.com/l/meeting/new" },
  { name: "Zoom", start: "https://zoom.us/start/videomeeting" },
];

/** What a conversation accepts as a file, checked again by the API. */
export const ACCEPT = "image/*,video/*,application/pdf,.docx,.pptx,.xlsx";
export const MAX_FILES = 6;
