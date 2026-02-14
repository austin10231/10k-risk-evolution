"""
Local JSON-file persistence layer.

Layout:
  data/
    index.json          – list of record metadata dicts
    html/{record_id}.html    – raw uploaded HTML
    results/{record_id}.json – structured analysis JSON
"""

import json
import uuid
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")
HTML_DIR = DATA_DIR / "html"
RESULTS_DIR = DATA_DIR / "results"
INDEX_FILE = DATA_DIR / "index.json"


def _init():
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("[]")


def load_index() -> list[dict]:
    _init()
    return json.loads(INDEX_FILE.read_text())


def _save_index(index: list[dict]):
    INDEX_FILE.write_text(json.dumps(index, indent=2, default=str))


def add_record(
    company: str,
    industry: str,
    year: int,
    filing_type: str,
    html_bytes: bytes,
    result_json: dict,
) -> str:
    """Persist a new analysis and return its record_id."""
    _init()
    rid = uuid.uuid4().hex[:10]

    (HTML_DIR / f"{rid}.html").write_bytes(html_bytes)
    (RESULTS_DIR / f"{rid}.json").write_text(
        json.dumps(result_json, indent=2, default=str)
    )

    index = load_index()
    index.append(
        {
            "record_id": rid,
            "company": company,
            "industry": industry,
            "year": int(year),
            "filing_type": filing_type,
            "created_at": datetime.now().isoformat(),
        }
    )
    _save_index(index)
    return rid


def get_result(record_id: str) -> dict | None:
    path = RESULTS_DIR / f"{record_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def get_html(record_id: str) -> bytes | None:
    path = HTML_DIR / f"{record_id}.html"
    if path.exists():
        return path.read_bytes()
    return None


def filter_records(
    industry: str | None = None,
    company: str | None = None,
    year: str | None = None,
    filing_type: str | None = None,
) -> list[dict]:
    recs = load_index()
    if industry and industry != "All":
        recs = [r for r in recs if r["industry"] == industry]
    if company and company != "All":
        recs = [r for r in recs if r["company"] == company]
    if year and year != "All":
        recs = [r for r in recs if str(r["year"]) == str(year)]
    if filing_type and filing_type != "All":
        recs = [r for r in recs if r["filing_type"] == filing_type]
    return recs
