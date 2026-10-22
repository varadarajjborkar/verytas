"use client";

import { useEffect, useRef, useState } from "react";
import { upload } from "@/lib/review-client";
import { CloseIcon } from "../Icons";

export const BRIEF_MIN = 20;
const MAX_SECONDS = 180;

export type BriefAudio = { id: string; seconds: number; url: string };

/**
 * "What's in it?": the creator's own account of the images or video: characters, people, products and
 * roughly when they appear. Typed, or said in a voice note recorded right here. The review uses it to
 * know what to look for, and checks it against what it finds; it never clears a rule on its own.
 * Required with a video (the API refuses a video without one), optional for images.
 */
export function BriefBox({ text, audio, required, onText, onAudio }: {
  text: string;
  audio: BriefAudio | null;
  required: boolean;
  onText: (v: string) => void;
  onAudio: (a: BriefAudio | null) => void;
}) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const started = useRef(0);

  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
    recorder.current?.stream.getTracks().forEach((t) => t.stop());
  }, []);

  async function start() {
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("The browser didn't allow the microphone. Type the brief instead, or allow it and try again.");
      return;
    }
    // Chrome and Firefox record WebM, Safari MP4; the API reads both.
    const mimeType = ["audio/webm", "audio/mp4"].find((t) => MediaRecorder.isTypeSupported(t));
    const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    rec.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      const length = Math.round((Date.now() - started.current) / 1000);
      const type = rec.mimeType || "audio/webm";
      const file = new File(chunks, `brief.${type.includes("mp4") ? "m4a" : "webm"}`, { type });
      setBusy(true);
      try {
        const media = await upload(file);
        onAudio({ id: media.id, seconds: length, url: URL.createObjectURL(file) });
      } catch (err) {
        setError(`Couldn't upload the voice note: ${(err as Error).message}`);
      } finally {
        setBusy(false);
      }
    };
    recorder.current = rec;
    started.current = Date.now();
    rec.start();
    setRecording(true);
    setSeconds(0);
    timer.current = setInterval(() => {
      const s = Math.round((Date.now() - started.current) / 1000);
      setSeconds(s);
      if (s >= MAX_SECONDS) stop();
    }, 500);
  }

  function stop() {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setRecording(false);
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  const short = required && !audio && text.trim().length < BRIEF_MIN;
  const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-line p-3">
      <div>
        <p className="text-sm font-medium">
          What&apos;s in it? {required ? <span className="text-xs font-normal text-[var(--vt-warning)]">required with video</span>
            : <span className="text-xs font-normal text-subtle">optional</span>}
        </p>
        <p className="mt-0.5 text-xs leading-5 text-subtle">
          In your own words: the characters, people and products in the images or video, and roughly when they
          appear. The review looks for exactly these, and checks what it finds against them.
        </p>
      </div>
      <textarea className="vt-input min-h-20" value={text} maxLength={4000} aria-label="Brief"
        placeholder="e.g. Kit the mascot waves at the start; Riya Sen talks about the festive offer from 0:05 to 0:20; captions are burned in"
        onChange={(e) => onText(e.target.value)} />
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {audio ? (
          <span className="flex items-center gap-2 rounded-lg bg-sunken px-2 py-1">
            <audio src={audio.url} controls className="h-8" />
            <span className="text-muted">Voice note · {clock(audio.seconds)}</span>
            <button type="button" onClick={() => onAudio(null)} aria-label="Remove the voice note"
              className="grid h-6 w-6 place-items-center rounded text-muted hover:bg-raised hover:text-ink"><CloseIcon size={12} /></button>
          </span>
        ) : recording ? (
          <button type="button" onClick={stop} className="vt-btn vt-btn-quiet h-8 text-xs">
            <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-[var(--vt-blocker)]" />
            Stop recording · {clock(seconds)}
          </button>
        ) : (
          <button type="button" onClick={start} disabled={busy} className="vt-btn vt-btn-quiet h-8 text-xs">
            {busy ? "Uploading the voice note…" : "Record a voice note instead"}
          </button>
        )}
        {short && (
          <span className="text-[var(--vt-warning)]">
            {text.trim().length ? `${BRIEF_MIN - text.trim().length} more characters, or a voice note` : "Write a line or record a voice note"}
          </span>
        )}
      </div>
      {error && <p role="alert" className="text-xs text-[var(--vt-blocker)]">{error}</p>}
    </div>
  );
}
