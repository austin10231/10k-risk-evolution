"""SEC filing section locators backed by edgartools, with no network calls."""

from __future__ import annotations

import re
import warnings
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


def _normalize_heading(text: str) -> str:
    value = _clean_text(text).lower()
    value = value.replace("\u00a0", " ")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


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


@lru_cache(maxsize=8)
def _parse_with_sec_parser(html_text: str) -> tuple[tuple[str, str], ...]:
    try:
        from sec_parser import Edgar10QParser
    except Exception as exc:
        raise SectionNotFound(f"sec-parser is unavailable: {exc}") from exc

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            elements = Edgar10QParser().parse(
                html_text,
                unwrap_elements=True,
                include_containers=False,
                include_irrelevant_elements=False,
            )
    except Exception as exc:
        raise SectionNotFound(f"sec-parser could not parse filing HTML: {exc}") from exc

    rows: list[tuple[str, str]] = []
    for element in elements or []:
        text = _clean_text(getattr(element, "text", "") or "")
        if not text:
            continue
        rows.append((type(element).__name__, text))
    if not rows:
        raise SectionNotFound("sec-parser returned no semantic text elements.")
    return tuple(rows)


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


def _looks_like_start(text: str, section: str) -> bool:
    heading = _normalize_heading(text)
    if section == "item1a":
        return bool(re.match(r"^item 1a?\b", heading) or re.match(r"^item 1 a\b", heading)) and "risk" in heading
    if section == "item1":
        return bool(re.match(r"^item 1\b", heading)) and not (
            re.match(r"^item 1a\b", heading) or re.match(r"^item 1 a\b", heading)
        )
    return False


def _looks_like_end(text: str, section: str) -> bool:
    heading = _normalize_heading(text)
    if section == "item1a":
        return bool(
            re.match(r"^item 1b\b", heading)
            or re.match(r"^item 1 b\b", heading)
            or re.match(r"^item 1c\b", heading)
            or re.match(r"^item 1 c\b", heading)
            or re.match(r"^item 2\b", heading)
            or re.match(r"^part ii\b", heading)
        )
    if section == "item1":
        return bool(re.match(r"^item 1a\b", heading) or re.match(r"^item 1 a\b", heading))
    return False


def _locate_with_sec_parser(html_bytes: bytes, section: str) -> tuple[str, dict[str, Any]]:
    html_text = _decode_html(html_bytes)
    rows = _parse_with_sec_parser(html_text)

    start_idx = None
    for idx, (kind, text) in enumerate(rows):
        if kind == "IntroductorySectionElement":
            continue
        if _looks_like_start(text, section):
            start_idx = idx
            break
    if start_idx is None:
        raise SectionNotFound(f"{section} start not found via sec-parser.")

    end_idx = len(rows)
    for idx in range(start_idx + 1, len(rows)):
        kind, text = rows[idx]
        if kind == "IntroductorySectionElement":
            continue
        if _looks_like_end(text, section):
            end_idx = idx
            break

    parts = [text for _kind, text in rows[start_idx:end_idx]]
    located = _clean_text("\n\n".join(parts))
    if len(located) < 100:
        raise SectionNotFound(f"{section} section was too short via sec-parser.")

    return located, {
        "source": "sec-parser",
        "section": section,
        "start_index": start_idx,
        "end_index": end_idx,
    }


def locate_item1a_with_sec_parser(html_bytes: bytes) -> tuple[str, dict[str, Any]]:
    return _locate_with_sec_parser(html_bytes, "item1a")


def locate_item1_overview_with_sec_parser(html_bytes: bytes) -> tuple[str, dict[str, Any]]:
    return _locate_with_sec_parser(html_bytes, "item1")
