"""Part 1 of S3_PLAN.md: relocate the existing 42 HTML filings under
`s3://<bucket>/10k_html_datasets/` into the new
`s3://<bucket>/10k_filings/<industry>/<company_dir>/<year>_10K.{html,json}`
hierarchy, re-extract risks with the current Bedrock pipeline, and
publish a fresh `10k_filings/index.json`.

Behaviour summary
-----------------
* Old objects are NEVER deleted — the user explicitly wants to confirm
  the new layout first and then `aws s3 rm` themselves.
* The script defaults to `--dry-run` (prints the migration plan, no
  writes). Run with `--write` to actually mutate S3.
* `--skip-airbus` defaults to True per S3_PLAN.md §1.1 (Airbus files no
  SEC 10-K). Override with `--keep-airbus` if you change your mind.
* `--reextract` defaults to True (run the Bedrock extractor on each HTML
  and persist the new risks JSON). Pass `--no-reextract` to copy HTMLs
  only; useful as a fast first pass before paying for Bedrock invokes.
* Resumable: the script checks `head_object` before each write, so re-runs
  with the same flags are idempotent (modulo `--force-rextract`).

Usage::

    # Plan only — no S3 writes, no Bedrock cost.
    python scripts/migrate_s3_layout.py --dry-run

    # Actually migrate. Bedrock + S3 credentials must be in env.
    python scripts/migrate_s3_layout.py --write

    # Re-run after a partial failure; HTMLs already uploaded are skipped,
    # JSONs already present are skipped (use --force-reextract to overwrite).
    python scripts/migrate_s3_layout.py --write
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentcore_deploy import main as backend  # noqa: E402
from scripts import extraction_pipeline as ep  # noqa: E402
from scripts.industry_mapping import (  # noqa: E402
    COMPANIES,
    LEGACY_FILENAME_TO_TICKER,
    SKIP_LEGACY_TOKENS,
)


LEGACY_HTML_PREFIX = "10k_html_datasets/"
LEGACY_FILENAME_RE = re.compile(r"^(.+)_(\d{4})_10-K_[0-9a-f]+\.html$")


# ──────────────────────────────────────────────────────────────────────
#  Filename parsing
# ──────────────────────────────────────────────────────────────────────


def list_legacy_html_keys() -> list[str]:
    keys: list[str] = []
    paginator = ep.s3_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=ep.s3_bucket(), Prefix=LEGACY_HTML_PREFIX):
        for obj in page.get("Contents", []) or []:
            k = str(obj.get("Key") or "")
            if k.endswith(".html"):
                keys.append(k)
    return sorted(keys)


def parse_legacy_key(key: str) -> Optional[tuple[str, int]]:
    name = key.rsplit("/", 1)[-1]
    m = LEGACY_FILENAME_RE.match(name)
    if not m:
        return None
    safe_company = m.group(1)
    year = int(m.group(2))
    return safe_company, year


def resolve_company_for_token(token: str) -> Optional[dict]:
    """Map a legacy filename token to a COMPANIES entry. Returns None if
    the token is in the skip set or unknown."""
    if token in SKIP_LEGACY_TOKENS:
        return None
    ticker = LEGACY_FILENAME_TO_TICKER.get(token)
    if not ticker:
        # Try a case-insensitive match against COMPANIES dirs as a last
        # resort (handles future legacy names without explicit mapping).
        for tk, meta in COMPANIES.items():
            base_dir = str(meta.get("dir") or "")
            display = str(meta.get("name") or "")
            if base_dir.split("_")[0].lower() == token.lower():
                ticker = tk
                break
            if display.replace(" ", "_").lower() == token.lower():
                ticker = tk
                break
    if not ticker:
        return None
    meta = COMPANIES.get(ticker)
    if not meta:
        return None
    return {
        "ticker": ticker,
        "name": meta.get("name", ""),
        "industry": meta.get("industry", "Other"),
        "dir": meta.get("dir", f"{token}_{ticker}"),
        "cik": meta.get("cik", ""),
    }


# ──────────────────────────────────────────────────────────────────────
#  Main migration loop
# ──────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def migrate(
    *,
    write: bool,
    keep_airbus: bool,
    reextract: bool,
    force_reextract: bool,
) -> dict:
    started = _now_iso()
    keys = list_legacy_html_keys()
    print(f"[plan] found {len(keys)} legacy HTML objects under {LEGACY_HTML_PREFIX}", flush=True)

    if not write:
        print("[plan] DRY RUN — no S3 writes, no Bedrock invocations", flush=True)

    # Build (or load) the new index document for incremental writes.
    index_doc = ep.load_new_index() if write else ep.empty_index_doc()
    if not isinstance(index_doc, dict) or not index_doc:
        index_doc = ep.empty_index_doc()

    report: dict[str, Any] = {
        "started_at": started,
        "ended_at": None,
        "total": len(keys),
        "ok": [],
        "skipped": [],
        "failed": [],
        "write": bool(write),
        "reextract": bool(reextract),
        "force_reextract": bool(force_reextract),
        "keep_airbus": bool(keep_airbus),
    }

    for idx, key in enumerate(keys, start=1):
        t0 = time.time()
        parsed = parse_legacy_key(key)
        if not parsed:
            print(f"[{idx}/{len(keys)}] FAIL {key} reason=cannot_parse_filename", flush=True)
            report["failed"].append({"key": key, "reason": "cannot_parse_filename"})
            continue
        token, year = parsed

        if (token in SKIP_LEGACY_TOKENS) and not keep_airbus:
            print(f"[{idx}/{len(keys)}] SKIP {key} reason=skip_legacy_token({token})", flush=True)
            report["skipped"].append({"key": key, "reason": f"skip_legacy_token:{token}"})
            continue

        meta = resolve_company_for_token(token)
        if not meta:
            print(f"[{idx}/{len(keys)}] FAIL {key} reason=unknown_company_token({token})", flush=True)
            report["failed"].append({"key": key, "reason": f"unknown_company_token:{token}"})
            continue

        industry_dir = meta["industry"]
        company_dir = meta["dir"]
        company_name = meta["name"]
        ticker = meta["ticker"]
        cik = meta.get("cik", "") or ""

        h_key = ep.html_key_for(industry_dir, company_dir, year)
        j_key = ep.json_key_for(industry_dir, company_dir, year)
        existing_html = ep.head_exists(h_key) if write else False
        existing_json = ep.head_exists(j_key) if write else False

        plan_line = (
            f"[{idx}/{len(keys)}] PLAN {key} "
            f"-> {h_key} (html_exists={existing_html}) + {j_key} "
            f"(json_exists={existing_json}, reextract={reextract})"
        )
        if not write:
            print(plan_line, flush=True)
            report["ok"].append({
                "key": key, "industry": industry_dir, "company_dir": company_dir,
                "year": year, "ticker": ticker, "html_key": h_key, "json_key": j_key,
                "html_exists": existing_html, "json_exists": existing_json,
                "planned": True,
            })
            continue

        # ── Real write below ─────────────────────────────────────────
        try:
            html_bytes = ep.get_bytes(key)
            if not html_bytes:
                raise RuntimeError("legacy object body was empty")

            # 1) HTML upload (skip if already in new layout).
            if existing_html:
                print(f"  · html already at {h_key}, skipping upload", flush=True)
            else:
                ep.put_bytes(h_key, html_bytes, content_type="text/html; charset=utf-8")
                print(f"  · uploaded html → {h_key} ({len(html_bytes)/1024:.0f} KB)", flush=True)

            sub_risk_count = 0
            if reextract and (force_reextract or not existing_json):
                # 2) Bedrock-backed extraction (overview + risks +
                #    dashboard_category + original_category).
                result, err = ep.extract_risks_for_html(
                    html_bytes,
                    company_display_name=company_name,
                    industry_label=industry_dir,
                    year=year,
                    filing_type="10-K",
                )
                if not result:
                    raise RuntimeError(f"extract failed: {err or 'unknown'}")

                risks = result.get("risks", []) if isinstance(result, dict) else []
                sub_risk_count = sum(
                    len(b.get("sub_risks", []) or [])
                    for b in (risks if isinstance(risks, list) else [])
                    if isinstance(b, dict)
                )
                if sub_risk_count < 5:
                    raise RuntimeError(f"risks coverage too low: {sub_risk_count} sub_risks (<5)")

                # 3) Priority/agent report so dashboard RPI is non-zero.
                _agent_report, agent_err = ep.attach_agent_priority_report(
                    result, company=company_name, year=year,
                )
                if agent_err:
                    print(f"  · WARNING: agent_priority skipped: {agent_err}", flush=True)

                result["source"] = "s3_migration_part1"
                result["sec_meta"] = {
                    "ticker": ticker,
                    "cik": cik,
                    "year": year,
                    "auto_fetch": False,
                    "legacy_key": key,
                }
                ep.write_filing_to_new_layout(
                    industry_dir=industry_dir,
                    company_dir=company_dir,
                    year=year,
                    html_bytes=html_bytes,
                    risks_json=result,
                    skip_html_if_exists=True,
                    skip_json_if_exists=False,
                )
                print(f"  · wrote risks json → {j_key} ({sub_risk_count} sub_risks)", flush=True)
            else:
                # 4) Read existing json to backfill sub_risk_count for index.
                raw = ep.get_bytes(j_key)
                if raw:
                    try:
                        existing = json.loads(raw.decode("utf-8", errors="ignore"))
                        if isinstance(existing, dict):
                            sub_risk_count = sum(
                                len(b.get("sub_risks", []) or [])
                                for b in existing.get("risks", []) or []
                                if isinstance(b, dict)
                            )
                    except Exception:
                        sub_risk_count = 0
                print(f"  · skipped extraction (reextract={reextract}, json_exists={existing_json})", flush=True)

            # 5) Update in-memory index, atomic flush every 5 records.
            ep.upsert_filing_into_index(
                index_doc,
                industry_dir=industry_dir,
                company_dir=company_dir,
                company_display_name=company_name,
                ticker=ticker,
                cik=cik,
                year=year,
                html_key=h_key,
                json_key=j_key,
                sub_risk_count=sub_risk_count,
                extracted_at=_now_iso(),
                filing_type="10-K",
            )
            if idx % 5 == 0:
                ep.save_new_index(index_doc)
                print(f"  · checkpoint flush of index.json (after {idx} records)", flush=True)

            duration = time.time() - t0
            print(
                f"[{idx}/{len(keys)}] OK   {industry_dir}/{company_dir}/{year}  "
                f"{sub_risk_count} sub_risks  {duration:.1f}s",
                flush=True,
            )
            report["ok"].append({
                "key": key, "industry": industry_dir, "company_dir": company_dir,
                "year": year, "ticker": ticker, "html_key": h_key, "json_key": j_key,
                "sub_risk_count": sub_risk_count, "duration_s": round(duration, 2),
            })

        except Exception as exc:
            duration = time.time() - t0
            tb = traceback.format_exc()
            print(f"[{idx}/{len(keys)}] FAIL {key}  reason={type(exc).__name__}:{exc}  {duration:.1f}s", flush=True)
            print(tb, flush=True)
            report["failed"].append({
                "key": key,
                "reason": f"{type(exc).__name__}: {exc}",
                "duration_s": round(duration, 2),
            })

    # Final flush of index.json (always do this on `--write` even if many
    # records failed — partial data is more useful than no data).
    if write:
        ep.save_new_index(index_doc)
        print(f"[done] flushed final index.json with "
              f"{sum(len(c.get('filings', [])) for ind in index_doc.get('industries', {}).values() for c in ind.values())}"
              f" filings", flush=True)

    report["ended_at"] = _now_iso()
    print(
        f"[done] ok={len(report['ok'])} skipped={len(report['skipped'])} failed={len(report['failed'])}",
        flush=True,
    )
    return report


# ──────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy S3 HTML filings into 10k_filings/ layout (S3_PLAN.md Part 1).")
    parser.add_argument("--dry-run", dest="write", action="store_false",
                        help="Default. Print the migration plan; no S3 writes, no Bedrock invokes.")
    parser.add_argument("--write", dest="write", action="store_true",
                        help="Actually mutate S3 and call Bedrock. Requires AWS credentials.")
    parser.add_argument("--keep-airbus", dest="keep_airbus", action="store_true",
                        help="Migrate Airbus filings instead of skipping them.")
    parser.add_argument("--no-reextract", dest="reextract", action="store_false",
                        help="Copy HTMLs only; do not run Bedrock to (re)generate risks JSON.")
    parser.add_argument("--force-reextract", action="store_true",
                        help="Re-extract risks even if the destination JSON already exists.")
    parser.add_argument("--report", default=str(ROOT / "scripts" / "migrate_s3_layout.report.json"),
                        help="Where to write the run report JSON (default: scripts/migrate_s3_layout.report.json).")
    parser.set_defaults(write=False, keep_airbus=False, reextract=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ep.s3_bucket()
    except RuntimeError as exc:
        print(f"[fatal] {exc}", file=sys.stderr)
        return 2

    report = migrate(
        write=args.write,
        keep_airbus=args.keep_airbus,
        reextract=args.reextract,
        force_reextract=args.force_reextract,
    )

    try:
        Path(args.report).write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"[report] wrote {args.report}", flush=True)
    except Exception as exc:
        print(f"[report] could not write {args.report}: {exc}", file=sys.stderr)

    return 0 if not report.get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
