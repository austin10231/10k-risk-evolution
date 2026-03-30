"""Minimal AgentCore HTTP runtime (no AgentCore SDK dependency)."""

from __future__ import annotations

import base64
import json
import os
import traceback
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

_RUN_AGENT = None


def _get_run_agent():
    global _RUN_AGENT
    if _RUN_AGENT is None:
        from agent import run_agent as _imported_run_agent
        _RUN_AGENT = _imported_run_agent
    return _RUN_AGENT


def _to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _coerce_payload(payload):
    if payload is None:
        return {}

    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = json.loads(payload.decode("utf-8", errors="ignore"))
        except Exception:
            return {}

    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                payload = parsed
            else:
                payload = {"prompt": payload}
        except Exception:
            payload = {"prompt": payload}

    if not isinstance(payload, dict):
        return {}

    # API Gateway/Lambda proxy-like event support.
    if "body" in payload:
        body = payload.get("body")
        if payload.get("isBase64Encoded") and isinstance(body, str):
            try:
                body = base64.b64decode(body).decode("utf-8", errors="ignore")
            except Exception:
                body = ""

        if isinstance(body, str):
            try:
                decoded = json.loads(body)
                if isinstance(decoded, dict):
                    payload = decoded
                else:
                    payload = {"prompt": body}
            except Exception:
                payload = {"prompt": body}
        elif isinstance(body, dict):
            payload = body

    # AgentCore HTTP passthrough is expected to send JSON body directly.
    candidate = payload.get("input", payload)
    if isinstance(candidate, dict):
        return candidate

    if isinstance(candidate, str):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {"prompt": candidate}

    return {}


def _invoke_logic(raw_payload):
    req = _coerce_payload(raw_payload)
    aws_ctx = req.get("_aws", {}) if isinstance(req, dict) else {}
    if isinstance(aws_ctx, dict):
        access_key = str(aws_ctx.get("aws_access_key_id", "")).strip()
        secret_key = str(aws_ctx.get("aws_secret_access_key", "")).strip()
        session_token = str(aws_ctx.get("aws_session_token", "")).strip()
        bedrock_region = str(aws_ctx.get("bedrock_region", "")).strip()
        if access_key and secret_key:
            os.environ["AWS_ACCESS_KEY_ID"] = access_key
            os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
            if session_token:
                os.environ["AWS_SESSION_TOKEN"] = session_token
            else:
                os.environ.pop("AWS_SESSION_TOKEN", None)
        if bedrock_region:
            os.environ["BEDROCK_REGION"] = bedrock_region

    user_query = req.get("user_query") or req.get("prompt") or ""
    company = req.get("company", "")
    year = _to_int(req.get("year", 0), default=0)
    risks = req.get("risks", [])
    compare_data = req.get("compare_data")

    print(
        "[runtime] parsed request meta:",
        json.dumps(
            {
                "has_company": bool(company),
                "year": year,
                "has_user_query": bool(user_query),
                "risk_count": len(risks) if isinstance(risks, list) else -1,
                "raw_keys": list(raw_payload.keys()) if isinstance(raw_payload, dict) else str(type(raw_payload)),
                "parsed_keys": list(req.keys()) if isinstance(req, dict) else [],
            },
            ensure_ascii=False,
        ),
    )

    run_agent = _get_run_agent()
    return run_agent(
        user_query=user_query,
        company=company,
        year=year,
        risks=risks,
        compare_data=compare_data,
    )


def handler(event, context=None):
    """Generic direct-call handler for local testing."""
    try:
        return _invoke_logic(event)
    except Exception as exc:
        err = {
            "error": str(exc),
            "type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        }
        print("[handler] failed", json.dumps(err, ensure_ascii=False))
        raise


class _RequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/ping":
            self._send_json(
                200,
                {
                    "status": "Healthy",
                    "time_of_last_update": int(time.time()),
                },
            )
            return
        self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        if self.path != "/invocations":
            self._send_json(404, {"error": "Not Found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception:
            length = 0

        raw_body = self.rfile.read(length) if length > 0 else b"{}"

        try:
            body = json.loads(raw_body.decode("utf-8", errors="ignore"))
        except Exception:
            body = {"prompt": raw_body.decode("utf-8", errors="ignore")}

        try:
            result = _invoke_logic(body)
            self._send_json(200, result if isinstance(result, dict) else {"result": result})
        except Exception as exc:
            err = {
                "error": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            }
            print("[runtime] invocation failed", json.dumps(err, ensure_ascii=False))
            self._send_json(500, err)

    def log_message(self, format, *args):
        # Keep logs concise in CloudWatch.
        return


# Backward-compatible aliases
invoke = handler
handle_request = handler


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.getenv("PORT", "8080"))
    print(f"[runtime] starting HTTP server on {host}:{port}")
    server = HTTPServer((host, port), _RequestHandler)
    server.serve_forever()
