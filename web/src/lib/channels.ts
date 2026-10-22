// The one list of channels: the composer offers it, and every list, filter and header names a channel from it.
export const CHANNELS: { value: string; label: string; short?: string; limit?: number }[] = [
  { value: "instagram", label: "Instagram", limit: 2200 },
  { value: "tiktok", label: "TikTok", limit: 2200 },
  { value: "x", label: "X (Twitter)", short: "X", limit: 280 },
  { value: "linkedin", label: "LinkedIn", limit: 3000 },
  { value: "youtube", label: "YouTube", limit: 5000 },
  { value: "youtube_shorts", label: "YouTube Shorts", limit: 5000 },
  { value: "facebook", label: "Facebook" },
  { value: "threads", label: "Threads", limit: 500 },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "email", label: "Email newsletter", short: "Email" },
  { value: "blog", label: "Blog or website", short: "Blog" },
  { value: "press", label: "Press release" },
  { value: "other", label: "Other…", short: "Other" },
];

const BY_VALUE = new Map(CHANNELS.map((c) => [c.value, c]));

/** A channel's display name; a custom "Other" channel keeps its own wording, first letter raised. */
export function channelName(value: string): string {
  const c = BY_VALUE.get(value);
  if (c) return c.short ?? c.label;
  const plain = value.replaceAll("_", " ");
  return plain.charAt(0).toUpperCase() + plain.slice(1);
}
