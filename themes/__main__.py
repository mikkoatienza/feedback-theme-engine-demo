import json, os, sys
from .engine import build_board, set_status, validate

STATE = ".state/board.json"

def main(argv):
    if len(argv) >= 3 and argv[0] in ("resolve", "dismiss", "reopen"):
        board = json.load(open(STATE))
        status = {"resolve": "resolved", "dismiss": "dismissed", "reopen": "open"}[argv[0]]
        set_status(board, argv[1], status)
    else:
        src = argv[0] if argv else "data/transcripts.json"
        prev = json.load(open(STATE)) if os.path.exists(STATE) else None
        board = build_board(json.load(open(src)), prev)
    problems = validate(board)
    if problems:
        sys.exit("validation failed: " + "; ".join(problems))
    os.makedirs(".state", exist_ok=True)
    json.dump(board, open(STATE, "w"), indent=2)
    for t in board["themes"]:
        print(f"[{t['status']:9}] {t['label']:28} accounts={t['accounts']} snippets={len(t['snippets'])}  key={t['key']}")

if __name__ == "__main__":
    main(sys.argv[1:])
