// Conversations between a creator and the brand team (backend api/messages.py), through the same proxy.

import { api, json } from "./review-client";

export type Party = { id: number; name: string; role: string };
export type Contact = Party & { conversation_id: number | null };

export type ChatMessage = {
  id: number;
  conversation_id: number;
  kind: "text" | "call" | "inki";
  text: string;
  call: { url: string; provider: string } | null;
  piece: { id: number; title: string } | null;
  /** null: Inki. */
  sender: Party | null;
  asked_by: Party | null;
  created_at: string;
};

export type ConversationRow = {
  id: number;
  other: Party;
  last: ChatMessage | null;
  unread: number;
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

export const sendMessage = (conversationId: number,
  body: { text?: string; call_url?: string; content_id?: number | null; client_id: string }) =>
  api<ChatMessage>(`conversations/${conversationId}/messages`, json(body));

export const markRead = (conversationId: number, lastId: number) =>
  api<null>(`conversations/${conversationId}/read`, json({ last_id: lastId }));

/** A fresh id per message, so a resend after a dropped connection is stored once. */
export const newClientId = () =>
  (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`).replace(/[^A-Za-z0-9_-]/g, "").slice(0, 40);

export const MESSAGES_SEEN_EVENT = "vt:messages-seen";

/** Meeting services the API accepts for a call card, with where to start a new meeting on each. */
export const CALL_STARTERS = [
  { name: "Google Meet", start: "https://meet.new" },
  { name: "Microsoft Teams", start: "https://teams.microsoft.com/l/meeting/new" },
  { name: "Zoom", start: "https://zoom.us/start/videomeeting" },
];
