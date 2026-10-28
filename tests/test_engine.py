import json, unittest
from themes.engine import build_board, set_status, validate, extract_snippets

DATA = json.load(open("data/transcripts.json"))

class EngineTest(unittest.TestCase):
    def test_finds_snippets(self):
        self.assertTrue(extract_snippets(DATA))

    def test_export_complaints_group_together(self):
        board = build_board(DATA)
        export = [t for t in board["themes"] if "csv" in t["key"]]
        self.assertTrue(export)
        self.assertGreaterEqual(max(t["accounts"] for t in export), 2)

    def test_validation_clean(self):
        self.assertEqual(validate(build_board(DATA)), [])

    def test_dismissed_persists_across_rebuild(self):
        b = build_board(DATA)
        key = b["themes"][0]["key"]
        set_status(b, key, "dismissed")
        b2 = build_board(DATA, b)
        self.assertEqual(next(t for t in b2["themes"] if t["key"] == key)["status"], "dismissed")

    def test_resolved_reopens_on_new_evidence(self):
        b = build_board(DATA)
        export = next(t for t in b["themes"] if "csv" in t["key"])
        set_status(b, export["key"], "resolved")
        more = DATA + [{"id": "call-99", "account": "Synthetic Co Z", "text": "CSV export still fails on big reports."}]
        b2 = build_board(more, b)
        self.assertEqual(next(t for t in b2["themes"] if t["key"] == export["key"])["status"], "open")

if __name__ == "__main__":
    unittest.main()
