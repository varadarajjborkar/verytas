// Shapes returned by the Verytas API (backend/verytas/api). Kept in one place
// so the demo data and the live client can't drift apart.

export type Level = "blocker" | "warning" | "advisory";

export type Overview = {
  content: Record<string, number>;
  reviews: { total: number; done: number; failed: number };
  findings: {
    total: number;
    by_level: Partial<Record<Level, number>>;
    by_category: Record<string, number>;
  };
  decisions: {
    accepted?: number;
    rejected?: number;
    edited?: number;
    escalated?: number;
    acceptance_rate: number | null;
  };
  top_rules: { rule_id: number; code: string; title: string; findings: number }[];
  trend: { day: string; blocker: number; warning: number; advisory: number }[];
};

export type RuleHealth = {
  rule_id: number;
  code: string;
  title: string;
  severity: "must" | "should" | "may";
  findings: number;
  decisions: number;
  accepted: number;
  rejected: number;
  override_rate: number;
  unclear_share: number;
  reviewer_disagreement: number;
  agreement_posterior: { mean: number; lower_90: number };
  ambiguity: number | null;
  enough_data: boolean;
  advice: string[];
};

export type Recurring = { rule: string; title: string; phrase: string; count: number; reviews: number };

export type Citation = { kind: "rule" | "fact"; id: number; label: string; source: string | null };

export type Suggestion = {
  id: number;
  original: string;
  proposed: string;
  rationale: string;
  intent_preserved: number | null;
  model: string | null;
};

export type Decision = {
  id: number;
  actor_id: number;
  action: "accepted" | "rejected" | "edited" | "escalated";
  reason_code: string | null;
  created_at: string;
};

export type Finding = {
  id: number;
  unit_id: string;
  category: string;
  level: Level;
  title: string;
  explanation: string;
  quote: string | null;
  span_start: number | null;
  span_end: number | null;
  confidence: number;
  checker: string;
  model: string | null;
  citations: Citation[];
  suggestions: Suggestion[];
  decisions: Decision[];
  signature_valid: boolean;
};

export type CoverageStatus = "checked" | "not_checked" | "not_configured" | "degraded";

export type CategoryScore = {
  checked: boolean;
  status?: CoverageStatus;
  score: number | null;
  findings: number;
  blockers: number;
};

export type Review = {
  id: number;
  version_id: number;
  status: "queued" | "running" | "done" | "failed";
  summary: {
    categories?: Record<string, CategoryScore>;
    overall?: number;
    blockers?: number;
    warnings?: number;
    advisories?: number;
  };
  coverage: {
    not_checked?: string[];
    notes?: string[];
    models?: { llm: string; judge: string };
    redactions?: number;
    workers?: Record<string, { status: string; note: string | null; findings: number; ms: number }>;
  };
  error: string | null;
  findings: Finding[];
};

export type ReviewResult = { review: Review; body: string; source: Source };

/** Where a payload came from. The UI labels demo data so nobody mistakes it for live. */
export type Source = "live" | "demo";

export type Sourced<T> = { data: T; source: Source };
