"""Transcript ingestion: plain text, WebVTT and JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from feedback_themes.models import Transcript, Utterance

_SPEAKER = re.compile(r"^\s*(?:\[[^\]]*\]\s*)?([A-Za-z][\w .'-]{0,40}):\s+(.+)$")
_VTT_TS = re.compile(r"^\d{2}:\d{2}(?::\d{2})?\.\d{3}\s+-->")
_VTT_VOICE = re.compile(r"^<v\s+([^>]+)>(.*?)(?:</v>)?$")


def parse_text(text: str, tid: str, account: str = "") -> Transcript:
    """``Speaker: words`` lines. Lines without a speaker continue the previous turn."""
    t = Transcript(tid, account)
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            hdr = re.match(r"#\s*(account|date):\s*(.+)", line.strip(), re.I)
            if hdr:
                setattr(t, hdr.group(1).lower(), hdr.group(2).strip())
            continue
        m = _SPEAKER.match(line)
        if m:
            t.utterances.append(Utterance(m.group(1).strip(), m.group(2).strip()))
        elif t.utterances:
            t.utterances[-1].text += " " + line.strip()
        else:
            t.utterances.append(Utterance("unknown", line.strip()))
    return t


def parse_vtt(text: str, tid: str, account: str = "") -> Transcript:
    """WebVTT captions with ``<v Speaker>`` voice tags or ``Speaker:`` prefixes."""
    t = Transcript(tid, account)
    for line in text.splitlines():
        s = line.strip()
        hdr = re.match(r"NOTE\s+(account|date):\s*(.+)", s, re.I)
        if hdr:
            setattr(t, hdr.group(1).lower(), hdr.group(2).strip())
            continue
        if not s or s == "WEBVTT" or _VTT_TS.match(s) or s.isdigit() or s.startswith("NOTE"):
            continue
        v = _VTT_VOICE.match(s)
        m = _SPEAKER.match(s)
        if v:
            spk, said = v.group(1).strip(), v.group(2).strip()
        elif m:
            spk, said = m.group(1).strip(), m.group(2).strip()
        else:
            spk, said = "unknown", s
        if t.utterances and t.utterances[-1].speaker == spk:
            t.utterances[-1].text += " " + said
        else:
            t.utterances.append(Utterance(spk, said))
    return t


def parse_json(data: dict[str, Any], tid: str = "") -> Transcript:
    """``{"id", "account", "date", "utterances": [{"speaker", "text"}]}`` or ``{"text": ...}``."""
    tid = str(data.get("id") or tid)
    if "utterances" in data:
        utt = [
            Utterance(str(u.get("speaker", "unknown")), str(u["text"])) for u in data["utterances"]
        ]
        return Transcript(tid, str(data.get("account", "")), str(data.get("date", "")), utt)
    t = parse_text(str(data.get("text", "")), tid, str(data.get("account", "")))
    t.date = str(data.get("date", ""))
    return t


def load_path(path: Path) -> list[Transcript]:
    """Load one file or every supported file in a directory (sorted, non-recursive)."""
    if path.is_dir():
        out: list[Transcript] = []
        for p in sorted(path.iterdir()):
            if p.suffix in (".txt", ".vtt", ".json"):
                out.extend(load_path(p))
        return out
    text = path.read_text()
    if path.suffix == ".vtt":
        return [parse_vtt(text, path.stem)]
    if path.suffix == ".json":
        data = json.loads(text)
        if isinstance(data, list):
            return [parse_json(d, f"{path.stem}-{i}") for i, d in enumerate(data)]
        return [parse_json(data, path.stem)]
    return [parse_text(text, path.stem)]
