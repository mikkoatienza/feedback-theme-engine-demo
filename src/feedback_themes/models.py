"""Core data types."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

KINDS = ("pain", "request", "confusion", "praise")
STATUSES = ("open", "resolved", "dismissed")


@dataclass
class Utterance:
    """One speaker turn."""

    speaker: str
    text: str


@dataclass
class Transcript:
    """A customer conversation."""

    id: str
    account: str = ""
    date: str = ""
    utterances: list[Utterance] = field(default_factory=list)


@dataclass
class FeedbackItem:
    """A single piece of customer feedback extracted from a transcript."""

    transcript_id: str
    account: str
    speaker: str
    text: str
    kind: str = "pain"

    @property
    def key(self) -> str:
        """Stable identity, so re-running on the same transcript does not duplicate evidence."""
        raw = f"{self.transcript_id}\x00{self.text.strip().lower()}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]


@dataclass
class Cluster:
    """A group of similar feedback items, before it is matched to a stored theme."""

    items: list[FeedbackItem]
    label: str
    terms: list[str]
