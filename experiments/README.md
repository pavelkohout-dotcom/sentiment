# Local llama3 RSS review

Run from the repository root with Python 3 and an already running local Ollama:

```sh
python3 experiments/llama3_review.py --prior /absolute/path/to/prior/results.json --output /absolute/path/outside/repository
```

Uses only the installed `llama3:latest` model. No model pulls, paid APIs, production writes or workflow changes. The output directory must be outside the repository so private RSS headlines are not accidentally published. The production source configuration and index remain unchanged.

The review fetches every item from enabled RSS feeds, deduplicates canonical URL/title pairs and scores all items without the production relevance or age filter. This tests false positives as well as coverage. It uses the same prompt, schema and generation options as the initial seven-headline experiment. Earlier real RSS ratings are retained as a separate cohort; synthetic checks are excluded. A headline can appear in both cohorts and is not counted as a new unique historical example.

Outputs: self-contained searchable `review.html`, `ratings.csv`, `results.json` (model digest, prompt, settings, repository revision, baseline snapshot, source errors and individual ratings), `sample.json`, and source XML snapshots. Never commit these private outputs. Feed publication times are preserved verbatim; Investing's timezone is unspecified in the feed (production assumes UTC).

The saved public index is a repository snapshot with its own timestamp, not a real-time comparison on the same corpus. Its event deduplication, 24-hour window, time decay and source minimums differ from this headline review. LLM labels are not an alternative index, calibrated probabilities or measured accuracy. Human labels are still needed to assess accuracy. Single-company direction must not be interpreted as broad-market direction.
