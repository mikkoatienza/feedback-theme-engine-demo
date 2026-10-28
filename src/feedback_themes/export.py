"""Board exports: Markdown and standalone HTML."""

from __future__ import annotations

import html

from feedback_themes.store import Store

ICON = {"open": "🟢", "resolved": "✅", "dismissed": "⚪"}


def to_markdown(store: Store, max_quotes: int = 3) -> str:
    """Markdown board grouped by status, with representative quotes."""
    out = ["# Feedback theme board", ""]
    for status in ("open", "resolved", "dismissed"):
        themes = store.themes(status)
        if not themes:
            continue
        out += [f"## {ICON[status]} {status.title()} ({len(themes)})", ""]
        for t in themes:
            out.append(f"### {t.label}  `{t.key}`")
            out.append(f"{t.accounts} account(s), {t.items} mention(s)")
            out.append("")
            for it in store.items_for(t.id)[:max_quotes]:
                who = it["account"] or it["transcript_id"]
                out.append(f"> {it['text']}  \n> — {who} ({it['kind']})")
                out.append("")
    return "\n".join(out).rstrip() + "\n"


def to_html(store: Store, max_quotes: int = 3) -> str:
    """Single-file HTML board (no external assets)."""
    cols = []
    for status in ("open", "resolved", "dismissed"):
        cards = []
        for t in store.themes(status):
            quotes = "".join(
                f"<blockquote>{html.escape(i['text'])}<cite>"
                f"{html.escape(i['account'] or i['transcript_id'])}</cite></blockquote>"
                for i in store.items_for(t.id)[:max_quotes]
            )
            cards.append(
                f"<article><h3>{html.escape(t.label)}</h3><code>{html.escape(t.key)}</code>"
                f"<p>{t.accounts} account(s) · {t.items} mention(s)</p>{quotes}</article>"
            )
        cols.append(f"<section><h2>{ICON[status]} {status.title()}</h2>{''.join(cards)}</section>")
    css = (
        "body{font-family:system-ui,sans-serif;margin:2rem;background:#f6f7f9}"
        "main{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}"
        "article{background:#fff;border-radius:8px;padding:1rem;margin-bottom:1rem;"
        "box-shadow:0 1px 3px #0002}blockquote{margin:.5rem 0;padding-left:.75rem;"
        "border-left:3px solid #ccd;color:#333}cite{display:block;font-size:.8em;color:#778}"
        "code{font-size:.8em;color:#667}"
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>Feedback themes</title>'
        f"<style>{css}</style></head><body><h1>Feedback theme board</h1>"
        f"<main>{''.join(cols)}</main></body></html>\n"
    )
