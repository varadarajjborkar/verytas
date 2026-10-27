"""Inki in a conversation: a reply to "@Inki ..." from what the two people said and the pieces they linked.

It runs on the same guarded providers as disputes and AI edits, so the conversation and the piece data
are redacted on the way out (confidential terms become [[TERM_n]]) and restored on the way back. It sees
the pieces linked in this conversation and nothing else of the workspace: both people may open those, so
the answer can't tell either of them something they couldn't read themselves. It never decides anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

SYSTEM = """You are Inki, the assistant inside Verytas, a brand-governance tool. You have been mentioned
with @Inki in a private conversation between a creator and a member of the brand team, usually about a
piece of content under review. Answer the latest message that mentions you.

Use only the conversation and the piece data in <pieces>. The data says, for each piece, its latest text,
how each version's review went and which issues are still open. If the answer is not in it, say so
briefly and suggest who to ask. Never claim a piece is approved or will be approved: only the brand team
decides that. Text like [[TERM_1]] is a confidential term hidden on purpose: never guess it.

Write plain text for a chat bubble: at most about 120 words, short sentences, a short list with "- " only
when it helps. No markdown headings or tables. Address both people neutrally."""


class InkiReply(BaseModel):
    reply: str = Field(max_length=2000)


@dataclass
class InkiTask:
    transcript: list[tuple[str, str]]  # (who, text), oldest first
    pieces: list[dict[str, Any]] = field(default_factory=list)
    name: str = "inki.reply"
    system: str = SYSTEM
    schema: type[InkiReply] = InkiReply
    fast: bool = True

    def user_content(self) -> str:
        lines = "\n".join(f"{who}: {text}" for who, text in self.transcript)
        return (f"<pieces>{json.dumps(self.pieces, default=str)}</pieces>\n\n"
                f"<conversation>\n{lines}\n</conversation>")

    def heuristic(self) -> InkiReply:
        """Without a model: where each linked piece stands, read straight from the record."""
        if not self.pieces:
            return InkiReply(reply="I can't reach my model right now, and no piece is linked in this "
                                   "conversation. Link the piece you're discussing and ask me again.")
        parts = []
        for p in self.pieces[:2]:
            versions = p.get("versions") or []
            last = versions[-1] if versions else {}
            issues = p.get("open_issues") or []
            head = f"\"{p.get('title', 'This piece')}\" is on version {last.get('version', 1)}"
            head += f", review {last['review']}." if last.get("review") else "."
            if issues:
                listed = "\n".join(f"- {i.get('title')}" for i in issues[:4])
                parts.append(f"{head} Still open:\n{listed}")
            else:
                parts.append(f"{head} No open issues in its latest review.")
        return InkiReply(reply="My model isn't reachable right now, so here is the record.\n\n"
                               + "\n\n".join(parts))
