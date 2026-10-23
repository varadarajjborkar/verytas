# OCR benchmark

Production OCR (`verytas.media.ocr.read`, RapidOCR PP-OCR on CPU) over 240 generated marketing images with known text. Generator: `evals/ocr/generate.py` (seeded; Devanagari shaped by pango). Scorer: `evals/ocr/run.py`.

Method: CER is character edit distance over NFKC, case-folded text with all whitespace removed (spacing is WER's job); punctuation, digits and currency signs are kept. WER is on whitespace tokens with sentence punctuation trimmed at word edges. A critical token (price, percent, date, URL, phone, hashtag, brand) counts as read when it appears exactly, ignoring case and spacing. Figures are pooled over all characters or tokens unless stated.

## Overall

| Images | CER (pooled) | CER (mean / median per image) | WER | Critical tokens read exactly | Time p50 / p95 per image |
|---|---|---|---|---|---|
| 240 | 27.1% | 23.6% / 2.9% | 34.9% | 88.0% (901/1024) | 0.49s / 0.84s |

Reading the low-confidence lines the filter drops as well would give a pooled CER of 27.1% (filter on: 27.1%).

### By script

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| latin | 182 | 26.1% | 32.1% | 89.2% (670/751) | 0.48 |
| hinglish | 29 | 8.4% | 12.5% | 87.3% (138/158) | 0.52 |
| devanagari | 29 | 56.0% | 77.2% | 80.9% (93/115) | 0.56 |

### By fine_print

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| no | 103 | 17.2% | 27.1% | 88.1% (458/520) | 0.40 |
| yes | 137 | 31.1% | 37.5% | 87.9% (443/504) | 0.56 |

### By size

_smallest non-legal line in the image, in pixels as stored: tiny < 14, small < 22, medium < 44, large_

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| tiny | 39 | 55.1% | 62.3% | 74.7% (124/166) | 0.32 |
| small | 45 | 38.4% | 51.3% | 91.0% (171/188) | 0.36 |
| medium | 156 | 16.7% | 23.5% | 90.4% (606/670) | 0.58 |

### By contrast

_median WCAG contrast ratio of text against the pixels under it: high >= 7, medium 3 to 7, low < 3_

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| high | 49 | 29.6% | 36.6% | 89.7% (175/195) | 0.48 |
| medium | 132 | 18.8% | 26.5% | 90.9% (520/572) | 0.51 |
| low | 59 | 41.2% | 49.6% | 80.2% (206/257) | 0.49 |

### By background

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| flat | 42 | 32.5% | 36.9% | 83.3% (140/168) | 0.46 |
| gradient | 65 | 27.4% | 35.4% | 91.6% (263/287) | 0.50 |
| photo | 74 | 25.9% | 33.7% | 90.2% (276/306) | 0.47 |
| shapes | 59 | 23.7% | 34.0% | 84.4% (222/263) | 0.52 |

### By angle

_degrees of rotation of the whole layout_

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| 0 | 154 | 23.6% | 31.1% | 90.0% (586/651) | 0.48 |
| 1-3 | 20 | 27.9% | 35.8% | 82.2% (74/90) | 0.50 |
| 4-8 | 66 | 34.3% | 42.5% | 85.2% (241/283) | 0.54 |

### By jpeg

_png is lossless; qN is JPEG quality N_

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| png | 61 | 27.8% | 35.5% | 91.9% (237/258) | 0.54 |
| q90 | 58 | 24.6% | 31.7% | 90.5% (248/274) | 0.48 |
| q70 | 56 | 22.3% | 28.6% | 88.0% (205/233) | 0.52 |
| q40 | 33 | 33.5% | 44.0% | 81.6% (111/136) | 0.55 |
| q20 | 32 | 32.4% | 41.4% | 81.3% (100/123) | 0.43 |

### By scale

_the image downscaled to this share of its drawn size before saving_

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| 100% | 163 | 16.2% | 23.2% | 90.7% (637/702) | 0.58 |
| 50% | 49 | 44.8% | 56.4% | 88.0% (184/209) | 0.36 |
| 30% | 28 | 58.7% | 64.2% | 70.8% (80/113) | 0.31 |

### By font

_body font class (headline class is `head_font`)_

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| devanagari | 29 | 56.0% | 77.2% | 80.9% (93/115) | 0.56 |
| handwriting | 11 | 40.5% | 48.9% | 65.1% (28/43) | 0.42 |
| mono | 19 | 21.0% | 27.9% | 96.3% (79/82) | 0.55 |
| sans | 118 | 22.6% | 27.8% | 88.6% (468/528) | 0.48 |
| serif | 63 | 24.0% | 30.5% | 91.0% (233/256) | 0.46 |

### By head_font

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| devanagari | 29 | 56.0% | 77.2% | 80.9% (93/115) | 0.56 |
| display | 48 | 23.3% | 30.5% | 83.3% (175/210) | 0.49 |
| handwriting | 18 | 48.0% | 53.9% | 81.5% (53/65) | 0.39 |
| mono | 16 | 26.9% | 31.6% | 91.9% (68/74) | 0.46 |
| sans | 95 | 16.9% | 22.5% | 92.1% (384/417) | 0.52 |
| serif | 34 | 27.8% | 32.9% | 89.5% (128/143) | 0.41 |

### By template

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| banner | 20 | 18.9% | 15.0% | 83.2% (79/95) | 0.36 |
| contact | 24 | 4.0% | 9.1% | 92.3% (120/130) | 0.37 |
| devanagari_card | 18 | 59.5% | 85.6% | 86.1% (62/72) | 0.45 |
| devanagari_legal | 11 | 52.3% | 68.6% | 72.1% (31/43) | 0.62 |
| hinglish_card | 22 | 5.9% | 11.2% | 87.5% (105/120) | 0.46 |
| hinglish_legal | 7 | 13.9% | 15.2% | 86.8% (33/38) | 0.63 |
| legal | 25 | 46.0% | 50.3% | n/a (0/0) | 0.62 |
| poster | 36 | 27.9% | 33.2% | 87.4% (187/214) | 0.55 |
| pricelist | 17 | 15.9% | 22.8% | 82.6% (71/86) | 0.49 |
| social | 41 | 20.1% | 27.0% | 98.4% (121/123) | 0.55 |
| story | 19 | 8.2% | 10.9% | 89.3% (92/103) | 0.60 |

### By coloured_text

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| false | 142 | 28.3% | 36.1% | 87.6% (510/582) | 0.51 |
| true | 98 | 25.2% | 32.9% | 88.5% (391/442) | 0.47 |

### By shadow

| Group | Images | CER | WER | Critical read exactly | Median s |
|---|---|---|---|---|---|
| false | 193 | 26.4% | 34.0% | 88.3% (726/822) | 0.51 |
| true | 47 | 29.8% | 38.6% | 86.6% (175/202) | 0.46 |

## Critical tokens by kind

| Kind | Tokens | Read exactly |
|---|---|---|
| brand | 159 | 98.7% |
| date | 131 | 86.3% |
| hashtag | 210 | 81.0% |
| percent | 82 | 97.6% |
| phone | 108 | 93.5% |
| price | 148 | 77.7% |
| url | 186 | 88.7% |

Critical tokens by kind and script:

| Kind | latin | hinglish | devanagari |
|---|---|---|---|
| brand | 98.0% (101) | 100.0% (29) | 100.0% (29) |
| date | 86.8% (114) | 100.0% (9) | 62.5% (8) |
| hashtag | 82.0% (133) | 79.2% (77) | - |
| percent | 100.0% (61) | 100.0% (11) | 80.0% (10) |
| phone | 93.7% (79) | - | 93.1% (29) |
| price | 83.7% (135) | 66.7% (3) | 0.0% (10) |
| url | 89.8% (128) | 89.7% (29) | 82.8% (29) |

Prices by how they were written (amount = digits only, symbol ignored):

| Written as | Tokens | Whole token exact | Amount exact |
|---|---|---|---|
| rupee sign | 27 | 3.7% | 85.2% |
| Rs. | 121 | 94.2% | 95.0% |

Devanagari images: 2494 characters came back, 0 of them Devanagari and 69 CJK. The model has no Devanagari vocabulary: Hindi words are mostly dropped, and the rest comes back as Latin or CJK look-alikes, often glued to the digits beside them (for example 'H市2,999' for '₹2,999').

## Word recall by kind of line (order ignored)

| Line | Words | Found |
|---|---|---|
| phone | 481 | 52.6% |
| legal | 3466 | 56.0% |
| body | 1329 | 76.2% |
| hashtag | 210 | 80.0% |
| headline | 786 | 80.5% |
| price | 489 | 86.9% |
| brand | 267 | 87.3% |
| url | 186 | 88.7% |
| discount | 203 | 89.2% |
| date | 320 | 90.6% |
| sub | 143 | 93.7% |

Fine-print (legal) word recall by line height as stored:

| Height | Words | Found |
|---|---|---|
| < 8 px | 1079 | 8.9% |
| 8 to 10 px | 131 | 18.3% |
| 10 to 12 px | 97 | 59.8% |
| 12 to 16 px | 1655 | 82.1% |
| >= 16 px | 504 | 80.0% |

## Failure patterns

123 of 1024 critical tokens were not read exactly.

Most common character edits inside near-miss critical tokens (truth to read-as; blank is a missing or extra character):

| Truth | Read as | Count |
|---|---|---|
| `s` | `(none)` | 23 |
| `i` | `l` | 21 |
| `e` | `(none)` | 15 |
| `o` | `(none)` | 14 |
| `₹` | `(none)` | 13 |
| `.` | `(none)` | 12 |
| `i` | `(none)` | 10 |
| `n` | `(none)` | 10 |
| `r` | `(none)` | 10 |
| `9` | `(none)` | 10 |
| `t` | `(none)` | 10 |
| `/` | `(none)` | 9 |

Misread critical tokens (truth, nearest OCR word, image conditions):

| Kind | Truth | Read as | Image |
|---|---|---|---|
| brand | `VERDANT FOODS` | `PERGITFOODS` | ocr_0054: latin, tiny, low contrast, shapes, q20, 30%, angle 1-3 |
| brand | `Sundari Silks` | `Sundari` | ocr_0058: latin, medium, low contrast, shapes, q40, 100%, angle 0 |
| date | `07/12/2026` | `50%` | ocr_0004: latin, tiny, high contrast, shapes, q20, 30%, angle 0 |
| date | `10/12/2026` | `50%` | ocr_0004: latin, tiny, high contrast, shapes, q20, 30%, angle 0 |
| date | `24` | `R市成6473511005` | ocr_0024: devanagari, small, high contrast, gradient, q90, 50%, angle 0 |
| date | `13 Dec 2026` | `2026` | ocr_0026: latin, medium, medium contrast, flat, q20, 100%, angle 0 |
| date | `24` | `40%` | ocr_0031: devanagari, tiny, medium contrast, gradient, q90, 30%, angle 0 |
| date | `24/10/2026` | `/10/2026` | ocr_0038: latin, tiny, low contrast, shapes, q90, 30%, angle 4-8 |
| date | `27/10/2026` | `/10/2026` | ocr_0038: latin, tiny, low contrast, shapes, q90, 30%, angle 4-8 |
| date | `9 Oct 2026` | `PERGITFOODS` | ocr_0054: latin, tiny, low contrast, shapes, q20, 30%, angle 1-3 |
| hashtag | `#MadeInIndia` | `#Madelnindia` | ocr_0006: hinglish, small, medium contrast, flat, q70, 50%, angle 4-8 |
| hashtag | `#MadeInIndia` | `#MadelnIndia` | ocr_0014: hinglish, medium, medium contrast, gradient, q40, 100%, angle 4-8 |
| hashtag | `#MadeInIndia` | `#MadelnIndia` | ocr_0023: latin, medium, high contrast, gradient, q70, 100%, angle 0 |
| hashtag | `#MadeInIndia` | `#MadelnIndia` | ocr_0034: latin, medium, medium contrast, shapes, q90, 100%, angle 0 |
| hashtag | `#MadeInIndia` | `#MadelnIndia` | ocr_0051: latin, medium, medium contrast, photo, q20, 100%, angle 4-8 |
| hashtag | `#TasteOfHome` | `#Taste0fHome` | ocr_0061: hinglish, medium, low contrast, shapes, png, 100%, angle 4-8 |
| hashtag | `#MadeInIndia` | `#MadelnIndia` | ocr_0069: latin, medium, medium contrast, photo, q90, 100%, angle 4-8 |
| hashtag | `#MadeInIndia` | `#Madelnlndia` | ocr_0090: hinglish, medium, medium contrast, photo, png, 100%, angle 4-8 |
| percent | `50%` | `R市可1800-313-9528` | ocr_0152: devanagari, small, medium contrast, gradient, q20, 50%, angle 4-8 |
| percent | `20%` | `市ぎ12,999T` | ocr_0175: devanagari, medium, medium contrast, flat, q40, 100%, angle 0 |
| phone | `6928707302` | `PERGITFOODS` | ocr_0054: latin, tiny, low contrast, shapes, q20, 30%, angle 1-3 |
| phone | `1800-267-0353` | `1800-267-0J5J` | ocr_0094: latin, small, high contrast, photo, png, 100%, angle 0 |
| phone | `1800-867-2673` | `299` | ocr_0123: latin, tiny, low contrast, flat, q40, 30%, angle 1-3 |
| phone | `6607447835` | `3TTTK灭3T` | ocr_0144: devanagari, medium, medium contrast, flat, q90, 100%, angle 4-8 |
| phone | `1800-971-2174` | `Lumo` | ocr_0173: devanagari, medium, medium contrast, gradient, q20, 100%, angle 0 |
| phone | `8843766308` | `Verdant` | ocr_0184: latin, medium, high contrast, shapes, png, 100%, angle 0 |
| phone | `+91 66105 96213` | `66105` | ocr_0212: latin, tiny, medium contrast, flat, q70, 30%, angle 4-8 |
| price | `₹799` | `Only799/-` | ocr_0008: latin, small, medium contrast, shapes, q70, 50%, angle 0 |
| price | `₹249` | `249` | ocr_0015: latin, tiny, high contrast, gradient, q90, 50%, angle 0 |
| price | `₹1,499` | `199` | ocr_0029: latin, medium, low contrast, shapes, q70, 100%, angle 0 |
| price | `₹199` | `199` | ocr_0029: latin, medium, low contrast, shapes, q70, 100%, angle 0 |
| price | `Rs.12,999` | `12.999` | ocr_0030: latin, tiny, low contrast, flat, q90, 30%, angle 0 |
| price | `Rs.4,999` | `4.999` | ocr_0030: latin, tiny, low contrast, flat, q90, 30%, angle 0 |
| price | `₹999` | `市999` | ocr_0035: devanagari, small, medium contrast, photo, png, 50%, angle 0 |
| price | `₹149` | `市H市149` | ocr_0042: devanagari, small, medium contrast, photo, q70, 50%, angle 0 |
| url | `www.sundarisilks.co.in/offers` | `Spacks` | ocr_0004: latin, tiny, high contrast, shapes, q20, 30%, angle 0 |
| url | `https://trailmate.in/shop?ref=social` | `https://troilmate.in/shop?ref=sooal` | ocr_0019: devanagari, tiny, medium contrast, photo, q70, 30%, angle 4-8 |
| url | `www.kiraanakart.com/offers` | `50%OFF` | ocr_0038: latin, tiny, low contrast, shapes, q90, 30%, angle 4-8 |
| url | `hello@verdantfoods.store` | `PERGITFOODS` | ocr_0054: latin, tiny, low contrast, shapes, q20, 30%, angle 1-3 |
| url | `hello@verdantfoods.in` | `PERGITFOODS` | ocr_0054: latin, tiny, low contrast, shapes, q20, 30%, angle 1-3 |
| url | `www.trailmate.com/offers` | `www.traiimate.com/offers` | ocr_0059: latin, tiny, high contrast, gradient, q20, 50%, angle 0 |
| url | `kiraanakart.co.in/offers` | `kiraanakartco.in/offers` | ocr_0061: hinglish, medium, low contrast, shapes, png, 100%, angle 4-8 |
| url | `hello@rasoifresh.co.in` | `hella@rasbifresh.co.in` | ocr_0066: devanagari, small, low contrast, gradient, q70, 50%, angle 0 |

## Worst images by CER

- ocr_0171 CER 96.6%: latin, size tiny, low contrast (1.47), gradient, q40, scale 30%, angle 0
  - truth: Grand Opening Offer / Quality you can trust at prices you will love / Prices are inclusive of all taxes. *Terms and conditions apply. Delivery charges may apply on orders below the minimum value. / Prices are inclusive of all taxes. Not valid in combination wi
  - read:  Grand Opening
- ocr_0054 CER 90.7%: latin, size tiny, low contrast (1.77), shapes, q20, scale 30%, angle 1-3
  - truth: VERDANT FOODS / WhatsApp 6928707302 / hello@verdantfoods.store / hello@verdantfoods.in / Offer valid till 9 Oct 2026
  - read:  PERGITFOODS
- ocr_0070 CER 88.8%: latin, size small, low contrast (1.61), flat, q70, scale 50%, angle 0
  - truth: Meet Our Newest Range / Visit your nearest store today / Offer valid on select products only while stocks last. Not valid in combination with any other offer or coupon. Delivery charges may apply on orders below the minimum value. / Delivery charges may apply 
  - read:  Meet Our Newest Range / Visit your nearest store today
- ocr_0003 CER 87.5%: latin, size tiny, medium contrast (4.87), photo, q90, scale 30%, angle 0
  - truth: BIG BILLION BONANZA / Tried, tested and loved by thousands / *Terms and conditions apply. Images are for representation purposes only. The company reserves the right to modify or withdraw this offer. / The company reserves the right to modify or withdraw this 
  - read:  BIG BILLION BONANZA / Tried, tested and loved by thousands
- ocr_0037 CER 87.3%: latin, size tiny, high contrast (17.96), flat, q90, scale 30%, angle 4-8
  - truth: Taste the Difference / Visit your nearest store today / Prices are inclusive of all taxes. Delivery charges may apply on orders below the minimum value. Not valid in combination with any other offer or coupon. / *Terms and conditions apply. Images are for repr
  - read:  Taste the Difference / Visit your nearest store today
- ocr_0102 CER 87.2%: latin, size tiny, high contrast (11.77), flat, q20, scale 30%, angle 4-8
  - truth: New Season, New You / Download our app for exclusive member deals / Delivery charges may apply on orders below the minimum value. Not valid in combination with any other offer or coupon. Prices are inclusive of all taxes. / Delivery charges may apply on orders
  - read:  New Season, New You / Download our app for exclusive member deals
- ocr_0204 CER 86.7%: latin, size small, high contrast (11.36), gradient, png, scale 50%, angle 0
  - truth: Upgrade Your Everyday / Gift something special to someone special / Not valid in combination with any other offer or coupon. Offer valid on select products only while stocks last. The company reserves the right to modify or withdraw this offer. / *Terms and co
  - read:  Upgrade Your Everyday / Gift something special to someone special
- ocr_0180 CER 84.2%: latin, size small, low contrast (2.01), photo, q40, scale 50%, angle 4-8
  - truth: Fresh Drop, Fresh Start / Download our app for exclusive member deals / Not valid in combination with any other offer or coupon. *Terms and conditions apply. Prices are inclusive of all taxes. / Discount applicable on MRP. Images are for representation purpose
  - read:  Fresh Drop, Fresh Start / Download our app for exclusive member deals
