# Brand-artwork benchmark (1200 scenes, pixel path only)

## Correct use: nothing should be raised

| Artwork | Scenes | Found | False alarms |
|---|---|---|---|
| icon | 168 | 98% | 2% |
| logo | 168 | 100% | 2% |
| none (absent) | 24 | n/a | 0% |
| pack | 168 | 100% | 1% |
| wordmark | 168 | 92% | 14% |

| Variant | Scenes | False alarms | Most common false finding |
|---|---|---|---|
| plain | 96 | 4% | VIS-ASSET-ALTERED (4) |
| busy | 96 | 3% | VIS-ASSET-ALTERED (3) |
| photo | 96 | 3% | VIS-ASSET-ALTERED (3) |
| text | 96 | 4% | VIS-ASSET-ALTERED (3), VIS-COMPETITOR-MARK (1) |
| small | 96 | 6% | VIS-ASSET-ALTERED (5), VIS-ASSET-DISTORTED (1) |
| rotated | 96 | 3% | VIS-ASSET-ALTERED (3) |
| jpeg | 96 | 10% | VIS-ASSET-ALTERED (10), VIS-ASSET-DISTORTED (1) |
| absent | 24 | 0% | none |

## Misuse: the expected finding should be raised

| Misuse | Artwork | Scenes | Caught | Raised instead (when missed) |
|---|---|---|---|---|
| competitor | competitor | 24 | 100% | n/a |
| mirrored | logo | 24 | 100% | n/a |
| mirrored | wordmark | 24 | 96% | nothing (1) |
| recoloured | icon | 24 | 33% | nothing (16) |
| recoloured | logo | 24 | 96% | nothing (1) |
| recoloured | pack | 24 | 100% | n/a |
| recoloured | wordmark | 24 | 92% | VIS-ASSET-RETIRED (1), nothing (1) |
| retired | retired | 24 | 100% | n/a |
| retired_photo | retired | 24 | 100% | n/a |
| skewed | icon | 24 | 75% | VIS-ASSET-ALTERED (1), nothing (5) |
| skewed | logo | 24 | 100% | n/a |
| skewed | pack | 24 | 100% | n/a |
| skewed | wordmark | 24 | 100% | n/a |
| squashed | icon | 24 | 88% | nothing (3) |
| squashed | logo | 24 | 100% | n/a |
| squashed | pack | 24 | 100% | n/a |
| squashed | wordmark | 24 | 96% | nothing (1) |
| stretched | icon | 24 | 88% | VIS-ASSET-ALTERED (2), nothing (1) |
| stretched | logo | 24 | 96% | nothing (1) |
| stretched | pack | 24 | 100% | n/a |
| stretched | wordmark | 24 | 92% | VIS-ASSET-ALTERED (1), nothing (1) |

Overall: false alarms 4.7% of 696 correct scenes; caught 92.9% of 504 misuses. Time per scene (6 library assets): median 2.76 s, p95 9.07 s.
