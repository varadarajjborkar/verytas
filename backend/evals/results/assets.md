# Brand-artwork benchmark (1200 scenes, pixel path only)

## Correct use: nothing should be raised

| Artwork | Scenes | Found | False alarms |
|---|---|---|---|
| icon | 168 | 97% | 62% |
| logo | 168 | 99% | 16% |
| none (absent) | 24 | n/a | 4% |
| pack | 168 | 100% | 7% |
| wordmark | 168 | 88% | 19% |

| Variant | Scenes | False alarms | Most common false finding |
|---|---|---|---|
| plain | 96 | 19% | VIS-ASSET-ALTERED (17), VIS-ASSET-DISTORTED (1) |
| busy | 96 | 17% | VIS-ASSET-ALTERED (16), VIS-ASSET-RETIRED (1) |
| photo | 96 | 20% | VIS-ASSET-ALTERED (19), VIS-COMPETITOR-MARK (2) |
| text | 96 | 23% | VIS-ASSET-ALTERED (20), VIS-COMPETITOR-MARK (4) |
| small | 96 | 27% | VIS-ASSET-ALTERED (25), VIS-COMPETITOR-MARK (2) |
| rotated | 96 | 21% | VIS-ASSET-ALTERED (20), VIS-COMPETITOR-MARK (1) |
| jpeg | 96 | 57% | VIS-ASSET-ALTERED (61), VIS-ASSET-DISTORTED (1) |
| absent | 24 | 4% | VIS-ASSET-DISTORTED (1) |

## Misuse: the expected finding should be raised

| Misuse | Artwork | Scenes | Caught | Raised instead (when missed) |
|---|---|---|---|---|
| competitor | competitor | 24 | 100% | n/a |
| mirrored | logo | 24 | 100% | n/a |
| mirrored | wordmark | 24 | 92% | nothing (2) |
| recoloured | icon | 24 | 29% | VIS-ASSET-DISTORTED (2), VIS-COMPETITOR-MARK (2), nothing (13) |
| recoloured | logo | 24 | 88% | nothing (3) |
| recoloured | pack | 24 | 100% | n/a |
| recoloured | wordmark | 24 | 96% | nothing (1) |
| retired | retired | 24 | 96% | nothing (1) |
| retired_photo | retired | 24 | 100% | n/a |
| skewed | icon | 24 | 12% | VIS-ASSET-ALTERED (16), VIS-COMPETITOR-MARK (1), nothing (5) |
| skewed | logo | 24 | 96% | nothing (1) |
| skewed | pack | 24 | 100% | n/a |
| skewed | wordmark | 24 | 83% | VIS-ASSET-ALTERED (3), nothing (1) |
| squashed | icon | 24 | 38% | VIS-ASSET-ALTERED (12), nothing (5) |
| squashed | logo | 24 | 75% | VIS-ASSET-ALTERED (3), nothing (3) |
| squashed | pack | 24 | 88% | VIS-ASSET-ALTERED (5) |
| squashed | wordmark | 24 | 46% | VIS-ASSET-ALTERED (8), nothing (5) |
| stretched | icon | 24 | 46% | VIS-ASSET-ALTERED (11), VIS-COMPETITOR-MARK (1), nothing (4) |
| stretched | logo | 24 | 71% | VIS-ASSET-ALTERED (3), nothing (5) |
| stretched | pack | 24 | 96% | VIS-ASSET-ALTERED (2) |
| stretched | wordmark | 24 | 50% | VIS-ASSET-ALTERED (6), VIS-COMPETITOR-MARK (1), nothing (5) |

Overall: false alarms 25.4% of 696 correct scenes; caught 76.2% of 504 misuses. Time per scene (6 library assets): median 1.32 s, p95 14.74 s.
