# ruff: noqa: E501  (the script tables are data: one script and its accepted spellings per line)
"""A speech benchmark: marketing voice-overs with known transcripts, from macOS `say`.

Scripts are written the way a presenter would say them (numbers as words, "dot" and "slash" in URLs,
phone numbers digit by digit) and that text is both what the voice reads and the truth. Four groups:

  en        English, read by Indian (Rishi, Tara, Aman), American and British voices
  hi        Hindi in Devanagari, read by Lekha
  hinglish  Roman-script Hindi mixed with English, read by Indian-English voices, and by Lekha

Hinglish is an approximation: macOS has no Hinglish voice, so an Indian-English voice reads romanised
Hindi with English phonology, and a Hindi voice reads the same Latin text with whatever rules it applies.
Real creators code-switch far more fluently, so treat the hinglish numbers as a rough guide.

Conditions applied to a subset of the clean clips: background noise (white, and a synthetic music bed of
chords with a bass line) mixed in at 15 dB and 5 dB signal to noise (speech power over the whole clip),
speed-ups of 1.25x and 1.5x (pitch kept, ffmpeg atempo), and disclaimers read at a very fast TTS rate.

Each case lists "critical" phrases (numbers, prices, brand names, a phone number, a URL, a date) with the
accepted spellings of each, which is what the brand checks need to hear right. Audio and `cases.jsonl`
go to an output folder, never into the repo:

    .venv/bin/python -m evals.speech.generate --out /private/tmp/.../scratchpad/speechbench
"""

from __future__ import annotations

import argparse
import json
import subprocess
import wave
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DEFAULT_OUT = Path("/private/tmp/claude-502/-Users-varadarajborkar-praj-code/"
                   "298965cb-f1e3-424a-8f01-ca8c15eeb018/scratchpad/speechbench")
RATE = 22050

# The brand names as they are said, for the what-if prompt in whatif.py.
BRANDS_SPOKEN = ["Zestora", "NovaBrew", "Kiraana Kart", "Lumo Wear", "Chaiwala Co", "PixelPulse", "Verdant Foods",
                 "Aarav Jewels", "Bluefin Mobiles", "TrailMate", "Sundari Silks", "Rasoi Fresh"]
IN_VOICES = ["Rishi", "Tara", "Aman"]
OTHER_VOICES = [("Samantha", "en_US"), ("Daniel", "en_GB"), ("Eddy (English (US))", "en_US"),
                ("Shelley (English (UK))", "en_GB"), ("Flo (English (US))", "en_US"), ("Reed (English (UK))", "en_GB"),
                ("Kathy", "en_US")]
HINDI_VOICE = "Lekha"


@dataclass
class Script:
    sid: str
    lang: str
    text: str
    # Each critical item: kind, display form, accepted spellings and how to match them
    # ("words": whole words after normalisation; "nospace": substring with spaces removed).
    crit: list[dict] = field(default_factory=list)
    fine_print: bool = False


def k(kind: str, shown: str, alts: list[str], mode: str = "words") -> dict:
    return {"kind": kind, "t": shown, "alts": alts, "mode": mode}


EN = [
    Script("en01", "en", "Flat forty percent off on everything at Zestora this weekend only. Visit w w w dot zestora "
           "dot in slash sale or call one eight zero zero one two three four five six seven.",
           [k("percent", "forty percent", ["forty percent"]), k("brand", "Zestora", ["zestora"], "nospace"),
            k("url", "w w w dot zestora dot in slash sale", ["w w w dot zestora dot in slash sale"], "nospace"),
            k("phone", "18001234567", ["one eight zero zero one two three four five six seven"])]),
    Script("en02", "en", "Meet NovaBrew cold brew coffee, now only four hundred and ninety nine rupees for a pack of six.",
           [k("brand", "NovaBrew", ["novabrew"], "nospace"),
            k("price", "four hundred ninety nine rupees", ["four hundred ninety nine rupees"])]),
    Script("en03", "en", "Kiraana Kart brings you fresh groceries delivered in thirty minutes. Order now and save twenty "
           "percent on your first order.",
           [k("brand", "Kiraana Kart", ["kiraanakart"], "nospace"), k("percent", "twenty percent", ["twenty percent"]),
            k("number", "thirty minutes", ["thirty minutes"])]),
    Script("en04", "en", "Introducing the new Lumo Wear festive collection. Prices start at one thousand four hundred and "
           "ninety nine rupees. Offer valid till thirty first October.",
           [k("brand", "Lumo Wear", ["lumowear"], "nospace"),
            k("price", "one thousand four hundred ninety nine rupees", ["one thousand four hundred ninety nine rupees"]),
            k("date", "thirty first October", ["thirty first october"])]),
    Script("en05", "en", "Chaiwala Co presents masala chai, made fresh every morning. Follow us on social media and use "
           "the hashtag chai time with Chaiwala.",
           [k("brand", "Chaiwala", ["chaiwala"], "nospace")]),
    Script("en06", "en", "Terms and conditions apply. This offer is valid on select products only, while stocks last, and "
           "cannot be combined with any other offer or coupon.", [], True),
    Script("en07", "en", "Call now on nine eight seven six five four three two one zero to book your free demo with "
           "PixelPulse. Limited slots available.",
           [k("phone", "9876543210", ["nine eight seven six five four three two one zero"]),
            k("brand", "PixelPulse", ["pixelpulse"], "nospace")]),
    Script("en08", "en", "Verdant Foods organic rice, five kilogram pack, at just six hundred and ninety nine rupees. Pure "
           "ingredients and honest pricing.",
           [k("brand", "Verdant Foods", ["verdantfoods"], "nospace"),
            k("price", "six hundred ninety nine rupees", ["six hundred ninety nine rupees"])]),
    Script("en09", "en", "Visit w w w dot aaravjewels dot com slash festive to explore handcrafted gold necklaces. Free "
           "shipping on all orders above ten thousand rupees.",
           [k("url", "w w w dot aaravjewels dot com slash festive", ["w w w dot aaravjewels dot com slash festive"], "nospace"),
            k("brand", "aaravjewels", ["aaravjewels", "aarav jewels"], "nospace"),
            k("price", "ten thousand rupees", ["ten thousand rupees"])]),
    Script("en10", "en", "Big billion bonanza starts today. Get up to seventy percent off on mobiles, laptops and "
           "accessories at Bluefin Mobiles.",
           [k("percent", "seventy percent", ["seventy percent"]), k("brand", "Bluefin Mobiles", ["bluefinmobiles"], "nospace")]),
    Script("en11", "en", "Download the TrailMate app today and get fifty rupees cashback on your first booking, valid "
           "for the next seven days.",
           [k("brand", "TrailMate", ["trailmate"], "nospace"), k("price", "fifty rupees", ["fifty rupees"]),
            k("number", "seven days", ["seven days"])]),
    Script("en12", "en", "Sundari Silks wedding sale begins on first November. Buy two sarees and get one free, only at "
           "Sundari Silks.",
           [k("brand", "Sundari Silks", ["sundarisilks"], "nospace"), k("date", "first November", ["first november", "one november"])]),
    Script("en13", "en", "Rasoi Fresh meal boxes, starting at just ninety nine rupees per meal. WhatsApp us on nine one "
           "eight eight eight eight seven seven seven seven.",
           [k("brand", "Rasoi Fresh", ["rasoifresh"], "nospace"), k("price", "ninety nine rupees", ["ninety nine rupees"]),
            k("phone", "9188887777", ["nine one eight eight eight eight seven seven seven seven"])]),
    Script("en14", "en", "Prices are inclusive of all taxes. Delivery charges may apply on orders below five hundred "
           "rupees. Images are for representation purposes only. The company reserves the right to modify or "
           "withdraw this offer without prior notice.",
           [k("price", "five hundred rupees", ["five hundred rupees"])], True),
]

HI = [
    Script("hi01", "hi", "ज़ेस्टोरा पर सभी उत्पादों पर चालीस प्रतिशत की छूट। यह ऑफर सिर्फ़ इस सप्ताहांत तक है।",
           [k("percent", "चालीस प्रतिशत", ["चालीस", "40", "४०"], "nospace"),
            k("brand", "ज़ेस्टोरा", ["ज़ेस्टोरा", "जेस्टोरा", "zestora"], "nospace")]),
    Script("hi02", "hi", "आज ही नोवाब्रू की ताज़ा कॉफ़ी आज़माएँ, कीमत सिर्फ़ चार सौ निन्यानवे रुपये।",
           [k("price", "चार सौ निन्यानवे रुपये", ["चारसौनिन्यानवे", "499", "४९९"], "nospace"),
            k("brand", "नोवाब्रू", ["नोवाब्रू", "novabrew"], "nospace")]),
    Script("hi03", "hi", "अधिक जानकारी के लिए हमें कॉल करें, नौ आठ सात छह पाँच चार तीन दो एक शून्य।",
           [k("phone", "9876543210", ["9876543210", "नौआठसातछहपाँचचारतीनदोएकशून्य", "९८७६५४३२१०"], "nospace")]),
    Script("hi04", "hi", "दिवाली पर हर ख़रीद पर पक्का उपहार, ऑफर इकतीस अक्टूबर तक मान्य।",
           [k("date", "इकतीस अक्टूबर", ["इकतीस", "31", "३१"], "nospace")]),
    Script("hi05", "hi", "हमारी वेबसाइट पर जाएँ, डब्ल्यू डब्ल्यू डब्ल्यू डॉट ज़ेस्टोरा डॉट इन, और पाएँ ख़ास ऑफर।",
           [k("url", "ज़ेस्टोरा डॉट इन", ["ज़ेस्टोरा", "जेस्टोरा", "zestora"], "nospace")]),
    Script("hi06", "hi", "मुफ़्त होम डिलीवरी, हर ऑर्डर पर, कोई छिपा हुआ शुल्क नहीं, और तीस मिनट में आपके दरवाज़े पर।",
           [k("number", "तीस मिनट", ["तीसमिनट", "30मिनट", "३०मिनट"], "nospace")]),
    Script("hi07", "hi", "मानसून सेल में पाएँ पच्चीस प्रतिशत तक की बचत, सिर्फ़ ट्रेलमेट ऐप पर।",
           [k("percent", "पच्चीस प्रतिशत", ["पच्चीस", "25", "२५"], "nospace"),
            k("brand", "ट्रेलमेट", ["ट्रेलमेट", "trailmate"], "nospace")]),
    Script("hi08", "hi", "शर्तें लागू। यह ऑफर चुनिंदा उत्पादों पर ही मान्य है और स्टॉक रहने तक उपलब्ध है। कंपनी किसी भी "
           "समय ऑफर में बदलाव या उसे वापस लेने का अधिकार रखती है।", [], True),
]

HG = [
    Script("hg01", "hinglish", "Diwali dhamaka sale mein paaiye chalis percent ki bachat, sirf Zestora par, is hafte ke "
           "liye.",
           [k("percent", "chalis percent", ["chalis percent", "forty percent", "चालीस प्रतिशत", "चालीस"]),
            k("brand", "Zestora", ["zestora", "ज़ेस्टोरा", "जेस्टोरा"], "nospace")]),
    Script("hg02", "hinglish", "Aaj hi kharido NovaBrew ki fresh coffee, price sirf char sau ninyanve rupaye, jaldi karo.",
           [k("price", "char sau ninyanve rupaye", ["char sau ninyanve rupaye", "four hundred ninety nine rupees",
                                                      "चार सौ निन्यानवे रुपये"]),
            k("brand", "NovaBrew", ["novabrew", "नोवाब्रू"], "nospace")]),
    Script("hg03", "hinglish", "Ab ghar baithe order karo, bas ek call karo, nine eight seven six five four three two "
           "one zero, aur delivery pao.",
           [k("phone", "9876543210", ["nine eight seven six five four three two one zero"])]),
    Script("hg04", "hinglish", "Offer thirty first October tak hi hai, isliye der mat karo aur aaj hi order karo.",
           [k("date", "thirty first October", ["thirty first october", "thirty one october", "इकतीस अक्टूबर"])]),
    Script("hg05", "hinglish", "Free delivery, koi hidden charge nahi, sirf Lumo Wear par, har order pe.",
           [k("brand", "Lumo Wear", ["lumowear", "लूमोवियर", "लूमोवेयर"], "nospace")]),
    Script("hg06", "hinglish", "Apni pasand ka maal, apne budget mein, visit w w w dot kiraanakart dot in.",
           [k("url", "w w w dot kiraanakart dot in", ["w w w dot kiraanakart dot in"], "nospace")]),
    Script("hg07", "hinglish", "Sirf ninety nine rupees mein, Chaiwala Co ki special masala chai, garma garam.",
           [k("price", "ninety nine rupees", ["ninety nine rupees", "निन्यानवे रुपये"]),
            k("brand", "Chaiwala", ["chaiwala", "चायवाला"], "nospace")]),
    Script("hg08", "hinglish", "Shaadi season ke liye special collection, flat twenty five percent off, Aarav Jewels par.",
           [k("percent", "twenty five percent", ["twenty five percent", "पच्चीस प्रतिशत", "पच्चीस"]),
            k("brand", "Aarav Jewels", ["aaravjewels", "आरवज्वेल्स"], "nospace")]),
    Script("hg09", "hinglish", "Mega monsoon sale mein pao seventy percent tak ki chhoot, sirf Bluefin Mobiles par.",
           [k("percent", "seventy percent", ["seventy percent", "सत्तर प्रतिशत", "सत्तर"]),
            k("brand", "Bluefin Mobiles", ["bluefinmobiles"], "nospace")]),
    Script("hg10", "hinglish", "Terms and conditions lagu, offer sirf select products par valid hai, stock khatam hone "
           "tak, company kabhi bhi offer badal sakti hai.", [], True),
]

# Which clips also get noise and speed variants (script id, voice) so every group is covered.
NOISE_ON = [("en01", "Rishi"), ("en04", "Rishi"), ("en07", "Rishi"), ("en02", "Daniel"), ("en10", "Eddy (English (US))"),
            ("hi01", HINDI_VOICE), ("hi03", HINDI_VOICE), ("hg01", "Rishi"), ("hg05", "Tara")]
SPEED_ON = [("en03", "Aman"), ("en08", "Tara"), ("en12", "Flo (English (US))"), ("hi02", HINDI_VOICE),
            ("hg02", "Tara"), ("hg08", "Tara")]
FAST_TTS = {"en06", "en14", "hi08", "hg10"}
NOISE_CONDITIONS = [("white", 15), ("white", 5), ("music", 15), ("music", 5)]


def say(voice: str, text: str, path: Path, rate: int | None = None) -> None:
    cmd = ["say", "-v", voice, "-o", str(path), f"--data-format=LEI16@{RATE}"]
    if rate:
        cmd += ["-r", str(rate)]
    subprocess.run(cmd + [text], check=True)


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def write_wav(path: Path, x: np.ndarray) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def pad(x: np.ndarray) -> np.ndarray:
    """A beat of room tone at each end, as a recorded voice-over has."""
    z = np.zeros(int(0.35 * RATE), np.float32)
    return np.concatenate([z, x, z])


def music_bed(n: int, rng: np.random.RandomState) -> np.ndarray:
    """Chords over a pentatonic scale with a bass line: tonal, rhythmic, speech-band energy, like a track."""
    t = np.arange(n) / RATE
    out = np.zeros(n, np.float32)
    scale = [261.63, 293.66, 329.63, 392.0, 440.0, 523.25]
    beat = 0.5
    for b in range(int(t[-1] / beat) + 1):
        i0, i1 = int(b * beat * RATE), min(n, int((b + 1) * beat * RATE))
        if i0 >= n:
            break
        seg = t[i0:i1] - t[i0]
        env = np.exp(-3.0 * seg / beat) * 0.6 + 0.4
        notes = rng.choice(scale, 3, replace=False)
        chord = sum(np.sin(2 * np.pi * f * seg) + 0.4 * np.sin(4 * np.pi * f * seg) for f in notes)
        bass = 0.9 * np.sin(2 * np.pi * (notes.min() / 4) * seg)
        out[i0:i1] = ((chord / 3 + bass) * env).astype(np.float32)
    return out


def mix(x: np.ndarray, kind: str, snr_db: float, seed: int) -> np.ndarray:
    rng = np.random.RandomState(seed)
    noise = rng.normal(0, 1, x.size).astype(np.float32) if kind == "white" else music_bed(x.size, rng)
    # Signal to noise over the whole clip, pauses included, so the figure means "this loud a bed".
    gain = np.sqrt(np.mean(x**2)) / (np.sqrt(np.mean(noise**2)) * 10 ** (snr_db / 20))
    y = x + noise * gain
    return y / max(1.0, float(np.abs(y).max()) / 0.95)


def speed(src: Path, dst: Path, factor: float) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-filter:a", f"atempo={factor}", str(dst)],
                   check=True)


def main() -> None:
    p = argparse.ArgumentParser(prog="evals.speech.generate")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    scripts = {s.sid: s for s in EN + HI + HG}
    jobs: list[tuple[str, str, str]] = []  # (script id, voice, accent group)
    for i, s in enumerate(EN):
        jobs.append((s.sid, IN_VOICES[i % 3], "en_IN"))
        v, g = OTHER_VOICES[i % len(OTHER_VOICES)]
        jobs.append((s.sid, v, g))
    for s in HI:
        jobs.append((s.sid, HINDI_VOICE, "hi_IN"))
    for i, s in enumerate(HG):
        jobs.append((s.sid, IN_VOICES[i % 3], "en_IN"))
        jobs.append((s.sid, HINDI_VOICE, "hi_IN"))

    cases = []

    def add(sid: str, voice: str, accent: str, file: str, wav: Path, noise: str, speed_tag: str) -> None:
        s = scripts[sid]
        with wave.open(str(wav)) as w:
            dur = w.getnframes() / w.getframerate()
        cases.append({"id": file.rsplit(".", 1)[0], "file": file, "script": sid, "lang": s.lang, "voice": voice,
                      "accent": accent, "text": s.text, "critical": s.crit, "fine_print": s.fine_print,
                      "noise": noise, "speed": speed_tag, "duration": round(dur, 2)})

    for sid, voice, accent in jobs:
        s = scripts[sid]
        tag = voice.split(" ")[0].lower()
        base = out / f"{sid}_{tag}_{accent}.wav"
        fast = sid in FAST_TTS
        say(voice, s.text, base, rate=300 if fast else None)
        x = pad(read_wav(base))
        write_wav(base, x)
        add(sid, voice, accent, base.name, base, "none", "tts_fast" if fast else "1.0")
        if (sid, voice) in NOISE_ON:
            for n, (kind, snr) in enumerate(NOISE_CONDITIONS):
                f = out / f"{sid}_{tag}_{accent}_{kind}{snr}.wav"
                write_wav(f, mix(x, kind, snr, seed=zlib.crc32(f"{sid}:{n}".encode()) % 10_000))
                add(sid, voice, accent, f.name, f, f"{kind}_{snr}", "1.0")
        if (sid, voice) in SPEED_ON:
            for factor in (1.25, 1.5):
                f = out / f"{sid}_{tag}_{accent}_x{factor}.wav"
                speed(base, f, factor)
                add(sid, voice, accent, f.name, f, "none", str(factor))

    with (out / "cases.jsonl").open("w") as fh:
        for case in cases:
            fh.write(json.dumps(case, ensure_ascii=False) + "\n")
    total = sum(c["duration"] for c in cases)
    print(f"{len(cases)} clips ({total / 60:.1f} min of audio) and cases.jsonl written to {out}")


if __name__ == "__main__":
    main()
