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
  reason_text?: string | null;
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
  /** "body" for typed text; otherwise a derived source such as "img:hero:ocr" or "vid:reel:speech". */
  source?: string;
  locator?: { image?: string; document?: string; page?: number; video?: string; time?: [number, number];
    box?: number[]; intake?: string } | null;
  assessment?: { by: string; outcome?: string; view?: string; reader_reading?: string; suggestion?: string;
    reader_probability?: number; dispute_id?: number } | null;
};

export type AgentNode = {
  id: string;
  role: string;
  label: string;
  parent: string | null;
  depth: number;
  status: "ok" | "not_checked" | "failed" | "skipped" | "running";
  note: string | null;
  ms: number;
  findings: number;
  detail: Record<string, unknown>;
};

export type SourceInfo = {
  id: string;
  kind: string;
  route: string;
  confidence: number;
  locator: Record<string, unknown>;
  parent: string | null;
  chars: number;
  text: string;
};

export type Escalation = { reason: string; detail?: string; finding?: string };

export type Dispute = {
  id: number;
  finding_id: number;
  content_id: number;
  status: "queued" | "running" | "upheld" | "overturned" | "escalated";
  claim: string;
  language: string | null;
  verdict: { decided_by?: string; reason?: string; safer_alternative?: string; reader_reading?: string;
    layers?: { layer: string; p: number | null }[] };
  created_at: string;
  decided_at: string | null;
};

export type Irregularity = { code: string; subject: string; value: string; expected: string; why: string;
  over_limit: boolean };

export type Precheck = { channel: string; metrics: Record<string, unknown>; irregularities: Irregularity[];
  needs_reason: boolean };

export type UploadedMedia = { id: string; media_type: string; name: string | null; bytes: number;
  metrics: Record<string, unknown> };

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
    models?: { llm: string; judge: string; vision?: string };
    redactions?: number;
    workers?: Record<string, { status: string; note: string | null; findings: number; ms: number }>;
    agents?: AgentNode[];
    sources?: SourceInfo[];
    scenes?: Record<string, { description?: string; tone?: string; risky_elements?: string[];
      text_in_image?: string }>;
    escalations?: Escalation[];
    usage?: Record<string, { input: number; output: number; calls: number }>;
  };
  error: string | null;
  findings: Finding[];
};

export type ReviewResult = { review: Review; body: string; source: Source };

/** Where a payload came from. The UI labels demo data so nobody mistakes it for live. */
export type Source = "live" | "demo";

export type Sourced<T> = { data: T; source: Source };

export type ContentStatus = "draft" | "in_review" | "changes_requested" | "approved" | "published" | "withdrawn";

/** A row in the review history: GET /contents. */
export type ContentRow = {
  id: number;
  title: string;
  channel: string;
  tier: "public" | "internal" | "confidential";
  status: ContentStatus;
  created_by: number;
  created_at: string;
  version_count: number;
  updated_at: string | null;
  /** When it entered its current status: how long it has waited in a queue. */
  status_since?: string | null;
  latest_review: {
    id: number; status: Review["status"]; overall: number | null;
    blockers: number; warnings: number; advisories: number; finished_at: string | null;
  } | null;
};

/** GET /contents/{id}. */
export type ContentDetail = Omit<ContentRow, "version_count" | "updated_at" | "latest_review"> & {
  versions: { id: number; version_no: number; parent_id: number | null; body: string; created_at: string }[];
  latest_review_id: number | null;
};

export type Me = { id: number; email: string; name: string; role: string; clearance: string };

// --- the brand team's side -------------------------------------------------------------------

export type Person = { id: number; name: string; role: string };

/** One entry in a piece's shared history (GET /contents/{id}/timeline). */
export type TimelineItem = { at: string; actor: Person | null } & (
  | { type: "version"; version: number }
  | { type: "review"; version: number; review_id: number; status: string; score: number | null; blockers: number;
      warnings: number; advisories: number }
  | { type: "status"; from: ContentStatus; to: ContentStatus; note: string | null }
  | { type: "comment"; id: number; parent_id: number | null; version: number | null; body: string; span: [number, number] | null }
  | { type: "decision"; finding: string; level: Level; version: number; action: Decision["action"];
      reason_code: string | null; reason: string | null }
);
export type Timeline = { status: ContentStatus; author: Person | null; items: TimelineItem[] };

export type RuleKind = "deterministic" | "semantic";
export type RuleCategory = "tone" | "terminology" | "messaging" | "visual" | "accessibility" | "legal" | "claims" | "confidentiality";
export type Rule = {
  id: number;
  code: string;
  version: number;
  category: RuleCategory;
  kind: RuleKind;
  severity: "must" | "should" | "may";
  title: string;
  text: string;
  good_examples: string[];
  bad_examples: string[];
  pattern: Record<string, unknown>;
  source_ref: string | null;
  tier: "public" | "internal" | "confidential";
  status: "draft" | "active" | "retired";
  system: boolean;
};
export type RuleDraft = Omit<Rule, "id" | "version" | "status" | "system">;

export type Fact = {
  id: number;
  statement: string;
  value: number | null;
  unit: string | null;
  subject: string | null;
  source_ref: string;
  tier: Rule["tier"];
  valid_from: string;
  valid_to: string | null;
  supersedes_id: number | null;
  approved: boolean;
};

export type Term = { id: number; term: string; note: string | null; embargo_until: string | null };

export type BrandAsset = {
  id: number;
  name: string;
  kind: "logo" | "mascot" | "other";
  part: string;
  wordmark: string | null;
  media_type: string;
  notes: string | null;
  tier: Rule["tier"];
  active: boolean;
  created_at: string;
  warning?: string | null;
};
