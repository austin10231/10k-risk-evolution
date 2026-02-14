# storage.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path("data")
DOCS_DIR = DATA_DIR / "docs"
INDEX_FILE = DATA_DIR / "index.json"


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text(json.dumps({"documents": []}, indent=2), encoding="utf-8")


def load_index() -> Dict[str, Any]:
    _ensure_dirs()
    return json.loads(INDEX_FILE.read_text(encoding="utf-8"))


def save_index(index: Dict[str, Any]) -> None:
    _ensure_dirs()
    INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")


def _doc_id(company: str, year: str) -> str:
    # stable-ish ID
    safe_company = "".join(ch for ch in company.lower() if ch.isalnum() or ch in "-_").strip("-_")
    safe_year = "".join(ch for ch in str(year) if ch.isdigit())
    return f"{safe_company}-{safe_year}"


def save_document(doc: Dict[str, Any]) -> str:
    """
    doc must include:
      - company_name
      - year
      - sector
      - extracted (dict)
    """
    _ensure_dirs()
    doc_id = _doc_id(doc["company_name"], str(doc["year"]))
    path = DOCS_DIR / f"{doc_id}.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    index = load_index()
    docs = index.get("documents", [])

    # Upsert
    docs = [d for d in docs if d.get("doc_id") != doc_id]
    docs.append(
        {
            "doc_id": doc_id,
            "company_name": doc["company_name"],
            "year": str(doc["year"]),
            "sector": doc.get("sector", "Unknown"),
        }
    )
    index["documents"] = sorted(docs, key=lambda x: (x["sector"], x["company_name"], x["year"]))
    save_index(index)
    return doc_id


def load_document(doc_id: str) -> Dict[str, Any]:
    _ensure_dirs()
    path = DOCS_DIR / f"{doc_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {doc_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_documents() -> List[Dict[str, Any]]:
    idx = load_index()
    return idx.get("documents", [])


def delete_document(doc_id: str) -> None:
    _ensure_dirs()
    path = DOCS_DIR / f"{doc_id}.json"
    if path.exists():
        path.unlink()

    index = load_index()
    docs = [d for d in index.get("documents", []) if d.get("doc_id") != doc_id]
    index["documents"] = docs
    save_index(index)


def group_by_sector(docs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for d in docs:
        out.setdefault(d.get("sector", "Unknown"), []).append(d)
    return out


def group_company_years(docs: List[Dict[str, Any]], company_name: str) -> List[Dict[str, Any]]:
    filtered = [d for d in docs if d["company_name"] == company_name]
    return sorted(filtered, key=lambda x: x["year"])
