"""AWS Bedrock runtime helpers for shared extraction code.

This module backs the *extraction* path (risk extraction, classification,
RPI scoring). The agent-chat path lives in ``agentcore_deploy/agent.py``
and uses a different default model. See PROJECT_CHANGELOG_CN.md entry 32
for the dual-model split rationale.
"""

import json
import os
import boto3


def _secret(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default)


# Default Bedrock model used by every extraction-side invocation in this
# module (and by the few extraction-style call sites inside
# ``agentcore_deploy/agent.py`` that delegate here). Override with
# ``BEDROCK_EXTRACTION_MODEL_ID``. The legacy ``MODEL_ID`` alias is kept so
# any old import (e.g. ``from core.bedrock import MODEL_ID``) keeps working.
EXTRACTION_MODEL_ID = _secret("BEDROCK_EXTRACTION_MODEL_ID", "us.amazon.nova-pro-v1:0")
MODEL_ID = EXTRACTION_MODEL_ID
# Back-compat: external callers historically imported this name.
BEDROCK_CLAUDE_OPUS_47_MODEL_ID = EXTRACTION_MODEL_ID


def get_extraction_model_id() -> str:
    """Public accessor so other modules can mirror the extraction modelId
    (e.g. when reporting it in chat context). Reads env each call so a
    runtime override (Railway/Lambda redeploy) takes effect without
    re-importing the module."""
    return _secret("BEDROCK_EXTRACTION_MODEL_ID", EXTRACTION_MODEL_ID)


def _get_bedrock():
    region = _secret("BEDROCK_REGION") or _secret("AWS_REGION", "us-west-2")
    kwargs = {"region_name": region}
    access_key = _secret("AWS_ACCESS_KEY_ID")
    secret_key = _secret("AWS_SECRET_ACCESS_KEY")
    session_token = _secret("AWS_SESSION_TOKEN")
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token
    return boto3.client("bedrock-runtime", **kwargs)


def _invoke(prompt, max_tokens=1024):
    client = _get_bedrock()
    response = client.converse(
        modelId=get_extraction_model_id(),
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0, "topP": 1.0},
    )
    return response["output"]["message"]["content"][0]["text"].strip()


def _strip_json_fences(text: str) -> str:
    return str(text or "").replace("```json", "").replace("```", "").strip()


def _extract_json_from_text(text: str):
    stripped = _strip_json_fences(text)
    try:
        return json.loads(stripped)
    except Exception:
        pass
    for left, right in (("{", "}"), ("[", "]")):
        start = stripped.find(left)
        end = stripped.rfind(right)
        if start >= 0 and end > start:
            try:
                return json.loads(stripped[start : end + 1])
            except Exception:
                pass
    return None


def invoke_with_schema(
    prompt: str,
    schema: dict,
    max_tokens: int = 1024,
    *,
    tool_name: str = "structured_output",
    tool_description: str = "Return the requested structured JSON payload.",
):
    client = _get_bedrock()
    response = client.converse(
        modelId=get_extraction_model_id(),
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0, "topP": 1.0},
        toolConfig={
            "tools": [
                {
                    "toolSpec": {
                        "name": tool_name,
                        "description": tool_description,
                        "inputSchema": {"json": schema},
                    }
                }
            ],
            "toolChoice": {"tool": {"name": tool_name}},
        },
    )

    content = response.get("output", {}).get("message", {}).get("content", [])
    for block in content:
        tool_use = block.get("toolUse") if isinstance(block, dict) else None
        if isinstance(tool_use, dict) and tool_use.get("name") == tool_name:
            return tool_use.get("input")

    for block in content:
        text = block.get("text") if isinstance(block, dict) else ""
        parsed = _extract_json_from_text(text)
        if parsed is not None:
            return parsed

    raise RuntimeError("Bedrock Converse did not return structured tool output")
