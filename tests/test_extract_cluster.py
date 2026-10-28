import pytest

from feedback_themes.cluster import agglomerate, cluster_items
from feedback_themes.embed import TfidfEmbedder, cosine, get_embedder, tokenize
from feedback_themes.extract import LLMExtractor, RuleExtractor
from feedback_themes.llm import OfflineLLM
from feedback_themes.models import FeedbackItem, Transcript, Utterance

T = Transcript(
    "t1",
    "Acme",
    utterances=[
        Utterance("Host", "Is anything slow or broken?"),
        Utterance("Cy", "Export is slow. Nice weather today. We would love dark mode."),
        Utterance("Cy", "I love the new charts."),
    ],
)


def test_rules_skip_internal_and_small_talk() -> None:
    items = RuleExtractor(internal_speakers=["host"]).extract(T)
    assert [(i.text, i.kind) for i in items] == [
        ("Export is slow.", "pain"),
        ("We would love dark mode.", "request"),
    ]


def test_praise_opt_in() -> None:
    items = RuleExtractor(internal_speakers=["Host"], include_praise=True).extract(T)
    assert ("I love the new charts.", "praise") in [(i.text, i.kind) for i in items]


def test_llm_extractor_parses_json_and_falls_back() -> None:
    good = '[{"speaker": "Cy", "text": "Export is slow", "kind": "pain"}, {"text": ""}]'
    items = LLMExtractor(OfflineLLM(lambda p: good)).extract(T)
    assert [i.text for i in items] == ["Export is slow"]
    fb = LLMExtractor(OfflineLLM(lambda p: "sorry"), internal=["Host"]).extract(T)
    assert len(fb) == 2


def test_item_key_stable_and_case_insensitive() -> None:
    a = FeedbackItem("t", "A", "s", "Export is slow")
    b = FeedbackItem("t", "B", "x", "export is slow ")
    assert a.key == b.key


def test_tokenize_and_tfidf() -> None:
    assert tokenize("The reports are failing, really!") == ["report", "failing"]
    v = TfidfEmbedder().embed(["csv export slow", "csv export fails", "dark mode"])
    assert cosine(v[0], v[1]) > cosine(v[0], v[2]) == 0.0
    with pytest.raises(ValueError):
        get_embedder("nope")


def test_agglomerate_threshold() -> None:
    vs = [[1.0, 0.0], [0.99, 0.141], [0.0, 1.0]]
    assert agglomerate(vs, 0.9) == [[0, 1], [2]]
    assert agglomerate(vs, -1.0) == [[0, 1, 2]]


def test_cluster_items_groups_by_topic() -> None:
    items = [
        FeedbackItem("1", "A", "s", "CSV export times out on large reports"),
        FeedbackItem("2", "B", "s", "Large CSV export fails"),
        FeedbackItem("3", "C", "s", "Please add dark mode"),
    ]
    cl = cluster_items(items, TfidfEmbedder(), threshold=0.2)
    assert len(cl) == 2
    assert {i.transcript_id for i in cl[0].items} == {"1", "2"}
    assert "csv" in cl[0].terms
    assert cluster_items([], TfidfEmbedder()) == []
    assert len(cluster_items(items, TfidfEmbedder(), 0.2, min_size=2)) == 1
