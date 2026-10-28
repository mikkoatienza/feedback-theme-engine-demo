"""End-to-end demo of the theme lifecycle on synthetic transcripts.

python examples/run_demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from feedback_themes.config import EngineConfig
from feedback_themes.engine import Engine
from feedback_themes.export import to_html, to_markdown
from feedback_themes.ingest import load_path
from feedback_themes.store import Store

HERE = Path(__file__).parent


def main() -> None:
    cfg = EngineConfig.load(HERE / "themes.yaml")
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "themes.db")
        engine = Engine.from_config(store, cfg)

        print("== Night 1: build the board from week 1")
        s1 = engine.rebuild(load_path(HERE / "transcripts/week1"))
        print(f"{s1.items} items -> {s1.themes} themes, problems: {s1.problems or 'none'}")
        for t in store.themes():
            print(f"  [{t.status}] {t.label} ({t.accounts} accounts)  key={t.key}")

        export = next(t for t in store.themes() if "export" in t.terms or "csv" in t.terms)
        store.set_status(export.key, "resolved", "Shipped streaming export")
        print(f"\n== Product team resolves {export.key!r}")

        print("\n== Night 2: rebuild with weeks 1 + 2")
        transcripts = load_path(HERE / "transcripts/week1") + load_path(HERE / "transcripts/week2")
        s2 = engine.rebuild(transcripts)
        print(f"{s2.new_items} new items, reopened: {s2.reopened or 'none'}")
        print(store.history(export.key)[-1])

        out = Path(tmp)
        (out / "board.html").write_text(to_html(store))
        print("\n" + to_markdown(store))


if __name__ == "__main__":
    main()
