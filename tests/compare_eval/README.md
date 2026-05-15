# Compare evaluation harness

This folder hosts the labelled fixtures used by `scripts/eval_compare.py`
to regression-test the Compare feature.

## Fixture layout

```
tests/compare_eval/
├── README.md
├── labels.example.jsonl   # template — see fields below
├── fixtures/              # full `result.json` dumps for each filing
│   ├── COMPANY_YEAR.json
│   └── ...
└── labels.jsonl           # the actual evaluation set (gitignored optional)
```

## Labels JSONL schema

Each line is one comparison case:

```json
{
  "case_id": "AAPL-2024-vs-2023",
  "prior_path": "tests/compare_eval/fixtures/AAPL_2023.json",
  "latest_path": "tests/compare_eval/fixtures/AAPL_2024.json",
  "mode": "yoy",
  "ground_truth": [
    {"prior_title": "...", "latest_title": "...", "label": "retained"},
    {"prior_title": "...", "latest_title": "...", "label": "modified"},
    {                       "latest_title": "...", "label": "added"},
    {"prior_title": "...",                          "label": "removed"}
  ]
}
```

- `label` is one of `retained | modified | added | removed`.
- `retained` ≈ same risk, near-identical wording.
- `modified` ≈ same risk, materially rewritten title.
- `added` / `removed` ≈ no counterpart on the other side.

## Running

```
python scripts/eval_compare.py \
    --labels tests/compare_eval/labels.jsonl \
    --output scripts/eval_compare.report.json
```

Add `--use-embeddings` to score with the Bedrock Titan path (needs AWS
credentials in env). Without it the script exercises the lexical-only
formula, which is what we want to guard against regressions in CI.

## Regression target

- Lexical-only macro-F1 ≥ **0.75** on the curated set.
- Embedding-enabled macro-F1 ≥ **0.85** on the same set.
