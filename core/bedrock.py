"""AWS Bedrock runtime helpers for shared extraction code."""

import os
import boto3

BEDROCK_CLAUDE_OPUS_47_MODEL_ID = "anthropic.claude-opus-4-7"
MODEL_ID = BEDROCK_CLAUDE_OPUS_47_MODEL_ID


def _secret(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default)


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
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0, "topP": 1.0},
    )
    return response["output"]["message"]["content"][0]["text"].strip()
