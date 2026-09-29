"""HWPX-FILL-REVIEW-LOG-ORCHESTRATION-01.

D동(학습 로그) ↔ 운영동(fill_review production) 배관.

운영동 결과 dict (run_fill_review_live_pipeline_sandbox() 반환)를
read-only로 받아서, D동 audit_learning_log_contract schema에 맞춰
기록한다. 본 모듈은 운영동을 호출만 하고, 운영동은 본 모듈을 import하지 않는다.

부분 준공 (V1):
- in-memory SQLite 또는 외부에서 주입된 connection만 받는다
- 실제 corpus DB 직접 연결은 다음 공정으로 분리
- AI/OCR/writer 미호출
- output HWPX 미생성

방화구획 (CLAUDE.md §6):
- production module (fill_review_contract, ui_adapter, live_pipeline,
  evidence_ingestion_contract)에서 본 모듈 import 금지
- raw 개인정보 저장 금지
- secret/DB URL 출력 금지
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

CONTRACT_NAME = "HWPX-FILL-REVIEW-LOG-ORCHESTRATION-01"
ORCHESTRATION_VERSION = "v1.1"  # v1.1: file-DB 옵션 + 운영 corpus 차단 게이트


# ── 운영 corpus 보호 (R2 트리거 미달 차단) ────────────────────────────────

_PROTECTED_DB_DIR_FRAGMENT = "data/recognition_corpus/"


class ProtectedDbPathRejected(RuntimeError):
    """RISK-LEDGER R2 차단 — 운영 corpus DB 직접 쓰기 시도 거부."""


def _normalize_path_str(p: str | Path) -> str:
    """Path 또는 str을 forward-slash 형태로 정규화 (Windows/POSIX 호환).

    raw str의 backslash 변환 + Path 표준화 양쪽 모두 처리.
    """
    raw = str(p).replace("\\", "/")
    # Path 표준화로 한 번 더 (relative case 등)
    try:
        return Path(raw).as_posix()
    except Exception:  # ruff: ignore[blind-except] - 정규화 실패 시 원본 문자열로 폴백(경로 차단 로직은 원본으로도 동작)
        return raw


def _is_protected_corpus_path(path: str | Path) -> bool:
    """data/recognition_corpus/*.sqlite3 직접 쓰기 여부."""
    norm = _normalize_path_str(path)
    if _PROTECTED_DB_DIR_FRAGMENT not in norm:
        return False
    if norm.rstrip("/").endswith(".sqlite3"):
        return True
    return False


def open_logging_connection(db_path: str | Path | None) -> sqlite3.Connection:
    """학습 로그 적재용 sqlite connection 생성.

    Args:
        db_path:
          - None → in-memory (기본, 안전)
          - 다른 path → file-based (R2 트리거 미충족 시 운영 corpus 경로 차단)

    Returns:
        schema가 init된 sqlite3.Connection.
    """
    from scripts.hwpx.recognition_corpus import (
        audit_learning_log_contract as al,
    )
    from scripts.hwpx.recognition_corpus import (
        corpus_schema as cs,
    )

    if db_path is None:
        target = ":memory:"
    else:
        if _is_protected_corpus_path(db_path):
            raise ProtectedDbPathRejected(
                f"protected corpus path rejected: {db_path}. "
                "See RISK-LEDGER R2 — set explicit activation gate before "
                "writing to data/recognition_corpus/*.sqlite3."
            )
        target = str(db_path)
    conn = sqlite3.connect(target)
    conn.execute("PRAGMA foreign_keys = ON")
    cs.init_db(conn)
    al.init_audit_learning_log_schema(conn)
    return conn


# 운영동 pipelineStatus → D동 session_status 매핑
_PIPELINE_TO_SESSION_STATUS = {
    "READY_FOR_REVIEW": "READY_FOR_DECISION",
    "DECISION_VALIDATED": "DECISION_VALIDATED",
    "WRITER_APPLIED": "WRITER_APPLIED",
    "WRITER_BLOCKED": "WRITER_BLOCKED",
    "READBACK_FAILED": "READBACK_FAILED",
    "COMPLETED": "COMPLETED",
    "CANCELLED": "CANCELLED",
}

# fill_review decision (운영동) → D동 decision enum
_DECISION_MAP = {
    "APPROVE": "APPROVE",
    "REJECT": "REJECT",
    "HOLD": "HOLD",
    "EDIT_VALUE": "EDIT_VALUE",
    "REQUEST_MATERIAL": "REQUEST_MATERIAL",
    "SYSTEM_APPROVE": "SYSTEM_APPROVE",
    "SYSTEM_HOLD": "SYSTEM_HOLD",
}


class OrchestrationError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_session_status(pipeline_status: str | None, errors: list | None) -> str:
    if errors:
        return "ERROR"
    return _PIPELINE_TO_SESSION_STATUS.get(pipeline_status or "", "REVIEW_STARTED")


def _new_session_id(request_id: str | None) -> str:
    if request_id and isinstance(request_id, str):
        return f"sess-{request_id}"
    return f"sess-{uuid.uuid4().hex[:16]}"


# ── 기록 단계별 헬퍼 (record_pipeline_result 분리) ──────────────────────────


def _record_decisions(
    conn: sqlite3.Connection, al, session_id: str, decision_payload: dict | None, now: str
) -> tuple[dict[str, int], int]:
    """decisionPayload 기반 결정 기록. (decision_log_id_by_item, count) 반환."""
    decision_log_id_by_item: dict[str, int] = {}
    count = 0
    if decision_payload and isinstance(decision_payload, dict):
        for d in decision_payload.get("decisions", []) or []:
            decision_raw = d.get("decision")
            if decision_raw not in _DECISION_MAP:
                continue
            review_item_id = d.get("reviewItemId") or ""
            normalized_label = d.get("label") or d.get("normalizedLabel")
            semantic_type = d.get("semanticType")
            target = d.get("target") or {}
            target_type = (target.get("targetType") or "").upper() or None
            target_key = target.get("cellKey") or target.get("paragraphKey")
            proposed = d.get("proposedValue") or d.get("editedValue")
            edited = d.get("editedValue")
            current = d.get("currentValue")
            rec_d = {
                "session_id": session_id,
                "review_item_id": review_item_id,
                "requirement_id": d.get("requirementId"),
                "normalized_label": normalized_label,
                "semantic_type": semantic_type,
                "target_type": target_type,
                "target_key": target_key,
                "current_value_hash": al.hash_value(current) if current else None,
                "proposed_value_hash": al.hash_value(proposed) if proposed else None,
                "edited_value_hash": al.hash_value(edited) if edited else None,
                "decision": _DECISION_MAP[decision_raw],
                "decision_source": d.get("decisionSource") or "USER",
                "decided_by": d.get("decidedBy") or "anonymous",
                "decided_at": d.get("decidedAt") or now,
                "reason": d.get("reason"),
                "risk_flags_json": None,
                "evidence_refs_json": None,
            }
            built = al.build_decision_log_records([rec_d])
            decision_log_id = al.insert_decision(conn, built[0])
            decision_log_id_by_item[review_item_id] = decision_log_id
            count += 1
    return decision_log_id_by_item, count


def _record_writer_operations(
    conn: sqlite3.Connection,
    al,
    session_id: str,
    pipeline_result: dict,
    decision_log_id_by_item: dict[str, int],
    now: str,
) -> tuple[list[int], dict[int, dict], list[dict], int]:
    """approvedEditPlan.operations 기록.

    (op_log_ids, op_results_by_index, ops, count) 반환.
    """
    plan = pipeline_result.get("approvedEditPlan") or {}
    ops = plan.get("operations") or []
    writer_status_summary = pipeline_result.get("writerResult") or {}
    writer_op_results = writer_status_summary.get("operationResults") or []
    op_results_by_index = {i: r for i, r in enumerate(writer_op_results)}

    op_log_ids: list[int] = []
    count = 0
    for idx, op in enumerate(ops):
        op_type = op.get("op") or op.get("operationType")
        if not op_type:
            continue
        target = op.get("target") or {}
        target_type = (target.get("targetType") or target.get("type") or "").upper() or "CELL"
        target_key = (
            target.get("cellKey") or target.get("paragraphKey") or target.get("targetKey") or ""
        )
        expected_before = op.get("expectedBeforeHash") or "PRECOMPUTED"
        value_after = (
            op.get("valueHash") or al.hash_value(op.get("value") or "")
            if op.get("value") is not None
            else None
        )
        wresult = op_results_by_index.get(idx, {})
        op_status_raw = wresult.get("status") or "CREATED"
        op_status = (
            op_status_raw
            if op_status_raw in ("CREATED", "BLOCKED", "APPLIED", "SKIPPED")
            else "CREATED"
        )
        blocked_reason = wresult.get("blockedReason")
        review_item_id = op.get("reviewItemId") or ""
        decision_log_id = decision_log_id_by_item.get(review_item_id)
        op_rec = {
            "session_id": session_id,
            "decision_log_id": decision_log_id,
            "operation_type": op_type,
            "writer_method": op.get("writerMethod"),
            "target_type": target_type,
            "target_key": target_key or "unknown",
            "expected_before_hash": expected_before,
            "value_hash": value_after,
            "operation_status": op_status,
            "blocked_reason": blocked_reason,
            "created_at": now,
        }
        built_op = al.build_writer_operation_log_records([op_rec])
        op_log_id = al.insert_writer_operation(conn, built_op[0])
        op_log_ids.append(op_log_id)
        count += 1

    return op_log_ids, op_results_by_index, ops, count


def _record_readbacks(
    conn: sqlite3.Connection,
    al,
    session_id: str,
    pipeline_result: dict,
    op_log_ids: list[int],
    now: str,
) -> tuple[list[dict], int]:
    """readback 결과 기록. (readback_op_results, count) 반환."""
    readback = pipeline_result.get("readback") or {}
    readback_op_results = readback.get("operationResults") or []
    count = 0
    for idx, r in enumerate(readback_op_results):
        status_raw = r.get("status") or "NOT_RUN"
        status = (
            status_raw if status_raw in ("MATCHED", "MISMATCH", "NOT_RUN", "BLOCKED") else "NOT_RUN"
        )
        r_rec = {
            "session_id": session_id,
            "operation_log_id": op_log_ids[idx] if idx < len(op_log_ids) else None,
            "readback_status": status,
            "expected_after_hash": r.get("expectedAfterHash"),
            "actual_after_hash": r.get("actualAfterHash"),
            "divergence_code": r.get("divergenceCode"),
            "divergence_summary": r.get("divergenceSummary"),
            "checked_at": r.get("checkedAt") or now,
        }
        built_r = al.build_readback_log_records([r_rec])
        al.insert_readback(conn, built_r[0])
        count += 1
    return readback_op_results, count


@dataclass
class _LogContext:
    """record_pipeline_result 단계별 헬퍼가 공유하는 세션 식별 정보."""

    session_id: str
    document_id: str
    now: str
    document_type: str | None = None
    sub_type: str | None = None


@dataclass
class _LearningSignalInputs:
    """_record_learning_signals 전용 입력 묶음(인자 개수 축소 목적)."""

    ops: list[dict]
    review_items: list[dict]
    decision_payload: dict | None
    op_results_by_index: dict[int, dict]
    readback_op_results: list[dict]


def _record_learning_signals(
    conn: sqlite3.Connection, al, ctx: _LogContext, inputs: _LearningSignalInputs
) -> int:
    """decision + writer + readback 결합 학습 신호 기록. count 반환."""
    count = 0
    for idx, op in enumerate(inputs.ops):
        review_item_id = op.get("reviewItemId") or ""
        item = next(
            (it for it in inputs.review_items if it.get("reviewItemId") == review_item_id), None
        )
        if not item:
            continue
        decision_rec = None
        if inputs.decision_payload:
            decision_rec = next(
                (
                    d
                    for d in inputs.decision_payload.get("decisions", []) or []
                    if d.get("reviewItemId") == review_item_id
                ),
                None,
            )
        decision_value = decision_rec.get("decision") if decision_rec else None
        if not decision_value:
            continue
        wresult = inputs.op_results_by_index.get(idx, {})
        rresult = inputs.readback_op_results[idx] if idx < len(inputs.readback_op_results) else {}
        signal_input = {
            "session_id": ctx.session_id,
            "document_id": ctx.document_id,
            "document_type": ctx.document_type,
            "sub_type": ctx.sub_type,
            "normalized_label": item.get("label") or item.get("normalizedLabel"),
            "semantic_type": item.get("semanticType"),
            "target_type": (op.get("target") or {}).get("targetType", "CELL").upper(),
            "target_pattern": _derive_target_pattern(op.get("target") or {}),
            "evidence_type": (item.get("evidenceRefs")[0] if item.get("evidenceRefs") else None),
            "decision": decision_value,
            "decision_source": decision_rec.get("decisionSource") or "USER",
            "writer_status": wresult.get("status") or "NOT_RUN",
            "readback_status": rresult.get("status") or "NOT_RUN",
            "target_key": (op.get("target") or {}).get("cellKey")
            or (op.get("target") or {}).get("paragraphKey"),
            "has_conflict": bool(item.get("semanticConflict")),
            "created_at": ctx.now,
        }
        built_sig = al.build_learning_signal_records([signal_input])
        al.insert_learning_signal(conn, built_sig[0])
        count += 1
    return count


def _record_xml_backlog_flags(
    conn: sqlite3.Connection,
    al,
    ctx: _LogContext,
    pipeline_result: dict,
    readback_op_results: list[dict],
) -> int:
    """readback mismatch + warnings 기반 XML deep analyzer backlog 기록. count 반환."""
    flags_input: list[dict] = []
    for r in readback_op_results:
        if r.get("status") == "MISMATCH":
            flags_input.append({
                "session_id": ctx.session_id,
                "document_id": ctx.document_id,
                "reason_code": "READBACK_MISMATCH",
                "target_key": r.get("targetKey"),
                "normalized_label": r.get("normalizedLabel"),
                "context_json": None,
                "severity": "HIGH",
                "created_at": ctx.now,
            })
    for warn in pipeline_result.get("warnings") or []:
        code = (warn.get("code") or "").upper()
        if code == "RUN_BOUNDARY_UNSUPPORTED":
            flags_input.append({
                "session_id": ctx.session_id,
                "document_id": ctx.document_id,
                "reason_code": "RUN_BOUNDARY_UNSUPPORTED",
                "target_key": warn.get("targetKey"),
                "normalized_label": warn.get("normalizedLabel"),
                "context_json": None,
                "severity": "MEDIUM",
                "created_at": ctx.now,
            })
        elif code in (
            "CHECKBOX_OR_SHAPE_NEEDED",
            "OBJECT_ANCHOR_NEEDED",
            "STYLE_RESOLUTION_NEEDED",
            "CELL_INTERNAL_PARAGRAPH_NEEDED",
            "MERGED_CELL_GEOMETRY_NEEDED",
            "TARGET_AMBIGUOUS",
            "LABEL_CONTEXT_INSUFFICIENT",
        ):
            flags_input.append({
                "session_id": ctx.session_id,
                "document_id": ctx.document_id,
                "reason_code": code,
                "target_key": warn.get("targetKey"),
                "normalized_label": warn.get("normalizedLabel"),
                "context_json": None,
                "severity": "MEDIUM",
                "created_at": ctx.now,
            })
    built_flags = al.build_xml_deep_analyzer_need_flags(flags_input)
    count = 0
    for f in built_flags:
        al.insert_xml_backlog(conn, f)
        count += 1
    return count


# ── 메인 진입점 ───────────────────────────────────────────────────────────


def record_pipeline_result(  # ruff: ignore[too-many-arguments] - 25개 이상 호출부(운영+테스트)가 있는 공개 API, 시그니처 변경 보류
    conn: sqlite3.Connection,
    pipeline_result: dict,
    *,
    decision_payload: dict | None = None,
    classifier_version: str | None = None,
    dictionary_version: str | None = None,
    created_by: str = "orchestration",
    now_iso: str | None = None,
) -> dict:
    """운영동 결과 1건을 D동 schema에 기록.

    Args:
        conn: D동 schema가 init된 SQLite connection (in-memory or file).
        pipeline_result: run_fill_review_live_pipeline_sandbox() 반환 dict.
        decision_payload: 사용자가 보낸 decisionPayload (없으면 None).
        classifier_version, dictionary_version: 메타.
        created_by: session log의 created_by 필드.
        now_iso: 테스트용 시각 주입.

    Returns:
        dict — 기록 결과 요약 (counts, sessionId, sessionStatus,
        learningSignalCount, xmlBacklogCount).
    """
    # D동 import는 lazy로 처리 (orchestration은 D동만 의존, 운영동 격리)
    from scripts.hwpx.recognition_corpus import (
        audit_learning_log_contract as al,
    )

    if not isinstance(pipeline_result, dict):
        raise OrchestrationError("pipeline_result must be a dict")

    now = now_iso or _now_iso()
    request_id = pipeline_result.get("requestId")
    document_id = pipeline_result.get("documentId") or "unknown"
    source_hash = pipeline_result.get("sourceDocumentHash") or ""
    pipeline_status = pipeline_result.get("pipelineStatus")
    errors = pipeline_result.get("errors") or []
    session_id = _new_session_id(request_id)
    session_status = _coerce_session_status(pipeline_status, errors)

    rec = pipeline_result.get("fillReview") or {}
    review_items = rec.get("reviewItems") or []
    document_type = (
        (pipeline_result.get("recognitionResult") or {}).get("documentType")
        if pipeline_result.get("recognitionResult")
        else None
    )
    sub_type = (
        (pipeline_result.get("recognitionResult") or {}).get("subType")
        if pipeline_result.get("recognitionResult")
        else None
    )

    # 1) session log
    session = al.build_fill_review_session_log(
        session_id=session_id,
        document_id=document_id,
        source_document_hash=source_hash,
        started_at=now,
        session_status=session_status,
        completed_at=now
        if session_status
        in (
            "COMPLETED",
            "WRITER_APPLIED",
            "READBACK_FAILED",
            "WRITER_BLOCKED",
            "CANCELLED",
            "ERROR",
        )
        else None,
        document_type=document_type,
        sub_type=sub_type,
        classifier_version=classifier_version,
        dictionary_version=dictionary_version,
        created_by=created_by,
    )
    al.insert_session(conn, session)

    counts = {
        "decisions": 0,
        "writerOps": 0,
        "readbacks": 0,
        "learningSignals": 0,
        "xmlBacklogFlags": 0,
    }

    decision_log_id_by_item, counts["decisions"] = _record_decisions(
        conn, al, session_id, decision_payload, now
    )
    op_log_ids, op_results_by_index, ops, counts["writerOps"] = _record_writer_operations(
        conn, al, session_id, pipeline_result, decision_log_id_by_item, now
    )
    readback_op_results, counts["readbacks"] = _record_readbacks(
        conn, al, session_id, pipeline_result, op_log_ids, now
    )
    log_ctx = _LogContext(
        session_id=session_id,
        document_id=document_id,
        now=now,
        document_type=document_type,
        sub_type=sub_type,
    )
    counts["learningSignals"] = _record_learning_signals(
        conn,
        al,
        log_ctx,
        _LearningSignalInputs(
            ops=ops,
            review_items=review_items,
            decision_payload=decision_payload,
            op_results_by_index=op_results_by_index,
            readback_op_results=readback_op_results,
        ),
    )
    counts["xmlBacklogFlags"] = _record_xml_backlog_flags(
        conn, al, log_ctx, pipeline_result, readback_op_results
    )

    conn.commit()

    return {
        "sessionId": session_id,
        "sessionStatus": session_status,
        "documentId": document_id,
        "counts": counts,
        "orchestrationVersion": ORCHESTRATION_VERSION,
        "recordedAt": now,
    }


def _derive_target_pattern(target: dict) -> str:
    """target dict에서 안정적 pattern key를 만든다 (학습 재사용 키)."""
    if "cellKey" in target:
        return f"cell:{target['cellKey']}"
    if "paragraphKey" in target:
        return f"paragraph:{target['paragraphKey']}"
    if "tableIndex" in target and "row" in target:
        return f"table:{target['tableIndex']}:r{target['row']}:c{target.get('col', '?')}"
    return "unknown"


# ── 방화구획 검증 ────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PATHS_FOR_ORCHESTRATION: tuple[Path, ...] = (
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_contract.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_ui_adapter.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_live_pipeline.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/evidence_ingestion_contract.py",
)
FORBIDDEN_ORCHESTRATION_IMPORTS: tuple[str, ...] = (
    "fill_review_log_recorder",
    "record_pipeline_result",
    "OrchestrationError",
)


def audit_orchestration_isolation() -> dict:
    """production 모듈이 orchestration을 import하면 안 된다.
    배관은 항상 외부에서 호출됨."""
    violations: list[dict] = []
    checked: list[str] = []
    for path in PRODUCTION_PATHS_FOR_ORCHESTRATION:
        if not path.is_file():
            continue
        checked.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in FORBIDDEN_ORCHESTRATION_IMPORTS:
            if needle in text:
                violations.append({
                    "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "forbidden": needle,
                })
    return {"violations": violations, "ok": not violations, "filesChecked": checked}
