"""Video: everything a viewer could see or hear, turned into checkable text.

A post's video can carry text four ways, and creators use all of them:

  burned-in captions  drawn into the frames (most reels: subtitles are not a
                      separate file but part of the picture)
  on-screen text      titles, stickers, prices, handles, anywhere in frame
  subtitle tracks     a text stream inside the file (mov_text, SubRip, ASS)
  speech              voice-over or dialogue; music-only tracks have none

Frames are sampled about once a second and OCR'd only when the text edges in
the frame change, so a 60 s reel costs about 20 OCR passes rather than 1,800.
Repeated lines across frames merge into timed cues. Keyframes at scene
changes go to the asset matcher and, as one contact sheet, to the vision
model. Decoding uses PyAV (FFmpeg bundled in the wheel); speech uses a local
Whisper model, so audio never leaves the machine.
"""

from __future__ import annotations

import difflib
import io
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw

from verytas.media.files import MediaError, shrink
from verytas.media.ocr import OcrResult

SAMPLE_EVERY_S = 1.0
MAX_FRAMES = 600  # held decoded at once; longer videos are sampled more sparsely (sample_every)
FRAME_SIDE = 960
OCR_MAX = 180  # OCR passes per video
OCR_REFRESH_S = 2.5  # re-read at least this often, even on a static frame
# Share of edge pixels that must change to trigger OCR. A subtitle strip is
# about 5% of the frame, so a caption swap moves well under 1% of all pixels.
EDGE_CHANGE = 0.004
MAX_KEYFRAMES = 9
SCENE_CHANGE = 0.55  # histogram correlation below this starts a new scene
SAMPLE_RATE = 16_000
_ASR_LOCK = threading.Lock()
_asr_models: dict[str, Any] = {}


@dataclass
class Cue:
    start: float
    end: float
    text: str
    confidence: float = 1.0
    box: tuple[int, int, int, int] | None = None  # where it sits in the (shrunk) frame, if read by OCR


def _open(raw: bytes):
    import av

    try:
        return av.open(io.BytesIO(raw))
    except (av.error.FFmpegError, ValueError) as exc:
        raise MediaError(f"not a readable video ({exc})") from exc


def probe(raw: bytes) -> dict[str, Any]:
    with _open(raw) as c:
        video = next((s for s in c.streams if s.type == "video"), None)
        if video is None:
            raise MediaError("file has no video stream")
        duration = c.duration / 1_000_000 if c.duration else (
            float(video.duration * video.time_base) if video.duration else 0.0)
        return {
            "duration": round(duration, 2),
            "width": video.codec_context.width, "height": video.codec_context.height,
            "fps": round(float(video.average_rate), 2) if video.average_rate else None,
            "bitrate": c.bit_rate, "codec": video.codec_context.name,
            "has_audio": any(s.type == "audio" for s in c.streams),
            "subtitle_streams": sum(1 for s in c.streams if s.type == "subtitle"),
            "bytes": len(raw),
        }


def sample_every(duration: float, max_seconds: float) -> float:
    """Seconds between samples so the checked part of the video fits in MAX_FRAMES."""
    return max(SAMPLE_EVERY_S, min(duration, max_seconds) / MAX_FRAMES)


def frames(raw: bytes, *, max_seconds: float, every_s: float = SAMPLE_EVERY_S) -> list[tuple[float, Image.Image]]:
    out: list[tuple[float, Image.Image]] = []
    with _open(raw) as c:
        stream = c.streams.video[0]
        stream.thread_type = "AUTO"
        next_t = 0.0
        for frame in c.decode(stream):
            t = float(frame.time or 0.0)
            if t > max_seconds:
                break
            if t + 1e-6 < next_t:
                continue
            out.append((round(t, 2), shrink(frame.to_image().convert("RGB"), FRAME_SIDE)))
            next_t = t + every_s
            if len(out) >= MAX_FRAMES:
                break
    return out


# --- burned-in captions and on-screen text ------------------------------------------------------

def _edges(img: Image.Image) -> np.ndarray:
    small = cv2.cvtColor(np.asarray(shrink(img, 480)), cv2.COLOR_RGB2GRAY)
    return cv2.Canny(small, 80, 200) > 0


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold()).strip()


def caption_cues(samples: list[tuple[float, Image.Image]],
                 read: Callable[[Image.Image], OcrResult]) -> tuple[list[Cue], int, float | None]:
    """Timed text cues from sampled frames, how many OCR passes it took, and
    the time reading stopped at if the OCR budget ran out first (else None)."""
    cues: list[Cue] = []
    open_cues: list[Cue] = []
    last_edges, last_read_t, passes = None, -1e9, 0
    for i, (t, img) in enumerate(samples):
        edges = _edges(img)
        changed = (last_edges is None or edges.shape != last_edges.shape
                   or np.logical_xor(edges, last_edges).mean() > EDGE_CHANGE)
        if not changed and t - last_read_t < OCR_REFRESH_S:
            for cue in open_cues:
                cue.end = t
            continue
        if passes >= OCR_MAX:
            return cues, passes, t
        result = read(img)
        passes += 1
        last_edges, last_read_t = edges, t
        still_open = []
        for line in result.lines:
            key = _norm(line.text)
            if len(key) < 2:
                continue
            match = next((c for c in open_cues if difflib.SequenceMatcher(None, _norm(c.text), key).ratio() > 0.8),
                         None)
            if match is not None:
                match.end = t
                if len(line.text) > len(match.text) and line.confidence >= match.confidence:
                    match.text = line.text  # keep the most complete reading
                still_open.append(match)
            else:
                cue = Cue(t, t, line.text, line.confidence, line.box)
                cues.append(cue)
                still_open.append(cue)
        open_cues = still_open
        if i + 1 < len(samples):
            for cue in open_cues:
                cue.end = samples[i + 1][0]
    return cues, passes, None


# --- subtitle tracks --------------------------------------------------------------------------

_ASS_TAGS = re.compile(r"\{[^}]*\}")


def subtitle_cues(raw: bytes) -> list[Cue]:
    cues: list[Cue] = []
    with _open(raw) as c:
        streams = [s for s in c.streams if s.type == "subtitle"]
        if not streams:
            return cues
        for packet in c.demux(*streams):
            if packet.pts is None:
                continue
            start = float(packet.pts * packet.time_base)
            end = start + float((packet.duration or 0) * packet.time_base)
            for sub in packet.decode():
                for rect in getattr(sub, "rects", []) or []:
                    text = getattr(rect, "text", None) or ""
                    ass = getattr(rect, "ass", None)
                    if not text and ass:
                        ass = ass.decode() if isinstance(ass, bytes) else ass
                        text = ass.split(",", 8)[-1] if ass.count(",") >= 8 else ass
                    text = _ASS_TAGS.sub("", text).replace("\\N", "\n").strip()
                    if text:
                        cues.append(Cue(round(start, 2), round(end, 2), text))
    return cues


# --- speech ------------------------------------------------------------------------------------

def audio_pcm(raw: bytes, *, max_seconds: float) -> np.ndarray | None:
    import av

    with _open(raw) as c:
        if not c.streams.audio:
            return None
        resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)
        chunks, total = [], 0
        for frame in c.decode(c.streams.audio[0]):
            for out in resampler.resample(frame):
                arr = out.to_ndarray().reshape(-1)
                chunks.append(arr)
                total += arr.size
            if total > max_seconds * SAMPLE_RATE:
                break
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return None
    return np.concatenate(chunks)[: int(max_seconds * SAMPLE_RATE)].astype(np.float32)


def transcribe(pcm: np.ndarray, model_name: str) -> tuple[list[Cue], str | None, float]:
    """Speech cues, detected language and its probability. Local Whisper (faster-whisper,
    int8 on CPU) with voice-activity detection, so music-only audio yields no cues."""
    from faster_whisper import WhisperModel

    with _ASR_LOCK:
        model = _asr_models.get(model_name)
        if model is None:
            model = _asr_models[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(pcm, vad_filter=True, beam_size=1, condition_on_previous_text=False)
        cues = [Cue(round(s.start, 2), round(s.end, 2), s.text.strip(), float(np.exp(s.avg_logprob)))
                for s in segments if s.text.strip()]
    return cues, info.language, float(info.language_probability)


def loudness(pcm: np.ndarray) -> float:
    """RMS level in dBFS: tells "silent" apart from "music, but nobody speaks"."""
    rms = float(np.sqrt(np.mean(np.square(pcm)))) if pcm.size else 0.0
    return round(float(20 * np.log10(max(rms, 1e-9))), 1)


# --- keyframes ----------------------------------------------------------------------------------

def keyframes(samples: list[tuple[float, Image.Image]], limit: int = MAX_KEYFRAMES) -> list[tuple[float, Image.Image]]:
    """The first frame plus one frame per scene change, thinned evenly to `limit`."""
    picked, last_hist = [], None
    for t, img in samples:
        hsv = cv2.cvtColor(np.asarray(shrink(img, 256)), cv2.COLOR_RGB2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        if last_hist is None or cv2.compareHist(last_hist, hist, cv2.HISTCMP_CORREL) < SCENE_CHANGE:
            picked.append((t, img))
            last_hist = hist
    if len(picked) <= limit:
        return picked
    step = len(picked) / limit
    return [picked[int(i * step)] for i in range(limit)]


def contact_sheet(frames_: list[tuple[float, Image.Image]], cell: int = 420) -> Image.Image:
    """Keyframes on a grid, each stamped with its time, for one vision call."""
    cols = 3 if len(frames_) > 4 else 2 if len(frames_) > 1 else 1
    rows = -(-len(frames_) // cols)
    sheet = Image.new("RGB", (cols * cell, rows * cell), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (t, img) in enumerate(frames_):
        thumb = img.copy()
        thumb.thumbnail((cell - 8, cell - 28))
        x, y = (i % cols) * cell + 4, (i // cols) * cell + 24
        sheet.paste(thumb, (x, y))
        draw.rectangle((x, y - 22, x + 90, y - 2), fill="black")
        draw.text((x + 6, y - 19), f"t={t:.1f}s", fill="white")
    return sheet


def cue_text(cues: list[Cue]) -> tuple[str, list[tuple[int, int, float, float]]]:
    """One line per cue, plus a char-offset to time map for locating findings."""
    parts, timeline, pos = [], [], 0
    for cue in sorted(cues, key=lambda c: (c.start, c.end)):
        parts.append(cue.text)
        timeline.append((pos, pos + len(cue.text), cue.start, cue.end))
        pos += len(cue.text) + 1
    return "\n".join(parts), timeline
