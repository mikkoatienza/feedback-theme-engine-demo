"""Clean-room demo: turn call transcripts into a living board of themes.

Pipeline: transcripts -> feedback snippets -> keyword vectors -> clusters (themes)
-> merge with the previous board so resolved/dismissed decisions persist.
Pure Python; swap `extract_snippets` / `label` for LLM calls in real use.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field, asdict

STOP = set("""a an the and or but to of in on for is are was were be been it its this that
we our us you your they their them i my me with at by from as so too also very please
would could should can will just not no some often never for into about""".split())

SIGNALS = ("painful", "slow", "fails", "times out", "want", "add", "confus", "unclear",
           "surprised", "never", "too long", "spam", "would be nice", "please")


@dataclass
class Snippet:
    call_id: str
    account: str
    text: str


@dataclass
class Theme:
    key: str
    label: str
    snippets: list[dict] = field(default_factory=list)
    status: str = "open"           # open | resolved | dismissed
    accounts: int = 0


def extract_snippets(transcripts: list[dict]) -> list[Snippet]:
    """Split each transcript into sentences and keep those that read like feedback."""
    out = []
    for t in transcripts:
        for s in re.split(r"(?<=[.!?])\s+", t["text"].strip()):
            if any(sig in s.lower() for sig in SIGNALS):
                out.append(Snippet(t["id"], t["account"], s))
    return out


def tokens(text: str) -> Counter:
    words = re.findall(r"[a-z]+", text.lower())
    return Counter(w for w in words if w not in STOP and len(w) > 2)


def cosine(a: Counter, b: Counter) -> float:
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def cluster(snips: list[Snippet], threshold: float = 0.25) -> list[list[Snippet]]:
    """Greedy single-pass clustering against each cluster's running centroid."""
    clusters: list[tuple[Counter, list[Snippet]]] = []
    for s in snips:
        v = tokens(s.text)
        best, score = None, 0.0
        for i, (c, _) in enumerate(clusters):
            sc = cosine(v, c)
            if sc > score:
                best, score = i, sc
        if best is not None and score >= threshold:
            clusters[best][0].update(v)
            clusters[best][1].append(s)
        else:
            clusters.append((Counter(v), [s]))
    return [m for _, m in clusters]


def label(members: list[Snippet]) -> tuple[str, str]:
    """Stable key + readable label from the most common terms."""
    c = Counter()
    for m in members:
        c.update(set(tokens(m.text)))
    top = [w for w, _ in c.most_common(2)]
    top_sorted = sorted(top)
    return "-".join(top_sorted), " / ".join(top)


def build_board(transcripts: list[dict], previous: dict | None = None) -> dict:
    """Rebuild the board. Resolved/dismissed themes keep their status;
    a resolved theme that gets *new* evidence is reopened."""
    prev = {t["key"]: t for t in (previous or {}).get("themes", [])}
    themes = []
    for members in cluster(extract_snippets(transcripts)):
        key, lab = label(members)
        th = Theme(key, lab, [asdict(m) for m in members],
                   accounts=len({m.account for m in members}))
        # Match by shared evidence first, so a theme keeps its identity
        # (and its key) even if its top terms shift as new snippets arrive.
        ids = {(m.call_id, m.text) for m in members}
        old = next((t for t in prev.values()
                    if ids & {(s["call_id"], s["text"]) for s in t["snippets"]}), None) or prev.get(key)
        if old:
            th.key, th.label = old["key"], old["label"]
            th.status = old["status"]
            seen = {(s["call_id"], s["text"]) for s in old["snippets"]}
            new = [s for s in th.snippets if (s["call_id"], s["text"]) not in seen]
            if old["status"] == "resolved" and new:
                th.status = "open"
        themes.append(th)
    themes.sort(key=lambda t: (t.status != "open", -t.accounts, t.key))
    return {"themes": [asdict(t) for t in themes]}


def set_status(board: dict, key: str, status: str) -> dict:
    if status not in ("open", "resolved", "dismissed"):
        raise ValueError(status)
    for t in board["themes"]:
        if t["key"] == key:
            t["status"] = status
            return board
    raise KeyError(key)


def validate(board: dict) -> list[str]:
    """Sanity checks run after every rebuild."""
    problems, keys = [], set()
    for t in board["themes"]:
        if t["key"] in keys:
            problems.append(f"duplicate key {t['key']}")
        keys.add(t["key"])
        if not t["snippets"]:
            problems.append(f"empty theme {t['key']}")
        if t["status"] not in ("open", "resolved", "dismissed"):
            problems.append(f"bad status {t['key']}")
    return problems
