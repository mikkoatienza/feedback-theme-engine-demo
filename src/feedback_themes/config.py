"""YAML configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class EngineConfig:
    """Settings for extraction, clustering, labeling and costs."""

    extractor: str = "rules"  # rules | llm
    llm_provider: str | None = None  # offline | openai | anthropic (env LLM_PROVIDER)
    embeddings: str = "tfidf"  # tfidf | openai
    internal_speakers: list[str] = field(default_factory=list)
    signals: dict[str, list[str]] | None = None
    include_praise: bool = False
    threshold: float = 0.3
    min_cluster_size: int = 1
    match_threshold: float = 0.5
    prices: dict[str, float] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None) -> EngineConfig:
        """Load YAML; unknown keys raise ``ValueError``."""
        if path is None:
            return cls()
        data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        return cls(**data)


SAMPLE = """\
# feedback-themes configuration
extractor: rules            # rules | llm (falls back to rules if the model output is unusable)
llm_provider: offline       # offline | openai | anthropic  (or LLM_PROVIDER env var)
embeddings: tfidf           # tfidf | openai
internal_speakers: [Host, Interviewer]   # your team; never counted as customer feedback
include_praise: false
threshold: 0.3              # cosine similarity needed to merge clusters (higher = more themes)
min_cluster_size: 1
match_threshold: 0.5        # term overlap needed to attach a cluster to an existing theme
prices:                     # USD per 1M tokens, from your provider's price list
  input_per_million: 0
  output_per_million: 0
# signals:                  # override rule keywords per kind
#   pain: [slow, broken]
#   request: [please add]
"""
