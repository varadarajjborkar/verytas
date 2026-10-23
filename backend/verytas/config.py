from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from VERYTAS_* env vars or a local .env file."""

    model_config = SettingsConfigDict(env_prefix="VERYTAS_", env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./verytas.db"

    # "live" talks to the hosted models. "offline" swaps in deterministic local
    # providers so the whole pipeline runs in tests and demos without keys.
    llm_mode: Literal["live", "offline"] = "live"

    # Which hosted LLM does the text work. Ollama Cloud is the default (free tier);
    # Claude is kept as a drop-in alternative behind the same interface.
    llm_backend: Literal["ollama", "claude"] = "ollama"

    ollama_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("OLLAMA_API_KEY", "VERYTAS_OLLAMA_API_KEY")
    )
    # A second account's key on the same plan, used when the first is refused or out of quota.
    ollama_api_key_fallback: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OLLAMA_API_KEY_FALLBACK", "VERYTAS_OLLAMA_API_KEY_FALLBACK"),
    )
    ollama_base_url: str = "https://ollama.com"
    ollama_model: str = "gpt-oss:120b"
    ollama_fast_model: str = "gpt-oss:20b"

    # The Anthropic SDK reads ANTHROPIC_API_KEY itself; only model routing lives here.
    claude_model: str = "claude-opus-5-5"
    claude_fast_model: str = "claude-haiku-5-5"
    claude_fallbacks: bool = True

    typesafe_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("TYPESAFE_API_KEY", "VERYTAS_TYPESAFE_API_KEY")
    )
    jev_base_url: str = "https://api.typesafe.ai"
    # Pinned on purpose: jev-latest can move scores under a tuned threshold.
    jev_model: str = "jev-1.13.0"

    # Without a TypeSafe key, the semantic judge runs on Ollama Cloud instead.
    # The fast model is plenty for yes/no and level questions, and resamples
    # cap how many extra calls a borderline answer may cost.
    ollama_judge_model: str = "gpt-oss:20b"
    # Resamples run in parallel inside one provider slot, so keep the cap small.
    judge_resamples: int = Field(default=2, ge=0, le=4)
    # Second look (prism/second_look.py): must-rule questions also go to the larger model, whose answer
    # decides; at most second_look_max calls (one per paragraph) per review. 0 turns it off.
    second_look_model: str = "gpt-oss:120b"
    second_look_max: int = Field(default=12, ge=0, le=60)

    # Image understanding. gemma4:31b is the free-plan vision model on Ollama
    # Cloud (verified 2026-10-20: exact transcription of a test image in ~1 s).
    ollama_vision_model: str = "gemma4:31b"
    # Below this local OCR confidence, the image is also transcribed by the
    # vision model (after pixel redaction).
    ocr_min_confidence: float = Field(default=0.8, ge=0, le=1)
    # Agent tree limits per review: how deep delegation may go, and how many
    # agents one submission may spawn in total.
    agent_max_depth: int = Field(default=8, ge=2, le=12)
    agent_max_nodes: int = Field(default=200, ge=10, le=1000)
    # Local speech-to-text for video (faster-whisper). On evals/speech "small" halves English word error
    # against "base" (17% to 10%), hears every English phone number and writes Hindi in Devanagari rather
    # than Urdu script, at about 2.6 times the compute. Audio longer than asr_long_seconds uses
    # asr_long_model so a long video can't hold a review for many minutes on a small server.
    asr_model: str = "small"
    asr_long_model: str = "base"
    asr_long_seconds: int = Field(default=180, ge=0)
    video_max_seconds: int = Field(default=15 * 60, ge=10, le=3600)

    keys_dir: Path = Path(".keys")

    environment: str = "development"
    cors_origins: list[str] = ["http://localhost:3000"]
    # Error monitoring is opt-in; nothing is sent unless a DSN is configured.
    sentry_dsn: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("SENTRY_DSN", "VERYTAS_SENTRY_DSN")
    )
    sentry_traces_sample_rate: float = 0.0

    # Governor limits (architecture section 6.3).
    max_concurrent_tasks: int = 8
    # Reviews that may run at once. A review holds its attachments in memory from the start, so this is
    # what bounds memory under a burst; the rest wait their turn in order.
    max_concurrent_reviews: int = 4
    task_timeout_s: float = 60.0
    # One blocking media step (decode a PDF, OCR an image, transcribe audio).
    # Past it the part is reported as not checked and the review moves on.
    media_timeout_s: float = Field(180.0, gt=0)
    review_token_budget: int = 400_000
    # Upload storage (media/storage.py): what one person and one workspace may hold, and how long an
    # upload no version uses is kept before the hourly sweep deletes it.
    # Model files for the visual checks (faces, segmentation), fetched on first use and pinned by hash
    # (media/model_store.py).
    vision_models_dir: Path = Path(".models")
    # Faces in images and video, identified against approved people (prism/people_agent.py).
    faces_enabled: bool = True
    # The vision worker (verytas/vision) that finds redrawn mascots and compares them with the artwork.
    # Unset, characters are checked by pixel match and the vision model only, and the review says so.
    vision_worker_url: str | None = None
    vision_worker_token: SecretStr | None = None
    vision_worker_timeout_s: float = Field(150.0, gt=0)
    # The EC2 instance the worker runs on, when it stops itself when idle: the API starts it on demand
    # (vision/wake.py) with its own instance role. Unset for a worker that is always on.
    vision_worker_instance_id: str | None = None
    # How long a review waits for a stopped worker to boot and load its models (about two minutes).
    vision_wake_timeout_s: float = Field(240.0, gt=0)
    upload_quota_user_mb: int = Field(default=1024, ge=1)
    upload_quota_workspace_mb: int = Field(default=10 * 1024, ge=1)
    orphan_upload_ttl_h: float = Field(default=24.0, gt=0)

    # Self-service accounts (api/accounts.py): anyone may create an empty workspace as its brand admin,
    # or join one as a creator with its join code. Off by default; the public demo turns it on. Bounded
    # several ways, because every new workspace can spend model calls: workspaces in all, sign-ups per
    # hour, and model-spending actions (reviews, disputes, AI edits, assistant turns) per self-serve
    # workspace per day and across all of them.
    self_signup: bool = False
    self_signup_max_workspaces: int = Field(default=200, ge=0)
    self_signup_per_hour: int = Field(default=30, ge=0)
    self_serve_actions_per_day: int = Field(default=60, ge=0)
    self_serve_actions_per_day_total: int = Field(default=600, ge=0)

    # Judge thresholds (architecture section 8.1). Tuned later by calibration.
    semantic_flag_threshold: float = 0.6
    blocker_confidence: float = 0.85


@lru_cache
def get_settings() -> Settings:
    return Settings()
