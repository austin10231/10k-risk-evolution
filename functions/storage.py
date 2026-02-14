import os
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

BASE_DIR = os.path.join("data", "library")
FILES_DIR = os.path.join(BASE_DIR, "files")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
INDEX_PATH = os.path.join(BASE_DIR, "index.jsonl")

def ensure_storage():
    os.makedirs(FILES_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(BASE_DIR, exist_ok=True)
    if not os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            pass

def _now():
    return datetime.utcnow().isoformat() + "Z"

def list_records() -> List[Dict]:
    ensure_storage()
    records = []
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    # newest first
    records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return records

def get_record_by_id(record_id: str) -> Optional[Dict]:
    for r in list_records():
        if r["record_id"] == record_id:
            return r
    return None

def upsert_record_and_save_files(
    company: str,
    year: int,
    filing_type: str,
    industry: str,
    html_filename: str,
    html_bytes: bytes,
    report_json: Dict,
) -> str:
    ensure_storage()
    record_id = str(uuid.uuid4())

    safe_company = company.replace("/", "_")
    html_path = os.path.join(FILES_DIR, f"{safe_company}-{year}-{filing_type}-{record_id}.html")
    report_path = os.path.join(REPORTS_DIR, f"{safe_company}-{year}-{filing_type}-{record_id}.json")

    with open(html_path, "wb") as f:
        f.write(html_bytes)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_json, f, ensure_ascii=False, indent=2)

    meta = {
        "record_id": record_id,
        "company": company,
        "year": year,
        "filing_type": filing_type,
        "industry": industry,
        "html_filename": html_filename,
        "html_path": html_path,
        "report_path": report_path,
        "created_at": _now(),
    }

    with open(INDEX_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")

    return record_id

def load_report_json(record_id: str) -> Dict:
    rec = get_record_by_id(record_id)
    if not rec:
        raise FileNotFoundError(f"record_id not found: {record_id}")
    with open(rec["report_path"], "r", encoding="utf-8") as f:
        return json.load(f)
