"""Amazon Comprehend enrichment for risk items.

Adds structured NLP fields to each risk entry:
  - entities:    [{"text", "type", "score"}]
  - key_phrases: [{"text", "score"}]
  - tags:        ["normalized_tag", ...]
"""

from __future__ import annotations

import re
from typing import Iterable

import boto3
import streamlit as st

_BATCH_SIZE = 25
_MAX_TEXT_BYTES = 4500


def _get_comprehend():
    region = st.secrets.get("COMPREHEND_REGION", st.secrets["AWS_REGION"])
    return boto3.client(
        "comprehend",
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=region,
    )


def _chunk(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _trim_text_bytes(text: str, max_bytes: int = _MAX_TEXT_BYTES) -> str:
    text = _clean_text(text)
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    raw = raw[:max_bytes]
    while raw:
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            raw = raw[:-1]
    return ""


def _normalize_tag(text: str) -> str:
    t = re.sub(r"[^\w\s]", "", _clean_text(text).lower())
    return re.sub(r"\s+", "_", t).strip("_")


def _batch_entities(client, texts: list[str]) -> tuple[dict[int, list[dict]], str]:
    entities_by_idx: dict[int, list[dict]] = {}
    offset = 0
    try:
        for chunk in _chunk(texts, _BATCH_SIZE):
            resp = client.batch_detect_entities(TextList=chunk, LanguageCode="en")
            for item in resp.get("ResultList", []):
                entities_by_idx[offset + item.get("Index", 0)] = item.get("Entities", [])
            for err in resp.get("ErrorList", []):
                entities_by_idx[offset + err.get("Index", 0)] = []
            offset += len(chunk)
        return entities_by_idx, ""
    except Exception as e:
        return {}, str(e)


def _batch_key_phrases(client, texts: list[str]) -> tuple[dict[int, list[dict]], str]:
    phrases_by_idx: dict[int, list[dict]] = {}
    offset = 0
    try:
        for chunk in _chunk(texts, _BATCH_SIZE):
            resp = client.batch_detect_key_phrases(TextList=chunk, LanguageCode="en")
            for item in resp.get("ResultList", []):
                phrases_by_idx[offset + item.get("Index", 0)] = item.get("KeyPhrases", [])
            for err in resp.get("ErrorList", []):
                phrases_by_idx[offset + err.get("Index", 0)] = []
            offset += len(chunk)
        return phrases_by_idx, ""
    except Exception as e:
        return {}, str(e)


def enrich_risks_with_comprehend(
    risks: list[dict],
    score_threshold: float = 0.8,
    max_entities: int = 3,
    max_key_phrases: int = 5,
) -> tuple[list[dict], dict]:
    """Enrich classified risks with Comprehend entities and key phrases.

    Returns:
      (enriched_risks, meta)
    """
    refs: list[tuple[int, int]] = []
    texts: list[str] = []

    for ci, cat in enumerate(risks):
        subs = cat.get("sub_risks", [])
        for si, sr in enumerate(subs):
            title = sr.get("title", "") if isinstance(sr, dict) else str(sr)
            cleaned = _trim_text_bytes(title)
            if not cleaned:
                continue
            refs.append((ci, si))
            texts.append(cleaned)

    if not texts:
        return risks, {"enabled": False, "processed": 0, "error": "No risk text to enrich."}

    try:
        client = _get_comprehend()
    except Exception as e:
        return risks, {"enabled": False, "processed": 0, "error": str(e)}

    entities_raw, ent_err = _batch_entities(client, texts)
    phrases_raw, phr_err = _batch_key_phrases(client, texts)

    # If both calls fail, return the original structure untouched.
    if ent_err and phr_err:
        return risks, {"enabled": False, "processed": 0, "error": f"entities={ent_err}; key_phrases={phr_err}"}

    enriched_count = 0
    for idx, (ci, si) in enumerate(refs):
        sr = risks[ci]["sub_risks"][si]
        if not isinstance(sr, dict):
            sr = {"title": str(sr)}
            risks[ci]["sub_risks"][si] = sr

        ents = []
        for e in entities_raw.get(idx, []):
            sc = float(e.get("Score", 0.0))
            if sc < score_threshold:
                continue
            text = _clean_text(e.get("Text", ""))
            if not text:
                continue
            ents.append({
                "text": text,
                "type": e.get("Type", "OTHER"),
                "score": round(sc, 3),
            })
            if len(ents) >= max_entities:
                break

        phrases = []
        for p in phrases_raw.get(idx, []):
            sc = float(p.get("Score", 0.0))
            if sc < score_threshold:
                continue
            text = _clean_text(p.get("Text", ""))
            if not text:
                continue
            phrases.append({
                "text": text,
                "score": round(sc, 3),
            })
            if len(phrases) >= max_key_phrases:
                break

        tags = []
        seen_tags = set()
        for ph in phrases:
            tag = _normalize_tag(ph["text"])
            if tag and tag not in seen_tags:
                seen_tags.add(tag)
                tags.append(tag)
        for ent in ents:
            tag = _normalize_tag(ent["text"])
            if tag and tag not in seen_tags:
                seen_tags.add(tag)
                tags.append(tag)

        sr["entities"] = ents
        sr["key_phrases"] = phrases
        sr["tags"] = tags[:8]
        if ents or phrases:
            enriched_count += 1

    meta = {
        "enabled": True,
        "processed": len(texts),
        "enriched": enriched_count,
        "errors": {
            "entities": ent_err,
            "key_phrases": phr_err,
        },
    }
    return risks, meta
