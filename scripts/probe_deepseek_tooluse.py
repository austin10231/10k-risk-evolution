"""Quick capability probe: does Bedrock Converse `toolConfig` work on
``deepseek.v3-v1:0`` (the AGENT_MODEL_ID we picked for the ReAct
orchestrator in entry 32)?

Per AWS Bedrock docs not every inference profile supports tool use. If
DeepSeek V3.2 rejects ``toolConfig`` we need to fall back to Nova Pro
for the ReAct orchestrator and keep DeepSeek only for plain text. This
script prints a definitive yes/no per model — run it BEFORE landing the
batch-2 ReAct loop.

Usage::

    AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... \\
    AWS_REGION=us-west-1 BEDROCK_REGION=us-west-2 \\
    python scripts/probe_deepseek_tooluse.py

The script tests two models by default — DeepSeek V3.2 (the candidate)
and Nova Pro (the known-good control). Pass --models id1,id2 to test a
custom set.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List

import boto3

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_MODELS = [
    os.getenv("BEDROCK_AGENT_MODEL_ID") or "deepseek.v3-v1:0",
    os.getenv("BEDROCK_EXTRACTION_MODEL_ID") or "us.amazon.nova-pro-v1:0",
]

# Trivial fake tool — we don't actually want the LLM to "do" anything,
# we just want to see whether it (a) accepts the toolConfig argument and
# (b) is willing to emit a toolUse block in its response.
TOOL_SPECS = [
    {
        "toolSpec": {
            "name": "get_weather",
            "description": (
                "Fetch the current weather for a city. Returns temperature in Celsius, "
                "conditions, and humidity percentage."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name, e.g. 'Tokyo' or 'San Francisco'."},
                        "units": {"type": "string", "enum": ["celsius", "fahrenheit"], "default": "celsius"},
                    },
                    "required": ["city"],
                }
            },
        }
    }
]

PROMPT = (
    "I'm planning a trip to Tokyo tomorrow and I want to know what to pack. "
    "Can you check the current weather there for me?"
)


def _bedrock_client():
    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or "us-west-2"
    kwargs = {"region_name": region}
    ak = os.getenv("AWS_ACCESS_KEY_ID")
    sk = os.getenv("AWS_SECRET_ACCESS_KEY")
    st = os.getenv("AWS_SESSION_TOKEN")
    if ak and sk:
        kwargs["aws_access_key_id"] = ak
        kwargs["aws_secret_access_key"] = sk
        if st:
            kwargs["aws_session_token"] = st
    return boto3.client("bedrock-runtime", **kwargs)


def _walk_blocks(blocks: list) -> dict:
    """Summarize the assistant message contentBlocks for diagnostics."""
    out = {"text_blocks": [], "tool_uses": [], "other": []}
    for b in blocks or []:
        if not isinstance(b, dict):
            out["other"].append(repr(b))
            continue
        if "text" in b:
            t = str(b.get("text") or "").strip()
            if t:
                out["text_blocks"].append(t[:200])
        elif "toolUse" in b:
            tu = b.get("toolUse") or {}
            out["tool_uses"].append({
                "name": tu.get("name"),
                "toolUseId": tu.get("toolUseId"),
                "input": tu.get("input"),
            })
        else:
            out["other"].append(list(b.keys()))
    return out


def probe_model(client, model_id: str) -> dict:
    """Return a result dict describing whether ``model_id`` accepted the
    toolConfig and whether it produced a toolUse block."""
    print(f"\n=== probing {model_id} ===", flush=True)
    started = time.time()
    converse_kwargs = {
        "modelId": model_id,
        "messages": [{"role": "user", "content": [{"text": PROMPT}]}],
        "system": [{"text": "You are a helpful assistant. When the user needs current information you cannot know directly, call the appropriate tool."}],
        "inferenceConfig": {"maxTokens": 600, "temperature": 0.0, "topP": 1.0},
        "toolConfig": {"tools": TOOL_SPECS, "toolChoice": {"auto": {}}},
    }
    try:
        response = client.converse(**converse_kwargs)
    except Exception as exc:
        elapsed = time.time() - started
        msg = str(exc)
        verdict = "tool_use_NOT_supported" if (
            "ValidationException" in type(exc).__name__
            or "tool" in msg.lower()
            or "not support" in msg.lower()
        ) else "error_other"
        print(f"  ✗ FAILED ({elapsed:.1f}s): {type(exc).__name__}: {msg[:300]}", flush=True)
        return {
            "model_id": model_id,
            "verdict": verdict,
            "supports_tool_use": False,
            "error": f"{type(exc).__name__}: {msg}",
            "elapsed_s": round(elapsed, 2),
        }

    elapsed = time.time() - started
    stop_reason = response.get("stopReason", "")
    output_msg = response.get("output", {}).get("message", {})
    content_blocks = output_msg.get("content", []) or []
    summary = _walk_blocks(content_blocks)
    has_tool_use = bool(summary["tool_uses"])
    usage = response.get("usage", {})

    if has_tool_use:
        verdict = "tool_use_supported_AND_invoked"
    elif stop_reason == "tool_use":
        verdict = "stop_reason_tool_use_but_no_block"
    else:
        verdict = "tool_use_supported_but_LLM_chose_text"

    print(f"  ✓ OK ({elapsed:.1f}s)  stopReason={stop_reason!r}  verdict={verdict}", flush=True)
    print(f"    blocks: text={len(summary['text_blocks'])}  toolUse={len(summary['tool_uses'])}  other={len(summary['other'])}", flush=True)
    if summary["tool_uses"]:
        for tu in summary["tool_uses"]:
            print(f"    toolUse: name={tu['name']!r}  input={tu['input']!r}", flush=True)
    if summary["text_blocks"]:
        print(f"    first text block (≤200 chars): {summary['text_blocks'][0]!r}", flush=True)
    print(f"    usage: {usage}", flush=True)

    return {
        "model_id": model_id,
        "verdict": verdict,
        "supports_tool_use": True,
        "stop_reason": stop_reason,
        "tool_uses": summary["tool_uses"],
        "text_blocks_preview": summary["text_blocks"],
        "usage": usage,
        "elapsed_s": round(elapsed, 2),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Probe Bedrock Converse toolConfig support per model.")
    p.add_argument("--models", default="", help="Comma-separated list of modelIds to test (default: DeepSeek V3.2 + Nova Pro).")
    p.add_argument("--report", default=str(ROOT / "scripts" / "probe_deepseek_tooluse.report.json"))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()] if args.models else DEFAULT_MODELS

    print(f"BEDROCK_REGION = {os.getenv('BEDROCK_REGION') or os.getenv('AWS_REGION') or 'us-west-2'}")
    print(f"AWS_ACCESS_KEY_ID = {'<set>' if os.getenv('AWS_ACCESS_KEY_ID') else '<unset>'}")
    print(f"models to probe = {models}")

    if not (os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")):
        print("[fatal] AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in env.", file=sys.stderr)
        return 2

    client = _bedrock_client()
    results = []
    for m in models:
        results.append(probe_model(client, m))

    print("\n=== SUMMARY ===")
    for r in results:
        flag = "✓" if r["supports_tool_use"] else "✗"
        print(f"  {flag} {r['model_id']}  →  {r['verdict']}")

    try:
        Path(args.report).write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"\n[report] wrote {args.report}")
    except Exception as exc:
        print(f"[report] could not write: {exc}", file=sys.stderr)

    return 0 if all(r["supports_tool_use"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
