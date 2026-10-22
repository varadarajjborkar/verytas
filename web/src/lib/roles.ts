// The console has two sides. Creators write and fix their own pieces; the brand
// team (reviewers, approvers, auditors, brand admins) works a queue, decides on
// findings and keeps the guideline library. Each side sees only its own screens.
// The API enforces what each role may change (library writes, approvals,
// dismissing blockers); reading a piece follows clearance, not side, so the
// workspace stays transparent to everyone in it.

export type Side = "creator" | "manager";

export const sideOf = (role: string | null | undefined): Side => (role === "creator" ? "creator" : "manager");
/** Only brand admins change the library; everyone on the brand team can read it. */
export const canEditLibrary = (role: string | null | undefined) => role === "brand_admin";
/** Who may accept or dismiss findings (the API also limits dismissing blockers to approvers). */
export const canDecide = (role: string | null | undefined) => role === "reviewer" || role === "approver" || role === "brand_admin";

export const ROLE_LABEL: Record<string, string> = {
  creator: "Creator",
  reviewer: "Reviewer",
  approver: "Approver",
  auditor: "Auditor",
  brand_admin: "Brand admin",
};
