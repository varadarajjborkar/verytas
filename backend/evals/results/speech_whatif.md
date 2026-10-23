# Speech what-if: telling Whisper the language and the brand names

Same clips and scoring as `speech.md`; the production figure is Whisper with language auto-detection and no prompt. Not production code: see `evals/speech/whatif.py`.

## hindi_forced

| Group | Model | Clips | WER production | WER what-if | Critical production | Critical what-if | Devanagari / Arabic / Latin what-if |
|---|---|---|---|---|---|---|---|
| Hindi (Lekha) | base | 18 | 105.5% | 102.4% | 3.8% (1/26) | 11.5% (3/26) | 0% / 17% / 77% |
| Hindi (Lekha) | small | 18 | 65.5% | 63.8% | 7.7% (2/26) | 7.7% (2/26) | 98% / 0% / 2% |
| Hinglish, Hindi voice (Lekha) | base | 10 | 64.2% | 69.8% | 21.4% (3/14) | 21.4% (3/14) | 0% / 16% / 84% |
| Hinglish, Hindi voice (Lekha) | small | 10 | 83.0% | 98.1% | 28.6% (4/14) | 14.3% (2/14) | 92% / 0% / 8% |
| Hinglish, Indian-English voices | base | 22 | 70.0% | 69.7% | 14.7% (5/34) | 14.7% (5/34) | 0% / 36% / 64% |
| Hinglish, Indian-English voices | small | 22 | 85.0% | 97.9% | 17.6% (6/34) | 2.9% (1/34) | 98% / 0% / 2% |

Critical phrases heard by kind (production, what-if):

| Kind | base | base what-if | small | small what-if |
|---|---|---|---|---|
| brand | 3.0% | 6.1% | 12.1% | 3.0% |
| date | 66.7% | 66.7% | 33.3% | 0.0% |
| number | 0.0% | 0.0% | 0.0% | 0.0% |
| percent | 27.8% | 33.3% | 38.9% | 16.7% |
| phone | 14.3% | 14.3% | 0.0% | 14.3% |
| price | 0.0% | 0.0% | 0.0% | 0.0% |
| url | 0.0% | 0.0% | 0.0% | 0.0% |

## hinglish_en

| Group | Model | Clips | WER production | WER what-if | Critical production | Critical what-if | Devanagari / Arabic / Latin what-if |
|---|---|---|---|---|---|---|---|
| Hinglish, Hindi voice (Lekha) | base | 10 | 64.2% | 73.0% | 21.4% (3/14) | 28.6% (4/14) | 0% / 0% / 100% |
| Hinglish, Hindi voice (Lekha) | small | 10 | 83.0% | 65.4% | 28.6% (4/14) | 35.7% (5/14) | 0% / 0% / 100% |
| Hinglish, Indian-English voices | base | 22 | 70.0% | 76.6% | 14.7% (5/34) | 32.4% (11/34) | 0% / 0% / 100% |
| Hinglish, Indian-English voices | small | 22 | 85.0% | 64.6% | 17.6% (6/34) | 38.2% (13/34) | 0% / 0% / 100% |

Critical phrases heard by kind (production, what-if):

| Kind | base | base what-if | small | small what-if |
|---|---|---|---|---|
| brand | 0.0% | 8.3% | 12.5% | 12.5% |
| date | 100.0% | 100.0% | 50.0% | 100.0% |
| percent | 41.7% | 66.7% | 50.0% | 100.0% |
| phone | 50.0% | 100.0% | 0.0% | 0.0% |
| price | 0.0% | 16.7% | 0.0% | 16.7% |
| url | 0.0% | 0.0% | 0.0% | 0.0% |

## brand_prompt

| Group | Model | Clips | WER production | WER what-if | Critical production | Critical what-if | Devanagari / Arabic / Latin what-if |
|---|---|---|---|---|---|---|---|
| English, Indian voices | base | 30 | 16.4% | 11.9% | 61.0% (47/77) | 90.9% (70/77) | 0% / 0% / 100% |
| English, Indian voices | small | 30 | 9.6% | 5.3% | 68.8% (53/77) | 93.5% (72/77) | 0% / 0% / 100% |
| English, US and UK voices | base | 24 | 22.5% | 12.3% | 66.7% (34/51) | 88.2% (45/51) | 0% / 0% / 100% |
| English, US and UK voices | small | 24 | 10.3% | 4.9% | 74.5% (38/51) | 86.3% (44/51) | 0% / 0% / 100% |

Critical phrases heard by kind (production, what-if):

| Kind | base | base what-if | small | small what-if |
|---|---|---|---|---|
| brand | 32.0% | 90.0% | 44.0% | 92.0% |
| date | 100.0% | 100.0% | 90.0% | 80.0% |
| number | 100.0% | 100.0% | 100.0% | 100.0% |
| percent | 100.0% | 100.0% | 100.0% | 100.0% |
| phone | 57.1% | 71.4% | 100.0% | 92.9% |
| price | 100.0% | 100.0% | 100.0% | 87.5% |
| url | 12.5% | 50.0% | 0.0% | 75.0% |

## brand_hotwords

| Group | Model | Clips | WER production | WER what-if | Critical production | Critical what-if | Devanagari / Arabic / Latin what-if |
|---|---|---|---|---|---|---|---|
| English, Indian voices | small | 30 | 9.6% | 5.3% | 68.8% (53/77) | 93.5% (72/77) | 0% / 0% / 100% |
| English, US and UK voices | small | 24 | 10.3% | 4.9% | 74.5% (38/51) | 86.3% (44/51) | 0% / 0% / 100% |

Critical phrases heard by kind (production, what-if):

| Kind | base | base what-if | small | small what-if |
|---|---|---|---|---|
| brand | - | - | 44.0% | 92.0% |
| date | - | - | 90.0% | 80.0% |
| number | - | - | 100.0% | 100.0% |
| percent | - | - | 100.0% | 100.0% |
| phone | - | - | 100.0% | 92.9% |
| price | - | - | 100.0% | 87.5% |
| url | - | - | 0.0% | 75.0% |

