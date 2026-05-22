"""HWPX-AUTO-FILL-MASTER-ORCHESTRATION-01.

마스터 컨트롤룸 — 단일 진입점으로 단지 전체 자동 채움 흐름을 가동한다.

흐름:
  ① 원본 HWPX 인식 결과 + 입력칸 감지 (외부 callable)
  ② 통합 Source Extractor로 외부 자료에서 값 추출 (callable)
  ③ AI 후보 생성 (callable, 없으면 source 추출만 사용)
  ④ 자동 채움 설계실로 review item 변환
  ⑤ 운영동(fill_review) 호환 결과 dict 구성
  ⑥ 학습 로그 적재용 형태 반환 (배관이 호출함)

본 모듈은 production fill_review를 import하지 않는다.
모든 외부 의존은 callable injection으로 받는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

CONTRACT_NAME = "HWPX-AUTO-FILL-MASTER-ORCHESTRATION-01"
CONTRACT_VERSION = "v1"

# 외부 callable signature:
# recognition_fn(source_hwpx_ref: str) -> dict (운영동 recognitionResult)
# slot_detect_fn(recognition_result: dict) -> list[dict]
# extractor_registry: dict[sourceType, ExtractorCallable]
# ai_proposal_fn(recognition, slots, extracted) -> list[proposal dict]
# (모두 optional — 없으면 placeholder 반환)


def run_auto_fill_master(
    *,
    source_hwpx_ref: str,
    source_documents: list[dict] | None = None,
    target_labels: list[str] | None = None,
    recognition_fn: Callable[[str], dict] | None = None,
    slot_detect_fn: Callable[[dict], list[dict]] | None = None,
    extractor_registry: dict[str, Callable] | None = None,
    ai_proposal_fn: Callable[[dict, list[dict], list[dict]], list[dict]] | None = None,
    conflict_labels: set[str] | None = None,
    request_id: str | None = None,
) -> dict:
    """단지 전체 자동 채움 흐름 1회 가동.

    반환은 운영동 fill_review_live_pipeline 결과와 호환되는 dict.
    실제 writer 호출은 별도 단계 — 본 함수는 review item까지만 만든다.
    """
    from scripts.hwpx.source_extractor import source_extractor_contract as se
    from scripts.hwpx.ai_proposal import review_item_builder as rib

    result: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "contractVersion": CONTRACT_VERSION,
        "requestId": request_id,
        "sourceHwpxRef": source_hwpx_ref,
        "stages": [],
        "warnings": [],
        "errors": [],
    }

    # ── ① 인식 ────────────────────────────────────────────────────────
    if recognition_fn is None:
        recognition_result = {"documentId": source_hwpx_ref,
                                "labelOccurrences": []}
        result["warnings"].append({
            "code": "RECOGNITION_FN_NOT_INJECTED",
            "stage": "recognition",
        })
    else:
        try:
            recognition_result = recognition_fn(source_hwpx_ref) or {}
        except Exception as e:
            result["errors"].append({"stage": "recognition",
                                          "error": str(e)[:200]})
            recognition_result = {"documentId": source_hwpx_ref,
                                    "labelOccurrences": []}
    result["recognitionResult"] = recognition_result
    result["stages"].append({"stage": "recognition", "ok": True,
                                "labelCount": len(
                                    recognition_result.get(
                                        "labelOccurrences") or [])})

    # ── ② 입력칸 감지 ─────────────────────────────────────────────────
    slots: list[dict] = []
    if slot_detect_fn is not None:
        try:
            slots = slot_detect_fn(recognition_result) or []
        except Exception as e:
            result["errors"].append({"stage": "slot_detection",
                                          "error": str(e)[:200]})
    result["inputSlots"] = slots
    result["stages"].append({"stage": "slot_detection",
                                "ok": True, "slotCount": len(slots)})

    # ── ③ 통합 Source Extractor ──────────────────────────────────────
    targets = target_labels or [
        (occ.get("normalizedLabel") or "")
            for occ in recognition_result.get("labelOccurrences") or []
    ]
    targets = [t for t in targets if t]
    extracted_result = se.extract_values_from_sources(
        source_documents or [], targets,
        extractor_registry=extractor_registry)
    result["extractedValues"] = extracted_result["extractedValues"]
    result["stages"].append({
        "stage": "source_extraction",
        "ok": True,
        "extractedCount": extracted_result["summary"]["extractedCount"],
        "skippedSources": len(extracted_result["skippedSources"]),
    })

    # ── ④ AI 후보 생성 (callable) ─────────────────────────────────────
    # 운영규칙: AI 없이 자동 입력 금지.
    # ai_proposal_fn=None 이면 자동 채움 자체를 차단하고 WARN만 적재한다.
    ai_proposals: list[dict] = []
    if ai_proposal_fn is None:
        result["warnings"].append({
            "code": "AI_REQUIRED_FOR_AUTO_FILL",
            "stage": "ai_proposal",
            "detail": (
                "ai_proposal_fn not injected. Auto-fill is blocked by policy "
                "(CLAUDE.md §10). Recognition + slot detection only, "
                "no proposals will be created."
            ),
        })
    else:
        try:
            ai_proposals = ai_proposal_fn(
                recognition_result, slots,
                extracted_result["extractedValues"]) or []
        except Exception as e:
            result["errors"].append({"stage": "ai_proposal",
                                          "error": str(e)[:200]})

    ai_review = rib.build_review_items_from_proposals(
        ai_proposals, recognition_result,
        conflict_labels=conflict_labels, request_id=request_id)
    result["aiProposalSummary"] = ai_review["summary"]
    result["reviewItems"] = ai_review["reviewItems"]
    result["holdProposals"] = ai_review["holdProposals"]
    result["rejectedProposals"] = ai_review["rejectedProposals"]
    result["stages"].append({
        "stage": "ai_proposal_routing",
        "ok": True,
        "reviewItemCount": ai_review["summary"]["acceptedReadyForReview"],
    })

    # ── ⑤ 운영동 호환 출력 형태 ──────────────────────────────────────
    # 배관(orchestration)이 받을 수 있는 dict로 변환.
    result["pipelineStatus"] = ("READY_FOR_REVIEW"
                                       if result["reviewItems"] else "READY_FOR_REVIEW")
    result["sourceDocumentHash"] = source_hwpx_ref
    result["documentId"] = recognition_result.get("documentId") or source_hwpx_ref
    result["fillReview"] = {"reviewItems": result["reviewItems"]}

    return result


def _proposals_from_extracted(extracted_values: list[dict]) -> list[dict]:
    """source extractor 결과 → AI proposal 호환 형식 변환 (도구만 제공).

    **AI 없이 자동 입력은 금지된다 (CLAUDE.md §10).** 본 함수는
    `ai_proposal_fn`이 명시적으로 호출할 수 있는 도구일 뿐, master 회로가
    자동 fallback으로 사용하지 않는다. 호출 권한은 AI가 가진다.
    """
    out: list[dict] = []
    for i, v in enumerate(extracted_values or []):
        out.append({
            "proposalId": f"src-{v.get('sourceId', 'unknown')}-{i}",
            "label": v.get("label"),
            "value": v.get("value"),
            "confidence": float(v.get("confidence") or 0.0),
            "evidence": [{"sourceRef": v.get("sourceRef"),
                            "evidenceType": v.get("evidenceType")}],
            "modelId": "source_extractor_fallback",
        })
    return out


def dump_contract_snapshot() -> dict:
    return {
        "contractName": CONTRACT_NAME,
        "contractVersion": CONTRACT_VERSION,
        "stages": ["recognition", "slot_detection",
                      "source_extraction", "ai_proposal_routing"],
    }


# ── production isolation ───────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PATHS_FOR_MASTER: tuple[Path, ...] = (
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_contract.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_ui_adapter.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_live_pipeline.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/evidence_ingestion_contract.py",
)
FORBIDDEN_MASTER_IMPORTS: tuple[str, ...] = (
    "auto_fill_master",
    "run_auto_fill_master",
)


def audit_master_isolation() -> dict:
    violations: list[dict] = []
    checked: list[str] = []
    for path in PRODUCTION_PATHS_FOR_MASTER:
        if not path.is_file():
            continue
        checked.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in FORBIDDEN_MASTER_IMPORTS:
            if needle in text:
                violations.append({
                    "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "forbidden": needle,
                })
    return {"violations": violations, "ok": not violations,
              "filesChecked": checked}
