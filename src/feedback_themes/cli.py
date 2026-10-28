"""Command-line interface: ``feedback-themes``."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from feedback_themes import __version__
from feedback_themes.config import SAMPLE, EngineConfig
from feedback_themes.engine import Engine
from feedback_themes.export import to_html, to_markdown
from feedback_themes.ingest import load_path
from feedback_themes.store import Store
from feedback_themes.validate import validate


def main(argv: list[str] | None = None) -> int:
    """Entry point. ``rebuild`` exits 2 when validation finds problems."""
    ap = argparse.ArgumentParser(prog="feedback-themes")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--db", type=Path, default=Path("themes.db"), help="SQLite file")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rb = sub.add_parser("rebuild", help="ingest transcripts and update the board (run nightly)")
    rb.add_argument("source", type=Path, help="file or directory of .txt/.vtt/.json")
    rb.add_argument("-c", "--config", type=Path)
    sub.add_parser("list", help="show themes")
    for name in ("resolve", "dismiss", "reopen"):
        p = sub.add_parser(name, help=f"{name} a theme")
        p.add_argument("key")
        p.add_argument("-m", "--note", default="")
    sh = sub.add_parser("show", help="evidence and history for a theme")
    sh.add_argument("key")
    ex = sub.add_parser("export", help="export the board")
    ex.add_argument("-f", "--format", choices=["md", "html", "json"], default="md")
    ex.add_argument("-o", "--output", type=Path)
    sub.add_parser("runs", help="recent rebuilds with costs")
    sub.add_parser("validate", help="run validation checks")
    ini = sub.add_parser("init", help="write a sample config")
    ini.add_argument("path", type=Path, nargs="?", default=Path("themes.yaml"))
    a = ap.parse_args(argv)

    if a.cmd == "init":
        if a.path.exists():
            print(f"{a.path} exists", file=sys.stderr)
            return 1
        a.path.write_text(SAMPLE)
        print(f"wrote {a.path}")
        return 0

    store = Store(a.db)
    if a.cmd == "rebuild":
        s = Engine.from_config(store, EngineConfig.load(a.config)).rebuild(load_path(a.source))
        print(
            f"run {s.run_id}: {s.transcripts} transcripts, {s.items} items "
            f"({s.new_items} new), {s.themes} themes ({s.new_themes} new), "
            f"reopened {s.reopened or 'none'}, llm calls {s.llm_calls}, "
            f"tokens {s.input_tokens}/{s.output_tokens}, est. cost ${s.cost_usd:.4f}"
        )
        for problem in s.problems:
            print(f"warning: {problem}", file=sys.stderr)
        return 2 if s.problems else 0
    if a.cmd == "list":
        for t in store.themes():
            print(f"[{t.status:9}] {t.label:30} accounts={t.accounts} items={t.items}  {t.key}")
        return 0
    if a.cmd in ("resolve", "dismiss", "reopen"):
        status = {"resolve": "resolved", "dismiss": "dismissed", "reopen": "open"}[a.cmd]
        try:
            store.set_status(a.key, status, a.note)
        except KeyError:
            print(f"no theme {a.key!r}", file=sys.stderr)
            return 1
        print(f"{a.key} -> {status}")
        return 0
    if a.cmd == "show":
        try:
            t = store.theme(a.key)
        except KeyError:
            print(f"no theme {a.key!r}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "theme": asdict(t),
                    "items": store.items_for(t.id),
                    "history": store.history(a.key),
                },
                indent=2,
            )
        )
        return 0
    if a.cmd == "export":
        if a.format == "md":
            text = to_markdown(store)
        elif a.format == "html":
            text = to_html(store)
        else:
            text = json.dumps([asdict(t) for t in store.themes()], indent=2)
        if a.output:
            a.output.write_text(text)
            print(f"wrote {a.output}")
        else:
            print(text)
        return 0
    if a.cmd == "runs":
        for r in store.runs():
            print(
                f"#{r['id']} {r['started_at']} items={r['items']} new={r['new_items']} "
                f"themes={r['themes']} reopened={r['reopened']} tokens={r['input_tokens']}/"
                f"{r['output_tokens']} cost=${r['cost_usd']:.4f} problems={r['problems']}"
            )
        return 0
    problems = validate(store)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
