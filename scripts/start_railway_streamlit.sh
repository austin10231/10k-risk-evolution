#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_ROOT"

mkdir -p .streamlit

python3 - <<'PY'
import json
import os
from pathlib import Path

KEYS = [
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_REGION",
    "S3_BUCKET",
    "BEDROCK_REGION",
    "COMPREHEND_REGION",
    "MARKETAUX_API_TOKEN",
    "AGENTCORE_REGION",
    "AGENTCORE_ARN",
    "AGENTCORE_RUNTIME_ARN",
    "AGENTCORE_QUALIFIER",
    "AGENTCORE_RUNTIME_QUALIFIER",
    "COGNITO_AUTH_ENABLED",
    "COGNITO_DOMAIN",
    "COGNITO_CLIENT_ID",
    "COGNITO_CLIENT_SECRET",
    "COGNITO_REDIRECT_URI",
    "COGNITO_ALLOWED_CALLBACK_URLS",
    "COGNITO_SCOPE",
]

BOOL_KEYS = {"COGNITO_AUTH_ENABLED"}
ARRAY_KEYS = {"COGNITO_ALLOWED_CALLBACK_URLS"}


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


lines = []
for key in KEYS:
    raw = os.getenv(key)
    if raw is None:
        continue

    val = raw.strip()

    if key in BOOL_KEYS and val.lower() in {"true", "false"}:
        lines.append(f"{key} = {val.lower()}")
        continue

    if key in ARRAY_KEYS and val:
        try:
            arr = json.loads(val)
            if isinstance(arr, list):
                rendered = ", ".join(_quote(str(x)) for x in arr)
                lines.append(f"{key} = [{rendered}]")
                continue
        except Exception:
            pass

    lines.append(f"{key} = {_quote(raw)}")

secrets_path = Path(".streamlit/secrets.toml")
secrets_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"[railway] wrote {secrets_path} with {len(lines)} keys")
PY

if [ "${RAILWAY_SKIP_STREAMLIT:-0}" = "1" ]; then
  echo "[railway] RAILWAY_SKIP_STREAMLIT=1, skip launching Streamlit"
  exit 0
fi

exec streamlit run app.py \
  --server.address=0.0.0.0 \
  --server.port="${PORT:-8501}" \
  --server.headless=true
