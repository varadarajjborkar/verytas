"""Built-in rules every workspace starts with.

These cover the checks the brief asks for regardless of brand (accessibility,
confidentiality, unsupported claims). Making them real Rule rows means their
findings cite something, and admins can tune or retire them like any other rule.
"""

from __future__ import annotations

from typing import Any

SYSTEM_RULES: list[dict[str, Any]] = [
    {
        "code": "CONF-LEAK",
        "category": "confidentiality",
        "kind": "deterministic",
        "severity": "must",
        "title": "No confidential or embargoed terms",
        "text": "Content must not mention terms the workspace has marked confidential while they are under embargo.",
        "pattern": {"type": "confidential_terms"},
    },
    {
        "code": "A11Y-ALT",
        "category": "accessibility",
        "kind": "deterministic",
        "severity": "must",
        "title": "Images need meaningful alt text",
        "text": "Every image needs alt text that describes it (WCAG 2.2 SC 1.1.1). "
        "Placeholders like 'image' or 'photo' do not count.",
        "pattern": {"type": "alt_text", "min_length": 8},
    },
    {
        "code": "A11Y-CONTRAST",
        "category": "accessibility",
        "kind": "deterministic",
        "severity": "must",
        "title": "Text must meet contrast minimums",
        "text": "Text over a background needs a contrast ratio of at least 4.5:1, or 3:1 for large text "
        "(WCAG 2.2 SC 1.4.3).",
        "pattern": {"type": "contrast", "min_ratio": 4.5, "min_ratio_large": 3.0},
    },
    {
        "code": "A11Y-HASHTAG",
        "category": "accessibility",
        "kind": "deterministic",
        "severity": "should",
        "title": "Use CamelCase for multi-word hashtags",
        "text": "Screen readers read all-lowercase hashtags as one long word. Capitalise each word.",
        "pattern": {"type": "hashtag_case", "min_length": 10},
    },
    {
        "code": "A11Y-CAPS",
        "category": "accessibility",
        "kind": "deterministic",
        "severity": "may",
        "title": "Avoid long runs of capitals",
        "text": "Several consecutive all-caps words are harder to read and some screen readers spell them out.",
        "pattern": {"type": "all_caps", "max_run": 2},
    },
    {
        "code": "A11Y-LINKTEXT",
        "category": "accessibility",
        "kind": "deterministic",
        "severity": "should",
        "title": "Link text must describe the destination",
        "text": "Link text such as 'click here' gives no context out of order (WCAG 2.2 SC 2.4.4).",
        "pattern": {"type": "link_text", "banned": ["click here", "here", "read more", "learn more", "link"]},
    },
    {
        "code": "A11Y-READ",
        "category": "accessibility",
        "kind": "deterministic",
        "severity": "may",
        "title": "Keep paragraphs readable",
        "text": "Paragraphs above the target reading grade lose a large part of the audience.",
        "pattern": {"type": "readability", "max_grade": 10, "min_words": 25},
    },
    {
        "code": "CLAIM-CONTRADICTED",
        "category": "claims",
        "kind": "deterministic",
        "severity": "must",
        "title": "Claims must match approved facts",
        "text": "A claim that conflicts with an approved, currently valid fact must be corrected.",
        "pattern": {"type": "claims"},
    },
    {
        "code": "CLAIM-OUTDATED",
        "category": "claims",
        "kind": "deterministic",
        "severity": "must",
        "title": "Claims must not rely on expired facts",
        "text": "A claim that only matches a fact whose validity window has ended is outdated.",
        "pattern": {"type": "claims"},
    },
    {
        "code": "CLAIM-UNSUPPORTED",
        "category": "claims",
        "kind": "deterministic",
        "severity": "should",
        "title": "Promotional claims need backing",
        "text": "Factual or promotional claims (numbers, superlatives, comparisons) need an approved fact behind them.",
        "pattern": {"type": "claims"},
    },
]
