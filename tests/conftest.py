from __future__ import annotations

from pathlib import Path

import pytest

from feedback_themes.config import EngineConfig
from feedback_themes.engine import Engine
from feedback_themes.ingest import load_path
from feedback_themes.models import Transcript
from feedback_themes.store import Store

EX = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def week1() -> list[Transcript]:
    return load_path(EX / "transcripts/week1")


@pytest.fixture
def week2() -> list[Transcript]:
    return load_path(EX / "transcripts/week2")


@pytest.fixture
def engine() -> Engine:
    return Engine.from_config(Store(), EngineConfig.load(EX / "themes.yaml"))
