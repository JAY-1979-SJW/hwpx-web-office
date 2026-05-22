"""HWPX-LIVE-SMOKE-HARNESS-01.

단지 전체 회로 1회 시운전 — deterministic fixture로 마스터→배관→D동 통합.
실 LLM/파서/writer 미호출. 모든 외부 의존은 deterministic stub로 대체.

목적:
- 단지 전체 회로가 한 번 가동 가능한지 검증
- 어디서 끊겼는지 진단
- 실 가동 전 회귀 잠금
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

HARNESS_NAME = "HWPX-LIVE-SMOKE-HARNESS-01"
HARNESS_VERSION = "v1"


def _fixture_recognition(source_ref: str) -> dict:
    """deterministic 인식 fixture — 검측요청서 라벨 2개 발견."""
    return {
        "documentId": source_ref,
        "documentType": "fillable_form",
        "subType": "검측요청서",
        "sourceDocumentHash": f"hash:{source_ref}",
        "labelOccurrences": [
            {"normalizedLabel": "공사명",
                "cellKey": "t0:r0:c1",
                "neighborText": "현장"},
            {"normalizedLabel": "계약금액",
                "cellKey": "t0:r1:c1",
                "neighborText": "원"},
        ],
    }


def _fixture_slot_detect(rec: dict) -> list[dict]:
    return [
        {"label": "공사명", "type": "label_right_blank",
            "cellKey": "t0:r0:c1"},
        {"label": "계약금액", "type": "label_right_blank",
            "cellKey": "t0:r1:c1"},
    ]


def _fixture_pdf_extractor(source: dict, labels: list[str]) -> list[dict]:
    return [{
        "label": "공사명",
        "value": "○○건축공사",
        "evidenceType": "pdf_text",
        "sourceRef": f"{source['sourceId']}:p1",
        "confidence": 0.93,
    }]


def _fixture_excel_extractor(source: dict, labels: list[str]) -> list[dict]:
    return [{
        "label": "계약금액",
        "value": "1,200,000,000",
        "evidenceType": "excel_cell",
        "sourceRef": f"{source['sourceId']}:Sheet1!B5",
        "confidence": 0.88,
    }]


def _fixture_ai_proposal(rec: dict, slots: list[dict],
                                extracted: list[dict]) -> list[dict]:
    """AI fixture — 추출값을 그대로 proposal로 변환."""
    out: list[dict] = []
    for i, e in enumerate(extracted or []):
        out.append({
            "proposalId": f"ai-{i}",
            "label": e.get("label"),
            "value": e.get("value"),
            "confidence": float(e.get("confidence") or 0.85),
            "semanticType": _infer_semantic(e.get("label") or ""),
            "modelId": "smoke-fixture-llm",
            "evidence": [{"sourceRef": e.get("sourceRef"),
                            "evidenceType": e.get("evidenceType")}],
        })
    return out


def _infer_semantic(label: str) -> str | None:
    if "공사명" in label: return "PROJECT_NAME"
    if "계약금액" in label: return "CONTRACT_AMOUNT"
    if "착공" in label: return "START_DATE"
    if "준공" in label: return "END_DATE"
    return None


def run_live_smoke(*, source_hwpx_ref: str = "smoke-doc-1",
                          source_documents: list[dict] | None = None,
                          ) -> dict:
    """단지 전체 회로 1회 시운전.

    Returns:
        {
          status: "PASS" | "FAIL",
          stages: [...],
          masterResult: {...},
          recorderResult: {...},
          errors: [...]
        }
    """
    from scripts.hwpx.master_orchestration import auto_fill_master as mo
    from scripts.hwpx.orchestration import fill_review_log_recorder as orc
    from scripts.hwpx.recognition_corpus import (
        corpus_schema as cs,
        audit_learning_log_contract as al,
    )

    if source_documents is None:
        source_documents = [
            {"sourceId": "smoke-contract.pdf", "sourceType": "pdf"},
            {"sourceId": "smoke-payment.xlsx", "sourceType": "excel"},
        ]

    stages: list[dict] = []
    errors: list[dict] = []

    # ── ① 마스터 회로 1회 가동 ─────────────────────────────────────
    try:
        master_result = mo.run_auto_fill_master(
            source_hwpx_ref=source_hwpx_ref,
            source_documents=source_documents,
            recognition_fn=_fixture_recognition,
            slot_detect_fn=_fixture_slot_detect,
            extractor_registry={
                "pdf": _fixture_pdf_extractor,
                "excel": _fixture_excel_extractor,
            },
            ai_proposal_fn=_fixture_ai_proposal,
            request_id=f"smoke-{source_hwpx_ref}",
        )
        stages.append({"stage": "master_pipeline", "ok": True,
                          "labelCount": len(master_result["recognitionResult"]
                                                .get("labelOccurrences") or []),
                          "extractedCount": len(master_result["extractedValues"]),
                          "reviewItemCount": len(master_result["reviewItems"])})
    except Exception as e:
        errors.append({"stage": "master_pipeline", "error": str(e)[:200]})
        return {"status": "FAIL", "stages": stages, "errors": errors,
                  "masterResult": None, "recorderResult": None}

    # ── ② 배관 — D동 학습 로그 적재 ────────────────────────────────
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    cs.init_db(conn)
    al.init_audit_learning_log_schema(conn)
    try:
        recorder_result = orc.record_pipeline_result(conn, master_result)
        stages.append({"stage": "log_recorder", "ok": True,
                          "sessionStatus": recorder_result["sessionStatus"],
                          "counts": recorder_result["counts"]})
    except Exception as e:
        errors.append({"stage": "log_recorder", "error": str(e)[:200]})
        conn.close()
        return {"status": "FAIL", "stages": stages, "errors": errors,
                  "masterResult": master_result, "recorderResult": None}

    # ── ③ D동 view 동작 확인 ──────────────────────────────────────
    try:
        view_rows = conn.execute(
            "SELECT decision, COUNT(*) FROM fill_review_decision_logs "
            "GROUP BY decision").fetchall()
        stages.append({"stage": "d_dong_views_query", "ok": True,
                          "decisionBreakdown": dict(view_rows)})
    except Exception as e:
        errors.append({"stage": "d_dong_views_query", "error": str(e)[:200]})
    finally:
        conn.close()

    status = "PASS" if not errors else "FAIL"
    return {
        "harnessName": HARNESS_NAME,
        "harnessVersion": HARNESS_VERSION,
        "status": status,
        "sourceHwpxRef": source_hwpx_ref,
        "stages": stages,
        "errors": errors,
        "masterResult": _summarize_master(master_result),
        "recorderResult": recorder_result if not errors else None,
    }


def _summarize_master(m: dict) -> dict:
    """master 결과에서 PII 포함 가능 부분 제외하고 요약만 반환."""
    return {
        "documentId": m.get("documentId"),
        "pipelineStatus": m.get("pipelineStatus"),
        "stages": m.get("stages"),
        "aiProposalSummary": m.get("aiProposalSummary"),
        "reviewItemCount": len(m.get("reviewItems") or []),
        "holdCount": len(m.get("holdProposals") or []),
        "rejectedCount": len(m.get("rejectedProposals") or []),
        "warnings": m.get("warnings"),
        "errors": m.get("errors"),
    }


# ── 방화구획 ────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PATHS_FOR_HARNESS: tuple[Path, ...] = (
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_contract.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_ui_adapter.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_live_pipeline.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/evidence_ingestion_contract.py",
)
FORBIDDEN_HARNESS_IMPORTS: tuple[str, ...] = (
    "live_smoke_harness",
    "run_live_smoke",
)


def audit_harness_isolation() -> dict:
    violations: list[dict] = []
    checked: list[str] = []
    for path in PRODUCTION_PATHS_FOR_HARNESS:
        if not path.is_file():
            continue
        checked.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in FORBIDDEN_HARNESS_IMPORTS:
            if needle in text:
                violations.append({
                    "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "forbidden": needle,
                })
    return {"violations": violations, "ok": not violations,
              "filesChecked": checked}
