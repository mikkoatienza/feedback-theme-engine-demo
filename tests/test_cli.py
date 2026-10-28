import json
from pathlib import Path

import pytest

from feedback_themes.cli import main

EX = Path(__file__).resolve().parents[1] / "examples"


def test_cli_lifecycle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = ["--db", str(tmp_path / "t.db")]
    cfg = ["-c", str(EX / "themes.yaml")]
    assert main([*db, "rebuild", str(EX / "transcripts/week1"), *cfg]) == 0
    assert "run 1:" in capsys.readouterr().out
    assert main([*db, "list"]) == 0
    key = capsys.readouterr().out.split()[-1]
    assert main([*db, "resolve", key, "-m", "fixed"]) == 0
    assert main([*db, "show", key]) == 0
    shown = json.loads(capsys.readouterr().out.split("\n", 1)[1])
    assert shown["theme"]["status"] == "resolved" and shown["history"][0]["note"] == "fixed"
    assert main([*db, "reopen", key]) == 0
    assert main([*db, "dismiss", "missing"]) == 1
    assert main([*db, "show", "missing"]) == 1
    out = tmp_path / "b.html"
    assert main([*db, "export", "-f", "html", "-o", str(out)]) == 0 and out.exists()
    assert main([*db, "export", "-f", "json"]) == 0
    assert main([*db, "export"]) == 0
    assert main([*db, "runs"]) == 0
    assert main([*db, "validate"]) == 0


def test_init(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    assert main(["init", str(p)]) == 0 and main(["init", str(p)]) == 1
