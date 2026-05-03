"""SEC filing section locators backed by edgartools, with no network calls."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any


class SectionNotFound(RuntimeError):
    """Raised when a requested SEC section cannot be located."""


def _decode_html(html_bytes: bytes) -> str:
    if isinstance(html_bytes, str):
        return html_bytes
    raw = bytes(html_bytes or b"")
    if not raw:
        raise SectionNotFound("Empty filing HTML.")
    return raw.decode("utf-8", errors="ignore")


def _clean_text(text: str) -> str:
    value = str(text or "").replace("\xa0", " ")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


@lru_cache(maxsize=8)
def _parse_with_edgartools(html_text: str):
    try:
        from edgar.documents import ParserConfig, parse_html
    except Exception as exc:
        raise SectionNotFound(f"edgartools is unavailable: {exc}") from exc

    try:
        config = ParserConfig(
            detect_sections=True,
            form="10-K",
            table_extraction=False,
            detect_table_types=False,
            extract_table_relationships=False,
            extract_images=False,
        )
        return parse_html(html_text, config)
    except Exception as exc:
        raise SectionNotFound(f"edgartools could not parse filing HTML: {exc}") from exc


def _get_edgar_section(html_bytes: bytes, section_keys: tuple[str, ...]) -> tuple[str, dict[str, Any]]:
    html_text = _decode_html(html_bytes)
    doc = _parse_with_edgartools(html_text)
    available = []
    try:
        available = list(doc.get_available_sec_sections() or [])
    except Exception:
        available = []

    for key in section_keys:
        try:
            section = doc.get_sec_section(key, clean=True, include_subsections=False)
        except Exception:
            section = None
        text = _clean_text(section or "")
        if len(text) >= 100:
            info = {}
            try:
                info = dict(doc.get_sec_section_info(key) or {})
            except Exception:
                info = {}
            info.update({"source": "edgartools", "section_key": key, "available_sections": available})
            return text, info

    raise SectionNotFound(f"Section not found via edgartools. Available sections: {available[:20]}")


def locate_item1a_with_edgartools(html_bytes: bytes) -> tuple[str, dict[str, Any]]:
    return _get_edgar_section(
        html_bytes,
        (
            "part_i_item_1a",
            "item_1a",
            "item1a",
        ),
    )


def locate_item1_overview_with_edgartools(html_bytes: bytes) -> tuple[str, dict[str, Any]]:
    return _get_edgar_section(
        html_bytes,
        (
            "part_i_item_1",
            "item_1",
            "item1",
        ),
    )
