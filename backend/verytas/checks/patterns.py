"""Schemas for rule `pattern` config, one per matcher type.

Validated when a rule is created or edited, so a typo in an admin's rule is a
422 at save time rather than a crashed worker on every later review.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

HexColour = Annotated[str, Field(pattern=r"^#?(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")]
Term = Annotated[str, Field(min_length=1, max_length=200)]


class _Pattern(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str


class BannedTerms(_Pattern):
    terms: list[Term] = Field(min_length=1, max_length=500)


class PreferredTerms(_Pattern):
    map: dict[Term, Term] = Field(min_length=1, max_length=500)


class Casing(_Pattern):
    terms: list[Term] = Field(min_length=1, max_length=500)


class Palette(_Pattern):
    colors: list[HexColour] = Field(min_length=1, max_length=32)
    max_delta_e: float = Field(default=12, gt=0, le=100)
    min_share: float = Field(default=0.1, ge=0, le=1)
    allow_neutrals: bool = True


class Readability(_Pattern):
    max_grade: float = Field(default=10, gt=0, le=30)
    min_words: int = Field(default=25, ge=1, le=1000)


class LinkText(_Pattern):
    banned: list[Term] = Field(min_length=1)


class HashtagCase(_Pattern):
    min_length: int = Field(default=10, ge=3, le=100)


class AllCaps(_Pattern):
    max_run: int = Field(default=2, ge=1, le=50)


class AltText(_Pattern):
    min_length: int = Field(default=8, ge=1, le=200)


class Contrast(_Pattern):
    min_ratio: float = Field(default=4.5, ge=1, le=21)
    min_ratio_large: float = Field(default=3.0, ge=1, le=21)


class NoConfig(_Pattern):
    pass


class VoiceScore(_Pattern):
    levels: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(min_length=2, max_length=10)
    min_level: float | None = Field(default=None, ge=0, le=9)


DETERMINISTIC: dict[str, type[_Pattern]] = {
    "banned_terms": BannedTerms, "preferred_terms": PreferredTerms, "casing": Casing, "palette": Palette,
    "readability": Readability, "link_text": LinkText, "hashtag_case": HashtagCase, "all_caps": AllCaps,
    "alt_text": AltText, "contrast": Contrast, "confidential_terms": NoConfig, "claims": NoConfig,
}
SEMANTIC: dict[str, type[_Pattern]] = {"voice_score": VoiceScore}


def validate_pattern(kind: str, pattern: dict[str, Any]) -> dict[str, Any]:
    """Returns the normalised pattern or raises ValueError with a readable message."""
    if kind == "semantic" and not pattern:
        return {}
    registry = DETERMINISTIC if kind == "deterministic" else SEMANTIC
    ptype = pattern.get("type")
    model = registry.get(ptype or "")
    if model is None:
        allowed = ", ".join(sorted(registry))
        raise ValueError(f"unknown pattern type {ptype!r} for a {kind} rule; use one of: {allowed}")
    try:
        return model.model_validate(pattern).model_dump()
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "pattern"
        raise ValueError(f"pattern.{where}: {first['msg']}") from None
