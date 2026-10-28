"""Group similar feedback items into clusters and label them."""

from __future__ import annotations

from collections import Counter

from feedback_themes.embed import Embedder, Vector, cosine, normalize, tokenize
from feedback_themes.models import Cluster, FeedbackItem


def _centroid(vs: list[Vector]) -> Vector:
    return normalize([sum(col) / len(vs) for col in zip(*vs, strict=True)])


def agglomerate(vectors: list[Vector], threshold: float) -> list[list[int]]:
    """Average-linkage-style agglomerative clustering on centroids.

    Repeatedly merges the two most similar groups while their centroid similarity
    is at least ``threshold``. O(n^3) in the worst case: fine for thousands of
    items per run; swap in a vector index for more.
    """
    groups = [[i] for i in range(len(vectors))]
    cents = [vectors[i] for i in range(len(vectors))]
    while len(groups) > 1:
        best, pair = threshold, None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                s = cosine(cents[i], cents[j])
                if s >= best:
                    best, pair = s, (i, j)
        if pair is None:
            break
        i, j = pair
        groups[i] += groups.pop(j)
        cents.pop(j)
        cents[i] = _centroid([vectors[k] for k in groups[i]])
    return groups


def label_terms(items: list[FeedbackItem], n: int = 3) -> list[str]:
    """Most frequent distinctive terms across a cluster's items (document frequency)."""
    df: Counter[str] = Counter()
    for it in items:
        df.update(set(tokenize(it.text)))
    return [w for w, _ in sorted(df.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def cluster_items(
    items: list[FeedbackItem], embedder: Embedder, threshold: float = 0.3, min_size: int = 1
) -> list[Cluster]:
    """Embed, cluster and label. Clusters smaller than ``min_size`` are dropped."""
    if not items:
        return []
    vecs = embedder.embed([i.text for i in items])
    out = []
    for g in agglomerate(vecs, threshold):
        members = [items[k] for k in g]
        if len(members) < min_size:
            continue
        terms = label_terms(members)
        out.append(Cluster(members, " / ".join(terms[:2]) or "misc", terms))
    out.sort(key=lambda c: (-len({m.account for m in c.items}), -len(c.items), c.label))
    return out
