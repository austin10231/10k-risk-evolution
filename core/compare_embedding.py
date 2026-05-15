"""Embedding service used by the Compare hybrid scorer.

Strategy
--------
- Use AWS Bedrock `amazon.titan-embed-text-v2:0` (the strongest text
  embedding currently in Bedrock; outputs an L2-normalised 1024-dim
  vector).
- Cache vectors in S3 under `compare_embeddings/<model>/<sha1>.json`
  so subsequent Compare runs are free.
- Keep a small in-process LRU as well so a single Compare request
  doesn't re-fetch from S3 for the same title twice.
- Degrade gracefully: if Bedrock or S3 isn't reachable, return None and
  the comparator falls back to the lexical-only formula.

The module is intentionally lazy: importing it doesn't open a Bedrock
client; clients are constructed on first use.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections import OrderedDict
from typing import Callable, List, Optional, Tuple

_MODEL_ID = os.getenv("COMPARE_EMBED_MODEL", "amazon.titan-embed-text-v2:0")
_EMBED_DIMS = int(os.getenv("COMPARE_EMBED_DIMS", "1024") or 1024)
_S3_PREFIX = os.getenv("COMPARE_EMBED_S3_PREFIX", "compare_embeddings").strip(
    "/"
)
_ENABLED = os.getenv("COMPARE_EMBED_ENABLED", "1").strip() not in {"0", "false", "False", ""}

_BEDROCK_CLIENT = None
_S3_CLIENT = None
_CLIENT_LOCK = threading.Lock()

_MEM_CACHE: "OrderedDict[str, Optional[List[float]]]" = OrderedDict()
_MEM_CACHE_MAX = 2048
_MEM_LOCK = threading.Lock()


def is_enabled() -> bool:
    return bool(_ENABLED)


# ---------- key derivation ----------

def _cache_key(text: str) -> str:
    h = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()
    safe_model = _MODEL_ID.replace("/", "_").replace(":", "_")
    return f"{_S3_PREFIX}/{safe_model}/{h}.json"


# ---------- client construction ----------

def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default)


def _bedrock_client():
    global _BEDROCK_CLIENT
    if _BEDROCK_CLIENT is not None:
        return _BEDROCK_CLIENT
    with _CLIENT_LOCK:
        if _BEDROCK_CLIENT is not None:
            return _BEDROCK_CLIENT
        try:
            import boto3  # boto3 is already in requirements.txt
        except Exception:
            return None
        region = _env("BEDROCK_REGION", "us-west-2")
        kwargs = {"region_name": region}
        ak = _env("AWS_ACCESS_KEY_ID")
        sk = _env("AWS_SECRET_ACCESS_KEY")
        st = _env("AWS_SESSION_TOKEN")
        if ak and sk:
            kwargs["aws_access_key_id"] = ak
            kwargs["aws_secret_access_key"] = sk
            if st:
                kwargs["aws_session_token"] = st
        try:
            _BEDROCK_CLIENT = boto3.client("bedrock-runtime", **kwargs)
        except Exception:
            _BEDROCK_CLIENT = None
        return _BEDROCK_CLIENT


def _s3_client_pair() -> Tuple[Optional[object], str]:
    """Return (client, bucket). Either may be empty/None."""
    global _S3_CLIENT
    bucket = _env("S3_BUCKET").strip()
    if not bucket:
        return None, ""
    if _S3_CLIENT is not None:
        return _S3_CLIENT, bucket
    with _CLIENT_LOCK:
        if _S3_CLIENT is not None:
            return _S3_CLIENT, bucket
        try:
            import boto3
        except Exception:
            return None, bucket
        region = _env("AWS_REGION", "us-west-1") or "us-west-1"
        kwargs = {"region_name": region}
        ak = _env("AWS_ACCESS_KEY_ID")
        sk = _env("AWS_SECRET_ACCESS_KEY")
        st = _env("AWS_SESSION_TOKEN")
        if ak and sk:
            kwargs["aws_access_key_id"] = ak
            kwargs["aws_secret_access_key"] = sk
            if st:
                kwargs["aws_session_token"] = st
        try:
            _S3_CLIENT = boto3.client("s3", **kwargs)
        except Exception:
            _S3_CLIENT = None
        return _S3_CLIENT, bucket


# ---------- S3 cache I/O ----------

def _read_cached(text: str) -> Optional[List[float]]:
    client, bucket = _s3_client_pair()
    if client is None or not bucket:
        return None
    key = _cache_key(text)
    try:
        obj = client.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
    except Exception:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    vec = payload.get("embedding") if isinstance(payload, dict) else None
    if isinstance(vec, list) and vec and all(isinstance(x, (int, float)) for x in vec):
        return [float(x) for x in vec]
    return None


def _write_cached(text: str, vec: List[float]) -> None:
    client, bucket = _s3_client_pair()
    if client is None or not bucket:
        return
    key = _cache_key(text)
    payload = {
        "model": _MODEL_ID,
        "dims": len(vec),
        "embedding": vec,
    }
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(payload).encode("utf-8"),
            ContentType="application/json",
        )
    except Exception:
        return


# ---------- Bedrock invocation ----------

def _invoke_titan(text: str) -> Optional[List[float]]:
    client = _bedrock_client()
    if client is None:
        return None
    body = {
        "inputText": text,
        "dimensions": _EMBED_DIMS,
        "normalize": True,
    }
    try:
        resp = client.invoke_model(
            modelId=_MODEL_ID,
            body=json.dumps(body).encode("utf-8"),
            contentType="application/json",
            accept="application/json",
        )
        raw = resp.get("body")
        if hasattr(raw, "read"):
            data = raw.read()
        else:
            data = raw
        parsed = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
    except Exception:
        return None
    vec = parsed.get("embedding") if isinstance(parsed, dict) else None
    if not isinstance(vec, list) or not vec:
        return None
    try:
        return [float(x) for x in vec]
    except Exception:
        return None


# ---------- public API ----------

def embed_one(text: str) -> Optional[List[float]]:
    """Return the embedding vector for `text`, or None on any failure.

    Order: in-process LRU → S3 cache → Bedrock invoke → write back.
    """
    if not _ENABLED:
        return None
    if not text or not str(text).strip():
        return None
    key = str(text).strip()
    with _MEM_LOCK:
        if key in _MEM_CACHE:
            _MEM_CACHE.move_to_end(key)
            return _MEM_CACHE[key]

    cached = _read_cached(key)
    if cached is not None:
        _store_mem(key, cached)
        return cached

    fresh = _invoke_titan(key)
    if fresh is None:
        _store_mem(key, None)
        return None
    _write_cached(key, fresh)
    _store_mem(key, fresh)
    return fresh


def _store_mem(key: str, vec: Optional[List[float]]) -> None:
    with _MEM_LOCK:
        _MEM_CACHE[key] = vec
        _MEM_CACHE.move_to_end(key)
        while len(_MEM_CACHE) > _MEM_CACHE_MAX:
            _MEM_CACHE.popitem(last=False)


def warm(titles: List[str]) -> int:
    """Pre-fetch embeddings for a batch of titles. Returns the count
    of titles whose embedding is now available (whether from cache or
    fresh invoke). Useful from the Compare endpoint so the per-pair
    score loop hits warm caches.
    """
    if not _ENABLED:
        return 0
    seen = set()
    ok = 0
    for t in titles:
        key = str(t or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        if embed_one(key) is not None:
            ok += 1
    return ok


def build_lookup() -> Callable[[str], Optional[List[float]]]:
    """Return a callable suitable for passing to `compare_risks` as
    `embed_lookup`. The callable returns None when embeddings are
    disabled or unavailable, which makes the comparator fall back to
    the lexical formula cleanly.
    """
    if not _ENABLED:
        return lambda _t: None

    def _lookup(text: str) -> Optional[List[float]]:
        return embed_one(text)

    return _lookup
