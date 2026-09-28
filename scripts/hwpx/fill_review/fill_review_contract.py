"""HWPX-DOCUMENT-FILL-REVIEW-CONTRACT-01

문서 인지 → 입력 필요항목 도출 → 자료 매칭 → 부족자료 요청 → 사용자 검수 → 승인된 항목만
writer에 넘기는 검수 계약(JSON contract).

이 모듈은 deterministic rule-based이며 외부 AI/API를 호출하지 않는다.
writer를 호출하지 않으며 output HWPX를 생성하지 않는다. 원본 HWPX 파일은 절대
수정되지 않는다.

공식 paragraph 전체 교체 operation 이름은 ``setParagraphText``로 고정한다.
``setCellParagraphText``는 공식 operation이 아니다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

SCHEMA_VERSION = "fill_review_v1"
ENGINE_VERSION = "0.1.0"

# 공식 paragraph 전체 교체 operation 이름 (lock)
OFFICIAL_PARAGRAPH_FULL_REPLACE_OP = "setParagraphText"
# 비공식/금지 paragraph operation 이름
FORBIDDEN_PARAGRAPH_OP_NAMES: frozenset[str] = frozenset({"setCellParagraphText"})

# 이번 fill review 계약에서 인정하는 writer operation 전체 목록
# 기존 edit_plan contract의 ALLOWED_OPERATION_TYPES의 부분집합이어야 한다.
ALLOWED_FILL_REVIEW_OPERATIONS: frozenset[str] = frozenset({
    "setCellText",
    "setCellHorizontalAlign",
    "setCellVerticalAlign",
    "setParagraphText",
    "replaceTextRun",
})

# 본 builder가 승인 결과로 자동 생성하는 operation 부분집합
# (align operation은 fill review 단계에서 자동 생성하지 않는다)
AUTOGEN_OPERATIONS: frozenset[str] = frozenset({
    "setCellText", "setParagraphText", "replaceTextRun",
})

# 승인 decision
DECISION_APPROVE = "APPROVE"
DECISION_REJECT = "REJECT"
DECISION_HOLD = "HOLD"
DECISION_EDIT_VALUE = "EDIT_VALUE"
DECISION_REQUEST_MATERIAL = "REQUEST_MATERIAL"
ALLOWED_DECISIONS: frozenset[str] = frozenset({
    DECISION_APPROVE, DECISION_REJECT, DECISION_HOLD,
    DECISION_EDIT_VALUE, DECISION_REQUEST_MATERIAL,
})

# semanticType / status 후보
SEMANTIC_TYPES: frozenset[str] = frozenset({
    "PROJECT_NAME", "CONTRACT_AMOUNT", "START_DATE", "END_DATE",
    "COMPANY_NAME", "BUSINESS_REGISTRATION_NUMBER", "SITE_MANAGER_NAME",
    "ADDRESS", "PHONE", "ATTACHMENT_DOCUMENT", "STAMP_OR_SEAL",
    "FREE_TEXT", "UNKNOWN",
})

STATUS_NEEDS_VALUE = "NEEDS_VALUE"
STATUS_MATCHED = "MATCHED"
STATUS_MISSING_SOURCE = "MISSING_SOURCE"
STATUS_NEEDS_USER_INPUT = "NEEDS_USER_INPUT"
STATUS_READY_FOR_REVIEW = "READY_FOR_REVIEW"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_HELD = "HELD"

# 위험 등급
RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"

# 라벨 텍스트 → semanticType 규칙 매핑
_LABEL_TO_SEMANTIC: dict[str, str] = {
    "공사명": "PROJECT_NAME",
    "프로젝트명": "PROJECT_NAME",
    "사업명": "PROJECT_NAME",
    "계약금액": "CONTRACT_AMOUNT",
    "총공사금액": "CONTRACT_AMOUNT",
    "도급금액": "CONTRACT_AMOUNT",
    "착공일": "START_DATE",
    "시작일": "START_DATE",
    "준공일": "END_DATE",
    "완공일": "END_DATE",
    "종료일": "END_DATE",
    "회사명": "COMPANY_NAME",
    "상호": "COMPANY_NAME",
    "업체명": "COMPANY_NAME",
    "사업자등록번호": "BUSINESS_REGISTRATION_NUMBER",
    "현장소장": "SITE_MANAGER_NAME",
    "현장소장명": "SITE_MANAGER_NAME",
    "주소": "ADDRESS",
    "소재지": "ADDRESS",
    "전화번호": "PHONE",
    "연락처": "PHONE",
    "휴대전화": "PHONE",
    "도장": "STAMP_OR_SEAL",
    "직인": "STAMP_OR_SEAL",
    "인감": "STAMP_OR_SEAL",
    "첨부": "ATTACHMENT_DOCUMENT",
    "첨부서류": "ATTACHMENT_DOCUMENT",
    "첨부파일": "ATTACHMENT_DOCUMENT",
    # ── HWPX-FILL-REVIEW-LABEL-DICTIONARY-EXPANSION-01: 실문서 라벨 확장 ──
    # 기관·회사 식별
    "기관명": "COMPANY_NAME",
    "명칭": "COMPANY_NAME",
    "명칭상호": "COMPANY_NAME",        # "명칭(상호)" 정규화 결과
    "수신": "COMPANY_NAME",
    "수신처": "COMPANY_NAME",
    "회사확인": "COMPANY_NAME",
    # 담당자/관리자/평가자
    "평가사": "SITE_MANAGER_NAME",
    "평가반장": "SITE_MANAGER_NAME",
    "점검자": "SITE_MANAGER_NAME",
    "작성자": "SITE_MANAGER_NAME",
    "관계인": "SITE_MANAGER_NAME",
    "주된점검인력": "SITE_MANAGER_NAME",
    "보조점검인력": "SITE_MANAGER_NAME",
    "소방안전관리자": "SITE_MANAGER_NAME",
    "성명": "SITE_MANAGER_NAME",
    "담당자": "SITE_MANAGER_NAME",
    # 첨부 자료
    "소방계획서": "ATTACHMENT_DOCUMENT",
    "사업계획서": "ATTACHMENT_DOCUMENT",
    "보고서": "ATTACHMENT_DOCUMENT",
    # 날짜류
    "시정조치기한": "END_DATE",
    "건축허가일": "START_DATE",
    "사용승인일": "END_DATE",
    "점검기간": "START_DATE",
    "평가일자": "START_DATE",
    "발행일자": "START_DATE",
    "접수일": "START_DATE",
    "처리일": "END_DATE",
    "일자": "START_DATE",
    # 자유 텍스트 입력란 (식별 가능한 폼 필드)
    "발행번호": "FREE_TEXT",
    "접수번호": "FREE_TEXT",
    "처리번호": "FREE_TEXT",
    "평가종류": "FREE_TEXT",
    "부적합내용": "FREE_TEXT",
    "원인분석": "FREE_TEXT",
    "재발방지대책": "FREE_TEXT",
    "시정조치결과": "FREE_TEXT",
    "시정조치결과확인": "FREE_TEXT",
    "확인내용": "FREE_TEXT",
    "처리기간": "FREE_TEXT",
    # 건설 현장/시공 라벨
    "현장명": "COMPANY_NAME",
    "자재공급공장명": "COMPANY_NAME",
    "공사감독자": "SITE_MANAGER_NAME",
    "시공자": "SITE_MANAGER_NAME",
    "시공위치": "ADDRESS",
    "점검일자": "START_DATE",
    "자재반입량": "FREE_TEXT",
}

# semanticType → 필요 evidence sourceType
_EVIDENCE_REQUIRED_FOR_SEMANTIC: dict[str, str] = {
    "BUSINESS_REGISTRATION_NUMBER": "BUSINESS_LICENSE",
    "STAMP_OR_SEAL": "SEAL_IMAGE",
    "ATTACHMENT_DOCUMENT": "UPLOADED_DOCUMENT",
}

# evidence extracted field → semanticType 매핑 (역방향)
_EVIDENCE_FIELD_TO_SEMANTIC: dict[str, str] = {
    "projectName": "PROJECT_NAME",
    "공사명": "PROJECT_NAME",
    "contractAmount": "CONTRACT_AMOUNT",
    "계약금액": "CONTRACT_AMOUNT",
    "startDate": "START_DATE",
    "착공일": "START_DATE",
    "endDate": "END_DATE",
    "준공일": "END_DATE",
    "companyName": "COMPANY_NAME",
    "상호": "COMPANY_NAME",
    "businessRegistrationNumber": "BUSINESS_REGISTRATION_NUMBER",
    "사업자등록번호": "BUSINESS_REGISTRATION_NUMBER",
    "siteManagerName": "SITE_MANAGER_NAME",
    "현장소장": "SITE_MANAGER_NAME",
    "address": "ADDRESS",
    "주소": "ADDRESS",
    "phone": "PHONE",
    "연락처": "PHONE",
}


# ── dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class FillReviewFinding:
    code: str
    detail: str
    requirementId: str | None = None
    reviewItemId: str | None = None

    def to_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail,
                "requirementId": self.requirementId,
                "reviewItemId": self.reviewItemId}


@dataclass
class ApprovedEditPlan:
    planId: str
    sourceDocumentHash: str
    schemaVersion: str = SCHEMA_VERSION
    operations: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    findings: list[FillReviewFinding] = field(default_factory=list)
    verdict: str = "BLOCKED_INVALID_PLAN"
    writerCalled: bool = False
    outputCreated: bool = False
    originalUnmodified: bool = True

    def to_dict(self) -> dict:
        return {
            "planId": self.planId,
            "sourceDocumentHash": self.sourceDocumentHash,
            "schemaVersion": self.schemaVersion,
            "operations": self.operations,
            "skipped": self.skipped,
            "findings": [f.to_dict() for f in self.findings],
            "verdict": self.verdict,
            "writerCalled": self.writerCalled,
            "outputCreated": self.outputCreated,
            "originalUnmodified": self.originalUnmodified,
        }


# ── builder helpers ─────────────────────────────────────────────────────────

def _normalize_label(text: str) -> str:
    if not text:
        return ""
    # 공백/괄호/콜론 등 제거
    t = text.strip()
    for ch in ("(", ")", ":", "：", " ", "　"):
        t = t.replace(ch, "")
    return t


def _label_to_semantic(label_text: str) -> str | None:
    norm = _normalize_label(label_text)
    if not norm:
        return None
    return _LABEL_TO_SEMANTIC.get(norm)


def _find_value_cell_for_label(cells: list[dict], label_cell: dict) -> dict | None:
    """label_cell의 오른쪽 셀(같은 row, col+1)을 반환. 없으면 None."""
    table_key_prefix = (label_cell.get("cellKey") or "").rsplit(":", 2)[0]
    row = label_cell.get("rowIndex")
    col = label_cell.get("cellIndex")
    if row is None or col is None or not table_key_prefix:
        return None
    target_col = col + 1
    for c in cells:
        if (c.get("cellKey") or "").startswith(table_key_prefix + ":") and \
                c.get("rowIndex") == row and c.get("cellIndex") == target_col:
            return c
    return None


# ── public API ──────────────────────────────────────────────────────────────

def make_document_recognition_result(*, documentId: str = "",
                                          sourceDocumentHash: str = "",
                                          sourcePath: str = "",
                                          sections: list | None = None,
                                          paragraphs: list | None = None,
                                          tables: list | None = None,
                                          cells: list | None = None,
                                          objects: list | None = None,
                                          objectCellMappings: list | None = None,
                                          recognitionWarnings: list | None = None) -> dict:
    """recognition 결과 dict 생성 (테스트 보조용)."""
    return {
        "documentId": documentId or str(uuid.uuid4()),
        "sourceDocumentHash": sourceDocumentHash,
        "sourcePath": sourcePath,
        "schemaVersion": SCHEMA_VERSION,
        "engineVersion": ENGINE_VERSION,
        "requestId": str(uuid.uuid4()),
        "sections": sections or [],
        "paragraphs": paragraphs or [],
        "tables": tables or [],
        "cells": cells or [],
        "objects": objects or [],
        "objectCellMappings": objectCellMappings or [],
        "recognitionWarnings": recognitionWarnings or [],
    }


def build_fill_requirements(recognition_result: dict) -> list[dict]:
    """recognition.cells / paragraphs에서 FillRequirement 목록 생성.

    규칙:
      - 셀 텍스트가 _LABEL_TO_SEMANTIC에 매칭되면 → 우측 셀이 value target
      - paragraph 텍스트가 ``__PLACEHOLDER__`` 패턴이면 → paragraph target
      - paragraph 텍스트가 _LABEL_TO_SEMANTIC에 매칭되면 → 해당 paragraph가 자체 target
    """
    cells = recognition_result.get("cells", []) or []
    paragraphs = recognition_result.get("paragraphs", []) or []
    requirements: list[dict] = []
    counter = 0

    # cell label → value 셀 매핑
    for cell in cells:
        label_text = cell.get("normalizedText", "") or ""
        semantic = _label_to_semantic(label_text)
        if semantic is None:
            continue
        value_cell = _find_value_cell_for_label(cells, cell)
        if value_cell is None:
            continue
        counter += 1
        current_value = value_cell.get("normalizedText", "") or ""
        # ATTACHMENT_DOCUMENT / STAMP_OR_SEAL은 셀 텍스트만으로 채워지지 않으므로 NEEDS_VALUE
        if current_value and semantic not in ("ATTACHMENT_DOCUMENT", "STAMP_OR_SEAL"):
            status = STATUS_MATCHED
        else:
            status = STATUS_NEEDS_VALUE
        requirements.append({
            "requirementId": f"req_{counter:03d}",
            "label": label_text,
            "semanticType": semantic,
            "target": {
                "targetType": "cell",
                "cellKey": value_cell.get("cellKey"),
                "paragraphKey": None,
            },
            "currentValue": current_value,
            "expectedBefore": current_value,
            "required": True,
            "status": status,
        })

    # paragraph placeholder 또는 label
    for p in paragraphs:
        text = (p.get("text", "") or "").strip()
        if not text:
            continue
        # __KEY__ placeholder
        if text.startswith("__") and text.endswith("__") and len(text) > 4:
            inner = text[2:-2]
            # 1) 직접 SEMANTIC_TYPES 이름 일치 (e.g. "__PROJECT_NAME__")
            if inner in SEMANTIC_TYPES:
                semantic = inner
            else:
                semantic = (_LABEL_TO_SEMANTIC.get(inner)
                             or _label_to_semantic(inner)
                             or "FREE_TEXT")
            counter += 1
            requirements.append({
                "requirementId": f"req_{counter:03d}",
                "label": inner,
                "semanticType": semantic,
                "target": {
                    "targetType": "paragraph",
                    "cellKey": None,
                    "paragraphKey": p.get("paragraphKey"),
                },
                "currentValue": text,
                "expectedBefore": text,
                "required": True,
                "status": STATUS_NEEDS_VALUE,
            })
    return requirements


def match_requirements_with_evidence(requirements: list[dict],
                                          evidence_sources: list[dict]) -> list[dict]:
    """FillRequirement와 EvidenceSource를 매칭해 FillMatch 목록 생성.

    confidence는 추천 강도일 뿐, 자동 APPROVE는 발생하지 않는다.
    """
    matches: list[dict] = []
    match_counter = 0
    for req in requirements:
        sem = req.get("semanticType")
        for ev in (evidence_sources or []):
            extracted = ev.get("extractedFields", {}) or {}
            for field_name, field_value in extracted.items():
                ev_sem = _EVIDENCE_FIELD_TO_SEMANTIC.get(field_name)
                if ev_sem == sem and field_value is not None and str(field_value):
                    match_counter += 1
                    matches.append({
                        "matchId": f"match_{match_counter:03d}",
                        "requirementId": req["requirementId"],
                        "evidenceId": ev.get("evidenceId"),
                        "fieldName": field_name,
                        "proposedValue": str(field_value),
                        "confidence": float(ev.get("confidence", 0.5)),
                        "matchReason": f"evidence_field_{field_name}_matched_semantic_{sem}",
                        "needsUserReview": True,
                    })
                    break   # 같은 evidence에서 첫 매칭만 사용
    return matches


def build_missing_material_requests(requirements: list[dict],
                                          evidence_sources: list[dict],
                                          matches: list[dict] | None = None) -> list[dict]:
    """필요 자료가 evidence에 없으면 MissingMaterialRequest 생성."""
    matched_req_ids = {m.get("requirementId") for m in (matches or [])}
    available_source_types = {(ev.get("sourceType") or "UNKNOWN").upper()
                                  for ev in (evidence_sources or [])}
    requests: list[dict] = []
    req_counter = 0
    for req in requirements:
        sem = req.get("semanticType")
        # 이미 matched이면 자료 요청 불필요
        if req["requirementId"] in matched_req_ids:
            continue
        if req.get("status") == STATUS_MATCHED:
            continue
        required_evidence = _EVIDENCE_REQUIRED_FOR_SEMANTIC.get(sem)
        if required_evidence is None:
            # 단순 텍스트 입력류 — 사용자 직접 입력 후보 (자료요청 아님)
            continue
        if required_evidence in available_source_types:
            continue
        req_counter += 1
        requests.append({
            "requestId": f"matreq_{req_counter:03d}",
            "requirementId": req["requirementId"],
            "requestedMaterialType": required_evidence,
            "messageToUser": _user_message_for_material(required_evidence, sem),
            "reason": f"semantic={sem} requires {required_evidence} but none uploaded",
            "blocking": True,
        })
    return requests


def _user_message_for_material(material: str, semantic: str | None) -> str:
    mapping = {
        "BUSINESS_LICENSE": "사업자등록증 파일을 업로드해주세요.",
        "SEAL_IMAGE": "도장/직인 이미지를 업로드해주세요.",
        "UPLOADED_DOCUMENT": "첨부서류 파일을 업로드해주세요.",
    }
    return mapping.get(material, f"{material} 자료를 업로드해주세요.")


def build_review_items(requirements: list[dict],
                          matches: list[dict],
                          missing_requests: list[dict]) -> list[dict]:
    """FillReviewItem 목록 생성 (브라우저 표시용)."""
    matches_by_req: dict[str, list[dict]] = {}
    for m in matches:
        matches_by_req.setdefault(m.get("requirementId", ""), []).append(m)
    requests_by_req: dict[str, list[dict]] = {}
    for r in missing_requests:
        requests_by_req.setdefault(r.get("requirementId", ""), []).append(r)

    items: list[dict] = []
    counter = 0
    for req in requirements:
        counter += 1
        rid = req["requirementId"]
        proposed_value = None
        evidence_refs: list[str] = []
        for m in matches_by_req.get(rid, []):
            if proposed_value is None:
                proposed_value = m.get("proposedValue")
            if m.get("evidenceId"):
                evidence_refs.append(m["evidenceId"])
        current_value = req.get("currentValue", "")
        related_requests = requests_by_req.get(rid, [])
        # risk: evidence 없는 proposedValue → HIGH, evidence 있으면 MEDIUM,
        # 이미 matched이면 LOW
        if proposed_value and evidence_refs:
            risk = RISK_MEDIUM
        elif proposed_value and not evidence_refs:
            risk = RISK_HIGH
        elif req.get("status") == STATUS_MATCHED:
            risk = RISK_LOW
        else:
            risk = RISK_MEDIUM
        # status 결정
        if related_requests:
            status = STATUS_NEEDS_USER_INPUT
        elif proposed_value:
            status = STATUS_READY_FOR_REVIEW
        elif req.get("status") == STATUS_MATCHED:
            status = STATUS_MATCHED
        else:
            status = STATUS_NEEDS_VALUE
        items.append({
            "reviewItemId": f"rev_{counter:03d}",
            "requirementId": rid,
            "target": dict(req.get("target") or {}),
            "currentValue": current_value,
            "proposedValue": proposed_value,
            "evidenceRefs": evidence_refs,
            "beforePreview": current_value,
            "afterPreview": proposed_value if proposed_value is not None else current_value,
            "riskLevel": risk,
            "status": status,
            "allowedDecisions": list(ALLOWED_DECISIONS),
            "relatedMaterialRequests": [r["requestId"] for r in related_requests],
        })
    return items


def _decision_dict_valid(d) -> bool:
    if not isinstance(d, dict):
        return False
    for k in ("reviewItemId", "decision"):
        if d.get(k) is None or (isinstance(d.get(k), str) and not d.get(k).strip()):
            return False
    return d.get("decision") in ALLOWED_DECISIONS


def _operation_for_review_item(item: dict, decision: dict,
                                    plan_id: str) -> tuple[dict | None, str | None]:
    """승인된 review item을 writer operation으로 변환.

    return (operation_dict | None, skip_reason | None)
    """
    target = item.get("target") or {}
    expected_before = item.get("currentValue", "")
    # APPROVE는 proposedValue를 그대로 적용, EDIT_VALUE는 사용자가 수정한 값 적용
    if decision.get("decision") == DECISION_EDIT_VALUE:
        new_value = decision.get("editedValue")
        if new_value is None:
            return None, "edit_value_missing"
    else:
        new_value = item.get("proposedValue")
        if new_value is None:
            return None, "proposed_value_missing"

    target_type = target.get("targetType")
    if target_type == "cell":
        cell_key = target.get("cellKey")
        if not cell_key:
            return None, "cell_key_missing"
        # cellKey "t_s0_000:r3:c1" → tableId / row / col
        try:
            table_id, r_part, c_part = cell_key.rsplit(":", 2)
            row = int(r_part[1:])
            col = int(c_part[1:])
        except (ValueError, IndexError):
            return None, "cell_key_unparseable"
        return {
            "operationId": f"op_{uuid.uuid4().hex[:8]}",
            "operationType": "setCellText",
            "target": {"tableId": table_id, "row": row, "col": col},
            "value": new_value,
            "preserveStyle": True,
            "expectedBefore": expected_before,
            "riskLevel": item.get("riskLevel", RISK_LOW).lower(),
            "requiresReview": False,
            "reason": f"approved_review_item={item.get('reviewItemId')}",
        }, None
    if target_type == "paragraph":
        para_key = target.get("paragraphKey")
        if not para_key:
            return None, "paragraph_key_missing"
        # paragraphKey "p_s0_0003" → section / para idx
        if not (para_key.startswith("p_s") and "_" in para_key[3:]):
            return None, "paragraph_key_unparseable"
        try:
            _, sec_part, idx_part = para_key.split("_")
            section_idx = int(sec_part[1:])
            paragraph_idx = int(idx_part)
        except (ValueError, IndexError):
            return None, "paragraph_key_unparseable"
        return {
            "operationId": f"op_{uuid.uuid4().hex[:8]}",
            "operationType": "setParagraphText",
            "target": {
                "sectionIndex": section_idx,
                "paragraphIndex": paragraph_idx,
                "paragraphKey": para_key,
            },
            "value": new_value,
            "preserveStyle": True,
            "expectedBefore": expected_before,
            "riskLevel": item.get("riskLevel", RISK_LOW).lower(),
            "requiresReview": False,
            "reason": f"approved_review_item={item.get('reviewItemId')}",
        }, None
    return None, "unsupported_target_type"


def build_approved_edit_plan(review_items: list[dict],
                                  decisions: list[dict],
                                  *, source_document_hash: str,
                                  plan_id: str | None = None) -> ApprovedEditPlan:
    """APPROVE / EDIT_VALUE decision만 writer operation으로 변환.

    sourceDocumentHash가 비면 BLOCKED_INVALID_PLAN.
    REJECT/HOLD/REQUEST_MATERIAL은 operation 생성 금지.
    """
    plan = ApprovedEditPlan(
        planId=plan_id or f"plan_{uuid.uuid4().hex[:8]}",
        sourceDocumentHash=source_document_hash or "",
    )

    if not source_document_hash:
        plan.verdict = "BLOCKED_INVALID_PLAN"
        plan.findings.append(FillReviewFinding(
            code="SOURCE_DOC_HASH_REQUIRED",
            detail="sourceDocumentHash is required",
        ))
        return plan

    items_by_id = {it.get("reviewItemId"): it for it in review_items}

    for d in (decisions or []):
        if not _decision_dict_valid(d):
            plan.skipped.append({
                "reviewItemId": d.get("reviewItemId") if isinstance(d, dict) else None,
                "reason": "invalid_decision",
            })
            plan.findings.append(FillReviewFinding(
                code="INVALID_DECISION",
                detail=f"decision={d}",
            ))
            continue
        rid = d["reviewItemId"]
        decision_val = d["decision"]
        item = items_by_id.get(rid)
        if item is None:
            plan.skipped.append({"reviewItemId": rid, "reason": "item_not_found"})
            plan.findings.append(FillReviewFinding(
                code="REVIEW_ITEM_NOT_FOUND",
                detail=f"reviewItemId={rid}", reviewItemId=rid,
            ))
            continue

        if decision_val in (DECISION_REJECT, DECISION_HOLD, DECISION_REQUEST_MATERIAL):
            plan.skipped.append({
                "reviewItemId": rid, "reason": f"decision_{decision_val.lower()}",
            })
            continue

        # APPROVE 또는 EDIT_VALUE
        op, skip_reason = _operation_for_review_item(item, d, plan.planId)
        if op is None:
            plan.skipped.append({"reviewItemId": rid, "reason": skip_reason or "no_op"})
            plan.findings.append(FillReviewFinding(
                code="OPERATION_NOT_GENERATED",
                detail=skip_reason or "no_op", reviewItemId=rid,
            ))
            continue

        # 추가 안전 검증
        if op["operationType"] not in AUTOGEN_OPERATIONS:
            plan.skipped.append({
                "reviewItemId": rid, "reason": "operation_not_in_autogen_set",
            })
            plan.findings.append(FillReviewFinding(
                code="UNSUPPORTED_OPERATION",
                detail=f"operationType={op['operationType']!r}",
                reviewItemId=rid,
            ))
            continue
        if op["operationType"] in FORBIDDEN_PARAGRAPH_OP_NAMES:
            plan.skipped.append({
                "reviewItemId": rid, "reason": "forbidden_operation_name",
            })
            plan.findings.append(FillReviewFinding(
                code="FORBIDDEN_OPERATION_NAME",
                detail=(f"operationType={op['operationType']!r} is forbidden; "
                          f"use {OFFICIAL_PARAGRAPH_FULL_REPLACE_OP}"),
                reviewItemId=rid,
            ))
            continue
        if "expectedBefore" not in op:
            plan.skipped.append({
                "reviewItemId": rid, "reason": "expected_before_missing",
            })
            plan.findings.append(FillReviewFinding(
                code="EXPECTED_BEFORE_REQUIRED",
                detail=f"reviewItemId={rid}", reviewItemId=rid,
            ))
            continue
        if not op.get("target"):
            plan.skipped.append({
                "reviewItemId": rid, "reason": "target_missing",
            })
            plan.findings.append(FillReviewFinding(
                code="TARGET_REQUIRED", detail=f"reviewItemId={rid}",
                reviewItemId=rid,
            ))
            continue
        plan.operations.append(op)

    plan.verdict = "READY_FOR_WRITER" if plan.operations and not any(
        f.code in {"SOURCE_DOC_HASH_REQUIRED"} for f in plan.findings
    ) else (
        "BLOCKED_NO_APPROVED_OPS" if not plan.operations else "BLOCKED_INVALID_PLAN"
    )
    # 불변식
    plan.writerCalled = False
    plan.outputCreated = False
    plan.originalUnmodified = True
    return plan


# ── operation naming audit helper ─────────────────────────────────────────────

def is_official_paragraph_full_replace(op_type: str) -> bool:
    return op_type == OFFICIAL_PARAGRAPH_FULL_REPLACE_OP


def is_forbidden_operation_name(op_type: str) -> bool:
    return op_type in FORBIDDEN_PARAGRAPH_OP_NAMES
