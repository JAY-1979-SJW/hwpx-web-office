"""
HWPX-FORM-AUTO-FILL-WRITER-API-ROUTE-AND-FRONTEND-07

FastAPI route — HWPX 자동작성 파이프라인 API.
기존 form_recommend_server.py 패턴을 따른다.

엔드포인트:
    GET  /api/hwpx/form-autofill/health
    POST /api/hwpx/form-autofill/e2e-smoke
    POST /api/hwpx/form-autofill/write-sandbox
    POST /api/hwpx/form-autofill/download-review
    POST /api/hwpx/form-autofill/final-export

실행:
    uvicorn scripts.ops.hwpx_form_autofill_api_route:app --reload --port 8766

SANDBOX_ONLY / sourceMutationAllowed=false 불변.
raw path / filename / PII 원문 응답 노출 금지.
AI API / OCR / Hancom 필수 의존 금지.
"""

from __future__ import annotations

import hashlib
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    FastAPI = object  # type: ignore
    BaseModel = object  # type: ignore

SCHEMA_VERSION = "hwpx_form_autofill_api_v1"
MODE = "SANDBOX_ONLY"

_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")


def _req_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


def _success(data: dict, warnings: list[str] | None = None) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "requestId": _req_id(),
        "status": "SUCCESS",
        "mode": MODE,
        "sourceMutationAllowed": False,
        "data": data,
        "warnings": warnings or [],
        "errors": [],
    }


def _failed(errors: list[dict], warnings: list[str] | None = None) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "requestId": _req_id(),
        "status": "FAILED",
        "mode": MODE,
        "sourceMutationAllowed": False,
        "data": {},
        "warnings": warnings or [],
        "errors": errors,
    }


def _sanitize(obj: Any, depth: int = 0) -> Any:
    """응답에서 raw path / filename / PII 패턴 제거."""
    if depth > 10:
        return obj
    if isinstance(obj, str):
        s = obj
        s = _PII_RE.sub("[MASKED]", s)
        # raw absolute path 제거
        for kw in ("C:\\", "C:/", "/home/", "/tmp/", "/var/", "/Users/"):
            if kw in s:
                s = hashlib.sha256(s.encode()).hexdigest()[:16]
                break
        return s
    if isinstance(obj, dict):
        return {k: _sanitize(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v, depth + 1) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

if _FASTAPI_AVAILABLE:
    class WriteSandboxRequest(BaseModel):
        approvalResultDict: dict = {}
        formId: str = ""
        dryRun: bool = False

    class DownloadReviewRequest(BaseModel):
        writerResultDict: dict
        formId: str = ""

    class FinalExportRequest(BaseModel):
        downloadPayloadDict: dict
        decisionResultDict: dict
        formId: str = ""
        formTitle: str = ""

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

def create_app() -> Any:
    if not _FASTAPI_AVAILABLE:
        return None

    app = FastAPI(title="HWPX 자동작성 API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/hwpx/form-autofill/health")
    def health():
        return _success({
            "mode": MODE,
            "sourceMutationAllowed": False,
            "pipelineReady": True,
            "stages": [
                "recommend", "catalog", "uploadParser", "mapping",
                "reviewPanel", "humanApproval", "sandboxWriter",
                "readbackHardening", "downloadReview", "finalExportGate",
            ],
        })

    @app.post("/api/hwpx/form-autofill/e2e-smoke")
    def e2e_smoke():
        from hwpx.pipeline.form_auto_fill_e2e_smoke import run_e2e_smoke
        try:
            with tempfile.TemporaryDirectory() as td:
                result = run_e2e_smoke(Path(td))
            safe = _sanitize(result)
            if safe.get("overallVerdict") == "PASS_E2E_SMOKE":
                return _success(safe, warnings=["WARN_SYNTHETIC_SCENARIO_ONLY", "WARN_SANDBOX_ONLY"])
            else:
                return _failed([{"code": "E2E_SMOKE_FAILED", "message": safe.get("overallVerdict", "")}])
        except Exception as e:
            return _failed([{"code": "INTERNAL_ERROR", "message": str(e)}])

    @app.post("/api/hwpx/form-autofill/write-sandbox")
    def write_sandbox(req: WriteSandboxRequest):
        from hwpx.pipeline.form_writer_ui_connect import (
            build_ui_connect_payload, _derive_approval_status, STATUS_READY,
        )
        approval_dict = req.approvalResultDict

        # READY_FOR_WRITER gate 검증
        status = _derive_approval_status(approval_dict)
        ui_payload = build_ui_connect_payload(approval_dict, form_id=req.formId)

        if status != STATUS_READY:
            return _failed(
                [{"code": "WRITER_BLOCKED", "message": f"approvalStatus={status}"}],
                warnings=["WARN_SANDBOX_ONLY"],
            )

        # dry_run 모드로 sandbox 실행
        from hwpx.pipeline.approval_gate import ApprovalResult, ApprovedField
        # approval_dict에서 ApprovalResult 재구성
        approved = [
            ApprovedField(
                fieldKey=f.get("fieldKey", ""),
                label=f.get("label", ""),
                value=f.get("value", ""),
                originalValue=f.get("originalValue", ""),
                action=f.get("action", "CONFIRM_FIELD"),
                sourceZone=f.get("sourceZone", ""),
                confidence=float(f.get("confidence", 0.8)),
                writerEligible=f.get("writerEligible", True),
            )
            for f in approval_dict.get("approvedFields", [])
            if f.get("writerEligible", True)
        ]

        safe_payload = _sanitize(ui_payload)
        return _success(
            {
                "uiPayload": safe_payload,
                "eligibleFieldCount": len(approved),
                "mode": MODE,
                "sourceMutationAllowed": False,
                "dryRun": True,
            },
            warnings=["WARN_SANDBOX_ONLY", "WARN_DRY_RUN_ONLY"],
        )

    @app.post("/api/hwpx/form-autofill/download-review")
    def download_review(req: DownloadReviewRequest):
        from hwpx.pipeline.form_writer_download_review import build_download_payload
        try:
            payload = build_download_payload(req.writerResultDict, form_id=req.formId)
            safe = _sanitize(payload)
            return _success(safe, warnings=["WARN_SANDBOX_ONLY"])
        except Exception as e:
            return _failed([{"code": "DOWNLOAD_REVIEW_ERROR", "message": str(e)}])

    @app.post("/api/hwpx/form-autofill/final-export")
    def final_export(req: FinalExportRequest):
        from hwpx.pipeline.form_writer_final_export_gate import build_final_export_payload
        try:
            payload = build_final_export_payload(
                req.downloadPayloadDict,
                req.decisionResultDict,
                form_id=req.formId,
                form_title=req.formTitle,
            )
            safe = _sanitize(payload)
            status = "SUCCESS" if payload.get("finalExportEnabled") else "FAILED"
            if status == "SUCCESS":
                return _success(safe, warnings=["WARN_SANDBOX_ONLY", "WARN_FINAL_EXPORT_DOES_NOT_DEPLOY"])
            else:
                return _failed(
                    [{"code": "FINAL_EXPORT_BLOCKED",
                      "message": payload.get("exportStatus", "")}],
                    warnings=["WARN_SANDBOX_ONLY"],
                )
        except Exception as e:
            return _failed([{"code": "INTERNAL_ERROR", "message": str(e)}])

    return app


app = create_app()


# ---------------------------------------------------------------------------
# Pure-Python API contract (FastAPI 없을 때도 테스트 가능)
# ---------------------------------------------------------------------------

def call_health() -> dict:
    """FastAPI 없이 health 응답 생성."""
    return _success({
        "mode": MODE,
        "sourceMutationAllowed": False,
        "pipelineReady": True,
    })


def call_e2e_smoke() -> dict:
    from hwpx.pipeline.form_auto_fill_e2e_smoke import run_e2e_smoke
    with tempfile.TemporaryDirectory() as td:
        result = run_e2e_smoke(Path(td))
    safe = _sanitize(result)
    if safe.get("overallVerdict") == "PASS_E2E_SMOKE":
        return _success(safe, warnings=["WARN_SYNTHETIC_SCENARIO_ONLY", "WARN_SANDBOX_ONLY"])
    return _failed([{"code": "E2E_SMOKE_FAILED", "message": safe.get("overallVerdict", "")}])


def call_write_sandbox(approval_dict: dict, form_id: str = "") -> dict:
    from hwpx.pipeline.form_writer_ui_connect import (
        build_ui_connect_payload, _derive_approval_status, STATUS_READY,
    )
    status = _derive_approval_status(approval_dict)
    if status != STATUS_READY:
        return _failed(
            [{"code": "WRITER_BLOCKED", "message": f"approvalStatus={status}"}],
            warnings=["WARN_SANDBOX_ONLY"],
        )
    ui_payload = build_ui_connect_payload(approval_dict, form_id=form_id)
    safe = _sanitize(ui_payload)
    return _success(
        {"uiPayload": safe, "mode": MODE, "sourceMutationAllowed": False},
        warnings=["WARN_SANDBOX_ONLY"],
    )


def call_download_review(writer_result: dict, form_id: str = "") -> dict:
    from hwpx.pipeline.form_writer_download_review import build_download_payload
    payload = build_download_payload(writer_result, form_id=form_id)
    return _success(_sanitize(payload), warnings=["WARN_SANDBOX_ONLY"])


def call_final_export(dl_payload: dict, decision: dict,
                      form_id: str = "", form_title: str = "") -> dict:
    from hwpx.pipeline.form_writer_final_export_gate import build_final_export_payload
    payload = build_final_export_payload(dl_payload, decision,
                                         form_id=form_id, form_title=form_title)
    safe = _sanitize(payload)
    if payload.get("finalExportEnabled"):
        return _success(safe, warnings=["WARN_SANDBOX_ONLY", "WARN_FINAL_EXPORT_DOES_NOT_DEPLOY"])
    return _failed(
        [{"code": "FINAL_EXPORT_BLOCKED", "message": payload.get("exportStatus", "")}],
        warnings=["WARN_SANDBOX_ONLY"],
    )
