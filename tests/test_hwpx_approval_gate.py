"""HWPX-FORM-HUMAN-APPROVAL-GATE-01 — 테스트."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# ── fixture helpers ───────────────────────────────────────────────────────────

def _panel_dict(
    auto=None,       # [(fieldKey, label, value, confidence)]
    review=None,     # [(fieldKey, label, value, confidence)]
    miss_req=None,   # [(fieldKey, label)]
    miss_opt=None,   # [(fieldKey, label)]
):
    def _auto_item(fk, lbl, val, conf):
        return {"fieldKey": fk, "label": lbl, "value": val, "confidence": conf,
                "sourceLabel": lbl, "matchReason": "direct_key"}

    def _review_item(fk, lbl, val, conf):
        return {"fieldKey": fk, "label": lbl,
                "candidates": [{"value": val, "confidence": conf, "sourceLabel": lbl}],
                "reason": "low_confidence", "evidenceHint": ""}

    def _miss_item(fk, lbl, hint=""):
        return {"fieldKey": fk, "label": lbl, "required": True,
                "evidenceHint": hint, "suggestedAttachments": []}

    return {
        "panelVersion": "v1",
        "formId": "test_form",
        "formName": "테스트 서식",
        "summary": {},
        "autoFillReady":   [_auto_item(*x) for x in (auto or [])],
        "needsReview":     [_review_item(*x) for x in (review or [])],
        "missingRequired": [_miss_item(*x) for x in (miss_req or [])],
        "missingOptional": [_miss_item(*x) for x in (miss_opt or [])],
        "requiredAttachments": [],
    }


# ── T01. import ───────────────────────────────────────────────────────────────

def test_approval_gate_importable():
    from hwpx.pipeline import approval_gate as ag
    assert hasattr(ag, "apply_decisions")
    assert hasattr(ag, "FieldDecision")
    assert hasattr(ag, "ApprovalResult")
    assert hasattr(ag, "ACTION_CONFIRM")
    assert hasattr(ag, "ACTION_EDIT")
    assert hasattr(ag, "ACTION_HOLD")
    assert hasattr(ag, "ACTION_ATTACHMENT")


# ── T02. CONFIRM_FIELD → writerEligible=True ─────────────────────────────────

def test_confirm_field_writer_eligible():
    from hwpx.pipeline.approval_gate import apply_decisions, FieldDecision, ACTION_CONFIRM
    panel = _panel_dict(auto=[("contractorName", "시공자", "대한소방", 0.92)])
    decisions = [FieldDecision(fieldKey="contractorName", action=ACTION_CONFIRM)]
    result = apply_decisions(panel, decisions)
    assert len(result.approvedFields) == 1
    assert result.approvedFields[0].writerEligible is True
    assert result.approvedFields[0].action == ACTION_CONFIRM


# ── T03. EDIT_VALUE → writerEligible=True, value 교체 ────────────────────────

def test_edit_value_replaces_value():
    from hwpx.pipeline.approval_gate import apply_decisions, FieldDecision, ACTION_EDIT
    panel = _panel_dict(auto=[("contractorName", "시공자", "대한소방", 0.92)])
    decisions = [FieldDecision(fieldKey="contractorName", action=ACTION_EDIT,
                               editedValue="한국소방공사")]
    result = apply_decisions(panel, decisions)
    assert len(result.approvedFields) == 1
    af = result.approvedFields[0]
    assert af.value == "한국소방공사"
    assert af.originalValue == "대한소방"
    assert af.writerEligible is True
    assert af.confidence == pytest.approx(1.0)


# ── T04. HOLD → writerEligible=False ─────────────────────────────────────────

def test_hold_not_writer_eligible():
    from hwpx.pipeline.approval_gate import apply_decisions, FieldDecision, ACTION_HOLD
    panel = _panel_dict(review=[("contractorName", "시공자", "대한소방", 0.70)])
    decisions = [FieldDecision(fieldKey="contractorName", action=ACTION_HOLD)]
    result = apply_decisions(panel, decisions)
    assert len(result.approvedFields) == 0
    assert len(result.pendingFields) == 1
    assert result.pendingFields[0].writerEligible is False


# ── T05. REQUEST_ATTACHMENT → writerEligible=False ───────────────────────────

def test_request_attachment_pending():
    from hwpx.pipeline.approval_gate import apply_decisions, FieldDecision, ACTION_ATTACHMENT
    panel = _panel_dict(miss_req=[("contractorName", "시공자")])
    decisions = [FieldDecision(fieldKey="contractorName", action=ACTION_ATTACHMENT,
                               comment="사업자등록증 첨부 필요")]
    result = apply_decisions(panel, decisions)
    assert len(result.pendingFields) == 1
    pf = result.pendingFields[0]
    assert pf.writerEligible is False
    assert pf.action == ACTION_ATTACHMENT


# ── T06. writerEnabled 항상 False ────────────────────────────────────────────

def test_writer_enabled_always_false():
    from hwpx.pipeline.approval_gate import apply_decisions, FieldDecision, ACTION_CONFIRM
    panel = _panel_dict(auto=[("contractorName", "시공자", "대한소방", 0.92)])
    decisions = [FieldDecision(fieldKey="contractorName", action=ACTION_CONFIRM)]
    result = apply_decisions(panel, decisions)
    assert result.writerEnabled is False
    assert result.to_dict()["writerEnabled"] is False


# ── T07. NEEDS_REVIEW 항목도 CONFIRM_FIELD 가능 ───────────────────────────────

def test_review_item_confirmable():
    from hwpx.pipeline.approval_gate import apply_decisions, FieldDecision, ACTION_CONFIRM
    panel = _panel_dict(review=[("contractorName", "시공자", "대한소방", 0.72)])
    decisions = [FieldDecision(fieldKey="contractorName", action=ACTION_CONFIRM)]
    result = apply_decisions(panel, decisions)
    assert len(result.approvedFields) == 1
    assert result.approvedFields[0].sourceZone == "needsReview"
    assert result.approvedFields[0].writerEligible is True


# ── T08. 복수 결정 혼합 ────────────────────────────────────────────────────────

def test_mixed_decisions():
    from hwpx.pipeline.approval_gate import (
        apply_decisions, FieldDecision,
        ACTION_CONFIRM, ACTION_EDIT, ACTION_HOLD, ACTION_ATTACHMENT,
    )
    panel = _panel_dict(
        auto=[
            ("contractorName", "시공자", "대한소방", 0.92),
            ("taskName",       "공사명", "소화배관",  0.88),
        ],
        review=[("startDate", "착공일자", "2026-05-01", 0.70)],
        miss_req=[("completionDate", "준공일자")],
    )
    decisions = [
        FieldDecision(fieldKey="contractorName", action=ACTION_CONFIRM),
        FieldDecision(fieldKey="taskName",       action=ACTION_EDIT, editedValue="소화배관 공사"),
        FieldDecision(fieldKey="startDate",      action=ACTION_HOLD),
        FieldDecision(fieldKey="completionDate", action=ACTION_ATTACHMENT),
    ]
    result = apply_decisions(panel, decisions)
    assert len(result.approvedFields) == 2
    assert len(result.pendingFields) == 2
    assert result.summary.writerEligibleCount == 2
    assert result.summary.holdCount == 1
    assert result.summary.attachmentCount == 1


# ── T09. summary 구조 ─────────────────────────────────────────────────────────

def test_approval_summary_structure():
    from hwpx.pipeline.approval_gate import apply_decisions, FieldDecision, ACTION_CONFIRM
    panel = _panel_dict(auto=[("contractorName", "시공자", "대한소방", 0.92)])
    decisions = [FieldDecision(fieldKey="contractorName", action=ACTION_CONFIRM)]
    result = apply_decisions(panel, decisions)
    s = result.summary
    for key in ("totalDecisions", "confirmedCount", "editedCount",
                "holdCount", "attachmentCount", "writerEligibleCount"):
        assert hasattr(s, key) or key in s.to_dict(), f"key missing: {key}"


# ── T10. to_dict 구조 ─────────────────────────────────────────────────────────

def test_approval_result_to_dict_keys():
    from hwpx.pipeline.approval_gate import apply_decisions, FieldDecision, ACTION_CONFIRM
    panel = _panel_dict(auto=[("contractorName", "시공자", "대한소방", 0.92)])
    decisions = [FieldDecision(fieldKey="contractorName", action=ACTION_CONFIRM)]
    d = apply_decisions(panel, decisions).to_dict()
    for key in ("gateVersion", "formId", "formName", "writerEnabled",
                "summary", "approvedFields", "pendingFields"):
        assert key in d, f"key missing: {key}"


# ── T11. PII 마스킹 (editedValue 포함) ───────────────────────────────────────

def test_pii_masked_in_edited_value():
    pii_re = re.compile(r"\d{3}-\d{2}-\d{5}|\d{6}-\d{7}")
    from hwpx.pipeline.approval_gate import apply_decisions, FieldDecision, ACTION_EDIT
    panel = _panel_dict(auto=[("registrationNumber", "등록번호", "", 0.0)])
    decisions = [FieldDecision(fieldKey="registrationNumber",
                               action=ACTION_EDIT, editedValue="123-45-67890")]
    result = apply_decisions(panel, decisions)
    out = json.dumps(result.to_dict(), ensure_ascii=False)
    assert not pii_re.search(out), f"PII in output: {out}"


# ── T12. sourceZone 정확히 기록 ──────────────────────────────────────────────

def test_source_zone_recorded():
    from hwpx.pipeline.approval_gate import apply_decisions, FieldDecision, ACTION_CONFIRM
    panel = _panel_dict(
        auto=[("contractorName", "시공자", "A", 0.90)],
        review=[("taskName", "공사명", "B", 0.70)],
        miss_req=[("startDate", "착공일자")],
    )
    decisions = [
        FieldDecision(fieldKey="contractorName", action=ACTION_CONFIRM),
        FieldDecision(fieldKey="taskName",       action=ACTION_CONFIRM),
        FieldDecision(fieldKey="startDate",      action=ACTION_CONFIRM),
    ]
    result = apply_decisions(panel, decisions)
    zones = {f.fieldKey: f.sourceZone for f in result.approvedFields}
    assert zones["contractorName"] == "autoFillReady"
    assert zones["taskName"] == "needsReview"
    assert zones["startDate"] == "missingRequired"


# ── T13. 미결정 필드 → undecidedCount ────────────────────────────────────────

def test_undecided_count():
    from hwpx.pipeline.approval_gate import (
        apply_decisions, FieldDecision, ACTION_CONFIRM, result_to_dict,
    )
    panel = _panel_dict(
        auto=[("contractorName", "시공자", "대한소방", 0.92),
              ("taskName", "공사명", "소화배관", 0.88)],
    )
    decisions = [FieldDecision(fieldKey="contractorName", action=ACTION_CONFIRM)]
    result = apply_decisions(panel, decisions)
    d = result_to_dict(result)
    assert d["summary"]["undecidedCount"] == 1


# ── T14. 잘못된 action → ValueError ──────────────────────────────────────────

def test_invalid_action_raises():
    from hwpx.pipeline.approval_gate import FieldDecision
    with pytest.raises(ValueError):
        FieldDecision(fieldKey="contractorName", action="INVALID_ACTION")


# ── T15. GATE_VERSION ────────────────────────────────────────────────────────

def test_gate_version():
    from hwpx.pipeline.approval_gate import apply_decisions, GATE_VERSION
    panel = _panel_dict()
    result = apply_decisions(panel, [])
    assert result.gateVersion == GATE_VERSION
    assert result.to_dict()["gateVersion"] == GATE_VERSION


# ── T16. writer 미참조 ────────────────────────────────────────────────────────

def test_approval_gate_no_writer():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "approval_gate.py").read_text("utf-8")
    assert "write_package"   not in src
    assert "apply_edit_plan" not in src


# ── T17. AI API 미참조 ────────────────────────────────────────────────────────

def test_approval_gate_no_ai():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "approval_gate.py").read_text("utf-8")
    for kw in ("anthropic", "openai", "ChatCompletion"):
        assert kw not in src


# ── T18. OCR 미참조 ──────────────────────────────────────────────────────────

def test_approval_gate_no_ocr():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "approval_gate.py").read_text("utf-8")
    for kw in ("pytesseract", "easyocr", "image_to_string"):
        assert kw not in src


# ── T19. apply_decisions_from_panel (ReviewPanel 인스턴스 경로) ───────────────

def test_apply_decisions_from_panel_instance():
    from hwpx.pipeline.form_field_mapper import (
        MappingResult, MappedField, ValidationResult, STATUS_AUTO,
    )
    from hwpx.pipeline.review_panel import build_review_panel
    from hwpx.pipeline.approval_gate import (
        apply_decisions_from_panel, FieldDecision, ACTION_CONFIRM,
    )
    mr = MappingResult(formId="f001", formName="서식A")
    mr.mappedFields.append(MappedField(
        fieldKey="contractorName", label="시공자", value="대한소방",
        status=STATUS_AUTO, confidence=0.90, matchReason="direct_key",
        sourceLabel="시공자", evidenceHint="",
        validation=ValidationResult(True, "text"),
    ))
    panel = build_review_panel(mr)
    decisions = [FieldDecision(fieldKey="contractorName", action=ACTION_CONFIRM)]
    result = apply_decisions_from_panel(panel, decisions)
    assert len(result.approvedFields) == 1
    assert result.writerEnabled is False


# ── T20. 기존 테스트 회귀 ────────────────────────────────────────────────────

def test_review_panel_still_passes():
    from hwpx.pipeline import review_panel as rp
    assert hasattr(rp, "build_review_panel")

def test_mapper_still_passes():
    from hwpx.pipeline import form_field_mapper as fm
    assert hasattr(fm, "map_fields")

def test_parser_still_passes():
    from hwpx.pipeline import upload_document_parser as up
    assert hasattr(up, "parse_hwpx")
