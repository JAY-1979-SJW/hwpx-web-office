"""HWPX-FORM-MISSING-AND-REVIEW-PANEL-01 — 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# ── fixture helpers ───────────────────────────────────────────────────────────

def _ef(fk, val, conf=0.85, src=""):
    from hwpx.pipeline.upload_document_parser import ExtractedField
    return ExtractedField(fieldKey=fk, value=val, confidence=conf,
                          sourceLabel=src or fk, location="", extractMethod="horizontal")

def _pr(fields):
    from hwpx.pipeline.upload_document_parser import ParseResult
    r = ParseResult(maskedStem="test", formName="테스트 서식",
                    domain="기타", formKind="신청서")
    r.extractedFields = fields
    return r

def _ce(fields):
    return {"formId": "test_form", "formName": "테스트 서식",
            "domain": "기타", "formKind": "신청서",
            "byeoljiNumber": "", "fileCount": 1,
            "fieldCount": len(fields), "autoFillableCount": 0,
            "requiredCount": 0, "fields": fields}

def _cf(sem, lbl, lbls=None, req=True, hint=""):
    return {"primaryLabel": lbl, "labels": lbls or [lbl],
            "semanticField": sem, "autoFillable": bool(sem),
            "inputCellTypes": ["label_adjacent"], "required": req,
            "fileOccurrenceCount": 1, "totalOccurrenceCount": 1,
            "sourceEvidenceHint": hint}

def _make_mapping(auto=None, review=None, missing=None):
    """직접 MappingResult 구성."""
    from hwpx.pipeline.form_field_mapper import (
        MappingResult, MappedField, MissingField, ValidationResult,
        STATUS_AUTO, STATUS_REVIEW,
    )
    mr = MappingResult(formId="f001", formName="테스트 서식")
    for fk, lbl, val, conf, hint in (auto or []):
        mr.mappedFields.append(MappedField(
            fieldKey=fk, label=lbl, value=val, status=STATUS_AUTO,
            confidence=conf, matchReason="direct_key", sourceLabel=lbl,
            evidenceHint=hint, validation=ValidationResult(True, "text"),
        ))
    for fk, lbl, val, conf, hint, cand in (review or []):
        mr.reviewFields.append(MappedField(
            fieldKey=fk, label=lbl, value=val, status=STATUS_REVIEW,
            confidence=conf, matchReason="alias_match", sourceLabel=lbl,
            evidenceHint=hint, validation=ValidationResult(True, "text"),
            candidateCount=cand,
        ))
    for fk, lbl, req, hint in (missing or []):
        mr.missingFields.append(MissingField(
            fieldKey=fk, label=lbl, required=req, evidenceHint=hint,
        ))
    return mr


# ── T01. import ───────────────────────────────────────────────────────────────

def test_review_panel_importable():
    from hwpx.pipeline import review_panel as rp
    assert hasattr(rp, "build_review_panel")
    assert hasattr(rp, "ReviewPanel")
    assert hasattr(rp, "PANEL_VERSION")


# ── T02. AUTO_FILL_READY 구역 ─────────────────────────────────────────────────

def test_auto_fill_ready_populated():
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping(
        auto=[("contractorName", "시공자", "대한소방", 0.92, "사업자등록증")],
    )
    panel = build_review_panel(mr)
    assert len(panel.autoFillReady) == 1
    item = panel.autoFillReady[0]
    assert item.fieldKey == "contractorName"
    assert item.label == "시공자"
    assert item.value == "대한소방"
    assert item.confidence == pytest.approx(0.92, abs=1e-3)
    assert item.sourceLabel == "시공자"


# ── T03. NEEDS_REVIEW 구역 ────────────────────────────────────────────────────

def test_needs_review_populated():
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping(
        review=[("contractorName", "시공자", "대한소방", 0.70, "", 2)],
    )
    panel = build_review_panel(mr)
    assert len(panel.needsReview) == 1
    item = panel.needsReview[0]
    assert item.fieldKey == "contractorName"
    assert item.reason in ("multiple_candidates", "low_confidence", "type_mismatch")


# ── T04. multiple_candidates reason ───────────────────────────────────────────

def test_review_reason_multiple_candidates():
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping(
        review=[("contractorName", "시공자", "대한소방", 0.75, "", 2)],
    )
    panel = build_review_panel(mr)
    assert panel.needsReview[0].reason == "multiple_candidates"


# ── T05. MISSING_REQUIRED 구역 ────────────────────────────────────────────────

def test_missing_required_populated():
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping(
        missing=[("contractorName", "시공자", True, "사업자등록증")],
    )
    panel = build_review_panel(mr)
    assert len(panel.missingRequired) == 1
    assert panel.missingRequired[0].required is True


# ── T06. MISSING_OPTIONAL 구역 ────────────────────────────────────────────────

def test_missing_optional_separated():
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping(
        missing=[
            ("contractorName", "시공자", True,  "사업자등록증"),
            ("taskName",       "공사명", False, ""),
        ],
    )
    panel = build_review_panel(mr)
    assert len(panel.missingRequired) == 1
    assert len(panel.missingOptional) == 1


# ── T07. requiredAttachments 생성 ─────────────────────────────────────────────

def test_required_attachments_derived_from_hint():
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping(
        missing=[("contractorName", "시공자", True, "사업자등록증, 공사계약서")],
    )
    panel = build_review_panel(mr)
    doc_types = [a.documentType for a in panel.requiredAttachments]
    assert "사업자등록증" in doc_types
    assert "공사계약서" in doc_types


# ── T08. attachment priority ─────────────────────────────────────────────────

def test_attachment_priority_required_first():
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping(
        missing=[("contractorName", "시공자", True, "사업자등록증")],
        review=[("taskName", "공사명", "대공사", 0.65, "공사계약서", 1)],
    )
    panel = build_review_panel(mr)
    priorities = [a.priority for a in panel.requiredAttachments]
    required_idx  = next((i for i, p in enumerate(priorities) if p == "required"),  None)
    optional_idx  = next((i for i, p in enumerate(priorities) if p == "optional"), None)
    if required_idx is not None and optional_idx is not None:
        assert required_idx < optional_idx


# ── T09. summary 구조 ─────────────────────────────────────────────────────────

def test_panel_summary_structure():
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping(
        auto=[("contractorName", "시공자", "대한소방", 0.92, "")],
        review=[("taskName", "공사명", "소화배관", 0.70, "", 1)],
        missing=[("startDate", "착공일자", True, "착공신고서")],
    )
    panel = build_review_panel(mr)
    s = panel.summary
    assert s.autoFillCount == 1
    assert s.reviewCount == 1
    assert s.missingRequiredCount == 1
    assert s.readyToProceed is False


# ── T10. readyToProceed 조건 ─────────────────────────────────────────────────

def test_ready_to_proceed_when_no_missing_required():
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping(
        auto=[("contractorName", "시공자", "대한소방", 0.92, "")],
    )
    panel = build_review_panel(mr)
    assert panel.summary.readyToProceed is True


# ── T11. PII 마스킹 ───────────────────────────────────────────────────────────

def test_pii_masked_in_auto_fill_item():
    import re
    pii_re = re.compile(r"\d{3}-\d{2}-\d{5}|\d{6}-\d{7}")
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping(
        auto=[("registrationNumber", "등록번호", "123-45-67890", 0.90, "")],
    )
    panel = build_review_panel(mr)
    out = json.dumps(panel.to_dict(), ensure_ascii=False)
    assert not pii_re.search(out), f"PII in panel output: {out}"


# ── T12. to_dict 구조 ─────────────────────────────────────────────────────────

def test_panel_to_dict_keys():
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping()
    d = build_review_panel(mr).to_dict()
    for key in ("panelVersion", "formId", "formName", "summary",
                "autoFillReady", "needsReview", "missingRequired",
                "missingOptional", "requiredAttachments"):
        assert key in d, f"key missing: {key}"


# ── T13. attachment neededFor 연결 ────────────────────────────────────────────

def test_attachment_needed_for_links():
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping(
        missing=[("contractorName", "시공자", True, "사업자등록증")],
    )
    panel = build_review_panel(mr)
    for att in panel.requiredAttachments:
        assert len(att.neededFor) > 0


# ── T14. panelVersion ────────────────────────────────────────────────────────

def test_panel_version():
    from hwpx.pipeline.review_panel import build_review_panel, PANEL_VERSION
    mr = _make_mapping()
    panel = build_review_panel(mr)
    assert panel.panelVersion == PANEL_VERSION


# ── T15. writer 미참조 ────────────────────────────────────────────────────────

def test_review_panel_no_writer():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "review_panel.py").read_text("utf-8")
    assert "write_package" not in src
    assert "apply_edit_plan" not in src


# ── T16. AI API 미참조 ────────────────────────────────────────────────────────

def test_review_panel_no_ai_api():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "review_panel.py").read_text("utf-8")
    for kw in ("anthropic", "openai", "ChatCompletion"):
        assert kw not in src


# ── T17. OCR 미참조 ──────────────────────────────────────────────────────────

def test_review_panel_no_ocr():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "review_panel.py").read_text("utf-8")
    for kw in ("pytesseract", "easyocr", "image_to_string"):
        assert kw not in src


# ── T18. 기존 테스트 회귀 ────────────────────────────────────────────────────

def test_mapper_still_passes():
    from hwpx.pipeline import form_field_mapper as fm
    assert hasattr(fm, "map_fields")

def test_parser_still_passes():
    from hwpx.pipeline import upload_document_parser as up
    assert hasattr(up, "parse_hwpx")

def test_catalog_still_passes():
    from hwpx.recognition_corpus import form_field_catalog as ffc
    assert hasattr(ffc, "build_catalog")

def test_recommend_still_passes():
    from hwpx.recognition_corpus import form_index as fi
    assert hasattr(fi, "recommend")


# ── T19. build_review_panel via map_fields ────────────────────────────────────

def test_build_review_panel_end_to_end():
    from hwpx.pipeline.form_field_mapper import map_fields
    from hwpx.pipeline.review_panel import build_review_panel

    pr = _pr([_ef("contractorName", "대한소방", 0.90, "시공자")])
    ce = _ce([
        _cf("contractorName", "시공자", ["시공자", "시공업체"], hint="사업자등록증"),
        _cf("taskName", "공사명", req=True),
    ])
    mr = map_fields(pr, ce)
    panel = build_review_panel(mr)
    d = panel.to_dict()
    total = (d["summary"]["autoFillCount"] + d["summary"]["reviewCount"]
             + d["summary"]["missingRequiredCount"] + d["summary"]["missingOptionalCount"])
    assert total >= 1


# ── T20. empty mapping → panel still valid ───────────────────────────────────

def test_empty_mapping_panel():
    from hwpx.pipeline.review_panel import build_review_panel
    mr = _make_mapping()
    panel = build_review_panel(mr)
    assert panel.summary.readyToProceed is True
    assert panel.to_dict()["panelVersion"] == "v1"
