import { z } from "zod/v4";
import { submitForReview } from "@/lib/backend";

const Input = z.object({
  title: z.string().trim().min(1).max(300),
  channel: z.enum(["general", "blog", "linkedin", "x", "instagram", "email", "press"]),
  body: z.string().trim().min(1).max(20_000),
});

export async function POST(request: Request) {
  const parsed = Input.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return Response.json({ error: "Give the content a title, a channel and some text (max 20,000 characters)." },
      { status: 400 });
  }
  try {
    return Response.json(await submitForReview(parsed.data));
  } catch (err) {
    console.error("[verytas] review failed:", (err as Error).message);
    return Response.json({ error: "The review service did not respond. Try again in a moment." }, { status: 502 });
  }
}
