# feedback-theme-engine-demo

A small, clean-room demo of an **AI product-feedback theme engine**: customer call transcripts in, a *living* board of themes out.

Built from scratch with **synthetic sample data only** (`data/transcripts.json`). It shows the shape of the system with plain Python so it runs anywhere; in production you would swap the extraction and labeling steps for LLM calls.

## How it works
1. **Extract.** Split transcripts into sentences and keep the ones that read like feedback (pain, requests, confusion).
2. **Cluster.** Group similar snippets into themes (bag-of-words cosine similarity against a running centroid).
3. **Label.** Give each theme a stable key and a readable label.
4. **Rebuild, don't reset.** Each run merges with the previous board, so product decisions stick:
   - `dismissed` themes stay dismissed.
   - `resolved` themes stay resolved, **unless new evidence arrives**, in which case they reopen.
5. **Validate.** Every rebuild is checked (no empty or duplicate themes, valid statuses) before it is saved.

## Quick start
```bash
python -m themes                      # build the board from data/transcripts.json
python -m themes resolve <theme-key>  # mark a theme resolved
python -m themes dismiss <theme-key>  # dismiss noise
python -m themes                      # rebuild; decisions persist
python -m unittest -v
```
Requires Python 3.10+. No dependencies. Run it on a schedule (e.g. nightly cron) to keep the board current.

## Ideas for extending
- Replace `extract_snippets` with an LLM prompt that returns structured feedback items.
- Replace keyword clustering with embeddings.
- Track model cost per rebuild and alert when it drifts.

## License
MIT
