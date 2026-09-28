"""HWPX-FILL-REVIEW-UI-ADAPTER-CONTRACT-01

FillReviewItem / MissingMaterialRequest / ApprovedEditPlan을
브라우저 검수 화면이 바로 렌더링할 수 있는 UI payload 계약으로 변환한다.

이 모듈은:
- writer를 호출하지 않는다.
- output HWPX를 생성하지 않는다.
- 원본 HWPX 파일을 수정하지 않는다.
- AI API / DB를 호출하지 않는다.
- 결정 자체를 만들지 않는다. confidence는 표시만 가능하며 자동 승인 근거가 아니다.

공식 paragraph 전체 교체 operation 이름은 setParagraphText로 고정한다.
setCellParagraphText는 금지된 이름이다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .fill_review_contract import (
    ALLOWED_DECISIONS,
    DECISION_APPROVE,
    DECISION_EDIT_VALUE,
    DECISION_HOLD,
    DECISION_REQUEST_MATERIAL,
    FORBIDDEN_PARAGRAPH_OP_NAMES,
    OFFICIAL_PARAGRAPH_FULL_REPLACE_OP,
    RISK_HIGH,
    RISK_LOW,
    STATUS_MATCHED,
    STATUS_NEEDS_USER_INPUT,
    STATUS_READY_FOR_REVIEW,
)
from .fill_review_contract import (
    SCHEMA_VERSION as CONTRACT_SCHEMA_VERSION,
)

UI_SCHEMA_VERSION = "fill_review_ui_v1"
UI_ENGINE_VERSION = "0.1.0"

# 요청 자료 종류별 업로드 라벨
_UPLOAD_LABEL_BY_MATERIAL: dict[str, str] = {
    "BUSINESS_LICENSE": "사업자등록증 업로드",
    "SEAL_IMAGE": "도장/직인 이미지 업로드",
    "UPLOADED_DOCUMENT": "첨부서류 업로드",
    "CONTRACT_XLSX": "계약서 Excel 업로드",
    "ESTIMATE_XLSX": "견적서 Excel 업로드",
    "USER_INPUT": "직접 입력",
    "OCR_RESULT": "OCR 결과 업로드",
    "MANUAL_ENTRY": "수기 입력",
    "UNKNOWN": "자료 업로드",
}

# 요청 자료 종류별 허용 확장자
_ACCEPTED_FILE_TYPES: dict[str, list[str]] = {
    "BUSINESS_LICENSE": ["pdf", "jpg", "jpeg", "png", "hwpx", "hwp"],
    "SEAL_IMAGE": ["png", "jpg", "jpeg"],
    "UPLOADED_DOCUMENT": ["pdf", "hwpx", "hwp", "docx"],
    "CONTRACT_XLSX": ["xlsx"],
    "ESTIMATE_XLSX": ["xlsx"],
    "OCR_RESULT": ["json", "txt"],
    "MANUAL_ENTRY": [],
    "USER_INPUT": [],
    "UNKNOWN": ["pdf", "jpg", "png"],
}


@dataclass
class DecisionValidationResult:
    valid: bool = False
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    acceptedDecisionCount: int = 0
    blockedDecisionCount: int = 0

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "acceptedDecisionCount": self.acceptedDecisionCount,
            "blockedDecisionCount": self.blockedDecisionCount,
        }


# ── target display & highlight ───────────────────────────────────────────────


def _parse_cell_key(cell_key: str | None):
    """t_s{section}_{table:03d}:r{row}:c{col} → (section, table, row, col)."""
    if not cell_key:
        return None
    try:
        table_part, r_part, c_part = cell_key.rsplit(":", 2)
        # table_part = "t_s0_000"
        prefix_parts = table_part.split("_")
        section = int(prefix_parts[1][1:])
        table_idx = int(prefix_parts[2])
        row = int(r_part[1:])
        col = int(c_part[1:])
        return section, table_idx, row, col
    except (ValueError, IndexError):
        return None


def _parse_paragraph_key(p_key: str | None):
    """p_s{section}_{paragraph:04d} → (section, paragraph)."""
    if not p_key:
        return None
    try:
        parts = p_key.split("_")
        if len(parts) != 3 or parts[0] != "p" or not parts[1].startswith("s"):
            return None
        return int(parts[1][1:]), int(parts[2])
    except (ValueError, IndexError):
        return None


def build_target_display(target: dict) -> str:
    """target dict → 사람이 읽는 표시 문자열."""
    if not isinstance(target, dict):
        return "위치 미지정"
    target_type = target.get("targetType")
    if target_type == "cell" and target.get("cellKey"):
        parsed = _parse_cell_key(target["cellKey"])
        if parsed is None:
            return "표 / 위치 파악 불가"
        section, table_idx, row, col = parsed
        return f"{section + 1}쪽 / 표 {table_idx + 1} / {row + 1}행 {col + 1}열"
    if target_type == "paragraph" and target.get("paragraphKey"):
        parsed = _parse_paragraph_key(target["paragraphKey"])
        if parsed is None:
            return "본문 / 위치 파악 불가"
        section, p_idx = parsed
        return f"본문 / {p_idx + 1}번째 문단"
    if target_type == "object" and target.get("objectKey"):
        obj_type = target.get("objectType") or "객체"
        return f"객체 / {obj_type}"
    return "위치 미지정"


def build_highlight(target: dict) -> dict:
    """target dict → highlight payload (시각화용 좌표/스타일)."""
    base = {
        "targetType": (target or {}).get("targetType"),
        "sectionIndex": None,
        "tableIndex": None,
        "rowIndex": None,
        "cellIndex": None,
        "paragraphIndex": None,
        "cellKey": None,
        "paragraphKey": None,
        "objectKey": None,
        "confidence": None,
        "highlightStyle": "MISSING",
    }
    if not isinstance(target, dict):
        return base
    ttype = target.get("targetType")
    if ttype == "cell" and target.get("cellKey"):
        parsed = _parse_cell_key(target["cellKey"])
        base["cellKey"] = target["cellKey"]
        base["highlightStyle"] = "CELL"
        if parsed is not None:
            section, table_idx, row, col = parsed
            base["sectionIndex"] = section
            base["tableIndex"] = table_idx
            base["rowIndex"] = row
            base["cellIndex"] = col
    elif ttype == "paragraph" and target.get("paragraphKey"):
        parsed = _parse_paragraph_key(target["paragraphKey"])
        base["paragraphKey"] = target["paragraphKey"]
        base["highlightStyle"] = "PARAGRAPH"
        if parsed is not None:
            section, p_idx = parsed
            base["sectionIndex"] = section
            base["paragraphIndex"] = p_idx
    elif ttype == "object" and target.get("objectKey"):
        base["objectKey"] = target["objectKey"]
        base["highlightStyle"] = "OBJECT"
    return base


def _evidence_badges_for_item(item: dict, evidence_index: dict) -> list[dict]:
    """item.evidenceRefs(list of evidenceId)로부터 EvidenceBadge[] 생성.

    evidence_index: {evidenceId: evidence_source_dict}
    """
    badges: list[dict] = []
    for ev_id in item.get("evidenceRefs") or []:
        ev = evidence_index.get(ev_id, {}) if isinstance(evidence_index, dict) else {}
        badges.append({
            "evidenceId": ev_id,
            "sourceType": ev.get("sourceType"),
            "sourceName": ev.get("sourceName"),
            "fieldName": None,
            "confidence": ev.get("confidence"),
            "displayText": ev.get("sourceName") or ev_id,
            "warning": None,
        })
    return badges


def _default_action_for(item: dict) -> str:
    status = item.get("status")
    allowed = item.get("allowedDecisions") or []
    if status == STATUS_NEEDS_USER_INPUT and DECISION_REQUEST_MATERIAL in allowed:
        return DECISION_REQUEST_MATERIAL
    if status == STATUS_READY_FOR_REVIEW and DECISION_APPROVE in allowed:
        return DECISION_APPROVE
    if status == STATUS_MATCHED and DECISION_APPROVE in allowed:
        return DECISION_APPROVE
    if DECISION_HOLD in allowed:
        return DECISION_HOLD
    return allowed[0] if allowed else DECISION_HOLD


def _section_title_for(section_idx: int | None) -> str:
    if section_idx is None:
        return "위치 미지정"
    return f"{section_idx + 1}쪽"


# ── main builder ─────────────────────────────────────────────────────────────


def _review_item_flags(item_status: str | None, risk_level: str | None) -> tuple[bool, bool, bool]:
    is_missing = item_status == STATUS_NEEDS_USER_INPUT
    is_ready = item_status in (STATUS_READY_FOR_REVIEW, STATUS_MATCHED)
    is_high_risk = risk_level == RISK_HIGH
    return is_missing, is_ready, is_high_risk


def _build_review_item_payload(
    item: dict,
    item_status: str | None,
    related_requests: list[dict],
    evidence_index: dict[str, dict],
) -> dict:
    highlight = build_highlight(item.get("target") or {})
    target_display = build_target_display(item.get("target") or {})
    evidence_badges = _evidence_badges_for_item(item, evidence_index)

    allowed_actions = [a for a in (item.get("allowedDecisions") or []) if a in ALLOWED_DECISIONS]
    if not related_requests and DECISION_REQUEST_MATERIAL in allowed_actions:
        allowed_actions = [a for a in allowed_actions if a != DECISION_REQUEST_MATERIAL]

    blocking_reason = None
    if item_status == STATUS_NEEDS_USER_INPUT and related_requests:
        blocking_reason = "missing_material_required"
    elif item.get("riskLevel") == RISK_HIGH:
        blocking_reason = "high_risk_review_required"

    return {
        "reviewItemId": item.get("reviewItemId"),
        "requirementId": item.get("requirementId"),
        "label": item.get("label", item.get("requirementId", "")),
        "semanticType": item.get("semanticType"),
        "target": dict(item.get("target") or {}),
        "targetDisplay": target_display,
        "currentValue": item.get("currentValue", ""),
        "proposedValue": item.get("proposedValue"),
        "beforePreview": item.get("beforePreview", ""),
        "afterPreview": item.get("afterPreview", ""),
        "evidenceBadges": evidence_badges,
        "riskLevel": item.get("riskLevel", RISK_LOW),
        "status": item_status,
        "allowedActions": allowed_actions,
        "defaultAction": _default_action_for({**item, "allowedDecisions": allowed_actions}),
        "blockingReason": blocking_reason,
        "highlight": highlight,
    }


def _build_missing_material_panel(missing_requests: list[dict]) -> tuple[list[dict], int, int]:
    panel_requests = []
    blocking_count = 0
    optional_count = 0
    for r in missing_requests or []:
        material = r.get("requestedMaterialType", "UNKNOWN")
        is_blocking = bool(r.get("blocking", True))
        if is_blocking:
            blocking_count += 1
        else:
            optional_count += 1
        panel_requests.append({
            "requestId": r.get("requestId"),
            "requirementId": r.get("requirementId"),
            "requestedMaterialType": material,
            "messageToUser": r.get("messageToUser", ""),
            "reason": r.get("reason", ""),
            "blocking": is_blocking,
            "suggestedUploadLabel": _UPLOAD_LABEL_BY_MATERIAL.get(
                material,
                _UPLOAD_LABEL_BY_MATERIAL["UNKNOWN"],
            ),
            "acceptedFileTypes": list(
                _ACCEPTED_FILE_TYPES.get(
                    material,
                    _ACCEPTED_FILE_TYPES["UNKNOWN"],
                )
            ),
        })
    return panel_requests, blocking_count, optional_count


def build_fill_review_page_payload(
    recognition_result: dict,
    review_items: list[dict],
    missing_requests: list[dict],
    evidence_sources: list[dict] | None = None,
) -> dict:
    """브라우저 검수 화면 payload 생성."""
    evidence_index: dict[str, dict] = {}
    for ev in evidence_sources or []:
        if isinstance(ev, dict) and ev.get("evidenceId"):
            evidence_index[ev["evidenceId"]] = ev

    requests_by_req: dict[str, list[dict]] = {}
    for r in missing_requests or []:
        requests_by_req.setdefault(r.get("requirementId", ""), []).append(r)

    # ReviewItemPayload[] 생성 + section 분류
    sections_map: dict[int, dict] = {}
    high_risk_count = 0
    ready_count = 0
    missing_count_items = 0

    for item in review_items:
        item_status = item.get("status")
        is_missing, is_ready, is_high_risk = _review_item_flags(item_status, item.get("riskLevel"))
        missing_count_items += is_missing
        ready_count += is_ready
        high_risk_count += is_high_risk

        # allowedActions: REQUEST_MATERIAL은 관련 request가 있을 때만 활성
        related_requests = requests_by_req.get(item.get("requirementId", ""), [])
        payload_item = _build_review_item_payload(
            item, item_status, related_requests, evidence_index
        )

        sec_idx = payload_item["highlight"].get("sectionIndex")
        sec_key = sec_idx if sec_idx is not None else -1
        section = sections_map.setdefault(
            sec_key,
            {
                "sectionId": f"sec_{sec_key:03d}" if sec_key >= 0 else "sec_unknown",
                "sectionTitle": _section_title_for(sec_idx),
                "sectionIndex": sec_idx,
                "items": [],
            },
        )
        section["items"].append(payload_item)

    review_sections = [sections_map[k] for k in sorted(sections_map.keys())]

    # missingMaterialPanel
    panel_requests, blocking_count, optional_count = _build_missing_material_panel(missing_requests)
    missing_material_panel = {
        "requests": panel_requests,
        "blockingCount": blocking_count,
        "optionalCount": optional_count,
    }

    summary = {
        "totalReviewItems": len(review_items),
        "readyForReviewCount": ready_count,
        "missingMaterialCount": len(panel_requests),
        "highRiskCount": high_risk_count,
        "approvedCount": 0,
        "rejectedCount": 0,
        "heldCount": 0,
    }

    decision_panel = {
        "allowedDecisions": sorted(ALLOWED_DECISIONS),
        "submitEndpointHint": "POST /api/fill-review/decisions",  # 정보용
    }

    payload = {
        "schemaVersion": UI_SCHEMA_VERSION,
        "contractSchemaVersion": CONTRACT_SCHEMA_VERSION,
        "engineVersion": UI_ENGINE_VERSION,
        "requestId": str(uuid.uuid4()),
        "documentId": (recognition_result or {}).get("documentId", ""),
        "sourceDocumentHash": (recognition_result or {}).get("sourceDocumentHash", ""),
        "summary": summary,
        "reviewSections": review_sections,
        "missingMaterialPanel": missing_material_panel,
        "decisionPanel": decision_panel,
        "warnings": [],
    }
    return payload


# ── decision payload validation ──────────────────────────────────────────────


def _decision_value_invalid(d: dict) -> bool:
    return d.get("decision") not in ALLOWED_DECISIONS


def validate_decision_payload(
    decision_payload: dict,
    review_items: list[dict],
    missing_requests: list[dict] | None = None,
    *,
    expected_source_hash: str | None = None,
) -> DecisionValidationResult:
    """브라우저에서 돌려보낸 decision payload 검증.

    writer plan을 만들지 않는다. fill_review_contract.build_approved_edit_plan에
    바로 넘길 수 있는 형태인지만 확인한다.
    """
    result = DecisionValidationResult()

    if not isinstance(decision_payload, dict):
        result.errors.append({
            "code": "PAYLOAD_NOT_OBJECT",
            "detail": "decision payload must be a dict",
        })
        result.valid = False
        result.blockedDecisionCount = 0
        return result

    # sourceDocumentHash 매칭
    payload_hash = decision_payload.get("sourceDocumentHash", "")
    if expected_source_hash is not None and payload_hash != expected_source_hash:
        result.errors.append({
            "code": "SOURCE_HASH_MISMATCH",
            "detail": f"expected={expected_source_hash!r} got={payload_hash!r}",
        })

    items_by_id = {it.get("reviewItemId"): it for it in (review_items or [])}
    items_with_missing = {r.get("requirementId") for r in (missing_requests or [])}

    decisions = decision_payload.get("decisions") or []
    if not isinstance(decisions, list):
        result.errors.append({"code": "DECISIONS_NOT_LIST", "detail": "decisions must be a list"})
        decisions = []

    seen_item_ids: set[str] = set()
    accepted = 0
    blocked = 0

    for idx, d in enumerate(decisions):
        if not isinstance(d, dict):
            result.errors.append({
                "code": "DECISION_NOT_OBJECT",
                "detail": f"decisions[{idx}] is not a dict",
            })
            blocked += 1
            continue

        item_id = d.get("reviewItemId")
        decision_val = d.get("decision")

        if not item_id:
            result.errors.append({
                "code": "REVIEW_ITEM_ID_REQUIRED",
                "detail": f"decisions[{idx}].reviewItemId missing",
            })
            blocked += 1
            continue

        if _decision_value_invalid(d):
            result.errors.append({
                "code": "INVALID_DECISION_VALUE",
                "detail": f"decision={decision_val!r} not in {sorted(ALLOWED_DECISIONS)}",
                "reviewItemId": item_id,
            })
            blocked += 1
            continue

        if item_id in seen_item_ids:
            result.errors.append({
                "code": "DUPLICATE_DECISION",
                "detail": f"duplicate reviewItemId={item_id!r}",
                "reviewItemId": item_id,
            })
            blocked += 1
            continue
        seen_item_ids.add(item_id)

        item = items_by_id.get(item_id)
        if item is None:
            result.errors.append({
                "code": "REVIEW_ITEM_NOT_FOUND",
                "detail": f"reviewItemId={item_id!r} not in review_items",
                "reviewItemId": item_id,
            })
            blocked += 1
            continue

        allowed_actions = item.get("allowedActions") or item.get("allowedDecisions") or []
        if decision_val not in allowed_actions:
            result.errors.append({
                "code": "DECISION_NOT_ALLOWED_FOR_ITEM",
                "detail": (f"decision={decision_val!r} not in allowedActions={allowed_actions}"),
                "reviewItemId": item_id,
            })
            blocked += 1
            continue

        if decision_val == DECISION_EDIT_VALUE:
            edited = d.get("editedValue")
            if edited is None or (isinstance(edited, str) and not edited.strip()):
                result.errors.append({
                    "code": "EDIT_VALUE_REQUIRES_VALUE",
                    "detail": "editedValue must be non-empty for EDIT_VALUE",
                    "reviewItemId": item_id,
                })
                blocked += 1
                continue

        if decision_val == DECISION_REQUEST_MATERIAL:
            # 해당 item의 requirementId에 missing material request가 있어야 함
            req_id = item.get("requirementId")
            if req_id not in items_with_missing:
                result.errors.append({
                    "code": "REQUEST_MATERIAL_NOT_AVAILABLE",
                    "detail": (
                        f"REQUEST_MATERIAL for reviewItemId={item_id!r} "
                        "but no missing material request"
                    ),
                    "reviewItemId": item_id,
                })
                blocked += 1
                continue

        # APPROVE on HIGH risk → warning만 (차단 X)
        if decision_val == DECISION_APPROVE and item.get("riskLevel") == RISK_HIGH:
            result.warnings.append({
                "code": "APPROVE_ON_HIGH_RISK",
                "detail": f"reviewItemId={item_id!r} is HIGH risk",
                "reviewItemId": item_id,
            })

        # naming guard: 어떤 경우에도 setCellParagraphText 등 금지명을
        # decision에 포함시키면 안 됨 (사실 decision은 op_type이 아니지만 방어선)
        for k in ("editedValueOperationType",):  # 미래 확장 대비
            if d.get(k) in FORBIDDEN_PARAGRAPH_OP_NAMES:
                result.errors.append({
                    "code": "FORBIDDEN_OPERATION_NAME",
                    "detail": (
                        f"{k}={d.get(k)!r} is forbidden; use {OFFICIAL_PARAGRAPH_FULL_REPLACE_OP}"
                    ),
                    "reviewItemId": item_id,
                })
                blocked += 1
                break
        else:
            accepted += 1
            continue

    result.acceptedDecisionCount = accepted
    result.blockedDecisionCount = blocked
    result.valid = (not result.errors) and accepted > 0
    return result


# ── operation naming reaffirmation (UI 측에서도 잠금) ────────────────────────


def is_official_paragraph_full_replace(op_type: str) -> bool:
    return op_type == OFFICIAL_PARAGRAPH_FULL_REPLACE_OP


def is_forbidden_operation_name(op_type: str) -> bool:
    return op_type in FORBIDDEN_PARAGRAPH_OP_NAMES
