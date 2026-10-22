// Realistic sample data for running the UI without a backend. The numbers are
// made up but internally consistent (counts add up, rates match counts).

import type { Overview, Recurring, Review, RuleHealth } from "./types";

function trend(days: number): Overview["trend"] {
  const start = new Date("2026-09-21T00:00:00Z");
  return Array.from({ length: days }, (_, i) => {
    const d = new Date(start);
    d.setUTCDate(start.getUTCDate() + i);
    const weekday = d.getUTCDay() !== 0 && d.getUTCDay() !== 6;
    // Volume dips at weekends; blockers trend down after the codename rule landed mid-month.
    const base = weekday ? 9 : 3;
    return {
      day: d.toISOString().slice(0, 10),
      blocker: Math.max(0, Math.round((i < 14 ? 3 : 1) * (weekday ? 1 : 0.4) + ((i * 7) % 3) - 1)),
      warning: base + ((i * 5) % 4),
      advisory: base + 4 + ((i * 3) % 5),
    };
  });
}

export const demoOverview: Overview = {
  content: { draft: 14, in_review: 9, changes_requested: 6, approved: 21, published: 48 },
  reviews: { total: 212, done: 207, failed: 5 },
  findings: {
    total: 1184,
    by_level: { blocker: 61, warning: 402, advisory: 721 },
    by_category: {
      terminology: 318, tone: 241, accessibility: 236, claims: 187, visual: 96, confidentiality: 38,
      legal: 41, messaging: 27,
    },
  },
  decisions: { accepted: 512, edited: 88, rejected: 171, escalated: 12, acceptance_rate: 0.778 },
  top_rules: [
    { rule_id: 11, code: "TERM-01", title: "House spellings", findings: 204 },
    { rule_id: 12, code: "VOICE-01", title: "Plain words, no jargon", findings: 161 },
    { rule_id: 2, code: "A11Y-ALT", title: "Images need meaningful alt text", findings: 118 },
    { rule_id: 10, code: "CLAIM-UNSUPPORTED", title: "Promotional claims need backing", findings: 97 },
    { rule_id: 4, code: "A11Y-HASHTAG", title: "Use CamelCase for multi-word hashtags", findings: 76 },
    { rule_id: 8, code: "CLAIM-CONTRADICTED", title: "Claims must match approved facts", findings: 58 },
    { rule_id: 15, code: "VIS-01", title: "Brand palette only", findings: 49 },
    { rule_id: 1, code: "CONF-LEAK", title: "No confidential or embargoed terms", findings: 38 },
  ],
  trend: trend(30),
};

export const demoHealth: RuleHealth[] = [
  {
    rule_id: 12, code: "VOICE-01", title: "Plain words, no jargon", severity: "should", findings: 161, decisions: 118,
    accepted: 61, rejected: 57, override_rate: 0.483, unclear_share: 0.561, reviewer_disagreement: 0.62,
    agreement_posterior: { mean: 0.517, lower_90: 0.442 }, ambiguity: 0.545, enough_data: true,
    advice: [
      "clarify wording: reviewers keep overriding or disagreeing on this rule",
      "add a good and a bad example: several rejections say the guideline is unclear",
    ],
  },
  {
    rule_id: 16, code: "MSG-02", title: "Lead with the customer outcome", severity: "should", findings: 27, decisions: 19,
    accepted: 9, rejected: 10, override_rate: 0.526, unclear_share: 0.4, reviewer_disagreement: 0.5,
    agreement_posterior: { mean: 0.476, lower_90: 0.31 }, ambiguity: 0.475, enough_data: true,
    advice: ["add a good and a bad example: several rejections say the guideline is unclear"],
  },
  {
    rule_id: 10, code: "CLAIM-UNSUPPORTED", title: "Promotional claims need backing", severity: "should",
    findings: 97, decisions: 81, accepted: 58, rejected: 23, override_rate: 0.284, unclear_share: 0.174,
    reviewer_disagreement: 0.21, agreement_posterior: { mean: 0.711, lower_90: 0.63 }, ambiguity: 0.227,
    enough_data: true, advice: [],
  },
  {
    rule_id: 4, code: "A11Y-HASHTAG", title: "Use CamelCase for multi-word hashtags", severity: "should", findings: 76,
    decisions: 52, accepted: 44, rejected: 8, override_rate: 0.154, unclear_share: 0.125, reviewer_disagreement: 0.1,
    agreement_posterior: { mean: 0.833, lower_90: 0.75 }, ambiguity: 0.13, enough_data: true, advice: [],
  },
  {
    rule_id: 11, code: "TERM-01", title: "House spellings", severity: "should", findings: 204, decisions: 176,
    accepted: 169, rejected: 7, override_rate: 0.04, unclear_share: 0.0, reviewer_disagreement: 0.05,
    agreement_posterior: { mean: 0.955, lower_90: 0.93 }, ambiguity: 0.029, enough_data: true, advice: [],
  },
  {
    rule_id: 1, code: "CONF-LEAK", title: "No confidential or embargoed terms", severity: "must", findings: 38,
    decisions: 36, accepted: 35, rejected: 1, override_rate: 0.028, unclear_share: 0.0, reviewer_disagreement: 0.0,
    agreement_posterior: { mean: 0.947, lower_90: 0.89 }, ambiguity: 0.011, enough_data: true, advice: [],
  },
  {
    rule_id: 17, code: "VIS-02", title: "Logo clear space", severity: "must", findings: 3, decisions: 2,
    accepted: 1, rejected: 1, override_rate: 0.5, unclear_share: 0, reviewer_disagreement: 0,
    agreement_posterior: { mean: 0.5, lower_90: 0.06 }, ambiguity: null, enough_data: false, advice: [],
  },
];

export const demoRecurring: Recurring[] = [
  { rule: "TERM-01", title: "House spellings", phrase: "e-mail", count: 63, reviews: 41 },
  { rule: "VOICE-01", title: "Plain words, no jargon", phrase: "leverage", count: 38, reviews: 30 },
  { rule: "A11Y-HASHTAG", title: "Use CamelCase for multi-word hashtags", phrase: "#brandgovernance", count: 22, reviews: 19 },
  { rule: "CLAIM-OUTDATED", title: "Claims must not rely on expired facts", phrase: "500+ teams", count: 17, reviews: 15 },
  { rule: "CONF-LEAK", title: "No confidential or embargoed terms", phrase: "project lumen", count: 9, reviews: 9 },
];

export const demoBody =
  "Verytas is trusted by 1,000+ teams. Sign-in takes seconds.\n\n" +
  "Project Lumen brings video review next month!\n\n" +
  "We leverage synergies to unlock paradigm shifts. Read [click here](https://verytas.example).";

export const demoReview: Review = {
  id: 0,
  version_id: 0,
  status: "done",
  summary: {
    overall: 0.5,
    blockers: 2,
    warnings: 3,
    advisories: 1,
    categories: {
      claims: { checked: true, score: 0.5, findings: 1, blockers: 1 },
      tone: { checked: true, score: 0.82, findings: 1, blockers: 0 },
      terminology: { checked: true, score: 0.82, findings: 1, blockers: 0 },
      messaging: { checked: true, score: 1, findings: 0, blockers: 0 },
      visual: { checked: true, score: 1, findings: 0, blockers: 0 },
      accessibility: { checked: true, score: 0.62, findings: 2, blockers: 1 },
      legal: { checked: true, score: 1, findings: 0, blockers: 0 },
      confidentiality: { checked: true, score: 0.5, findings: 1, blockers: 1 },
    },
  },
  coverage: {
    not_checked: [],
    notes: ["demo data: start the backend and set VERYTAS_API_URL for live reviews"],
    models: { llm: "ollama/gpt-oss:120b", judge: "typesafe/jev-1.13.0" },
    redactions: 2,
  },
  error: null,
  findings: [
    {
      id: 1, unit_id: "p2.s1", category: "confidentiality", level: "blocker",
      title: 'Confidential term "Project Lumen"',
      explanation: '"Project Lumen" is marked confidential until 2026-12-01. Publishing it would leak protected information.',
      quote: "Project Lumen", span_start: 60, span_end: 73, confidence: 1, checker: "deterministic", model: null,
      citations: [{ kind: "rule", id: 1, label: "CONF-LEAK v1: No confidential or embargoed terms", source: "Verytas built-in" }],
      suggestions: [], decisions: [], signature_valid: true,
    },
    {
      id: 2, unit_id: "p1.s1", category: "claims", level: "blocker", title: "Claim conflicts with an approved fact",
      explanation: 'The approved fact says "Verytas is used by 800+ teams" (Board deck Q3).',
      quote: "Verytas is trusted by 1,000+ teams.", span_start: 0, span_end: 35, confidence: 1, checker: "claims",
      model: null,
      citations: [
        { kind: "rule", id: 8, label: "CLAIM-CONTRADICTED v1: Claims must match approved facts", source: "Verytas built-in" },
        { kind: "fact", id: 3, label: "Verytas is used by 800+ teams", source: "Board deck Q3" },
      ],
      suggestions: [{
        id: 1, original: "Verytas is trusted by 1,000+ teams.", proposed: "Verytas is trusted by 800+ teams.",
        rationale: "Matches the approved fact: Verytas is used by 800+ teams", intent_preserved: 0.96, model: null,
      }],
      decisions: [], signature_valid: true,
    },
    {
      id: 3, unit_id: "p1.s2", category: "terminology", level: "warning", title: 'Use "sign in" instead of "Sign-in"',
      explanation: "Use our house spellings.", quote: "Sign-in", span_start: 36, span_end: 43, confidence: 1,
      checker: "deterministic", model: null,
      citations: [{ kind: "rule", id: 11, label: "TERM-01 v2: House spellings", source: "Style guide p.4" }],
      suggestions: [{ id: 2, original: "Sign-in", proposed: "Sign in", rationale: "House style prefers 'sign in'.",
        intent_preserved: null, model: null }],
      decisions: [], signature_valid: true,
    },
    {
      id: 4, unit_id: "p3", category: "tone", level: "warning", title: "May break VOICE-01: Plain words, no jargon",
      explanation: "\"Leverage synergies\" and \"paradigm shifts\" are the buzzwords VOICE-01 rules out; say what the product does instead.",
      quote: "We leverage synergies to unlock paradigm shifts.", span_start: 107, span_end: 155, confidence: 0.88,
      checker: "semantic", model: "typesafe/jev-1.13.0",
      citations: [{ kind: "rule", id: 12, label: "VOICE-01 v1: Plain words, no jargon", source: "Brand voice guide p.2" }],
      suggestions: [{
        id: 3, original: "We leverage synergies to unlock paradigm shifts.",
        proposed: "We help your teams publish on-brand content faster.",
        rationale: "Replaces jargon with the concrete benefit while keeping the claim modest.",
        intent_preserved: 0.81, model: "ollama/gpt-oss:120b",
      }],
      decisions: [], signature_valid: true,
    },
    {
      id: 5, unit_id: "p3.s2", category: "accessibility", level: "warning", title: 'Vague link text "click here"',
      explanation: "Link text such as 'click here' gives no context out of order (WCAG 2.2 SC 2.4.4).",
      quote: "click here", span_start: 162, span_end: 172, confidence: 1, checker: "deterministic", model: null,
      citations: [{ kind: "rule", id: 6, label: "A11Y-LINKTEXT v1: Link text must describe the destination", source: "Verytas built-in" }],
      suggestions: [], decisions: [], signature_valid: true,
    },
    {
      id: 6, unit_id: "img:cover", category: "accessibility", level: "advisory", title: "Image cover has no alt text",
      explanation: "Every image needs alt text that describes it (WCAG 2.2 SC 1.1.1).", quote: null,
      span_start: null, span_end: null, confidence: 1, checker: "deterministic", model: null,
      citations: [{ kind: "rule", id: 2, label: "A11Y-ALT v1: Images need meaningful alt text", source: "Verytas built-in" }],
      suggestions: [], decisions: [], signature_valid: true,
    },
  ],
};
