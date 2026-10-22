import { z } from "zod/v4";
import { BackendError, recordDecision } from "@/lib/backend";

const Input = z.object({
  findingId: z.number().int().positive(),
  action: z.enum(["accepted", "rejected", "edited", "escalated"]),
  suggestion_id: z.number().int().positive().optional(),
  reason_code: z.enum(["false_positive", "not_applicable", "guideline_unclear", "intentional", "other"]).optional(),
  reason_text: z.string().max(2000).optional(),
});

export async function POST(request: Request) {
  const parsed = Input.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return Response.json({ error: "invalid decision" }, { status: 400 });
  const { findingId, ...decision } = parsed.data;
  try {
    return Response.json(await recordDecision(findingId, decision));
  } catch (err) {
    const status = err instanceof BackendError ? err.status : 502;
    return Response.json({ error: status === 403 ? "Only approvers can dismiss a blocker." : "Could not save the decision." },
      { status: status === 403 ? 403 : 502 });
  }
}
