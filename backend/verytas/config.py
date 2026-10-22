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

    keys_dir: Path = Path(".keys")

    # Governor limits (architecture section 6.3).
    max_concurrent_tasks: int = 8
    task_timeout_s: float = 60.0
    review_token_budget: int = 400_000

    # Judge thresholds (architecture section 8.1). Tuned later by calibration.
    semantic_flag_threshold: float = 0.6
    blocker_confidence: float = 0.85


@lru_cache
def get_settings() -> Settings:
    return Settings()
