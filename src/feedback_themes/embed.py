"""Embedding providers: TF-IDF fallback (pure Python) and optional OpenAI embeddings."""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from typing import Protocol

Vector = list[float]

_STOP_TEXT = """
a an the and or but to of in on for is are was were be been being it its this that these
those we our us you your they their them i my me with at by from as so too also very please
would could should can will just not no some often never into about there here what when how
really kind sort like get got have has had do does did one thing things lot much more any
all out up yeah okay ok um uh know think going want need it's that's don't
"""
STOPWORDS = frozenset(_STOP_TEXT.split())


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens with stopwords and short words removed, light plural folding."""
    words = re.findall(r"[a-z][a-z'-]+", text.lower())
    out = []
    for w in words:
        w = w.strip("'-")
        if len(w) < 3 or w in STOPWORDS:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


class Embedder(Protocol):
    """Maps texts to vectors. Vectors from one call must be comparable with each other."""

    def embed(self, texts: list[str]) -> list[Vector]:
        """Embed a batch."""
        ...


class TfidfEmbedder:
    """Fits a TF-IDF vocabulary on each batch. Deterministic and offline."""

    def __init__(self) -> None:
        self.vocab: list[str] = []
        self.idf: dict[str, float] = {}

    def embed(self, texts: list[str]) -> list[Vector]:
        docs = [Counter(tokenize(t)) for t in texts]
        df: Counter[str] = Counter()
        for d in docs:
            df.update(d.keys())
        n = len(docs)
        self.vocab = sorted(df)
        self.idf = {w: math.log((1 + n) / (1 + df[w])) + 1 for w in self.vocab}
        idx = {w: i for i, w in enumerate(self.vocab)}
        vecs = []
        for d in docs:
            v = [0.0] * len(self.vocab)
            for w, c in d.items():
                v[idx[w]] = c * self.idf[w]
            vecs.append(normalize(v))
        return vecs


class OpenAIEmbedder:
    """OpenAI embeddings. Needs the ``[openai]`` extra and ``OPENAI_API_KEY``."""

    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI

        self.model = model or os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small")
        self._client = OpenAI()

    def embed(self, texts: list[str]) -> list[Vector]:
        r = self._client.embeddings.create(model=self.model, input=texts)
        return [normalize(list(d.embedding)) for d in r.data]


def normalize(v: Vector) -> Vector:
    """Scale to unit length (zero vectors stay zero)."""
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def cosine(a: Vector, b: Vector) -> float:
    """Cosine similarity of two unit vectors."""
    return sum(x * y for x, y in zip(a, b, strict=False))


def get_embedder(name: str | None = None) -> Embedder:
    """``tfidf`` (default) or ``openai``; also read from ``EMBEDDINGS_PROVIDER``."""
    name = (name or os.environ.get("EMBEDDINGS_PROVIDER", "tfidf")).lower()
    if name == "openai":
        return OpenAIEmbedder()
    if name == "tfidf":
        return TfidfEmbedder()
    raise ValueError(f"unknown embeddings provider: {name!r}")
