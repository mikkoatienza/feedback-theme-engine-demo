import json
from pathlib import Path

from feedback_themes.ingest import load_path, parse_json, parse_text, parse_vtt
from feedback_themes.models import Transcript


def test_text_headers_and_continuation() -> None:
    t = parse_text("# account: Acme\n# date: 2026-01-01\nA: one\ncontinued\nB: two", "x")
    assert t.account == "Acme" and t.date == "2026-01-01"
    assert [(u.speaker, u.text) for u in t.utterances] == [("A", "one continued"), ("B", "two")]


def test_text_without_speaker() -> None:
    assert parse_text("hello there", "x").utterances[0].speaker == "unknown"


def test_vtt_voice_tags_merge_same_speaker() -> None:
    vtt = (
        "WEBVTT\n\n1\n00:00.000 --> 00:01.000\n<v Ann>Hi</v>\n\n"
        "2\n00:01.000 --> 00:02.000\n<v Ann>there</v>\nBob: yo"
    )
    t = parse_vtt(vtt, "v")
    assert [(u.speaker, u.text) for u in t.utterances] == [("Ann", "Hi there"), ("Bob", "yo")]


def test_json_utterances_and_text() -> None:
    a = parse_json({"id": "a", "utterances": [{"speaker": "S", "text": "x"}]})
    b = parse_json({"text": "S: y", "date": "d"}, "b")
    assert a.utterances[0].text == "x" and b.id == "b" and b.date == "d"


def test_load_directory(week1: list[Transcript], tmp_path: Path) -> None:
    assert [t.id for t in week1] == ["call-001", "call-002", "call-003", "call-004"]
    assert week1[1].account == "Juniper Labs (synthetic)"
    (tmp_path / "one.json").write_text(json.dumps({"text": "A: b"}))
    (tmp_path / "skip.md").write_text("ignored")
    assert [t.id for t in load_path(tmp_path)] == ["one"]
