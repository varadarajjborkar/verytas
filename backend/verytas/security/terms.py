"""Matching confidential terms the way people actually write them.

"Project Lumen" also appears as "Project-Lumen", "project_lumen", "ProjectLumen",
"Project  Lumen", a line-wrapped "Project\\nLumen", or "Project Lumens". Both the
leak check and the egress redactor need to catch those.

Two strictness levels:
  bounded : not glued to other letters or digits on either side, so "Zebra" does
            not fire inside "Zebrafish". Used for CONF-LEAK findings, where a false
            positive becomes a blocker.
  loose   : plain substring. Used for egress redaction, where over-redacting only
            costs the model a little context and under-redacting leaks a secret.
"""

from __future__ import annotations

import re

_SPLIT = re.compile(r"[\s_\-]+")
_SEP = r"[\s_\-]*"


def term_pattern(term: str, *, loose: bool = False) -> re.Pattern[str]:
    parts = [re.escape(p) for p in _SPLIT.split(term.strip()) if p]
    if not parts:
        raise ValueError("empty confidential term")
    core = _SEP.join(parts) + r"(?:e?s)?"  # tolerate simple plurals
    if loose:
        return re.compile(core, re.IGNORECASE)
    return re.compile(rf"(?<![A-Za-z0-9]){core}(?![A-Za-z0-9])", re.IGNORECASE)
