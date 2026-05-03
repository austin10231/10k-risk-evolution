"""Diagnose the three Item 1A locator providers (edgartools → sec-parser →
BS4-regex) on a list of S3 filings, printing how many characters each layer
returned and the first 500 characters of the slice.

Defaults to the 6 records that failed the migrate_s3_layout coverage check
(<5 sub_risks). The migrate report's stack-trace is silent about which
provider mis-located the section, so this script gives operators the raw
char counts they need to decide whether the issue is edgartools, sec-parser,
or the regex fallback.

Usage::

    # Diagnose default failed records.
    python scripts/diagnose_item1a_locator.py

    # Diagnose every record under one industry.
    python scripts/diagnose_item1a_locator.py --industry Energy

    # Diagnose a specific record.
    python scripts/diagnose_item1a_locator.py --industry Energy --company Chevron_CVX --year 2022
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extraction_pipeline as ep  # noqa: E402

# Default targets = the 6 failures noted in EXTRACTION_FIX_PLAN.md P3.
DEFAULT_TARGETS: list[tuple[str, str, int]] = [
    ("Energy", "Chevron_CVX", 2021),
    ("Energy", "Chevron_CVX", 2022),
    ("Energy", "ExxonMobil_XOM", 2021),
    ("Consumer_Defensive", "Kroger_KR", 2023),
    ("Consumer_Defensive", "Kroger_KR", 2024),
    ("Consumer_Defensive", "Kroger_KR", 2025),
]


def _diagnose_one(industry: str, company_dir: str, year: int) -> None:
    key = f"10k_filings/{industry}/{company_dir}/{int(year)}_10K.html"
    print(f"\n[diagnose] {key}", flush=True)
    body = ep.get_bytes(key)
    if not body:
        print("  · S3 object missing or empty — skipping.", flush=True)
        return

    # Lazy imports so the script still loads when only one provider is broken.
    from core.sec_sections import (
        SectionNotFound,
        locate_item1a_with_edgartools,
        locate_item1a_with_sec_parser,
    )
    from core.extractor import _full_text, _make_soup, _locate_item1a_range, _clean_text

    def _layer(name: str, fn) -> None:
        try:
            text, _meta = fn(body)
            cleaned = _clean_text(text) if text else ""
            head = cleaned[:500].replace("\n", " ")
            print(f"  [{name}] chars={len(cleaned)}  head={head!r}", flush=True)
        except SectionNotFound:
            print(f"  [{name}] SectionNotFound", flush=True)
        except Exception as exc:
            print(f"  [{name}] {type(exc).__name__}: {exc}", flush=True)

    _layer("edgartools", locate_item1a_with_edgartools)
    _layer("sec-parser", locate_item1a_with_sec_parser)

    # BS4 + regex fallback
    try:
        full = _full_text(_make_soup(body))
        rng = _locate_item1a_range(full)
        if rng is None:
            print("  [bs4-regex] no range found", flush=True)
        else:
            start_pos, end_pos = rng
            cleaned = _clean_text(full[start_pos:end_pos])
            head = cleaned[:500].replace("\n", " ")
            print(
                f"  [bs4-regex] chars={len(cleaned)} range={start_pos}-{end_pos}  head={head!r}",
                flush=True,
            )
    except Exception as exc:
        print(f"  [bs4-regex] {type(exc).__name__}: {exc}", flush=True)


def _expand_targets(industry: str, company: str, year_str: str) -> list[tuple[str, str, int]]:
    if industry and company and year_str:
        return [(industry, company, int(year_str))]

    paginator = ep.s3_client().get_paginator("list_objects_v2")
    prefix = "10k_filings/"
    if industry:
        prefix += f"{industry}/"
        if company:
            prefix += f"{company}/"
    keys: list[str] = []
    for page in paginator.paginate(Bucket=ep.s3_bucket(), Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            k = str(obj.get("Key") or "")
            if k.endswith("_10K.html"):
                keys.append(k)

    pattern = re.compile(r"10k_filings/([^/]+)/([^/]+)/(\d{4})_10K\.html$")
    out: list[tuple[str, str, int]] = []
    for k in sorted(keys):
        m = pattern.match(k)
        if m:
            out.append((m.group(1), m.group(2), int(m.group(3))))
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print Item 1A locator output sizes for one or more filings.",
    )
    parser.add_argument("--industry", default="", help="Filter by industry directory.")
    parser.add_argument("--company", default="", help="Filter by company directory.")
    parser.add_argument("--year", default="", help="Filter by year (requires --industry and --company).")
    parser.add_argument("--all-failed", action="store_true",
                        help="Diagnose the 6 default failure records (default behavior when no filters).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ep.s3_bucket()
    except RuntimeError as exc:
        print(f"[fatal] {exc}", file=sys.stderr)
        return 2

    if not args.industry and not args.company and not args.year:
        targets: list[tuple[str, str, int]] = list(DEFAULT_TARGETS)
    else:
        targets = _expand_targets(args.industry, args.company, args.year)

    if not targets:
        print("[diagnose] no targets matched filters.", file=sys.stderr)
        return 1

    for industry, company, year in targets:
        _diagnose_one(industry, company, year)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
