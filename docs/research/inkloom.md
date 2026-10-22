# Inkloom and the problem space: public research (October 2026)

Method: web search and fetches of openly published pages only. No sign-ups or logins, and nothing that looked like leaked or private material.

## What Inkloom builds

- Inkloom (inkloom.art) describes itself as specialised AI models for logo design: a brand-analysis model turns a business into constraints, typography and symbol models build the mark, and a composition engine makes lockups and clear-space rules. The public site and repository state that generation is not live yet; accounts, credits and an operations console are. Sources: https://inkloom.art/ and https://github.com/Inkloom-art/inkloom (README).
- Stack stated in the README: Cloudflare Workers, Postgres, React Router. Its tests include concurrency (25 simultaneous redemptions of one code, exactly one ledger entry), which Verytas mirrors in its black-box concurrency runs.
- No public reviews, incidents or press about Inkloom were found. inkloom.ai currently serves an unrelated book-writing product.

## Public incidents that shaped Verytas

| Problem | Example | What Verytas does about it |
|---|---|---|
| Off-model or uncanny AI visuals | Coca-Cola AI holiday ads, 2024 and 2025 (campaignlive.com, campaignasia.com) | official assets as ground truth, pixel comparison, vision cross-check |
| Tone-deaf content through an agency pipeline | McDonald's Netherlands AI ad, pulled 9-10 Dec 2025 (nbcnews.com) | context layers, escalation to the manager, same gate for every uploader |
| Undisclosed AI from a vendor | Wizards of the Coast marketing image, Jan 2024 (geekwire.com) | AI-disclosure rule, creator declaration, visible-signs check |
| Hallucinated claims creating liability | Air Canada chatbot, BC tribunal, Feb 2024 (kiplinger.com) | every figure checked against approved, time-valid facts |
| AI imagery misrepresenting the offer, garbled signage | Glasgow "Willy's Chocolate Experience", Feb 2024 (petapixel.com) | OCR of text in images, wordmark spelling, claims checks on image text |
| Burned-in captions | open captions can't be turned off or read by screen readers (boia.org, 2021) | caption OCR plus a caption-file accessibility finding |
| Misleading ads and AI disclosure in India | ASCI: 81% of complaints are misleading claims; draft AI-disclosure guidelines (mondaq.com, moneylife.in); MeitY draft synthetic-content labelling (mondaq.com) | claims verification, configurable AI-disclosure rule |
| Code-mixed language | Hinglish hate-speech research (arxiv.org/abs/2403.02121) | language-aware context layers, language field on disputes and notes |

Figures are as reported by the cited sources; regulatory drafts may have changed and are configured as rules, not code.
