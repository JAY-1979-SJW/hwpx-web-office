"""HWPX-FILL-REVIEW-LIVE-PIPELINE-INTEGRATION-01

문서 인지 → evidence ingestion → fill review contract → UI adapter payload →
decision validation → ApprovedEditPlan → live sandbox writer → readback까지
종단을 연결하는 orchestrator.

원칙:
- 원본 HWPX는 절대 수정하지 않는다 (sha256/mtime 검증으로 고정).
- writer 실행은 사용자 APPROVE/EDIT_VALUE 이후에만, sandbox output 경로에 한해 허용.
- blocking missing material / decision validation 실패 시 writer 미호출.
- sourceDocumentHash / expectedBefore / target 누락 시 writer 미호출.
- outputPath == sourcePath 차단.
- confidence는 자동 승인 근거가 아니다.
- setParagraphText 공식명 / setCellParagraphText 금지명 유지.
- AI API / OCR / DB / network 호출 없음.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from . import evidence_ingestion_contract as ingest
from . import fill_review_contract as fr
from . import fill_review_ui_adapter as ui

# 통합 pipeline에서 허용하는 operation type → live writer method
OP_TO_WRITER_METHOD: dict[str, str] = {
    "setCellText": "writer.set_cell_text",
    "setParagraphText": "writer.set_paragraph_text",
    "replaceTextRun": "writer.replace_text_run",
}

# 이번 pipeline에서 ApprovedEditPlan에 들어올 수 있는 operationType 화이트리스트
PIPELINE_ALLOWED_OPERATIONS: frozenset[str] = frozenset(OP_TO_WRITER_METHOD.keys())

PIPELINE_SCHEMA_VERSION = "fill_review_live_pipeline_v1"
PIPELINE_ENGINE_VERSION = "0.1.0"


def _to_writer_call(op: dict, source_hash: str) -> dict:
    """ApprovedEditPlan operation dict → live sandbox WriterCallSpec dict."""
    return {
        "commandId": f"cmd_{uuid.uuid4().hex[:8]}",
        "operationId": op.get("operationId"),
        "operationType": op.get("operationType"),
        "writerMethod": OP_TO_WRITER_METHOD.get(op.get("operationType")),
        "target": dict(op.get("target") or {}),
        "value": op.get("value"),
        "expectedBefore": op.get("expectedBefore"),
        "preserveStyle": bool(op.get("preserveStyle", True)),
        "riskLevel": op.get("riskLevel", "low"),
        "approvedBy": op.get("approvedBy", "fill_review_user"),
        "sourceDocumentHash": source_hash,
    }


def _empty_result(input_dict: dict) -> dict:
    return {
        "schemaVersion": PIPELINE_SCHEMA_VERSION,
        "engineVersion": PIPELINE_ENGINE_VERSION,
        "requestId": str(uuid.uuid4()),
        "documentId": (input_dict.get("recognitionResult") or {}).get("documentId", ""),
        "sourceDocumentHash": input_dict.get("sourceDocumentHash", ""),
        "pipelineStatus": "READY_FOR_REVIEW",
        "evidenceIngestion": None,
        "fillReview": None,
        "uiPayload": None,
        "decisionValidation": None,
        "approvedEditPlan": None,
        "writerResult": None,
        "readback": None,
        "originalUnmodified": True,
        "outputCreated": False,
        "warnings": [],
        "errors": [],
    }


def run_fill_review_live_pipeline_sandbox(input_dict: dict,
                                                live_writer=None) -> dict:
    """전체 fill review 파이프라인을 sandbox 모드로 실행.

    live_writer: 의존성 주입용. 기본은 generic_edit_plan_writer_executor_live_sandbox.
    test에서 monkeypatch 또는 직접 주입 가능.
    """
    result = _empty_result(input_dict)
    rec = input_dict.get("recognitionResult") or {}
    source_hash = input_dict.get("sourceDocumentHash", "") or rec.get("sourceDocumentHash", "")
    result["sourceDocumentHash"] = source_hash
    evidence_inputs = input_dict.get("evidenceInputs", []) or []
    decision_payload = input_dict.get("decisionPayload")
    source_path = input_dict.get("sourcePath")
    output_path = input_dict.get("outputPath")

    # 1) Evidence ingestion
    ingestion_res = ingest.build_evidence_sources(evidence_inputs)
    result["evidenceIngestion"] = ingestion_res.to_dict()
    if ingestion_res.rejectedInputs:
        result["warnings"].append({
            "code": "EVIDENCE_INPUTS_REJECTED",
            "detail": f"rejected={ingestion_res.rejectedCount}",
        })
    evidence_sources = list(ingestion_res.evidenceSources)

    # 2) Fill review contract
    reqs = fr.build_fill_requirements(rec)
    matches = fr.match_requirements_with_evidence(reqs, evidence_sources)
    missing_requests = fr.build_missing_material_requests(
        reqs, evidence_sources, matches,
    )
    items = fr.build_review_items(reqs, matches, missing_requests)
    result["fillReview"] = {
        "requirements": reqs,
        "matches": matches,
        "missingRequests": missing_requests,
        "reviewItems": items,
    }

    # 3) UI payload
    ui_payload = ui.build_fill_review_page_payload(
        rec, items, missing_requests, evidence_sources,
    )
    result["uiPayload"] = ui_payload

    # 4) Decision 없음 → READY_FOR_REVIEW
    if decision_payload is None:
        result["pipelineStatus"] = "READY_FOR_REVIEW"
        return result

    # 5) blocking missing material 확인
    blocking_requests = [r for r in missing_requests if r.get("blocking")]
    # decision에 REQUEST_MATERIAL이 모든 missing requirement에 대응되면 통과 가능
    # 그 외에 APPROVE/EDIT_VALUE만 있고 blocking이 남아 있으면 차단.
    if blocking_requests:
        # 어떤 review item이 APPROVE/EDIT_VALUE로 들어왔는지 확인
        approve_or_edit = [
            d for d in (decision_payload.get("decisions") or [])
            if isinstance(d, dict) and d.get("decision") in (
                fr.DECISION_APPROVE, fr.DECISION_EDIT_VALUE,
            )
        ]
        if approve_or_edit:
            result["pipelineStatus"] = "BLOCKED_BY_MISSING_MATERIAL"
            result["errors"].append({
                "code": "MISSING_MATERIAL_BLOCKS_WRITE",
                "detail": (f"blocking missing materials remain: "
                              f"{[r.get('requestId') for r in blocking_requests]}"),
            })
            return result
        # APPROVE/EDIT_VALUE가 없으면 BLOCKED_BY_MISSING_MATERIAL로 단정 (writer 미호출)
        result["pipelineStatus"] = "BLOCKED_BY_MISSING_MATERIAL"
        return result

    # 6) Decision validation
    ui_items = [it for sec in ui_payload["reviewSections"] for it in sec["items"]]
    validation = ui.validate_decision_payload(
        decision_payload, ui_items,
        missing_requests=missing_requests,
        expected_source_hash=source_hash,
    )
    result["decisionValidation"] = validation.to_dict()
    if not validation.valid:
        result["pipelineStatus"] = "BLOCKED_BY_DECISION_VALIDATION"
        return result

    # 7) ApprovedEditPlan 생성 (APPROVE/EDIT_VALUE만 operation 생성)
    plan = fr.build_approved_edit_plan(
        items, decision_payload.get("decisions") or [],
        source_document_hash=source_hash,
    )
    result["approvedEditPlan"] = plan.to_dict()
    if not plan.operations:
        result["pipelineStatus"] = "BLOCKED_BY_EMPTY_APPROVALS"
        return result

    # operationType은 pipeline whitelist 안에 있어야 함
    forbidden_ops = [op for op in plan.operations
                        if op.get("operationType") not in PIPELINE_ALLOWED_OPERATIONS]
    if forbidden_ops:
        result["pipelineStatus"] = "WRITER_BLOCKED"
        result["errors"].append({
            "code": "UNSUPPORTED_OPERATION_IN_PIPELINE",
            "detail": f"forbidden={[o.get('operationType') for o in forbidden_ops]}",
        })
        return result

    # 8) sourcePath/outputPath 안전선
    if not source_hash:
        result["pipelineStatus"] = "BLOCKED_BY_SOURCE_HASH"
        result["errors"].append({"code": "SOURCE_HASH_REQUIRED"})
        return result
    if source_path is None or output_path is None:
        result["pipelineStatus"] = "WRITER_BLOCKED"
        result["errors"].append({
            "code": "PATHS_REQUIRED",
            "detail": "sourcePath and outputPath are required for writer step",
        })
        return result
    src = Path(source_path)
    out = Path(output_path)
    try:
        same_path = src.resolve() == out.resolve()
    except Exception:  # noqa: BLE001 -- 이 단계만 기록 후 계속
        same_path = str(src) == str(out)
    if same_path:
        result["pipelineStatus"] = "WRITER_BLOCKED"
        result["errors"].append({
            "code": "OUTPUT_OVERWRITES_SOURCE",
            "detail": f"outputPath == sourcePath ({src})",
        })
        result["originalUnmodified"] = True
        result["outputCreated"] = False
        return result

    # 9) WriterCallPlan 변환
    writer_call_plan = {
        "planId": plan.planId,
        "verdict": "READY_FOR_WRITER",
        "readyForWriter": True,
        "writerCalls": [_to_writer_call(op, source_hash) for op in plan.operations],
        "blockedOps": [],
    }

    # 10) live sandbox writer 실행
    if live_writer is None:
        from ..pipeline import generic_edit_plan_writer_executor_live_sandbox as _live
        live_writer = _live.execute_writer_call_plan_live_sandbox
    writer_result = live_writer(writer_call_plan, src, out)
    # writer_result는 LiveSandboxResult dataclass 또는 dict
    if hasattr(writer_result, "to_dict"):
        result["writerResult"] = writer_result.to_dict()
        rb = writer_result.readback
        result["readback"] = rb.to_dict() if hasattr(rb, "to_dict") else dict(rb or {})
        result["originalUnmodified"] = bool(writer_result.originalUnmodified)
        result["outputCreated"] = bool(writer_result.outputCreated)
        writer_verdict = writer_result.verdict
    else:
        result["writerResult"] = dict(writer_result or {})
        result["readback"] = (writer_result or {}).get("readback", {})
        result["originalUnmodified"] = bool((writer_result or {}).get("originalUnmodified", True))
        result["outputCreated"] = bool((writer_result or {}).get("outputCreated", False))
        writer_verdict = (writer_result or {}).get("verdict", "")

    if writer_verdict == "PASS_LIVE_SANDBOX_APPLIED":
        # readback divergences 확인
        div = (result["readback"] or {}).get("divergences") or []
        if div:
            result["pipelineStatus"] = "READBACK_FAILED"
        else:
            result["pipelineStatus"] = "WRITER_APPLIED"
    elif writer_verdict == "FAIL_READBACK_MISMATCH":
        result["pipelineStatus"] = "READBACK_FAILED"
    else:
        result["pipelineStatus"] = "WRITER_BLOCKED"

    return result


# ── helper: source hash 계산 ─────────────────────────────────────────────────

def sha256_of_file(path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
