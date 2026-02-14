"""
Local JSON-file persistence layer.

Layout:
  data/
    index.json
    html/{record_id}.html
    results/{record_id}.json
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
    _init()
    rid = uuid.uuid4().hex[:10]
    (HTML_DIR / f"{rid}.html").write_bytes(html_bytes)
    (RESULTS_DIR / f"{rid}.json").write_text(
        json.dumps(result_json, indent=2, default=str, ensure_ascii=False)
    )
    index = load_index()
    index.append({
        "record_id": rid,
        "company": company,
        "industry": industry,
        "year": int(year),
        "filing_type": filing_type,
        "created_at": datetime.now().isoformat(),
    })
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


def delete_record(record_id: str):
    """Remove a record from the index and delete its files."""
    _init()
    index = load_index()
    index = [r for r in index if r["record_id"] != record_id]
    _save_index(index)

    html_path = HTML_DIR / f"{record_id}.html"
    result_path = RESULTS_DIR / f"{record_id}.json"
    if html_path.exists():
        html_path.unlink()
    if result_path.exists():
        result_path.unlink()


def filter_records(
    industry=None, company=None, year=None, filing_type=None,
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
