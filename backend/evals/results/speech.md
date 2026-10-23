# Speech benchmark

Production speech-to-text (`verytas.media.video.audio_pcm` then `transcribe`, faster-whisper int8 on CPU, VAD on, beam 1, language auto-detected) on clips with known scripts. Generator: `evals/speech/generate.py` (macOS `say` voices, synthetic noise and music, ffmpeg speed changes). Scorer: `evals/speech/run.py`; its docstring defines the normalisation (spoken numbers, URLs and phone numbers are made comparable).

Caveat: every voice is text-to-speech. Real voices are noisier and less regular, so absolute errors will be higher in the field. Hinglish is an approximation (an Indian-English voice reading romanised Hindi, or the Hindi voice reading the same Latin text); real code-switching is harder to read and to transcribe.

## Base vs small

| Model | Clips | Audio | WER (pooled) | CER | Critical phrases heard | RTF median | RTF mean | Empty transcripts |
|---|---|---|---|---|---|---|---|---|
| base | 104 | 13.2 min | 43.8% | 27.9% | 44.6% (90/202) | 0.16 | 0.27 | 0 |
| small | 104 | 13.2 min | 36.5% | 24.3% | 51.0% (103/202) | 0.42 | 0.66 | 0 |

The 104 clips both models transcribed (a fair like-for-like):

| Model | WER | Critical phrases heard |
|---|---|---|
| base | 43.8% | 44.6% (90/202) |
| small | 36.5% | 51.0% (103/202) |

RTF is transcription seconds per second of audio on this machine (8 CPU cores, int8); the tables below show WER and critical phrases heard per condition and model.

## By language group

| Group | Clips | WER base | Critical base | WER small | Critical small |
|---|---|---|---|---|---|
| English, Indian voices | 30 | 16.4% | 61.0% (47/77) | 9.6% | 68.8% (53/77) |
| English, US and UK voices | 24 | 22.5% | 66.7% (34/51) | 10.3% | 74.5% (38/51) |
| Hindi (Lekha) | 18 | 105.5% | 3.8% (1/26) | 65.5% | 7.7% (2/26) |
| Hinglish, Indian-English voices | 22 | 70.0% | 14.7% (5/34) | 85.0% | 17.6% (6/34) |
| Hinglish, Hindi voice (Lekha) | 10 | 64.2% | 21.4% (3/14) | 83.0% | 28.6% (4/14) |

## By condition

All languages pooled; clean means no added noise at normal speed.

| Condition | Clips | WER base | Critical base | WER small | Critical small |
|---|---|---|---|---|---|
| clean, normal speed | 49 | 43.5% | 43.9% (43/98) | 37.3% | 50.0% (49/98) |
| white noise, 15 dB SNR | 9 | 45.8% | 52.6% (10/19) | 33.9% | 47.4% (9/19) |
| white noise, 5 dB SNR | 9 | 55.9% | 31.6% (6/19) | 40.1% | 42.1% (8/19) |
| music bed, 15 dB SNR | 9 | 41.2% | 47.4% (9/19) | 35.6% | 52.6% (10/19) |
| music bed, 5 dB SNR | 9 | 39.0% | 42.1% (8/19) | 33.9% | 57.9% (11/19) |
| clean, 1.25x speed-up | 6 | 53.6% | 46.2% (6/13) | 40.2% | 53.8% (7/13) |
| clean, 1.5x speed-up | 6 | 49.5% | 46.2% (6/13) | 37.1% | 53.8% (7/13) |
| fine print read very fast | 7 | 30.9% | 100.0% (2/2) | 32.5% | 100.0% (2/2) |

### Condition within each language group

**English, Indian voices**

| Condition | Clips | WER base | Critical base | WER small | Critical small |
|---|---|---|---|---|---|
| clean, normal speed | 12 | 17.4% | 56.7% (17/30) | 10.0% | 66.7% (20/30) |
| white noise, 15 dB SNR | 3 | 15.0% | 77.8% (7/9) | 10.0% | 66.7% (6/9) |
| white noise, 5 dB SNR | 3 | 18.8% | 44.4% (4/9) | 8.8% | 66.7% (6/9) |
| music bed, 15 dB SNR | 3 | 17.5% | 55.6% (5/9) | 10.0% | 66.7% (6/9) |
| music bed, 5 dB SNR | 3 | 16.2% | 55.6% (5/9) | 10.0% | 66.7% (6/9) |
| clean, 1.25x speed-up | 2 | 21.6% | 80.0% (4/5) | 13.5% | 80.0% (4/5) |
| clean, 1.5x speed-up | 2 | 18.9% | 80.0% (4/5) | 10.8% | 80.0% (4/5) |
| fine print read very fast | 2 | 5.1% | 100.0% (1/1) | 3.4% | 100.0% (1/1) |

**English, US and UK voices**

| Condition | Clips | WER base | Critical base | WER small | Critical small |
|---|---|---|---|---|---|
| clean, normal speed | 12 | 20.8% | 66.7% (20/30) | 10.8% | 70.0% (21/30) |
| white noise, 15 dB SNR | 2 | 28.6% | 75.0% (3/4) | 17.1% | 50.0% (2/4) |
| white noise, 5 dB SNR | 2 | 37.1% | 50.0% (2/4) | 14.3% | 50.0% (2/4) |
| music bed, 15 dB SNR | 2 | 14.3% | 75.0% (3/4) | 8.6% | 100.0% (4/4) |
| music bed, 5 dB SNR | 2 | 11.4% | 75.0% (3/4) | 8.6% | 100.0% (4/4) |
| clean, 1.25x speed-up | 1 | 66.7% | 50.0% (1/2) | 11.1% | 100.0% (2/2) |
| clean, 1.5x speed-up | 1 | 44.4% | 50.0% (1/2) | 11.1% | 100.0% (2/2) |
| fine print read very fast | 2 | 8.5% | 100.0% (1/1) | 3.4% | 100.0% (1/1) |

**Hindi (Lekha)**

| Condition | Clips | WER base | Critical base | WER small | Critical small |
|---|---|---|---|---|---|
| clean, normal speed | 7 | 104.8% | 0.0% (0/10) | 62.5% | 10.0% (1/10) |
| white noise, 15 dB SNR | 2 | 100.0% | 0.0% (0/3) | 69.7% | 0.0% (0/3) |
| white noise, 5 dB SNR | 2 | 130.3% | 0.0% (0/3) | 90.9% | 0.0% (0/3) |
| music bed, 15 dB SNR | 2 | 100.0% | 33.3% (1/3) | 63.6% | 0.0% (0/3) |
| music bed, 5 dB SNR | 2 | 93.9% | 0.0% (0/3) | 57.6% | 33.3% (1/3) |
| clean, 1.25x speed-up | 1 | 100.0% | 0.0% (0/2) | 69.2% | 0.0% (0/2) |
| clean, 1.5x speed-up | 1 | 107.7% | 0.0% (0/2) | 61.5% | 0.0% (0/2) |
| fine print read very fast | 1 | 106.5% | - | 54.8% | - |

**Hinglish, Indian-English voices**

| Condition | Clips | WER base | Critical base | WER small | Critical small |
|---|---|---|---|---|---|
| clean, normal speed | 9 | 66.7% | 21.4% (3/14) | 76.1% | 21.4% (3/14) |
| white noise, 15 dB SNR | 2 | 89.7% | 0.0% (0/3) | 79.3% | 33.3% (1/3) |
| white noise, 5 dB SNR | 2 | 96.6% | 0.0% (0/3) | 100.0% | 0.0% (0/3) |
| music bed, 15 dB SNR | 2 | 72.4% | 0.0% (0/3) | 106.9% | 0.0% (0/3) |
| music bed, 5 dB SNR | 2 | 72.4% | 0.0% (0/3) | 103.4% | 0.0% (0/3) |
| clean, 1.25x speed-up | 2 | 65.5% | 25.0% (1/4) | 79.3% | 25.0% (1/4) |
| clean, 1.5x speed-up | 2 | 65.5% | 25.0% (1/4) | 75.9% | 25.0% (1/4) |
| fine print read very fast | 1 | 33.3% | - | 95.2% | - |

**Hinglish, Hindi voice (Lekha)**

| Condition | Clips | WER base | Critical base | WER small | Critical small |
|---|---|---|---|---|---|
| clean, normal speed | 9 | 65.9% | 21.4% (3/14) | 80.4% | 28.6% (4/14) |
| fine print read very fast | 1 | 52.4% | - | 100.0% | - |

## By voice

| Voice | Clips | WER base | Critical base | WER small | Critical small |
|---|---|---|---|---|---|
| Aman (en_IN) | 9 | 28.9% | 50.0% (9/18) | 23.7% | 61.1% (11/18) |
| Daniel (en_GB) | 6 | 14.7% | 76.9% (10/13) | 15.6% | 69.2% (9/13) |
| Eddy (English (US)) (en_US) | 6 | 22.9% | 61.5% (8/13) | 5.5% | 76.9% (10/13) |
| Flo (English (US)) (en_US) | 4 | 48.0% | 42.9% (3/7) | 13.3% | 71.4% (5/7) |
| Kathy (en_US) | 2 | 13.6% | 100.0% (3/3) | 6.8% | 100.0% (3/3) |
| Lekha (hi_IN) | 28 | 90.9% | 10.0% (4/40) | 71.7% | 15.0% (6/40) |
| Reed (English (UK)) (en_GB) | 2 | 10.4% | 66.7% (2/3) | 8.3% | 66.7% (2/3) |
| Rishi (en_IN) | 25 | 31.9% | 46.0% (29/63) | 30.4% | 52.4% (33/63) |
| Samantha (en_US) | 2 | 15.4% | 66.7% (4/6) | 5.8% | 66.7% (4/6) |
| Shelley (English (UK)) (en_GB) | 2 | 31.0% | 66.7% (4/6) | 16.7% | 83.3% (5/6) |
| Tara (en_IN) | 18 | 39.1% | 46.7% (14/30) | 45.5% | 50.0% (15/30) |

## Critical phrases by kind

Share of phrases heard, English clips and Hindi plus Hinglish clips apart.

| Kind | Phrases (en / hi+hinglish) | base en | base hi+hinglish | small en | small hi+hinglish |
|---|---|---|---|---|---|
| brand | 50 / 33 | 32.0% (50) | 3.0% (33) | 44.0% (50) | 12.1% (33) |
| date | 10 / 3 | 100.0% (10) | 66.7% (3) | 90.0% (10) | 33.3% (3) |
| number | 6 / 1 | 100.0% (6) | 0.0% (1) | 100.0% (6) | 0.0% (1) |
| percent | 16 / 18 | 100.0% (16) | 27.8% (18) | 100.0% (16) | 38.9% (18) |
| phone | 14 / 7 | 57.1% (14) | 14.3% (7) | 100.0% (14) | 0.0% (7) |
| price | 24 / 9 | 100.0% (24) | 0.0% (9) | 100.0% (24) | 0.0% (9) |
| url | 8 / 3 | 12.5% (8) | 0.0% (3) | 0.0% (8) | 0.0% (3) |

## Language detection

| Group | Clips | detected as (base) | detected as (small) |
|---|---|---|---|
| English, Indian voices | 30 | en 30 | en 30 |
| English, US and UK voices | 24 | en 24 | en 24 |
| Hindi (Lekha) | 18 | hi 18 | hi 17, ur 1 |
| Hinglish, Indian-English voices | 22 | hi 18, en 3, ur 1 | hi 11, en 8, ur 3 |
| Hinglish, Hindi voice (Lekha) | 10 | hi 10 | hi 7, en 3 |

Language accuracy, English clips, base: 100.0%

Language accuracy, Hindi clips, base: 100.0%

Language accuracy, English clips, small: 100.0%

Language accuracy, Hindi clips, small: 94.4%

Script of the transcript (share of letters) for the Hindi and Hinglish groups:

| Group | Model | Devanagari | Arabic (Urdu) | Latin |
|---|---|---|---|---|
| Hindi (Lekha) | base | 11% | 28% | 61% |
| Hindi (Lekha) | small | 93% | 6% | 2% |
| Hinglish, Indian-English voices | base | 0% | 37% | 63% |
| Hinglish, Indian-English voices | small | 48% | 14% | 39% |
| Hinglish, Hindi voice (Lekha) | base | 0% | 26% | 74% |
| Hinglish, Hindi voice (Lekha) | small | 69% | 0% | 31% |

## Failure examples

**Worst clips, base**

- hi01_lekha_hi_IN_white5 (Hindi (Lekha); white noise, 5 dB SNR) WER 150.0%
  - said: ज़ेस्टोरा पर सभी उत्पादों पर चालीस प्रतिशत की छूट। यह ऑफर सिर्फ़ इस सप्ताहांत तक है।
  - heard: दिस्जूरादभर सबि वभान। पड़़ फाड। व फाड। फाड। भालिब फर वब फर जालिब फर जाज़ की थो भ़़ सिड़ किव़ फेड़ फेड़ फन ज़ा़ हाड।
- hi07_lekha_hi_IN (Hindi (Lekha); clean, normal speed) WER 123.1%
  - said: मानसून सेल में पाएँ पच्चीस प्रतिशत तक की बचत, सिर्फ़ ट्रेलमेट ऐप पर।
  - heard: من سون سےل میں پائ پچیس پر تشک تک کی بچت، صرف ٹریل میں تک بر
- hi04_lekha_hi_IN (Hindi (Lekha); clean, normal speed) WER 116.7%
  - said: दिवाली पर हर ख़रीद पर पक्का उपहार, ऑफर इकतीस अक्टूबर तक मान्य।
  - heard: دیوالی پر ہر خرید پر پکہ اُٹھار, اُفر ایک ٹیس اتوبر تک مانے پر
- hg01_rishi_en_IN_white5 (Hinglish, Indian-English voices; white noise, 5 dB SNR) WER 112.5%
  - said: Diwali dhamaka sale mein paaiye chalis percent ki bachat, sirf Zestora par, is hafte ke liye.
  - heard: بھیوالی دھماء کا سیل میں پانلہ چالیس پر سلس کی بچکھ، سیس رسٹور پاک کے حق کے لئے
- hi03_lekha_hi_IN_white5 (Hindi (Lekha); white noise, 5 dB SNR) WER 111.8%
  - said: अधिक जानकारी के लिए हमें कॉल करें, नौ आठ सात छह पाँच चार तीन दो एक शून्य।
  - heard: Adi jankari ke liye amhe kondkar ye,
No. 8,6,8,7,5,6,6,6,10,21 sunye.
- hi02_lekha_hi_IN_x1.5 (Hindi (Lekha); clean, 1.5x speed-up) WER 107.7%
  - said: आज ही नोवाब्रू की ताज़ा कॉफ़ी आज़माएँ, कीमत सिर्फ़ चार सौ निन्यानवे रुपये।
  - heard: آج ہی نوابرو کی تازا коفی آسمائی کی مجھ سے 440 ننیانوے رو بے

Critical phrases missed by base: 112

- brand `Zestora` in en01_rishi_en_IN (clean, normal speed): heard `Flat 40% off on everything at Zestor this week and only, visit www.Zestor.inslashsale or call 1-800-123-4567.`
- url `w w w dot zestora dot in slash sale` in en01_rishi_en_IN (clean, normal speed): heard `Flat 40% off on everything at Zestor this week and only, visit www.Zestor.inslashsale or call 1-800-123-4567.`
- brand `Zestora` in en01_rishi_en_IN_white5 (white noise, 5 dB SNR): heard `Plac 40% of on everything at the store this week and only visit www.vastore.inslash.shale or call 1 8 00 1234567`
- url `w w w dot zestora dot in slash sale` in en01_rishi_en_IN_white5 (white noise, 5 dB SNR): heard `Plac 40% of on everything at the store this week and only visit www.vastore.inslash.shale or call 1 8 00 1234567`
- brand `Zestora` in en01_rishi_en_IN_music15 (music bed, 15 dB SNR): heard `Flat 40% off on everything at Zestor this week and only, visit www.Zestor.inslashsale.orcall18001234567.`
- url `w w w dot zestora dot in slash sale` in en01_rishi_en_IN_music15 (music bed, 15 dB SNR): heard `Flat 40% off on everything at Zestor this week and only, visit www.Zestor.inslashsale.orcall18001234567.`
- phone `9876543210` in en07_rishi_en_IN (clean, normal speed): heard `Call now on 9875432102 book your free demo with pixel pulse, limited slots available.`
- phone `9876543210` in en07_rishi_en_IN_white15 (white noise, 15 dB SNR): heard `Call now on 9-8-76543-102-Boukier-Free demo with Pixel Pulse, limited slots available.`
- phone `9876543210` in en07_rishi_en_IN_white5 (white noise, 5 dB SNR): heard `Call now on 9875-43202 book your free demo with PixelTiles, limited slots available.`
- percent `चालीस प्रतिशत` in hi01_lekha_hi_IN (clean, normal speed): heard `Zestura per sabhi utpado par chalice prate shakhi chhood, یہ offer sirf is saptahan takhhe.`
- percent `चालीस प्रतिशत` in hi01_lekha_hi_IN_white15 (white noise, 15 dB SNR): heard `Jai Sura Par Sabhi Utspano Par Chalice Pratishat Ki Chhoog, Yeho Par Seer Is Satahan Takhe`
- percent `चालीस प्रतिशत` in hi01_lekha_hi_IN_white5 (white noise, 5 dB SNR): heard `दिस्जूरादभर सबि वभान। पड़़ फाड। व फाड। फाड। भालिब फर वब फर जालिब फर जाज़ की थो भ़़ सिड़ किव़ फेड़ फेड़ फन ज़ा़ हाड।`
- price `चार सौ निन्यानवे रुपये` in hi02_lekha_hi_IN (clean, normal speed): heard `اجھ ہی نوروابرو کی تازا коفی آزمائی, کی مطرف 400 Ninjaanwe Rupé.`
- price `चार सौ निन्यानवे रुपये` in hi02_lekha_hi_IN_x1.25 (clean, 1.25x speed-up): heard `Aaj hinovabru ki taza koffi azma'i ki madh sirf charso ninyanwe rupe.`
- price `चार सौ निन्यानवे रुपये` in hi02_lekha_hi_IN_x1.5 (clean, 1.5x speed-up): heard `آج ہی نوابرو کی تازا коفی آسمائی کی مجھ سے 440 ننیانوے رو بے`
- date `इकतीस अक्टूबर` in hi04_lekha_hi_IN (clean, normal speed): heard `دیوالی پر ہر خرید پر پکہ اُٹھار, اُفر ایک ٹیس اتوبر تک مانے پر`
- number `तीस मिनट` in hi06_lekha_hi_IN (clean, normal speed): heard `مفتھون دلیوری, HER OR DURPAR, QUI CHIPA HWAK SHULT NAYE, OR TEECE MINUTMENT ME AAPKED DURVAZE PAR.`

**Worst clips, small**

- hg01_rishi_en_IN (Hinglish, Indian-English voices; clean, normal speed) WER 112.5%
  - said: Diwali dhamaka sale mein paaiye chalis percent ki bachat, sirf Zestora par, is hafte ke liye.
  - heard: दिवाली दमा का सेल में पाए आई चालिस पर संथ की बच्चत, सिर्फ जिस्टोरपा इस हैट्च्ट के लिए
- hg01_rishi_en_IN_music15 (Hinglish, Indian-English voices; music bed, 15 dB SNR) WER 112.5%
  - said: Diwali dhamaka sale mein paaiye chalis percent ki bachat, sirf Zestora par, is hafte ke liye.
  - heard: दिवाली दमा का सेल में पाए आई चालिस पर संथ की बच्चत, सिर्फ जिस्टोरपा इस हैफ्ट के लिए.
- hg08_lekha_hi_IN (Hinglish, Hindi voice (Lekha); clean, normal speed) WER 107.1%
  - said: Shaadi season ke liye special collection, flat twenty five percent off, Aarav Jewels par.
  - heard: शादी सीजन के लिए स्पेश्यल कलेक्षन, आप आप परच्वन्त परसेंट पाफ, आप आप जोल स्पारग्रो़्फ.
- hi01_lekha_hi_IN_white5 (Hindi (Lekha); white noise, 5 dB SNR) WER 106.2%
  - said: ज़ेस्टोरा पर सभी उत्पादों पर चालीस प्रतिशत की छूट। यह ऑफर सिर्फ़ इस सप्ताहांत तक है।
  - heard: دیس طورہ پر سبھی اٹھبادوں پر چالیس کرتے شکی چھوک
یہ وفر سے اس سبتہان سکت ہے
- hg01_rishi_en_IN_music5 (Hinglish, Indian-English voices; music bed, 5 dB SNR) WER 106.2%
  - said: Diwali dhamaka sale mein paaiye chalis percent ki bachat, sirf Zestora par, is hafte ke liye.
  - heard: दिवाली दमा का सेल में पाई आई चालिस परस्वंद की बच्चत, सिर्फ जिस्टोरपा इस हैफ्ट के लिए.
- hg01_rishi_en_IN_white15 (Hinglish, Indian-English voices; white noise, 15 dB SNR) WER 100.0%
  - said: Diwali dhamaka sale mein paaiye chalis percent ki bachat, sirf Zestora par, is hafte ke liye.
  - heard: दिवाली दमा का सेल में पाए या चालिस परसेंट की बच्चत, सिर्फ जिस्टोरपा लिए आपके लिए.

Critical phrases missed by small: 99

- brand `Zestora` in en01_rishi_en_IN (clean, normal speed): heard `Flat 40% off on everything at Zistora this week and only, visit www.zistora.in slash sale or call 1-800-123-4567.`
- url `w w w dot zestora dot in slash sale` in en01_rishi_en_IN (clean, normal speed): heard `Flat 40% off on everything at Zistora this week and only, visit www.zistora.in slash sale or call 1-800-123-4567.`
- brand `Zestora` in en01_rishi_en_IN_white15 (white noise, 15 dB SNR): heard `Flat 40% off on everything at Zistora this week and only, visit www.zistora.in slash sale or call 1-800-123-4567.`
- url `w w w dot zestora dot in slash sale` in en01_rishi_en_IN_white15 (white noise, 15 dB SNR): heard `Flat 40% off on everything at Zistora this week and only, visit www.zistora.in slash sale or call 1-800-123-4567.`
- brand `Zestora` in en01_rishi_en_IN_white5 (white noise, 5 dB SNR): heard `Plag 40% off on everything at Distoradoes weekend only, visit www.distoradoes.in slash sale or call 1-800-123-4567.`
- url `w w w dot zestora dot in slash sale` in en01_rishi_en_IN_white5 (white noise, 5 dB SNR): heard `Plag 40% off on everything at Distoradoes weekend only, visit www.distoradoes.in slash sale or call 1-800-123-4567.`
- date `thirty first October` in en04_rishi_en_IN (clean, normal speed): heard `Introducing the new Lumoware festive collection, prices start at Rs 1,499, offer valid till 31 October.`
- percent `चालीस प्रतिशत` in hi01_lekha_hi_IN (clean, normal speed): heard `जेस्तोरा पर सभी उद्पादों पर चालिस्प्रतिषत की चुड, ये अफर सिर्फ इस सब टाहांथ तक है.`
- percent `चालीस प्रतिशत` in hi01_lekha_hi_IN_white15 (white noise, 15 dB SNR): heard `जेस्टूरापर सभी उपादोंपर चालिस प्रतिषव्ट की चुग, ये वाफर सिर इस सबताहां तक है`
- percent `चालीस प्रतिशत` in hi01_lekha_hi_IN_white5 (white noise, 5 dB SNR): heard `دیس طورہ پر سبھی اٹھبادوں پر چالیس کرتے شکی چھوک یہ وفر سے اس سبتہان سکت ہے`
- price `चार सौ निन्यानवे रुपये` in hi02_lekha_hi_IN (clean, normal speed): heard `आज ही नोवाब्रो की ताजा कोफी आज्माए, की मत सिर्फ चार्सो निन्यानवे रुपे.`
- price `चार सौ निन्यानवे रुपये` in hi02_lekha_hi_IN_x1.25 (clean, 1.25x speed-up): heard `आज ही नोवाब्रो की ताजा कोफी आज माए, की मत सिर्फ चार्सो निन्यानवे रुपे.`
- price `चार सौ निन्यानवे रुपये` in hi02_lekha_hi_IN_x1.5 (clean, 1.5x speed-up): heard `आज ही नवाब्रो की ताजा कोफी आज्माई, की मच सिर्फ चार्सो निन्यानवे रुपे.`
- phone `9876543210` in hi03_lekha_hi_IN (clean, normal speed): heard `अदिक जान्कारी के लिए हमें कोल करे, नो आद साथ चेक पाच चार तीन तो एक शोन्ये.`
- phone `9876543210` in hi03_lekha_hi_IN_white15 (white noise, 15 dB SNR): heard `अगिग जान्कारी के लिए हमें कौल करे, नोवाद का च्छ फाज चार फीं भो एक शोन्ये।`
- phone `9876543210` in hi03_lekha_hi_IN_white5 (white noise, 5 dB SNR): heard `अगिज जान्कारी के लिए हमें कोल करे, नो आज्टा च्छ फाज चार्चीं जो एक शुन्यें।`
- date `इकतीस अक्टूबर` in hi04_lekha_hi_IN (clean, normal speed): heard `दिवाली पर हर खरीद पर पका उठार, अफर एक तीस अध्वबर तक मानिप.`
- number `तीस मिनट` in hi06_lekha_hi_IN (clean, normal speed): heard `मुझ्द्हों दिलीव्री, हर अडर पर, कोई चिपा हुए शुल्प नहीं, और तीस मिनत में आपके दरवाजे पर.`
- date `thirty first October` in hg04_rishi_en_IN (clean, normal speed): heard `افرہ 31 اکتوبر تاکھا ہے، ایسلی ایدر مٹ کرو اور آج ہائی اوڑر کرو`

