"""Post-rebuild validation checks."""

from __future__ import annotations

from feedback_themes.models import STATUSES
from feedback_themes.store import Store


def validate(store: Store, max_share: float = 0.6) -> list[str]:
    """Return a list of problems (empty means healthy).

    Checks: no empty themes, valid statuses, no orphan items, unique labels among
    open themes, and no single theme swallowing more than ``max_share`` of all
    evidence (a sign the similarity threshold is too low).
    """
    problems = []
    themes = store.themes()
    total = sum(t.items for t in themes)
    seen: dict[str, str] = {}
    for t in themes:
        if t.items == 0:
            problems.append(f"theme {t.key} has no evidence")
        if t.status not in STATUSES:
            problems.append(f"theme {t.key} has invalid status {t.status!r}")
        if t.status == "open":
            if t.label in seen:
                problems.append(f"themes {seen[t.label]} and {t.key} share label {t.label!r}")
            seen[t.label] = t.key
        if total >= 10 and t.items / total > max_share:
            problems.append(
                f"theme {t.key} holds {t.items}/{total} items; consider a higher threshold"
            )
    orphans = store.db.execute(
        "SELECT COUNT(*) FROM items WHERE theme_id IS NULL "
        "OR theme_id NOT IN (SELECT id FROM themes)"
    ).fetchone()[0]
    if orphans:
        problems.append(f"{orphans} item(s) are not attached to a theme")
    return problems
