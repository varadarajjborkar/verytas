# Video benchmark (36 videos, offline models, production review path)

Rendered with Hyperframes hyperframes@0.8.143, 30 fps, 21 portrait and 15 landscape, 663 s in total. Seed 7. Videos: 24 with artwork misuse, 6 with planted claims only, 6 clean.

Planted items: 45 artwork misuses, 11 on-screen claims, 10 spoken claims, 1 subtitle-track claims. 14 mascot appearances are in the videos and are not scored (no vision worker locally: not applicable, not missed). Reviews that did not finish: 0.

A finding counts as caught when it has an expected rule code and its time range overlaps the planted one (0.5 s tolerance for visuals, 1 s for on-screen text, 1.5 s for speech). 'Any time' drops the time condition.

## By channel

| Channel | Planted | Caught (right code, right time) | Caught (right code, any time) |
|---|---|---|---|
| Visuals (artwork misuse) | 45 | 15/45 (33%) | 18/45 (40%) |
| On-screen text (OCR) | 11 | 11/11 (100%) | 11/11 (100%) |
| Speech (Whisper) | 10 | 8/10 (80%) | 8/10 (80%) |
| Subtitle track | 1 | 0/1 (0%) | 0/1 (0%) |

## Artwork misuse by appearance length

| Appearance | Items | Caught | Caught any time | Caught if every 1 s sample were matched | Has a 1 s sample inside | Has a keyframe inside |
|---|---|---|---|---|---|---|
| 0.5 s | 10 | 3/10 (30%) | 4/10 (40%) | 4/10 (40%) | 7/10 | 5/10 |
| 1.0 s | 10 | 3/10 (30%) | 3/10 (30%) | 8/10 (80%) | 10/10 | 5/10 |
| 2.0 s | 10 | 4/10 (40%) | 5/10 (50%) | 8/10 (80%) | 10/10 | 5/10 |
| 4.0 s | 10 | 3/10 (30%) | 4/10 (40%) | 10/10 (100%) | 10/10 | 5/10 |
| whole shot | 5 | 2/5 (40%) | 2/5 (40%) | 4/5 (80%) | 5/5 | 5/5 |

## Artwork misuse by placement, variant, size and orientation

| Dimension | Value | Items | Caught | Any time | Matcher on the middle frame | Matcher on 1 s samples |
|---|---|---|---|---|---|---|
| Placement | cut | 25 | 15/25 (60%) | 15/25 (60%) | 21/25 (84%) | 20/25 (80%) |
| Placement | mid | 20 | 0/20 (0%) | 3/20 (15%) | 17/20 (85%) | 14/20 (70%) |
| Misuse | stretched | 9 | 2/9 (22%) | 3/9 (33%) | 6/9 (67%) | 5/9 (56%) |
| Misuse | recoloured | 9 | 1/9 (11%) | 2/9 (22%) | 6/9 (67%) | 4/9 (44%) |
| Misuse | mirrored | 9 | 5/9 (56%) | 6/9 (67%) | 8/9 (89%) | 9/9 (100%) |
| Misuse | retired | 9 | 3/9 (33%) | 3/9 (33%) | 9/9 (100%) | 8/9 (89%) |
| Misuse | competitor | 9 | 4/9 (44%) | 4/9 (44%) | 9/9 (100%) | 8/9 (89%) |
| Size | large | 23 | 9/23 (39%) | 10/23 (43%) | 20/23 (87%) | 16/23 (70%) |
| Size | medium | 13 | 2/13 (15%) | 4/13 (31%) | 12/13 (92%) | 11/13 (85%) |
| Size | small | 9 | 4/9 (44%) | 4/9 (44%) | 6/9 (67%) | 7/9 (78%) |
| Orientation | portrait | 27 | 10/27 (37%) | 12/27 (44%) | 24/27 (89%) | 21/27 (78%) |
| Orientation | landscape | 18 | 5/18 (28%) | 6/18 (33%) | 14/18 (78%) | 13/18 (72%) |

## Keyframe-only effect

| Question | Items | Result |
|---|---|---|
| Production: caught at the right time | 45 | 15/45 (33%) |
| A 1 s sample falls inside the appearance | 45 | 42/45 |
| A keyframe falls inside the appearance | 45 | 25/45 |
| Matcher gets the right finding on the middle frame (upper bound, ignores sampling) | 45 | 38/45 (84%) |
| Matcher on every 1 s sample inside it (what matching all samples would give) | 45 | 34/45 (76%) |
| Missed in production but caught if every sample were matched | 45 | 19 |
| Caught in production although no keyframe is inside (credited to a nearby keyframe or a longer shot) | 45 | 0 |
| Matcher on each keyframe inside it, reviewed alone (no merge across keyframes) | 45 | 19/45 (42%) |
| A keyframe inside it gives the right finding when reviewed alone, yet the review missed it | 45 | 4 |
| Appearances 1 s or longer: production catch | 25 | 9/25 (36%) |

## What a miss was called instead

| Findings at the planted time with another code | Items |
|---|---|
| VIS-ASSET-ALTERED | 2 |
| (nothing at that time) | 25 |

## False alarms

Clean videos: 6; with any finding other than the captions, reading-grade and layout notes: 6. Findings on clean videos: 12. Findings no planted item explains, on all videos: 85 across 28 videos.

| Rule | Channel | Count | Clean videos | Example |
|---|---|---|---|---|
| TERM-NAME | captions | 33 | 2 | Write "Kitepath" with its official casing |
| CLAIM-CONTRADICTED | captions | 12 | 1 | Claim conflicts with an approved fact |
| CLAIM-CONTRADICTED | speech | 8 | 0 | Claim conflicts with an approved fact |
| CLAIM-UNSUPPORTED | captions | 6 | 2 | Unsupported figure |
| MSG-COMPETITOR | captions | 3 | 0 | Avoid "Dhara" |
| VIS-ASSET-ALTERED | v11 | 2 | 0 | Dhara app icon differs from the official artwork |
| CLAIM-UNSUPPORTED | speech | 2 | 0 | Unsupported figure |
| VIS-ASSET-DISTORTED | v27 | 2 | 2 | Dhara logo is mirrored (flipped left to right) |
| VIS-ASSET-ALTERED | v27 | 2 | 2 | Dhara app icon differs from the official artwork |
| VIS-ASSET-ALTERED | v35 | 2 | 0 | Dhara logo differs from the official artwork |
| VIS-ASSET-ALTERED | v05 | 1 | 1 | Zope app icon differs from the official artwork |
| VIS-ASSET-EXTENDED | v06 | 1 | 1 | Unapproved additions to Nezo wordmark: parts joined to it |
| MEDIA-UNREAD | v08 | 1 | 0 | Part of vid:v08 could not be read reliably |
| VIS-ASSET-ALTERED | v09 | 1 | 1 | Ridhano pack differs from the official artwork |
| VIS-ASSET-ALTERED | v19 | 1 | 0 | Dhara pack differs from the official artwork |
| MEDIA-UNREAD | v20 | 1 | 0 | Part of vid:v20 could not be read reliably |
| VIS-ASSET-ALTERED | v23 | 1 | 0 | Mino pack differs from the official artwork |
| MEDIA-UNREAD | v23 | 1 | 0 | Part of vid:v23 could not be read reliably |
| MEDIA-UNREAD | v24 | 1 | 0 | Part of vid:v24 could not be read reliably |
| VIS-ASSET-ALTERED | v26 | 1 | 0 | Kitepath app icon differs from the official artwork |
| MEDIA-UNREAD | v28 | 1 | 0 | Part of vid:v28 could not be read reliably |
| VIS-ASSET-EXTENDED | v32 | 1 | 0 | Unapproved additions to Kitepath wordmark: parts joined to it |
| VIS-ASSET-EXTENDED | v33 | 1 | 0 | Unapproved additions to Ridhano wordmark: parts joined to it |

## Time

Review plus upload per video: median 30.4 s, p95 67.6 s, max 71.6 s (median video 18 s).
Hyperframes render per video: median 48 s, max 76 s.

## Misses, with times

- v24 speech 'Unlike SkillSprint, we teach with real people.' at 13.35-15.94 s (2.6 s)
- v29 speech 'Big news is coming with Project Kestrel.' at 6.35-8.52 s (2.2 s)
- v04 subtitles 'Guaranteed results in 30 days' at 11.6-15.6 s (4.0 s)
- v00 visual retired retired at 4.19-6.19 s (2.0 s, mid, large, samples 2, keyframes 0, matcher on frame: yes)
- v00 visual mirrored wordmark at 8.78-9.28 s (0.5 s, mid, medium, samples 1, keyframes 0, matcher on frame: yes)
- v02 visual mirrored wordmark at 4.31-6.31 s (2.0 s, mid, small, samples 2, keyframes 0, matcher on frame: yes)
- v02 visual retired retired at 11.91-15.91 s (4.0 s, mid, medium, samples 3, keyframes 0, matcher on frame: yes)
- v03 visual stretched wordmark at 3.0-4.0 s (1.0 s, cut, large, samples 1, keyframes 1, matcher on frame: yes)
- v03 visual recoloured logo at 12.28-14.28 s (2.0 s, mid, large, samples 2, keyframes 0, matcher on frame: yes)
- v07 visual recoloured icon at 4.25-4.75 s (0.5 s, mid, large, samples 0, keyframes 0, matcher on frame: yes)
- v08 visual recoloured wordmark at 3.0-7.0 s (4.0 s, cut, small, samples 4, keyframes 1, matcher on frame: yes)
- v08 visual recoloured icon at 9.33-13.33 s (4.0 s, mid, medium, samples 4, keyframes 0, matcher on frame: yes)
- v14 visual mirrored wordmark at 4.24-5.24 s (1.0 s, mid, medium, samples 1, keyframes 0, matcher on frame: yes)
- v14 visual recoloured wordmark at 7.0-9.0 s (2.0 s, cut, large, samples 2, keyframes 1, matcher on frame: no)
- v15 visual stretched pack at 4.34-5.34 s (1.0 s, mid, small, samples 1, keyframes 0, matcher on frame: yes)
- v16 visual recoloured wordmark at 3.0-4.0 s (1.0 s, cut, large, samples 1, keyframes 1, matcher on frame: no)
- v16 visual retired retired at 6.0-9.0 s (shot s, cut, large, samples 4, keyframes 2, matcher on frame: yes)
- v18 visual competitor competitor at 4.36-6.36 s (2.0 s, mid, large, samples 2, keyframes 0, matcher on frame: yes)
- v18 visual competitor competitor at 8.78-12.78 s (4.0 s, mid, large, samples 4, keyframes 0, matcher on frame: yes)
- v19 visual stretched wordmark at 3.0-3.5 s (0.5 s, cut, large, samples 1, keyframes 1, matcher on frame: yes)
- v19 visual competitor competitor at 6.0-9.0 s (shot s, cut, medium, samples 4, keyframes 2, matcher on frame: yes)
- v21 visual stretched logo at 11.86-12.36 s (0.5 s, mid, medium, samples 1, keyframes 0, matcher on frame: no)
- v23 visual mirrored logo at 4.03-8.03 s (4.0 s, mid, medium, samples 3, keyframes 0, matcher on frame: yes)
- v24 visual retired retired at 8.0-12.0 s (4.0 s, cut, medium, samples 4, keyframes 1, matcher on frame: yes)
- v25 visual retired retired at 4.22-5.22 s (1.0 s, mid, large, samples 1, keyframes 0, matcher on frame: yes)
- v25 visual competitor competitor at 7.87-8.87 s (1.0 s, mid, medium, samples 1, keyframes 0, matcher on frame: yes)
- v28 visual stretched wordmark at 6.0-10.0 s (shot s, cut, small, samples 5, keyframes 2, matcher on frame: no)
- v29 visual retired retired at 4.34-4.84 s (0.5 s, mid, large, samples 0, keyframes 0, matcher on frame: yes)
- v30 visual competitor competitor at 9.11-9.61 s (0.5 s, mid, large, samples 0, keyframes 0, matcher on frame: yes)
- v30 visual stretched wordmark at 11.87-13.87 s (2.0 s, mid, large, samples 2, keyframes 0, matcher on frame: no)
- v31 visual stretched wordmark at 6.71-10.71 s (4.0 s, mid, medium, samples 4, keyframes 0, matcher on frame: yes)
- v32 visual recoloured icon at 3.73-4.73 s (1.0 s, mid, small, samples 1, keyframes 0, matcher on frame: no)
- v34 visual recoloured wordmark at 6.0-6.5 s (0.5 s, cut, medium, samples 1, keyframes 1, matcher on frame: yes)
