"""HWPX real-like SANDBOX_ONLY batch API route.

HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-API-BATCH-12

Endpoints:
    GET  /api/hwpx/form-autofill/batch/health
    POST /api/hwpx/form-autofill/batch/real-like-sandbox
    GET  /api/hwpx/form-autofill/batch/result/{batchId}

The implementation is intentionally SANDBOX_ONLY and uses sanitized real-like
fixtures for API-level smoke. It never accepts real user file execution.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    _FASTAPI_AVAILABLE = True
except ImportError:  # pragma: no cover - optional runtime
    _FASTAPI_AVAILABLE = False
    FastAPI = object  # type: ignore
    BaseModel = object  # type: ignore

from hwpx.pipeline import form_auto_fill_real_like_sandbox_batch as batch_runner

SCHEMA_VERSION = "hwpx_form_autofill_real_like_api_batch_v1"
MODE = "SANDBOX_ONLY"
SOURCE_MUTATION_ALLOWED = False

STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_BLOCKED = "BLOCKED"

BLOCKED_NON_SANDBOX_MODE = "BLOCKED_NON_SANDBOX_MODE"
BLOCKED_REAL_USER_FILE = "BLOCKED_REAL_USER_FILE"
FAILED_READBACK = "FAILED_READBACK"
FAILED_UNEXPECTED_MUTATION = "FAILED_UNEXPECTED_MUTATION"
FAILED_SOURCE_MUTATION = "FAILED_SOURCE_MUTATION"
FAILED_SECURITY_LEAK = "FAILED_SECURITY_LEAK"
FAILED_OUTPUT_EQUALS_SOURCE = "FAILED_OUTPUT_EQUALS_SOURCE"

_RESULT_STORE: dict[str, dict[str, Any]] = {}
_PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)
_ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/]|/(home|tmp|var|Users)/)")
_RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)


BatchRunner = Callable[[int], dict[str, Any]]


def _request_id() -> str:
    return "req_" + uuid.uuid4().hex[:12]


def _batch_id(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    return "batch_" + digest


def _base_response(batch_id: str = "", request_id: str | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "requestId": request_id or _request_id(),
        "batchId": batch_id,
        "mode": MODE,
        "status": STATUS_SUCCESS,
        "sourceMutationAllowed": SOURCE_MUTATION_ALLOWED,
        "summary": {
            "limit": 0,
            "processed": 0,
            "ready": 0,
            "writtenFiles": 0,
            "blockedFiles": 0,
            "failedFiles": 0,
            "readbackFail": 0,
            "unexpectedMutation": 0,
            "sourceMutation": 0,
        },
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
            "aiCalled": False,
            "ocrCalled": False,
            "hancomRequired": False,
        },
        "fileResults": [],
        "blockedResults": [],
        "warnings": [],
        "errors": [],
    }


def _blocked(code: str, message: str, batch_id: str = "", request_id: str | None = None) -> dict[str, Any]:
    response = _base_response(batch_id=batch_id, request_id=request_id)
    response["status"] = STATUS_BLOCKED
    response["errors"] = [{"code": code, "message": message}]
    response["warnings"] = ["WARN_SANDBOX_ONLY"]
    return response


def _failed(code: str, message: str, batch_id: str = "", request_id: str | None = None) -> dict[str, Any]:
    response = _base_response(batch_id=batch_id, request_id=request_id)
    response["status"] = STATUS_FAILED
    response["errors"] = [{"code": code, "message": message}]
    response["warnings"] = ["WARN_SANDBOX_ONLY"]
    return response


def _sanitize_text(value: str) -> str:
    value = _PII_RE.sub("[MASKED]", value)
    value = _ABS_PATH_RE.sub("[PATH]", value)
    value = _RAW_FILENAME_RE.sub("[FILENAME]", value)
    return value


def _sanitize(obj: Any, depth: int = 0) -> Any:
    if depth > 10:
        return obj
    if isinstance(obj, str):
        return _sanitize_text(obj)
    if isinstance(obj, dict):
        return {str(k): _sanitize(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v, depth + 1) for v in obj]
    return obj


def _response_has_leak(response: dict[str, Any]) -> bool:
    text = json.dumps(response, ensure_ascii=False)
    return bool(_ABS_PATH_RE.search(text) or _RAW_FILENAME_RE.search(text) or _PII_RE.search(text))


def _default_runner(limit: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        input_dir = batch_runner.create_batch_fixture_dir(tmp / "input", limit)
        return batch_runner.run_real_like_sandbox_batch(
            input_dir=input_dir,
            output_dir=tmp / "out",
            limit=limit,
            sandbox_only=True,
            mask_pii=True,
            fail_on_source_mutation=True,
            fail_on_readback_fail=True,
            fail_on_unexpected_mutation=True,
        )


def _normalize_batch_result(raw: dict[str, Any], limit: int, request_id: str, batch_id: str) -> dict[str, Any]:
    summary = raw.get("summary", {})
    security = {
        "piiLeak": int(summary.get("piiLeak", 0)),
        "rawPathLeak": int(summary.get("rawPathLeak", 0)),
        "rawFilenameLeak": int(summary.get("rawFilenameLeak", 0)),
        "aiCalled": False,
        "ocrCalled": False,
        "hancomRequired": False,
    }
    response = _base_response(batch_id=batch_id, request_id=request_id)
    response["summary"] = {
        "limit": limit,
        "processed": int(summary.get("processed", 0)),
        "ready": int(summary.get("ready", 0)),
        "writtenFiles": int(summary.get("writtenFiles", 0)),
        "blockedFiles": int(summary.get("blockedFiles", 0)),
        "failedFiles": int(summary.get("failedFiles", 0)),
        "readbackFail": int(summary.get("readbackFail", 0)),
        "unexpectedMutation": int(summary.get("unexpectedMutation", 0)),
        "sourceMutation": int(summary.get("sourceMutation", 0)),
    }
    response["security"] = security
    response["fileResults"] = [
        {
            "sampleId": str(row.get("sampleId", "")),
            "status": str(row.get("status", "")),
            "sourceHashChanged": bool(row.get("sourceHashChanged", False)),
            "sourceMtimeChanged": bool(row.get("sourceMtimeChanged", False)),
            "writtenFields": int(row.get("writtenFields", 0)),
            "readbackPass": int(row.get("readbackPass", 0)),
            "readbackFail": int(row.get("readbackFail", 0)),
            "unexpectedMutation": int(row.get("unexpectedMutation", 0)),
            "finalExportEnabled": bool(row.get("finalExportEnabled", False)),
        }
        for row in raw.get("fileResults", [])
    ]
    response["blockedResults"] = [
        {
            "sampleId": str(row.get("sampleId", "")),
            "status": str(row.get("status", "")),
            "blockedReason": str(row.get("blockedReason", "")),
            "writtenFields": int(row.get("writtenFields", 0)),
        }
        for row in raw.get("blockedResults", [])
    ]
    response["warnings"] = list(raw.get("warnings", ["WARN_SANDBOX_ONLY"]))
    return _sanitize(response)


def _apply_failure_rules(response: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    summary = response["summary"]
    security = response["security"]
    error_code = ""
    if raw.get("output_path") and raw.get("source_path") and raw.get("output_path") == raw.get("source_path"):
        error_code = FAILED_OUTPUT_EQUALS_SOURCE
    elif summary["readbackFail"] > 0:
        error_code = FAILED_READBACK
    elif summary["unexpectedMutation"] > 0:
        error_code = FAILED_UNEXPECTED_MUTATION
    elif summary["sourceMutation"] > 0:
        error_code = FAILED_SOURCE_MUTATION
    elif security["piiLeak"] > 0 or security["rawPathLeak"] > 0 or security["rawFilenameLeak"] > 0:
        error_code = FAILED_SECURITY_LEAK

    if error_code:
        response["status"] = STATUS_FAILED
        response["errors"] = [{"code": error_code, "message": error_code}]
    else:
        response["status"] = STATUS_SUCCESS
        response["errors"] = []
    return response


def call_health() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "requestId": _request_id(),
        "batchId": "",
        "mode": MODE,
        "status": STATUS_SUCCESS,
        "sourceMutationAllowed": SOURCE_MUTATION_ALLOWED,
        "data": {
            "pipelineReady": True,
            "supportedLimits": [1, 5, 10],
            "endpoints": [
                "GET /api/hwpx/form-autofill/batch/health",
                "POST /api/hwpx/form-autofill/batch/real-like-sandbox",
                "GET /api/hwpx/form-autofill/batch/result/{batchId}",
            ],
        },
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
            "aiCalled": False,
            "ocrCalled": False,
            "hancomRequired": False,
        },
        "warnings": ["WARN_SANDBOX_ONLY", "WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY"],
        "errors": [],
    }


def call_real_like_sandbox(payload: dict[str, Any] | None = None, runner: BatchRunner | None = None) -> dict[str, Any]:
    payload = payload or {}
    request_id = _request_id()
    batch_id = _batch_id(payload)
    mode = payload.get("mode", MODE)
    if mode != MODE:
        return _blocked(BLOCKED_NON_SANDBOX_MODE, "mode must be SANDBOX_ONLY", batch_id, request_id)
    if payload.get("realUserFile") is True or payload.get("realUserFileUsed") is True:
        return _blocked(BLOCKED_REAL_USER_FILE, "real user files are not allowed", batch_id, request_id)

    limit = int(payload.get("limit", 10))
    if limit not in (1, 5, 10):
        limit = 10
    runner = runner or _default_runner
    raw = runner(limit)
    response = _normalize_batch_result(raw, limit, request_id, batch_id)
    response = _apply_failure_rules(response, raw)
    response = _sanitize(response)
    if _response_has_leak(response):
        response = _failed(FAILED_SECURITY_LEAK, "response leak detected", batch_id, request_id)
    _RESULT_STORE[batch_id] = response
    return response


def call_result(batch_id: str) -> dict[str, Any]:
    return _RESULT_STORE.get(batch_id) or _blocked("BLOCKED_BATCH_NOT_FOUND", "batch result not found", batch_id)


if _FASTAPI_AVAILABLE:
    class BatchRequest(BaseModel):
        limit: int = 10
        mode: str = MODE
        realUserFile: bool = False
        realUserFileUsed: bool = False


def create_app() -> Any:
    if not _FASTAPI_AVAILABLE:
        return None
    app = FastAPI(title="HWPX real-like batch API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/hwpx/form-autofill/batch/health")
    def health():
        return call_health()

    @app.post("/api/hwpx/form-autofill/batch/real-like-sandbox")
    def real_like_sandbox(req: BatchRequest):
        payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
        return call_real_like_sandbox(payload)

    @app.get("/api/hwpx/form-autofill/batch/result/{batch_id}")
    def result(batch_id: str):
        return call_result(batch_id)

    return app


app = create_app()
