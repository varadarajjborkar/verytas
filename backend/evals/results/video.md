# Video benchmark (36 videos, offline models, production review path)

Rendered with Hyperframes hyperframes@0.8.143, 30 fps, 21 portrait and 15 landscape, 663 s in total. Seed 7. Videos: 24 with artwork misuse, 6 with planted claims only, 6 clean.

Planted items: 45 artwork misuses, 11 on-screen claims, 10 spoken claims, 1 subtitle-track claims. 14 mascot appearances are in the videos and are not scored (no vision worker locally: not applicable, not missed). Reviews that did not finish: 0.

A finding counts as caught when it has an expected rule code and its time range overlaps the planted one (0.5 s tolerance for visuals, 1 s for on-screen text, 1.5 s for speech). 'Any time' drops the time condition.

## By channel

| Channel | Planted | Caught (right code, right time) | Caught (right code, any time) |
|---|---|---|---|
| Visuals (artwork misuse) | 45 | 32/45 (71%) | 39/45 (87%) |
| On-screen text (OCR) | 11 | 11/11 (100%) | 11/11 (100%) |
| Speech (Whisper) | 10 | 8/10 (80%) | 8/10 (80%) |
| Subtitle track | 1 | 1/1 (100%) | 1/1 (100%) |

## Artwork misuse by appearance length

| Appearance | Items | Caught | Caught any time | Caught if every 1 s sample were matched | Has a 1 s sample inside | Has a keyframe inside |
|---|---|---|---|---|---|---|
| 0.5 s | 10 | 4/10 (40%) | 7/10 (70%) | 4/10 (40%) | 7/10 | 5/10 |
| 1.0 s | 10 | 8/10 (80%) | 10/10 (100%) | 8/10 (80%) | 10/10 | 5/10 |
| 2.0 s | 10 | 8/10 (80%) | 9/10 (90%) | 8/10 (80%) | 10/10 | 5/10 |
| 4.0 s | 10 | 8/10 (80%) | 9/10 (90%) | 10/10 (100%) | 10/10 | 5/10 |
| whole shot | 5 | 4/5 (80%) | 4/5 (80%) | 4/5 (80%) | 5/5 | 5/5 |

## Artwork misuse by placement, variant, size and orientation

| Dimension | Value | Items | Caught | Any time | Matcher on the middle frame | Matcher on 1 s samples |
|---|---|---|---|---|---|---|
| Placement | cut | 25 | 19/25 (76%) | 23/25 (92%) | 21/25 (84%) | 20/25 (80%) |
| Placement | mid | 20 | 13/20 (65%) | 16/20 (80%) | 17/20 (85%) | 14/20 (70%) |
| Misuse | stretched | 9 | 3/9 (33%) | 5/9 (56%) | 6/9 (67%) | 5/9 (56%) |
| Misuse | recoloured | 9 | 4/9 (44%) | 9/9 (100%) | 6/9 (67%) | 4/9 (44%) |
| Misuse | mirrored | 9 | 9/9 (100%) | 9/9 (100%) | 8/9 (89%) | 9/9 (100%) |
| Misuse | retired | 9 | 8/9 (89%) | 8/9 (89%) | 9/9 (100%) | 8/9 (89%) |
| Misuse | competitor | 9 | 8/9 (89%) | 8/9 (89%) | 9/9 (100%) | 8/9 (89%) |
| Size | large | 23 | 15/23 (65%) | 19/23 (83%) | 20/23 (87%) | 16/23 (70%) |
| Size | medium | 13 | 9/13 (69%) | 12/13 (92%) | 12/13 (92%) | 11/13 (85%) |
| Size | small | 9 | 8/9 (89%) | 8/9 (89%) | 6/9 (67%) | 7/9 (78%) |
| Orientation | portrait | 27 | 18/27 (67%) | 23/27 (85%) | 24/27 (89%) | 21/27 (78%) |
| Orientation | landscape | 18 | 14/18 (78%) | 16/18 (89%) | 14/18 (78%) | 13/18 (72%) |

## Keyframe-only effect

| Question | Items | Result |
|---|---|---|
| Production: caught at the right time | 45 | 32/45 (71%) |
| A 1 s sample falls inside the appearance | 45 | 42/45 |
| A keyframe falls inside the appearance | 45 | 25/45 |
| Matcher gets the right finding on the middle frame (upper bound, ignores sampling) | 45 | 38/45 (84%) |
| Matcher on every 1 s sample inside it (what matching all samples would give) | 45 | 34/45 (76%) |
| Missed in production but caught if every sample were matched | 45 | 3 |
| Caught in production although no keyframe is inside (credited to a nearby keyframe or a longer shot) | 45 | 13 |
| Matcher on each keyframe inside it, reviewed alone (no merge across keyframes) | 45 | not measured (run with --add-keyframe-probes) |
| A keyframe inside it gives the right finding when reviewed alone, yet the review missed it | 45 | not measured |
| Appearances 1 s or longer: production catch | 25 | 20/25 (80%) |

## What a miss was called instead

| Findings at the planted time with another code | Items |
|---|---|
| VIS-ASSET-ALTERED | 5 |
| VIS-ASSET-RETIRED | 1 |
| (nothing at that time) | 2 |

## False alarms

Clean videos: 6; with any finding other than the captions, reading-grade and layout notes: 6. Findings on clean videos: 26. Findings no planted item explains, on all videos: 109 across 31 videos.

| Rule | Channel | Count | Clean videos | Example |
|---|---|---|---|---|
| CLAIM-UNSUPPORTED | captions | 6 | 2 | Unsupported figure |
| TERM-NAME | captions | 5 | 0 | Write "Kitepath" with its official casing |
| VIS-ASSET-ALTERED | v04 | 5 | 0 | Learning kit box differs from the official artwork |
| VIS-ASSET-ALTERED | v12 | 5 | 5 | Learning kit box differs from the official artwork |
| VIS-ASSET-ALTERED | v26 | 5 | 0 | Kitepath app icon differs from the official artwork |
| VIS-ASSET-ALTERED | v11 | 4 | 0 | Dhara pack differs from the official artwork |
| VIS-ASSET-ALTERED | v27 | 4 | 4 | Dhara pack differs from the official artwork |
| VIS-ASSET-DISTORTED | v27 | 4 | 4 | Dhara pack is mirrored (flipped left to right) |
| VIS-ASSET-ALTERED | v02 | 3 | 0 | Learning kit box differs from the official artwork |
| VIS-ASSET-DISTORTED | v04 | 3 | 0 | Learning kit box is mirrored (flipped left to right) |
| VIS-ASSET-ALTERED | v10 | 3 | 0 | Kitepath logo, reversed differs from the official artwork |
| CLAIM-CONTRADICTED | captions | 3 | 0 | Claim conflicts with an approved fact |
| MSG-COMPETITOR | captions | 3 | 0 | Avoid "Dhara" |
| VIS-ASSET-ALTERED | v30 | 3 | 0 | Nezo logo differs from the official artwork |
| VIS-ASSET-ALTERED | v35 | 3 | 0 | Dhara logo differs from the official artwork |
| VIS-ASSET-ALTERED | v00 | 2 | 0 | Kitepath logo differs from the official artwork |
| VIS-ASSET-ALTERED | v06 | 2 | 2 | Nezo logo differs from the official artwork |
| VIS-ASSET-RETIRED | v10 | 2 | 0 | Old version of the artwork: Kitepath logo 2024 |
| CLAIM-UNSUPPORTED | speech | 2 | 0 | Unsupported figure |
| VIS-ASSET-DISTORTED | v12 | 2 | 2 | Learning kit box is mirrored (flipped left to right) |
| VIS-ASSET-DISTORTED | v16 | 2 | 0 | Kitepath wordmark is mirrored (flipped left to right) |
| VIS-ASSET-ALTERED | v19 | 2 | 0 | Dhara pack differs from the official artwork |
| VIS-ASSET-ALTERED | v20 | 2 | 0 | Learning kit box differs from the official artwork |
| VIS-ASSET-ALTERED | v23 | 2 | 0 | Mino pack differs from the official artwork |
| VIS-ASSET-ALTERED | v31 | 2 | 0 | Mino pack differs from the official artwork |
| VIS-ASSET-DISTORTED | v34 | 2 | 0 | Kitepath logo is mirrored (flipped left to right) |
| VIS-ASSET-ALTERED | v01 | 1 | 1 | Ridhano pack differs from the official artwork |
| CLAIM-UNSUPPORTED | subtitles | 1 | 0 | Unsupported figure |
| VIS-ASSET-ALTERED | v05 | 1 | 1 | Zope app icon differs from the official artwork |
| VIS-ASSET-EXTENDED | v06 | 1 | 1 | Unapproved additions to Nezo wordmark: parts joined to it |
| VIS-ASSET-DISTORTED | v08 | 1 | 0 | Kitepath logo is mirrored (flipped left to right) |
| VIS-ASSET-DISTORTED | v09 | 1 | 1 | Ridhano pack is mirrored (flipped left to right) |
| VIS-ASSET-ALTERED | v09 | 1 | 1 | Ridhano pack differs from the official artwork |
| VIS-ASSET-DISTORTED | v10 | 1 | 0 | Kitepath logo is mirrored (flipped left to right) |
| VIS-ASSET-EXTENDED | v12 | 1 | 1 | Unapproved additions to Kitepath app icon: parts joined to it |
| VIS-ASSET-ALTERED | v13 | 1 | 0 | Zope pack differs from the official artwork |
| VIS-COMPETITOR-MARK | v15 | 1 | 0 | Ridhano logo appears in this image |
| VIS-ASSET-EXTENDED | v15 | 1 | 0 | Unapproved additions to Mino wordmark: parts joined to it |
| VIS-ASSET-EXTENDED | v16 | 1 | 0 | Unapproved additions to Kitepath wordmark: parts joined to it |
| VIS-ASSET-DISTORTED | v18 | 1 | 0 | Learning kit box is mirrored (flipped left to right) |
| VIS-ASSET-ALTERED | v18 | 1 | 0 | Learning kit box differs from the official artwork |
| VIS-ASSET-EXTENDED | v19 | 1 | 0 | Unapproved additions to Dhara wordmark: parts joined to it |
| VIS-ASSET-RETIRED | v20 | 1 | 0 | Old version of the artwork: Kitepath logo 2024 |
| VIS-ASSET-DISTORTED | v24 | 1 | 0 | Kitepath app icon is mirrored (flipped left to right) |
| VIS-ASSET-EXTENDED | v24 | 1 | 0 | Unapproved additions to Kitepath app icon: parts joined to it |
| VIS-ASSET-ALTERED | v24 | 1 | 0 | Learning kit box differs from the official artwork |
| VIS-ASSET-DISTORTED | v26 | 1 | 0 | Kitepath logo is mirrored (flipped left to right) |
| VIS-ASSET-EXTENDED | v27 | 1 | 1 | Unapproved additions to Dhara wordmark: parts joined to it |
| VIS-ASSET-ALTERED | v28 | 1 | 0 | Kitepath logo, reversed differs from the official artwork |
| VIS-ASSET-EXTENDED | v32 | 1 | 0 | Unapproved additions to Kitepath wordmark: parts joined to it |
| VIS-ASSET-ALTERED | v33 | 1 | 0 | Ridhano pack differs from the official artwork |
| VIS-ASSET-EXTENDED | v33 | 1 | 0 | Unapproved additions to Ridhano wordmark: parts joined to it |
| VIS-COMPETITOR-MARK | v33 | 1 | 0 | Dhara logo appears in this image |
| VIS-COMPETITOR-MARK | v34 | 1 | 0 | SkillSprint appears in this image |

## Time

Review plus upload per video: median 11.4 s, p95 18.6 s, max 34.2 s (median video 18 s).
Hyperframes render per video: median 48 s, max 76 s.

## Misses, with times

- v24 speech 'Unlike SkillSprint, we teach with real people.' at 13.35-15.94 s (2.6 s)
- v29 speech 'Big news is coming with Project Kestrel.' at 6.35-8.52 s (2.2 s)
- v03 visual stretched wordmark at 3.0-4.0 s (1.0 s, cut, large, samples 1, keyframes 1, matcher on frame: yes)
- v07 visual recoloured icon at 4.25-4.75 s (0.5 s, mid, large, samples 0, keyframes 0, matcher on frame: yes)
- v08 visual recoloured icon at 9.33-13.33 s (4.0 s, mid, medium, samples 4, keyframes 0, matcher on frame: yes)
- v14 visual recoloured wordmark at 7.0-9.0 s (2.0 s, cut, large, samples 2, keyframes 1, matcher on frame: no)
- v16 visual recoloured wordmark at 3.0-4.0 s (1.0 s, cut, large, samples 1, keyframes 1, matcher on frame: no)
- v19 visual stretched wordmark at 3.0-3.5 s (0.5 s, cut, large, samples 1, keyframes 1, matcher on frame: yes)
- v21 visual stretched logo at 11.86-12.36 s (0.5 s, mid, medium, samples 1, keyframes 0, matcher on frame: no)
- v28 visual stretched wordmark at 6.0-10.0 s (shot s, cut, small, samples 5, keyframes 2, matcher on frame: no)
- v29 visual retired retired at 4.34-4.84 s (0.5 s, mid, large, samples 0, keyframes 0, matcher on frame: yes)
- v30 visual competitor competitor at 9.11-9.61 s (0.5 s, mid, large, samples 0, keyframes 0, matcher on frame: yes)
- v30 visual stretched wordmark at 11.87-13.87 s (2.0 s, mid, large, samples 2, keyframes 0, matcher on frame: no)
- v31 visual stretched wordmark at 6.71-10.71 s (4.0 s, mid, medium, samples 4, keyframes 0, matcher on frame: yes)
- v34 visual recoloured wordmark at 6.0-6.5 s (0.5 s, cut, medium, samples 1, keyframes 1, matcher on frame: yes)
