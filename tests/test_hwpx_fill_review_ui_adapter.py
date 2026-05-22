"""HWPX-FILL-REVIEW-UI-ADAPTER-CONTRACT-01 테스트.

브라우저 UI payload 변환 + decision payload 검증.
writer 미호출, output 미생성, 원본 무수정.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

METADATA_FORM = PROJECT_ROOT / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"


@pytest.fixture(scope="module")
def fr():
    from hwpx.fill_review import fill_review_contract as m
    return m


@pytest.fixture(scope="module")
def ui():
    from hwpx.fill_review import fill_review_ui_adapter as m
    return m


def _make_label_value_cells(label, label_key, value_key,
                                label_col=0, value_col=1, row=0):
    return [
        {"cellKey": label_key, "normalizedText": label,
          "rowIndex": row, "cellIndex": label_col},
        {"cellKey": value_key, "normalizedText": "",
          "rowIndex": row, "cellIndex": value_col},
    ]


def _recognition(fr, cells=None, paragraphs=None, source_hash="sha256:abc",
                    document_id="doc-1"):
    return fr.make_document_recognition_result(
        documentId=document_id,
        sourceDocumentHash=source_hash,
        sourcePath="/tmp/doc.hwpx",
        cells=cells or [],
        paragraphs=paragraphs or [],
    )


def _evidence(eid, source_type, fields, name="evidence", confidence=0.8):
    return {
        "evidenceId": eid, "sourceType": source_type,
        "sourceName": name, "sourceHash": "sha:ev",
        "extractedFields": fields, "confidence": confidence,
        "warnings": [],
    }


def _decision_payload(items, source_hash, decisions):
    return {
        "documentId": "doc-1",
        "sourceDocumentHash": source_hash,
        "decisions": decisions,
    }


def _decision(rid, decision, edited=None, comment="",
                 reviewer="manual", at="2026-05-18T01:00:00Z"):
    d = {
        "reviewItemId": rid, "decision": decision,
        "userComment": comment, "decidedBy": reviewer, "decidedAt": at,
    }
    if edited is not None:
        d["editedValue"] = edited
    return d


def _build_simple(fr, project_name="VAL", source_hash="sha256:abc"):
    cells = _make_label_value_cells(
        "공사명", "t_s0_000:r0:c0", "t_s0_000:r0:c1",
    )
    rec = _recognition(fr, cells=cells, source_hash=source_hash)
    reqs = fr.build_fill_requirements(rec)
    ev = _evidence("ev1", "CONTRACT_XLSX", {"projectName": project_name})
    matches = fr.match_requirements_with_evidence(reqs, [ev])
    items = fr.build_review_items(reqs, matches, [])
    return rec, reqs, items, [ev], []


def _build_with_missing(fr, source_hash="sha256:abc"):
    """사업자등록번호 라벨 + evidence 없음 → missing material 시나리오."""
    cells = _make_label_value_cells(
        "사업자등록번호", "t_s0_000:r2:c0", "t_s0_000:r2:c1", row=2,
    )
    rec = _recognition(fr, cells=cells, source_hash=source_hash)
    reqs = fr.build_fill_requirements(rec)
    matches = fr.match_requirements_with_evidence(reqs, [])
    requests = fr.build_missing_material_requests(reqs, [], matches)
    items = fr.build_review_items(reqs, matches, requests)
    return rec, reqs, items, [], requests


# ── T01: payload 1건 생성 ────────────────────────────────────────────────────

def test_single_item_produces_payload(fr, ui):
    rec, _, items, evidence, requests = _build_simple(fr)
    payload = ui.build_fill_review_page_payload(rec, items, requests, evidence)
    assert payload["schemaVersion"] == ui.UI_SCHEMA_VERSION
    assert payload["documentId"] == "doc-1"
    assert payload["sourceDocumentHash"] == "sha256:abc"
    assert payload["summary"]["totalReviewItems"] == 1
    assert len(payload["reviewSections"]) >= 1


# ── T02: summary count ─────────────────────────────────────────────────────

def test_summary_counts(fr, ui):
    rec, _, items, evidence, requests = _build_simple(fr)
    payload = ui.build_fill_review_page_payload(rec, items, requests, evidence)
    s = payload["summary"]
    for k in ("totalReviewItems", "readyForReviewCount", "missingMaterialCount",
                "highRiskCount", "approvedCount", "rejectedCount", "heldCount"):
        assert k in s
    assert s["readyForReviewCount"] == 1   # proposedValue 있음 → ready
    assert s["missingMaterialCount"] == 0


# ── T03: cell target → "1쪽 / 표 1 / 1행 2열" ────────────────────────────────

def test_cell_target_display(ui):
    target = {"targetType": "cell", "cellKey": "t_s0_000:r0:c1",
                "paragraphKey": None}
    disp = ui.build_target_display(target)
    assert disp == "1쪽 / 표 1 / 1행 2열"


# ── T04: paragraph target → "본문 / 4번째 문단" ─────────────────────────────

def test_paragraph_target_display(ui):
    target = {"targetType": "paragraph", "paragraphKey": "p_s0_0003"}
    disp = ui.build_target_display(target)
    assert disp == "본문 / 4번째 문단"


# ── T05: object target → "객체 / ..." ───────────────────────────────────────

def test_object_target_display(ui):
    target = {"targetType": "object", "objectKey": "obj:s0:1:0001",
                "objectType": "도장"}
    disp = ui.build_target_display(target)
    assert disp == "객체 / 도장"


# ── T06: target 없음 → highlightStyle=MISSING ──────────────────────────────

def test_missing_target_highlight(ui):
    h = ui.build_highlight({"targetType": "cell", "cellKey": None})
    assert h["highlightStyle"] == "MISSING"
    h2 = ui.build_highlight({})
    assert h2["highlightStyle"] == "MISSING"


def test_cell_highlight_populated(ui):
    h = ui.build_highlight({"targetType": "cell", "cellKey": "t_s0_000:r3:c2"})
    assert h["highlightStyle"] == "CELL"
    assert h["sectionIndex"] == 0
    assert h["tableIndex"] == 0
    assert h["rowIndex"] == 3
    assert h["cellIndex"] == 2
    assert h["cellKey"] == "t_s0_000:r3:c2"


def test_paragraph_highlight_populated(ui):
    h = ui.build_highlight({"targetType": "paragraph", "paragraphKey": "p_s1_0007"})
    assert h["highlightStyle"] == "PARAGRAPH"
    assert h["sectionIndex"] == 1
    assert h["paragraphIndex"] == 7
    assert h["paragraphKey"] == "p_s1_0007"


# ── T07: evidenceRefs → evidenceBadges ─────────────────────────────────────

def test_evidence_badges_built_from_refs(fr, ui):
    rec, _, items, evidence, _ = _build_simple(fr)
    payload = ui.build_fill_review_page_payload(rec, items, [], evidence)
    item = payload["reviewSections"][0]["items"][0]
    assert len(item["evidenceBadges"]) == 1
    badge = item["evidenceBadges"][0]
    assert badge["evidenceId"] == "ev1"
    assert badge["sourceType"] == "CONTRACT_XLSX"
    assert badge["sourceName"] == "evidence"


# ── T08: HIGH risk → highRiskCount ──────────────────────────────────────────

def test_high_risk_count_reflected(fr, ui):
    cells = _make_label_value_cells("공사명", "t:r0:c0", "t:r0:c1")
    rec = _recognition(fr, cells=cells)
    reqs = fr.build_fill_requirements(rec)
    fake_match = {
        "matchId": "m", "requirementId": reqs[0]["requirementId"],
        "evidenceId": None, "fieldName": "x",
        "proposedValue": "P", "confidence": 0.95,
        "matchReason": "ai", "needsUserReview": True,
    }
    items = fr.build_review_items(reqs, [fake_match], [])
    assert items[0]["riskLevel"] == "HIGH"
    payload = ui.build_fill_review_page_payload(rec, items, [], [])
    assert payload["summary"]["highRiskCount"] == 1


# ── T09: BUSINESS_LICENSE → suggestedUploadLabel / acceptedFileTypes ───────

def test_business_license_request_panel(fr, ui):
    rec, _, items, _, requests = _build_with_missing(fr)
    payload = ui.build_fill_review_page_payload(rec, items, requests)
    panel = payload["missingMaterialPanel"]
    assert len(panel["requests"]) == 1
    req = panel["requests"][0]
    assert req["requestedMaterialType"] == "BUSINESS_LICENSE"
    assert req["suggestedUploadLabel"] == "사업자등록증 업로드"
    assert "pdf" in req["acceptedFileTypes"]
    assert "hwpx" in req["acceptedFileTypes"]


# ── T10: SEAL_IMAGE → 이미지 확장자 ─────────────────────────────────────────

def test_seal_image_request_panel(fr, ui):
    cells = _make_label_value_cells("직인", "t:r0:c0", "t:r0:c1")
    rec = _recognition(fr, cells=cells)
    reqs = fr.build_fill_requirements(rec)
    requests = fr.build_missing_material_requests(reqs, [], [])
    items = fr.build_review_items(reqs, [], requests)
    payload = ui.build_fill_review_page_payload(rec, items, requests)
    req = payload["missingMaterialPanel"]["requests"][0]
    assert req["requestedMaterialType"] == "SEAL_IMAGE"
    assert set(req["acceptedFileTypes"]) == {"png", "jpg", "jpeg"}


# ── T11: blockingCount / optionalCount ──────────────────────────────────────

def test_blocking_and_optional_counts(fr, ui):
    cells = _make_label_value_cells("사업자등록번호", "t:r0:c0", "t:r0:c1")
    rec = _recognition(fr, cells=cells)
    reqs = fr.build_fill_requirements(rec)
    requests = fr.build_missing_material_requests(reqs, [], [])
    # optional 요청을 하나 더 추가
    optional_req = dict(requests[0])
    optional_req["requestId"] = "matreq_opt"
    optional_req["blocking"] = False
    requests = list(requests) + [optional_req]
    items = fr.build_review_items(reqs, [], requests)
    payload = ui.build_fill_review_page_payload(rec, items, requests)
    panel = payload["missingMaterialPanel"]
    assert panel["blockingCount"] == 1
    assert panel["optionalCount"] == 1


# ── T12: allowedActions에 5종 ───────────────────────────────────────────────

def test_allowed_actions_include_all_five(fr, ui):
    rec, _, items, evidence, _ = _build_simple(fr)
    payload = ui.build_fill_review_page_payload(rec, items, [], evidence)
    item = payload["reviewSections"][0]["items"][0]
    # related missing request가 없으므로 REQUEST_MATERIAL은 비활성
    expected = {"APPROVE", "REJECT", "HOLD", "EDIT_VALUE"}
    assert expected.issubset(set(item["allowedActions"]))
    assert "REQUEST_MATERIAL" not in item["allowedActions"]


def test_request_material_action_active_when_request_exists(fr, ui):
    rec, _, items, _, requests = _build_with_missing(fr)
    payload = ui.build_fill_review_page_payload(rec, items, requests)
    item = payload["reviewSections"][0]["items"][0]
    assert "REQUEST_MATERIAL" in item["allowedActions"]


# ── T13: missing source → defaultAction=REQUEST_MATERIAL ───────────────────

def test_default_action_request_material_for_needs_user_input(fr, ui):
    rec, _, items, _, requests = _build_with_missing(fr)
    payload = ui.build_fill_review_page_payload(rec, items, requests)
    item = payload["reviewSections"][0]["items"][0]
    assert item["defaultAction"] == "REQUEST_MATERIAL"


# ── T14: ready item → defaultAction=APPROVE ─────────────────────────────────

def test_default_action_approve_for_ready_item(fr, ui):
    rec, _, items, evidence, _ = _build_simple(fr)
    payload = ui.build_fill_review_page_payload(rec, items, [], evidence)
    item = payload["reviewSections"][0]["items"][0]
    assert item["defaultAction"] == "APPROVE"


# ── T15-T18: decision validation positive cases ─────────────────────────────

def _build_with_payload(fr, ui, source_hash="sha256:abc"):
    rec, _, items, evidence, _ = _build_simple(fr, source_hash=source_hash)
    payload = ui.build_fill_review_page_payload(rec, items, [], evidence)
    ui_items = [it for sec in payload["reviewSections"] for it in sec["items"]]
    return rec, items, ui_items


def test_validate_approve_decision_valid(fr, ui):
    _, _, ui_items = _build_with_payload(fr, ui)
    dp = _decision_payload(ui_items, "sha256:abc",
                              [_decision(ui_items[0]["reviewItemId"], "APPROVE")])
    res = ui.validate_decision_payload(dp, ui_items,
                                            expected_source_hash="sha256:abc")
    assert res.valid is True
    assert res.acceptedDecisionCount == 1
    assert res.errors == []


def test_validate_reject_decision_valid(fr, ui):
    _, _, ui_items = _build_with_payload(fr, ui)
    dp = _decision_payload(ui_items, "sha256:abc",
                              [_decision(ui_items[0]["reviewItemId"], "REJECT")])
    res = ui.validate_decision_payload(dp, ui_items,
                                            expected_source_hash="sha256:abc")
    assert res.valid is True
    assert res.acceptedDecisionCount == 1


def test_validate_hold_decision_valid(fr, ui):
    _, _, ui_items = _build_with_payload(fr, ui)
    dp = _decision_payload(ui_items, "sha256:abc",
                              [_decision(ui_items[0]["reviewItemId"], "HOLD")])
    res = ui.validate_decision_payload(dp, ui_items,
                                            expected_source_hash="sha256:abc")
    assert res.valid is True


def test_validate_edit_value_with_value_valid(fr, ui):
    _, _, ui_items = _build_with_payload(fr, ui)
    dp = _decision_payload(ui_items, "sha256:abc",
                              [_decision(ui_items[0]["reviewItemId"], "EDIT_VALUE",
                                            edited="user-typed")])
    res = ui.validate_decision_payload(dp, ui_items,
                                            expected_source_hash="sha256:abc")
    assert res.valid is True
    assert res.acceptedDecisionCount == 1


# ── T19: EDIT_VALUE without editedValue → error ─────────────────────────────

def test_edit_value_missing_value_blocked(fr, ui):
    _, _, ui_items = _build_with_payload(fr, ui)
    dp = _decision_payload(ui_items, "sha256:abc",
                              [_decision(ui_items[0]["reviewItemId"], "EDIT_VALUE")])
    res = ui.validate_decision_payload(dp, ui_items,
                                            expected_source_hash="sha256:abc")
    assert res.valid is False
    assert any(e["code"] == "EDIT_VALUE_REQUIRES_VALUE" for e in res.errors)


# ── T20: unknown reviewItemId → error ───────────────────────────────────────

def test_unknown_review_item_id_blocked(fr, ui):
    _, _, ui_items = _build_with_payload(fr, ui)
    dp = _decision_payload(ui_items, "sha256:abc",
                              [_decision("rev_does_not_exist", "APPROVE")])
    res = ui.validate_decision_payload(dp, ui_items,
                                            expected_source_hash="sha256:abc")
    assert res.valid is False
    assert any(e["code"] == "REVIEW_ITEM_NOT_FOUND" for e in res.errors)


# ── T21: sourceDocumentHash mismatch → error ────────────────────────────────

def test_source_hash_mismatch_blocked(fr, ui):
    _, _, ui_items = _build_with_payload(fr, ui)
    dp = _decision_payload(ui_items, "sha256:WRONG",
                              [_decision(ui_items[0]["reviewItemId"], "APPROVE")])
    res = ui.validate_decision_payload(dp, ui_items,
                                            expected_source_hash="sha256:abc")
    assert res.valid is False
    assert any(e["code"] == "SOURCE_HASH_MISMATCH" for e in res.errors)


# ── T22: duplicate decision → error ─────────────────────────────────────────

def test_duplicate_decision_blocked(fr, ui):
    _, _, ui_items = _build_with_payload(fr, ui)
    rid = ui_items[0]["reviewItemId"]
    dp = _decision_payload(ui_items, "sha256:abc",
                              [_decision(rid, "APPROVE"),
                               _decision(rid, "REJECT")])
    res = ui.validate_decision_payload(dp, ui_items,
                                            expected_source_hash="sha256:abc")
    assert res.valid is False
    assert any(e["code"] == "DUPLICATE_DECISION" for e in res.errors)


# ── T23: decision not in allowedActions → error ─────────────────────────────

def test_decision_not_in_allowed_actions_blocked(fr, ui):
    _, _, ui_items = _build_with_payload(fr, ui)
    rid = ui_items[0]["reviewItemId"]
    # allowedActions에서 REQUEST_MATERIAL이 빠진 상태에서 REQUEST_MATERIAL 시도
    dp = _decision_payload(ui_items, "sha256:abc",
                              [_decision(rid, "REQUEST_MATERIAL")])
    res = ui.validate_decision_payload(dp, ui_items,
                                            expected_source_hash="sha256:abc")
    assert res.valid is False
    assert any(e["code"] == "DECISION_NOT_ALLOWED_FOR_ITEM" for e in res.errors)


# ── T24: REQUEST_MATERIAL without missing request → error ───────────────────

def test_request_material_without_missing_request(fr, ui):
    """REQUEST_MATERIAL은 해당 item의 requirementId에 missing request가 있어야 한다."""
    rec, _, items, _, requests = _build_with_missing(fr)
    payload = ui.build_fill_review_page_payload(rec, items, requests)
    ui_items = [it for sec in payload["reviewSections"] for it in sec["items"]]
    rid = ui_items[0]["reviewItemId"]
    # 정상 케이스: missing request 있음 → REQUEST_MATERIAL 허용
    dp_ok = _decision_payload(ui_items, "sha256:abc",
                                  [_decision(rid, "REQUEST_MATERIAL")])
    res_ok = ui.validate_decision_payload(dp_ok, ui_items,
                                               missing_requests=requests,
                                               expected_source_hash="sha256:abc")
    assert res_ok.valid is True

    # 비정상: missing_requests=[]를 넘겨서 mismatch 시뮬
    res_bad = ui.validate_decision_payload(dp_ok, ui_items,
                                                missing_requests=[],
                                                expected_source_hash="sha256:abc")
    assert res_bad.valid is False
    assert any(e["code"] == "REQUEST_MATERIAL_NOT_AVAILABLE" for e in res_bad.errors)


# ── T25: 고 confidence라도 decision 자동 생성 없음 ─────────────────────────

def test_high_confidence_does_not_auto_create_decision(fr, ui):
    rec, _, items, evidence, _ = _build_simple(fr)
    # decisions를 비워둬도 payload 생성은 정상이지만 acceptedDecisionCount=0
    payload = ui.build_fill_review_page_payload(rec, items, [], evidence)
    ui_items = [it for sec in payload["reviewSections"] for it in sec["items"]]
    dp = _decision_payload(ui_items, "sha256:abc", [])
    res = ui.validate_decision_payload(dp, ui_items,
                                            expected_source_hash="sha256:abc")
    assert res.acceptedDecisionCount == 0
    assert res.valid is False  # 빈 decisions는 valid=False (accepted 없음)


# ── T26: setParagraphText 공식명 유지 ──────────────────────────────────────

def test_official_paragraph_full_replace_op_name_locked(ui, fr):
    assert ui.is_official_paragraph_full_replace("setParagraphText") is True
    assert fr.OFFICIAL_PARAGRAPH_FULL_REPLACE_OP == "setParagraphText"


# ── T27: setCellParagraphText 금지명 ───────────────────────────────────────

def test_forbidden_paragraph_op_name_still_forbidden(ui, fr):
    assert ui.is_forbidden_operation_name("setCellParagraphText") is True
    assert "setCellParagraphText" in fr.FORBIDDEN_PARAGRAPH_OP_NAMES
    assert "setCellParagraphText" not in fr.ALLOWED_FILL_REVIEW_OPERATIONS


# ── T28: writer 미호출 ─────────────────────────────────────────────────────

def test_writer_not_invoked_during_ui_build(fr, ui, monkeypatch):
    from hwpx.pipeline import generic_edit_plan_writer_executor_live_sandbox as live
    call_log: list = []
    monkeypatch.setattr(live, "execute_writer_call_plan_live_sandbox",
                          lambda *a, **k: call_log.append("live"))
    rec, _, items, evidence, _ = _build_simple(fr)
    ui.build_fill_review_page_payload(rec, items, [], evidence)
    assert call_log == []


# ── T29: output 미생성 ─────────────────────────────────────────────────────

def test_no_output_files_created(fr, ui, tmp_path):
    before = sorted(p.name for p in tmp_path.iterdir())
    rec, _, items, _, _ = _build_simple(fr)
    ui.build_fill_review_page_payload(rec, items, [], [])
    assert sorted(p.name for p in tmp_path.iterdir()) == before


# ── T30: 원본 fixture sha256/mtime 무변경 ──────────────────────────────────

def test_original_fixture_unchanged(fr, ui):
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_before = METADATA_FORM.stat().st_mtime
    rec, _, items, evidence, _ = _build_simple(fr)
    ui.build_fill_review_page_payload(rec, items, [], evidence)
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before
    assert METADATA_FORM.stat().st_mtime == mtime_before


# ── T31: fill_review_contract 33 회귀 ──────────────────────────────────────

def test_fill_review_contract_regression_smoke(fr):
    # 빠른 회귀 확인: 빈 plan은 BLOCKED, 정상 plan은 READY
    plan_blocked = fr.build_approved_edit_plan([], [], source_document_hash="")
    assert plan_blocked.verdict == "BLOCKED_INVALID_PLAN"
    cells = _make_label_value_cells("공사명", "t_s0_000:r0:c0", "t_s0_000:r0:c1")
    rec = _recognition(fr, cells=cells)
    reqs = fr.build_fill_requirements(rec)
    ev = _evidence("ev", "CONTRACT_XLSX", {"projectName": "P"})
    matches = fr.match_requirements_with_evidence(reqs, [ev])
    items = fr.build_review_items(reqs, matches, [])
    plan_ok = fr.build_approved_edit_plan(
        items, [{"reviewItemId": items[0]["reviewItemId"], "decision": "APPROVE",
                    "reviewer": "x", "reason": "y"}],
        source_document_hash="sha:1",
    )
    assert plan_ok.verdict == "READY_FOR_WRITER"
    assert len(plan_ok.operations) == 1


# ── T32: audit script PASS ─────────────────────────────────────────────────

def test_ui_adapter_audit_script_passes():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_hwpx_fill_review_ui_adapter",
        PROJECT_ROOT / "scripts/ops/audit_hwpx_fill_review_ui_adapter.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.run_audit()
    assert result["auditVerdict"] == "PASS", result


# ── schema sanity ──────────────────────────────────────────────────────────

_REQUIRED_PAYLOAD_KEYS = (
    "schemaVersion", "contractSchemaVersion", "engineVersion", "requestId",
    "documentId", "sourceDocumentHash", "summary", "reviewSections",
    "missingMaterialPanel", "decisionPanel", "warnings",
)

_REQUIRED_ITEM_KEYS = (
    "reviewItemId", "requirementId", "label", "semanticType", "target",
    "targetDisplay", "currentValue", "proposedValue", "beforePreview",
    "afterPreview", "evidenceBadges", "riskLevel", "status",
    "allowedActions", "defaultAction", "blockingReason", "highlight",
)


def test_payload_required_top_level_keys(fr, ui):
    rec, _, items, evidence, _ = _build_simple(fr)
    payload = ui.build_fill_review_page_payload(rec, items, [], evidence)
    for k in _REQUIRED_PAYLOAD_KEYS:
        assert k in payload, f"missing top-level key: {k}"


def test_review_item_required_keys(fr, ui):
    rec, _, items, evidence, _ = _build_simple(fr)
    payload = ui.build_fill_review_page_payload(rec, items, [], evidence)
    item = payload["reviewSections"][0]["items"][0]
    for k in _REQUIRED_ITEM_KEYS:
        assert k in item, f"missing item key: {k}"


def test_highlight_required_keys(ui):
    h = ui.build_highlight({"targetType": "cell", "cellKey": "t_s0_000:r0:c0"})
    for k in ("targetType", "sectionIndex", "tableIndex", "rowIndex",
                "cellIndex", "paragraphIndex", "cellKey", "paragraphKey",
                "objectKey", "confidence", "highlightStyle"):
        assert k in h


def test_missing_panel_required_keys(fr, ui):
    rec, _, items, _, requests = _build_with_missing(fr)
    payload = ui.build_fill_review_page_payload(rec, items, requests)
    panel = payload["missingMaterialPanel"]
    for k in ("requests", "blockingCount", "optionalCount"):
        assert k in panel
    req = panel["requests"][0]
    for k in ("requestId", "requirementId", "requestedMaterialType",
                "messageToUser", "reason", "blocking",
                "suggestedUploadLabel", "acceptedFileTypes"):
        assert k in req
