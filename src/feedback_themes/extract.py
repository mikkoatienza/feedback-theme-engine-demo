"""Feedback extraction: rule-based by default, LLM optional."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from feedback_themes.llm import LLM
from feedback_themes.models import KINDS, FeedbackItem, Transcript

DEFAULT_SIGNALS: dict[str, list[str]] = {
    "pain": [
        "painful",
        "slow",
        "fails",
        "failed",
        "broken",
        "times out",
        "crash",
        "bug",
        "annoying",
        "frustrat",
        "never arrives",
        "doesn't work",
        "does not work",
        "lost",
    ],
    "request": [
        "wish",
        "would love",
        "would be nice",
        "please add",
        "we want",
        "we need",
        "can you add",
        "feature request",
        "it would help",
    ],
    "confusion": ["confus", "unclear", "not sure how", "surprised", "didn't know", "hard to find"],
    "praise": ["love", "great", "works well", "really like", "fantastic"],
}
_SENT = re.compile(r"(?<=[.!?])\s+")


class Extractor(Protocol):
    """Finds feedback items in transcripts."""

    def extract(self, transcript: Transcript) -> list[FeedbackItem]:
        """Return feedback items for one transcript."""
        ...


class RuleExtractor:
    """Keyword signals per kind, applied sentence by sentence to customer turns.

    ``internal_speakers`` (case-insensitive) are skipped so your own team's
    words never become customer feedback. ``include_praise`` is off by default.
    """

    def __init__(
        self,
        signals: dict[str, list[str]] | None = None,
        internal_speakers: list[str] | None = None,
        include_praise: bool = False,
    ) -> None:
        self.signals = signals or DEFAULT_SIGNALS
        self.internal = {s.lower() for s in internal_speakers or []}
        self.include_praise = include_praise

    def classify(self, sentence: str) -> str | None:
        """Return the first matching kind, checking pain/request/confusion before praise."""
        low = sentence.lower()
        for kind in ("pain", "request", "confusion", "praise"):
            if kind == "praise" and not self.include_praise:
                continue
            if any(sig in low for sig in self.signals.get(kind, [])):
                return kind
        return None

    def extract(self, transcript: Transcript) -> list[FeedbackItem]:
        out = []
        for u in transcript.utterances:
            if u.speaker.lower() in self.internal:
                continue
            for s in _SENT.split(u.text.strip()):
                kind = self.classify(s)
                if kind and len(s.split()) >= 3:
                    out.append(FeedbackItem(transcript.id, transcript.account, u.speaker, s, kind))
        return out


class LLMExtractor:
    """Ask a model for feedback items as JSON; fall back to rules on bad output."""

    PROMPT = (
        "Extract customer product feedback from this transcript. Ignore small talk and "
        "anything said by these internal speakers: {internal}. Answer with a JSON array of "
        'objects {{"speaker": str, "text": str, "kind": one of {kinds}}}. Quote the customer '
        "closely; do not invent feedback.\n\n{body}"
    )

    def __init__(
        self, llm: LLM, fallback: RuleExtractor | None = None, internal: list[str] | None = None
    ):
        self.llm = llm
        self.internal = internal or []
        self.fallback = fallback or RuleExtractor(internal_speakers=self.internal)

    def extract(self, transcript: Transcript) -> list[FeedbackItem]:
        body = "\n".join(f"{u.speaker}: {u.text}" for u in transcript.utterances)
        prompt = self.PROMPT.format(internal=self.internal or "none", kinds=list(KINDS), body=body)
        raw = self.llm.complete(prompt, max_tokens=2048).text
        try:
            start, end = raw.index("["), raw.rindex("]") + 1
            data: list[dict[str, Any]] = json.loads(raw[start:end])
            return [
                FeedbackItem(
                    transcript.id,
                    transcript.account,
                    str(d.get("speaker", "unknown")),
                    str(d["text"]).strip(),
                    str(d["kind"]) if d.get("kind") in KINDS else "pain",
                )
                for d in data
                if str(d.get("text", "")).strip()
            ]
        except (ValueError, KeyError, TypeError):
            return self.fallback.extract(transcript)
