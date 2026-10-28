from pathlib import Path

import pytest

from feedback_themes.config import EngineConfig
from feedback_themes.cost import CostTracker, Prices
from feedback_themes.engine import Engine
from feedback_themes.export import to_html, to_markdown
from feedback_themes.llm import OfflineLLM
from feedback_themes.models import Transcript
from feedback_themes.store import Store
from feedback_themes.validate import validate


def themes_with(engine: Engine, term: str) -> list[str]:
    return [t.key for t in engine.store.themes() if term in t.terms]


def test_first_build(engine: Engine, week1: list[Transcript]) -> None:
    s = engine.rebuild(week1)
    assert s.items > 0 and s.themes == s.new_themes > 2
    assert s.problems == []
    export = engine.store.theme(themes_with(engine, "csv")[0])
    assert export.accounts >= 3


def test_rebuild_is_idempotent(engine: Engine, week1: list[Transcript]) -> None:
    engine.rebuild(week1)
    before = [(t.key, t.items) for t in engine.store.themes()]
    s = engine.rebuild(week1)
    assert s.new_items == 0 and s.new_themes == 0
    assert [(t.key, t.items) for t in engine.store.themes()] == before


def test_resolved_reopens_on_new_evidence(
    engine: Engine, week1: list[Transcript], week2: list[Transcript]
) -> None:
    engine.rebuild(week1)
    key = themes_with(engine, "csv")[0]
    engine.store.set_status(key, "resolved", "shipped fix")
    assert engine.rebuild(week1).reopened == []  # same evidence: stays resolved
    assert engine.store.theme(key).status == "resolved"
    s = engine.rebuild(week1 + week2)
    assert key in s.reopened
    hist = engine.store.history(key)
    assert [h["to_status"] for h in hist] == ["resolved", "open"]
    assert hist[-1]["actor"] == "engine"


def test_dismissed_stays_dismissed(
    engine: Engine, week1: list[Transcript], week2: list[Transcript]
) -> None:
    engine.rebuild(week1)
    key = themes_with(engine, "dark")[0]
    engine.store.set_status(key, "dismissed", "not on roadmap")
    engine.rebuild(week1 + week2)
    t = engine.store.theme(key)
    assert t.status == "dismissed" and t.accounts == 3


def test_status_errors() -> None:
    st = Store()
    with pytest.raises(ValueError):
        st.set_status("x", "done")
    with pytest.raises(KeyError):
        st.set_status("x", "open")
    with pytest.raises(KeyError):
        st.theme("x")


def test_llm_extractor_with_cost_tracking(week1: list[Transcript]) -> None:
    reply = '[{"speaker": "C", "text": "Exports to CSV keep failing", "kind": "pain"}]'
    tracker = CostTracker(OfflineLLM(lambda p: reply), Prices(1.0, 2.0))
    cfg = EngineConfig(extractor="llm")
    from feedback_themes.embed import TfidfEmbedder
    from feedback_themes.extract import LLMExtractor

    eng = Engine(Store(), LLMExtractor(tracker), TfidfEmbedder(), cfg, tracker)
    s = eng.rebuild(week1)
    assert s.llm_calls == 4 and s.input_tokens > 0
    assert s.cost_usd == pytest.approx((s.input_tokens * 1 + s.output_tokens * 2) / 1e6)
    run = eng.store.runs()[0]
    assert run["llm_calls"] == 4 and run["finished_at"]


def test_from_config_llm_offline() -> None:
    eng = Engine.from_config(Store(), EngineConfig(extractor="llm", llm_provider="offline"))
    assert eng.tracker is not None


def test_validation_flags_problems() -> None:
    st = Store()
    st.create_theme("a", "same", [])
    tid = st.create_theme("b", "same", [])
    from feedback_themes.models import FeedbackItem

    st.add_items(tid, [FeedbackItem("t", "A", "s", f"item {i}") for i in range(12)], 1)
    p = validate(st)
    assert any("no evidence" in x for x in p)
    assert any("share label" in x for x in p)
    assert any("holds 12/12" in x for x in p)


def test_create_theme_key_collision() -> None:
    st = Store()
    st.create_theme("k", "l", [])
    st.create_theme("k", "l2", [])
    assert sorted(t.key for t in st.themes()) == ["k", "k-2"]


def test_exports(engine: Engine, week1: list[Transcript]) -> None:
    engine.rebuild(week1)
    engine.store.set_status(engine.store.themes()[-1].key, "dismissed")
    md = to_markdown(engine.store)
    assert md.startswith("# Feedback theme board") and "Dismissed" in md and "> " in md
    h = to_html(engine.store)
    assert h.startswith("<!doctype html>") and "<script" not in h


def test_config(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text("bogus: 1")
    with pytest.raises(ValueError):
        EngineConfig.load(p)
    assert EngineConfig.load(None).threshold == 0.3
