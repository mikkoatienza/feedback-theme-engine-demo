"""Rebuild: transcripts -> items -> clusters -> merged into the persistent theme store."""

from __future__ import annotations

from dataclasses import dataclass, field

from feedback_themes.cluster import cluster_items
from feedback_themes.config import EngineConfig
from feedback_themes.cost import CostTracker, Prices
from feedback_themes.embed import Embedder, get_embedder
from feedback_themes.extract import Extractor, LLMExtractor, RuleExtractor
from feedback_themes.llm import get_llm
from feedback_themes.models import Cluster, FeedbackItem, Transcript
from feedback_themes.store import Store
from feedback_themes.validate import validate


@dataclass
class RunSummary:
    """What a rebuild did."""

    run_id: int
    transcripts: int = 0
    items: int = 0
    new_items: int = 0
    themes: int = 0
    new_themes: int = 0
    reopened: list[str] = field(default_factory=list)
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    problems: list[str] = field(default_factory=list)


class Engine:
    """Composable rebuild pipeline. Build from config or pass your own parts."""

    def __init__(
        self,
        store: Store,
        extractor: Extractor,
        embedder: Embedder,
        config: EngineConfig | None = None,
        tracker: CostTracker | None = None,
    ) -> None:
        self.store, self.extractor, self.embedder = store, extractor, embedder
        self.cfg = config or EngineConfig()
        self.tracker = tracker

    @classmethod
    def from_config(cls, store: Store, cfg: EngineConfig) -> Engine:
        """Wire providers from :class:`EngineConfig`."""
        tracker = None
        extractor: Extractor
        rules = RuleExtractor(cfg.signals, cfg.internal_speakers, cfg.include_praise)
        if cfg.extractor == "llm":
            tracker = CostTracker(get_llm(cfg.llm_provider), Prices(**cfg.prices))
            extractor = LLMExtractor(tracker, rules, cfg.internal_speakers)
        else:
            extractor = rules
        return cls(store, extractor, get_embedder(cfg.embeddings), cfg, tracker)

    def _match(self, c: Cluster) -> int | None:
        """Find the stored theme for a cluster: shared evidence first, then term overlap."""
        owners = self.store.theme_for_items([i.key for i in c.items])
        if owners:
            return max(owners, key=lambda k: owners[k])
        best, best_id = self.cfg.match_threshold, None
        for t in self.store.themes():
            a, b = set(t.terms), set(c.terms)
            if a and b:
                j = len(a & b) / len(a | b)
                if j >= best:
                    best, best_id = j, t.id
        return best_id

    def rebuild(self, transcripts: list[Transcript]) -> RunSummary:
        """Idempotent rebuild. Lifecycle rules:

        * ``dismissed`` themes stay dismissed; new evidence is attached quietly.
        * ``resolved`` themes reopen when genuinely new evidence arrives.
        * Items seen before keep their identity, so re-runs do not duplicate.
        """
        run_id = self.store.start_run()
        s = RunSummary(run_id, transcripts=len(transcripts))
        items: list[FeedbackItem] = []
        seen: set[str] = set()
        for t in transcripts:
            for it in self.extractor.extract(t):
                if it.key not in seen:
                    seen.add(it.key)
                    items.append(it)
        s.items = len(items)
        clusters = cluster_items(
            items, self.embedder, self.cfg.threshold, self.cfg.min_cluster_size
        )
        with self.store.tx():
            for c in clusters:
                tid = self._match(c)
                if tid is None:
                    tid = self.store.create_theme(c.label.replace(" / ", "-"), c.label, c.terms)
                    s.new_themes += 1
                new = self.store.add_items(tid, c.items, run_id)
                s.new_items += new
                row = self.store.db.execute(
                    "SELECT key, status FROM themes WHERE id = ?", (tid,)
                ).fetchone()
                if new and row["status"] == "resolved":
                    s.reopened.append(row["key"])
            self.store.drop_empty_themes()
        for key in s.reopened:
            self.store.set_status(key, "open", "new evidence after resolve", actor="engine")
        s.themes = len(self.store.themes())
        if self.tracker:
            s.llm_calls, s.input_tokens = self.tracker.calls, self.tracker.input_tokens
            s.output_tokens, s.cost_usd = self.tracker.output_tokens, self.tracker.cost_usd
        s.problems = validate(self.store)
        self.store.finish_run(
            run_id,
            transcripts=s.transcripts,
            items=s.items,
            new_items=s.new_items,
            themes=s.themes,
            new_themes=s.new_themes,
            reopened=len(s.reopened),
            llm_calls=s.llm_calls,
            input_tokens=s.input_tokens,
            output_tokens=s.output_tokens,
            cost_usd=s.cost_usd,
            problems=s.problems,
        )
        return s
