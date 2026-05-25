# scripts/

Operational scripts for one-off data work. None of these run automatically;
they are invoked manually from a host that has AWS + Bedrock credentials in
its environment.

## Inventory

| Script | Plan | Purpose |
|---|---|---|
| `migrate_s3_layout.py` | S3_PLAN.md Part 1 | Relocate the 42 legacy `10k_html_datasets/*.html` files into `10k_filings/<industry>/<company_dir>/<year>_10K.{html,json}` and re-extract risks via the current Bedrock pipeline. |
| `bulk_ingest.py` | S3_PLAN.md Part 2 | Pull recent 10-Ks for ~80 SEC tickers from EDGAR, extract risks with the same pipeline, and write into the new layout. |
| `backfill_10k_financial_tables.py` | — | Scan existing 10-K records and backfill saved financial statement table JSON/CSV. Dry-run by default; HTML/iXBRL extraction is preferred, PDF/Textract is fallback. |
| `bulk_ingest_targets.py` | — | Hardcoded target list (ticker × industry) consumed by `bulk_ingest.py`. |
| `industry_mapping.py` | — | Single source of truth for industry → company → S3-dir mappings shared by Part 1 and Part 2. |
| `extraction_pipeline.py` | — | Thin reuse layer over `agentcore_deploy/main.py`'s extraction + priority helpers (`_manual_extract_result`, `_generate_agent_priority_report`). Guarantees migrated and ingested filings have the same JSON schema as runtime-uploaded ones. |
| `reclassify_existing_records.py` | (older work) | Backfill `dashboard_category` on legacy `risk_analysis_results/*.json`. Independent of S3_PLAN.md. |
| `upload_phase7_regression.py` | (older work) | Phase-7 regression for SEC download + extraction. Independent. |

## Required environment

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...                # only if using STS
export AWS_REGION=us-west-1                 # S3 bucket region
export BEDROCK_REGION=us-west-2             # Bedrock model region
export S3_BUCKET=10k-risk-alert-app

# Optional — Bedrock dual-model split. Defaults shown; override only when
# your account has a different inference-profile id enabled.
export BEDROCK_EXTRACTION_MODEL_ID=us.amazon.nova-pro-v1:0   # extraction / classification / RPI
export BEDROCK_AGENT_MODEL_ID=deepseek.v3-v1:0               # chat agent / Q&A
```

The scripts call `agentcore_deploy.main`'s helpers, which read these vars
the same way the live runtime does — no separate config to maintain.

## Quick reference

### Part 1 — migrate the existing 42 filings

```bash
# 1. Plan only — prints what would happen, no S3 writes, no Bedrock cost.
python scripts/migrate_s3_layout.py --dry-run

# 2. Actually migrate. ~42 Bedrock invocations (~5–10 min wall clock).
python scripts/migrate_s3_layout.py --write

# 3. Re-run after a partial failure. HTMLs already in the new layout are
#    skipped; existing JSONs are kept unless --force-reextract is passed.
python scripts/migrate_s3_layout.py --write
python scripts/migrate_s3_layout.py --write --force-reextract  # re-score everything
```

Default behaviour:
* `--dry-run` is the default; you must pass `--write` to mutate S3.
* Airbus filings are skipped (`--keep-airbus` to opt them in).
* Old `10k_html_datasets/` and `risk_analysis_results/` keys are **never**
  deleted — clean those up manually after verifying the new layout.

A run report lands at `scripts/migrate_s3_layout.report.json`.

### Part 2 — bulk-ingest ~80 new tickers

```bash
# 1. Plan only.
python scripts/bulk_ingest.py --dry-run

# 2. Real run. Honors SEC's 0.5s/req throttle.
#    --limit lets you smoke-test before committing to a full run.
python scripts/bulk_ingest.py --write --limit 5

# 3. Full run, 2021–2025 (PXD auto-caps at 2023).
python scripts/bulk_ingest.py --write

# 4. Resume after interruption (idempotent).
python scripts/bulk_ingest.py --write
```

Configurable knobs:
* `--start-year 2021 --end-year 2025` — year window (default).
* `--max-failures-per-company 2` — abort a company after N failed years.
* `--limit 0` — cap on number of NEW records to write this run (0 = unlimited).

A local report lands at `scripts/bulk_ingest.report.json`. The same report
is also uploaded to `s3://<bucket>/10k_filings/_ingest_reports/<ISO>.json`
on real runs.

### Backfill 10-K financial tables

```bash
# 1. Plan only. No S3 writes and no extraction jobs.
python scripts/backfill_10k_financial_tables.py --limit 10

# 2. Smoke-test one company/year. HTML/iXBRL is attempted first, then PDF/Textract.
python scripts/backfill_10k_financial_tables.py --execute --ticker AAPL --year 2024

# If your local shell cannot read the production records index, bypass it for
# a one-company smoke test by calling the deployed API, which already has AWS env:
python scripts/backfill_10k_financial_tables.py --execute --api-base https://api.risklensai.org --direct --ticker AAPL --year 2024 --company Apple

# You can also use the deployed API to scan global records from your laptop:
python scripts/backfill_10k_financial_tables.py --execute --api-base https://api.risklensai.org --limit 10

# If a company has slow PDF/Textract filings, the API mode still defaults to
# HTML-first by downloading SEC HTML locally and sending it to the deployed API:
python scripts/backfill_10k_financial_tables.py --execute --api-base https://api.risklensai.org --ticker ADBE --year 2022

# 3. Resume-safe full run. Existing table payloads are skipped.
python scripts/backfill_10k_financial_tables.py --execute --sleep 0.5

# 4. Replace existing table payloads if extraction logic changed.
python scripts/backfill_10k_financial_tables.py --execute --force --ticker MSFT
```

The backfill writes table payloads under `tables_extraction/`. With
`--api-base`, HTML-first extraction sends SEC HTML to
`/api/tables/extract/manual` so local runs do not need AWS credentials and do
not get stuck on slow PDF/Textract filings. A local report lands at
`scripts/backfill_10k_financial_tables.report.json`.

## Backend dual-read

`agentcore_deploy/main.py` reads the new layout when env var
`USE_NEW_S3_LAYOUT=1`; otherwise it reads the old `risk_analysis_results/`
+ `filing_records_index.json` paths. Switch the flag on in Railway after
verifying `10k_filings/index.json` looks healthy:

```bash
# Railway dashboard → Variables → set USE_NEW_S3_LAYOUT=1 → redeploy.
# To roll back, unset / set to 0 and redeploy. No data is deleted.
```

The two layouts can coexist: the dual-read code prefers `10k_filings/`
when the flag is on but falls back to legacy paths if a record is not
found there, so partially-migrated state still works.
