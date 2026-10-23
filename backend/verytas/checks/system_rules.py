"""Built-in rules every workspace starts with.

These cover the checks the brief asks for regardless of brand (accessibility,
confidentiality, unsupported claims). Making them real Rule rows means their
findings cite something, and admins can tune or retire them like any other rule.
"""

from __future__ import annotations

from typing import Any

SYSTEM_RULES: list[dict[str, Any]] = [
    {
        "code": "TONE-SHIFT",
        "category": "tone",
        "kind": "deterministic",
        "severity": "should",
        "title": "Stay in the brand's voice",
        "text": "Posts keep the voice of the brand's published work: no insults, sarcasm, slang, hype or corporate "
        "stiffness the brand doesn't use, and no change of tone partway through a piece.",
        "pattern": {"type": "tone_shift"},
    },
    {
        "code": "MSG-OFF-TOPIC",
        "category": "messaging",
        "kind": "deterministic",
        "severity": "should",
        "title": "Stay on the brand's topics",
        "text": "Posts stay on what the brand talks about. Politics, religion, trading tips, betting, gossip or the "
        "writer's personal life pull the brand into places it never chose.",
        "pattern": {"type": "topic_drift"},
    },
    {
        "code": "CONTACT-PUBLIC",
        "category": "confidentiality",
        "kind": "deterministic",
        "severity": "must",
        "title": "Only the company's public contact details",
        "text": "Phone numbers and email addresses in a post must be ones the company publishes (Library, Public "
        "contacts). A personal or unlisted number exposes someone's private data and can't be taken back once "
        "posted.",
        "pattern": {"type": "public_contacts"},
    },
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
        "code": "CLAIM-MISMATCH",
        "category": "claims",
        "kind": "deterministic",
        "severity": "must",
        "title": "Figures and names must agree across the post",
        "text": "A price, discount, rate or count must read the same in the text, the images, what is said and "
        "what is shown on screen, and the person the text names must be the person shown. Viewers believe "
        "whichever version they meet first.",
        "pattern": {"type": "cross_source"},
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
    {
        "code": "VIS-ASSET-ALTERED",
        "category": "visual",
        "kind": "deterministic",
        "severity": "must",
        "title": "Official assets must not be altered",
        "text": "Where an official logo or mascot appears, it must match the approved artwork: same shapes, "
        "features and colours. AI-generated look-alikes often change small details.",
        "pattern": {"type": "brand_assets"},
    },
    {
        "code": "VIS-ASSET-EXTENDED",
        "category": "visual",
        "kind": "deterministic",
        "severity": "must",
        "title": "No unapproved additions to official assets",
        "text": "Only the approved parts of a mascot or logo may be used. Adding a body, outfit, pose or "
        "features the brand has not approved creates an unofficial character.",
        "pattern": {"type": "brand_assets"},
    },
    {
        "code": "VIS-ASSET-IMITATION",
        "category": "visual",
        "kind": "deterministic",
        "severity": "should",
        "title": "No off-model imitations of brand characters",
        "text": "A character or mark that resembles an official asset without matching it reads as the brand "
        "but is not approved artwork. Use the official asset or none.",
        "pattern": {"type": "brand_assets"},
    },
    {
        "code": "VIS-ASSET-DISTORTED",
        "category": "visual",
        "kind": "deterministic",
        "severity": "must",
        "title": "Official artwork keeps its proportions",
        "text": "Logos, wordmarks, icons and characters may be resized and placed, but never stretched, "
        "squashed, skewed or mirrored. Scale both sides together.",
        "pattern": {"type": "brand_assets"},
    },
    {
        "code": "VIS-ASSET-RETIRED",
        "category": "visual",
        "kind": "deterministic",
        "severity": "must",
        "title": "Use the current version of brand artwork",
        "text": "The brand has retired this version of its artwork. Use the current one from the Library.",
        "pattern": {"type": "brand_assets"},
    },
    {
        "code": "VIS-COMPETITOR-MARK",
        "category": "messaging",
        "kind": "deterministic",
        "severity": "should",
        "title": "No other brands' logos without a reason",
        "text": "A competitor's logo in our content draws a comparison, or borrows their name, and needs legal "
        "sign-off. Leave it out, or escalate with the reason it is there.",
        "pattern": {"type": "brand_assets"},
    },
    {
        "code": "CTX-IMPLIED",
        "category": "messaging",
        "kind": "deterministic",
        "severity": "should",
        "title": "Watch what the content implies, not just what it says",
        "text": "Indirect taunts, insinuation, sarcasm, double meanings, coded language and digs at others "
        "carry the brand's name as much as direct statements do, including across caption and image.",
        "pattern": {"type": "context"},
    },
    {
        "code": "LIKENESS-UNLICENSED",
        "category": "legal",
        "kind": "deterministic",
        "severity": "must",
        "title": "Only people the brand has an agreement with may appear",
        "text": "A recognisable person in an image or video needs the brand's agreement for this channel, "
        "campaign and date (Library, People). Featuring anyone else, a celebrity especially, invites a claim "
        "against the brand for using their likeness.",
        "pattern": {"type": "media"},
    },
    {
        "code": "LIKENESS-UNKNOWN",
        "category": "legal",
        "kind": "deterministic",
        "severity": "should",
        "title": "Say who appears in the content",
        "text": "A clearly visible person who isn't in the brand's records and isn't named in the brief can't be "
        "checked. Name them in the brief, or register them in the Library (a creator registers themselves).",
        "pattern": {"type": "media"},
    },
    {
        "code": "MEDIA-UNREAD",
        "category": "visual",
        "kind": "deterministic",
        "severity": "must",
        "title": "Every part of the content must be readable",
        "text": "Text inside images and documents is checked like any other text. When part of it could not "
        "be read reliably, it has not been checked and needs a human look.",
        "pattern": {"type": "media"},
    },
    {
        "code": "INPUT-IRREGULAR",
        "category": "messaging",
        "kind": "deterministic",
        "severity": "should",
        "title": "Content should be shaped for its channel",
        "text": "Uploads far outside what the channel normally carries (page counts, caption length, image size, "
        "video length, hidden characters) were accepted with the creator's reason and checked in full, "
        "but count against the score until someone confirms they are intended.",
        "pattern": {"type": "input"},
    },
    {
        "code": "A11Y-CAPTIONS",
        "category": "accessibility",
        "kind": "deterministic",
        "severity": "should",
        "title": "Video speech needs captions",
        "text": "Spoken content needs captions (WCAG 2.2 SC 1.2.2). Captions burned into the picture cannot be "
        "turned off, resized, translated or read by screen readers, so provide a caption file or transcript too.",
        "pattern": {"type": "captions"},
    },
    {
        "code": "AI-DISCLOSURE",
        "category": "legal",
        "kind": "deterministic",
        "severity": "should",
        "title": "Label AI-generated content",
        "text": "Public content made with generative AI should say so, in line with ASCI's draft AI-disclosure "
        "guidelines and MeitY's draft synthetic-content labelling rules. Configure to match the final rules.",
        "pattern": {"type": "disclosure"},
    },
    {
        "code": "EMOJI-RISK",
        "category": "messaging",
        "kind": "deterministic",
        "severity": "should",
        "title": "Emoji carry meaning too",
        "text": "Emoji with common slang readings (innuendo, drugs, violence, mockery, slurs) or political and "
        "religious weight are read the way the audience reads them. Obscene gestures are never on-brand.",
        "pattern": {"type": "emoji_risk"},
    },
    {
        "code": "A11Y-EMOJI",
        "category": "accessibility",
        "kind": "deterministic",
        "severity": "may",
        "title": "Use emoji sparingly and between words",
        "text": "Screen readers read each emoji's full name aloud, so long runs become noise and an emoji inside "
        "a word breaks it. Keep runs to three and put emoji between words.",
        "pattern": {"type": "emoji_a11y", "max_run": 3},
    },
    {
        "code": "PRES-FOLD",
        "category": "legal",
        "kind": "deterministic",
        "severity": "should",
        "title": "Disclosures must be visible without tapping 'more'",
        "text": "Paid-partnership and AI labels must appear before the platform cuts the caption, so every "
        "viewer sees them (ASCI asks for upfront disclosure).",
        "pattern": {"type": "presentation"},
    },
    {
        "code": "PRES-CROP",
        "category": "visual",
        "kind": "deterministic",
        "severity": "should",
        "title": "Key text and logos must survive the feed crop",
        "text": "Feeds and profile grids crop images to fixed shapes. Text, prices, disclaimers or the logo "
        "outside the visible area are lost for most viewers.",
        "pattern": {"type": "presentation"},
    },
    {
        "code": "PRES-SAFEZONE",
        "category": "accessibility",
        "kind": "deterministic",
        "severity": "should",
        "title": "Keep text clear of the app's buttons",
        "text": "On vertical video and full-screen posts the app overlays its own buttons and caption at the "
        "edges. Text under them can't be read.",
        "pattern": {"type": "presentation"},
    },
]
