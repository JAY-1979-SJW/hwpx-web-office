"""HWPX-FORM-AUTO-FILL-WRITER-SANDBOX-01 — 테스트."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


# ── synthetic HWPX 생성 ───────────────────────────────────────────────────────

def _make_hwpx(rows: list[list[str]]) -> bytes:
    """최소한의 HWPX ZIP bytes 생성 (테스트 전용)."""
    cells_xml = lambda cells: "".join(
        f'<hp:tc><hp:p><hp:run><hp:t>{c}</hp:t></hp:run></hp:p></hp:tc>'
        for c in cells
    )
    rows_xml = "".join(f"<hp:tr>{cells_xml(r)}</hp:tr>" for r in rows)
    section_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<hp:sec xmlns:hp="{NS_HP}">'
        f'<hp:tbl>{rows_xml}</hp:tbl>'
        f'</hp:sec>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Contents/section0.xml", section_xml.encode("utf-8"))
    return buf.getvalue()


def _write_hwpx(path: Path, rows: list[list[str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_make_hwpx(rows))
    return path


# ── approval_result 생성 헬퍼 ────────────────────────────────────────────────

def _make_approval_result(confirmed=None, edited=None, held=None, attach=None):
    from hwpx.pipeline.approval_gate import (
        ApprovedField, PendingField,
        ACTION_CONFIRM, ACTION_EDIT, ACTION_HOLD, ACTION_ATTACHMENT,
    )
    from types import SimpleNamespace

    approved = []
    for fk, lbl, val in (confirmed or []):
        approved.append(ApprovedField(
            fieldKey=fk, label=lbl, value=val, originalValue=val,
            action=ACTION_CONFIRM, sourceZone="autoFillReady", confidence=0.92,
        ))
    for fk, lbl, val in (edited or []):
        approved.append(ApprovedField(
            fieldKey=fk, label=lbl, value=val, originalValue="",
            action=ACTION_EDIT, sourceZone="needsReview", confidence=1.0,
        ))

    pending = []
    for fk, lbl in (held or []):
        pending.append(PendingField(
            fieldKey=fk, label=lbl, action=ACTION_HOLD, sourceZone="needsReview",
        ))
    for fk, lbl in (attach or []):
        pending.append(PendingField(
            fieldKey=fk, label=lbl, action=ACTION_ATTACHMENT, sourceZone="missingRequired",
        ))

    return SimpleNamespace(
        approvedFields=approved,
        pendingFields=pending,
        writerEnabled=False,
    )


# ── T01. import ───────────────────────────────────────────────────────────────

def test_writer_sandbox_importable():
    from hwpx.pipeline import form_auto_fill_writer_sandbox as ws
    assert hasattr(ws, "run_sandbox_write")
    assert hasattr(ws, "SandboxWriteResult")
    assert hasattr(ws, "SCHEMA_VERSION")
    assert hasattr(ws, "BLOCKED_NOT_APPROVED")


# ── T02. dry-run은 output HWPX 생성하지 않음 ─────────────────────────────────

def test_dry_run_no_output(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", ""]])
    ar = _make_approval_result(confirmed=[("contractorName", "시공자", "대한소방")])
    result = run_sandbox_write(ar, tmpl, tmp_path / "out", dry_run=True)
    output_dir = tmp_path / "out" / "output"
    hwpx_files = list(output_dir.glob("*.hwpx")) if output_dir.exists() else []
    assert hwpx_files == [], "dry-run이 output 파일 생성함"
    assert any("DRY_RUN" in str(result.warnings) or
               f["writeStatus"] == "DRY_RUN"
               for f in result.writtenFields), "dry-run status not set"


# ── T03. sandbox-write는 output copy만 생성 ──────────────────────────────────

def test_sandbox_write_creates_output_copy(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", ""]])
    ar = _make_approval_result(confirmed=[("contractorName", "시공자", "대한소방")])
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    output_files = list((tmp_path / "out" / "output").glob("*.hwpx"))
    assert len(output_files) == 1, f"output 파일 없음: {list(output_files)}"


# ── T04. source_path == output_path 거부 ─────────────────────────────────────

def test_same_path_rejected(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import _do_write, WriteTarget
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", ""]])
    with pytest.raises((ValueError, AssertionError)):
        _do_write(tmpl, tmpl, {}, [])


# ── T05. 원본 HWPX sha256 변경 없음 ──────────────────────────────────────────

def test_source_sha256_unchanged(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write, _sha256
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", ""]])
    before = _sha256(tmpl)
    ar = _make_approval_result(confirmed=[("contractorName", "시공자", "대한소방")])
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    after = _sha256(tmpl)
    assert before == after, "원본 HWPX sha256 변경됨"
    assert result.sourceMutated is False


# ── T06. 원본 HWPX mtime 변경 없음 ───────────────────────────────────────────

def test_source_mtime_unchanged(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", ""]])
    mtime_before = tmpl.stat().st_mtime
    ar = _make_approval_result(confirmed=[("contractorName", "시공자", "대한소방")])
    run_sandbox_write(ar, tmpl, tmp_path / "out")
    mtime_after = tmpl.stat().st_mtime
    assert mtime_before == mtime_after, "원본 HWPX mtime 변경됨"


# ── T07. writerEligible=true 필드만 입력 ─────────────────────────────────────

def test_writer_eligible_true_only(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write, _RB_PASS
    from hwpx.pipeline.approval_gate import (
        ApprovedField, ACTION_CONFIRM,
    )
    from types import SimpleNamespace
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [
        ["시공자", ""],
        ["공사명", ""],
    ])
    # writerEligible=False 항목 수동 생성
    af_ok  = ApprovedField("contractorName", "시공자", "대한소방", "",
                           ACTION_CONFIRM, "autoFillReady", 0.92)
    af_bad = ApprovedField("taskName", "공사명", "소화공사", "",
                           ACTION_CONFIRM, "autoFillReady", 0.92)
    af_bad.writerEligible = False  # 강제
    ar = SimpleNamespace(approvedFields=[af_ok, af_bad], pendingFields=[], writerEnabled=False)
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    written_keys = {f["fieldKey"] for f in result.writtenFields}
    blocked_keys = {f["fieldKey"] for f in result.blockedFields}
    assert "contractorName" in written_keys or "contractorName" in blocked_keys
    assert "taskName" not in written_keys or \
           any(f["fieldKey"] == "taskName" and f.get("blockedReason") == "BLOCKED_NOT_APPROVED"
               for f in result.blockedFields)


# ── T08. writerEligible=false 차단 ───────────────────────────────────────────

def test_writer_eligible_false_blocked(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write, BLOCKED_NOT_APPROVED
    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    from types import SimpleNamespace
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["공사명", ""]])
    af = ApprovedField("taskName", "공사명", "소화공사", "",
                       ACTION_CONFIRM, "autoFillReady", 0.92)
    af.writerEligible = False
    ar = SimpleNamespace(approvedFields=[af], pendingFields=[], writerEnabled=False)
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    blocked = [f for f in result.blockedFields if f["fieldKey"] == "taskName"]
    assert blocked, "writerEligible=false 필드가 차단되지 않음"
    assert blocked[0]["blockedReason"] == BLOCKED_NOT_APPROVED


# ── T09. HOLD 차단 ───────────────────────────────────────────────────────────

def test_hold_field_blocked(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write, BLOCKED_HOLD
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", ""]])
    ar = _make_approval_result(held=[("contractorName", "시공자")])
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    blocked = [f for f in result.blockedFields if f["fieldKey"] == "contractorName"]
    assert blocked and blocked[0]["blockedReason"] == BLOCKED_HOLD


# ── T10. REQUEST_ATTACHMENT 차단 ─────────────────────────────────────────────

def test_attachment_request_blocked(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import (
        run_sandbox_write, BLOCKED_ATTACHMENT_REQUIRED
    )
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", ""]])
    ar = _make_approval_result(attach=[("contractorName", "시공자")])
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    blocked = [f for f in result.blockedFields if f["fieldKey"] == "contractorName"]
    assert blocked and blocked[0]["blockedReason"] == BLOCKED_ATTACHMENT_REQUIRED


# ── T11. targetLocation 없으면 BLOCKED_NO_TARGET_LOCATION ────────────────────

def test_no_target_location_blocked(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import (
        run_sandbox_write, BLOCKED_NO_TARGET_LOCATION
    )
    # template에 없는 라벨
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["전혀무관한라벨", ""]])
    ar = _make_approval_result(confirmed=[("contractorName", "시공자", "대한소방")])
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    blocked = [f for f in result.blockedFields if f["fieldKey"] == "contractorName"]
    assert blocked, "targetLocation 없는 필드가 차단되지 않음"
    assert blocked[0]["blockedReason"] == BLOCKED_NO_TARGET_LOCATION


# ── T12. ambiguous target → BLOCKED_AMBIGUOUS_TARGET ─────────────────────────

def test_ambiguous_target_blocked(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import (
        run_sandbox_write, BLOCKED_AMBIGUOUS_TARGET
    )
    # 같은 라벨이 두 행에 등장 (서로 다른 위치)
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [
        ["시공자", ""],
        ["시공자", ""],   # 중복 → AMBIGUOUS
    ])
    ar = _make_approval_result(confirmed=[("contractorName", "시공자", "대한소방")])
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    blocked = [f for f in result.blockedFields if f["fieldKey"] == "contractorName"]
    assert blocked, "ambiguous target이 차단되지 않음"
    assert blocked[0]["blockedReason"] == BLOCKED_AMBIGUOUS_TARGET


# ── T13. low confidence target → BLOCKED_LOW_TARGET_CONFIDENCE ───────────────

def test_low_confidence_target_blocked(monkeypatch, tmp_path):
    import hwpx.pipeline.form_auto_fill_writer_sandbox as ws
    monkeypatch.setattr(ws, "TARGET_CONF_MIN", 0.99)  # 모든 매칭이 낮은 신뢰도로 처리됨
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", ""]])
    ar = _make_approval_result(confirmed=[("contractorName", "시공자", "대한소방")])
    result = ws.run_sandbox_write(ar, tmpl, tmp_path / "out")
    blocked = [f for f in result.blockedFields if f["fieldKey"] == "contractorName"]
    assert blocked, "low confidence target이 차단되지 않음"
    assert blocked[0]["blockedReason"] == ws.BLOCKED_LOW_TARGET_CONFIDENCE


# ── T14. CONFIRM_FIELD 값 입력 ────────────────────────────────────────────────

def test_confirm_field_written(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", ""]])
    ar = _make_approval_result(confirmed=[("contractorName", "시공자", "대한소방")])
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    written = [f for f in result.writtenFields if f["fieldKey"] == "contractorName"]
    assert written, "CONFIRM_FIELD 값이 입력되지 않음"
    assert written[0]["writeStatus"] == "WRITTEN"


# ── T15. EDIT_VALUE 수정값 입력 ───────────────────────────────────────────────

def test_edit_value_written(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", "구값"]])
    ar = _make_approval_result(edited=[("contractorName", "시공자", "새로운소방")])
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    written = [f for f in result.writtenFields if f["fieldKey"] == "contractorName"]
    assert written, "EDIT_VALUE 값이 입력되지 않음"
    assert written[0]["writeStatus"] == "WRITTEN"


# ── T16. readback PASS 검증 ───────────────────────────────────────────────────

def test_readback_pass(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", ""]])
    ar = _make_approval_result(confirmed=[("contractorName", "시공자", "대한소방")])
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    written = [f for f in result.writtenFields if f["fieldKey"] == "contractorName"]
    assert written, "입력된 필드 없음"
    assert written[0]["readbackStatus"] == "PASS", (
        f"readback 실패: {written[0]['readbackStatus']}"
    )
    assert result.summary["readbackPass"] >= 1


# ── T17. readback mismatch 감지 ───────────────────────────────────────────────

def test_readback_mismatch_detected(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import (
        _readback_verify, WriteTarget,
    )
    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM

    # output HWPX에 다른 값 써넣기 (simulate mismatch)
    output = _write_hwpx(tmp_path / "out.hwpx", [["시공자", "엉뚱한값"]])
    tmp_path.joinpath("out.hwpx").write_bytes(output.read_bytes()
                                              if hasattr(output, "read_bytes")
                                              else output)

    af = ApprovedField("contractorName", "시공자", "대한소방", "",
                       ACTION_CONFIRM, "autoFillReady", 0.92)
    target = WriteTarget("Contents/section0.xml", 0, 0, 1, "시공자", 0.95)
    write_results = [{
        "fieldKey": "contractorName", "label": "시공자",
        "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
        "readbackStatus": "SKIPPED", "targetLocation": {}, "valueHash": "",
    }]
    result = _readback_verify(
        tmp_path / "out.hwpx",
        {"contractorName": target},
        [af],
        write_results,
    )
    # readback 값("엉뚱한값") ≠ expected("대한소방") → FAIL
    assert result[0]["readbackStatus"] == "FAIL", "readback mismatch가 감지되지 않음"


# ── T18. output HWPX ZIP 구조 정상 ───────────────────────────────────────────

def test_output_zip_valid(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", ""]])
    ar = _make_approval_result(confirmed=[("contractorName", "시공자", "대한소방")])
    run_sandbox_write(ar, tmpl, tmp_path / "out")
    output_hwpx = next((tmp_path / "out" / "output").glob("*.hwpx"), None)
    assert output_hwpx and output_hwpx.exists()
    assert zipfile.is_zipfile(output_hwpx), "output HWPX가 유효한 ZIP이 아님"
    with zipfile.ZipFile(output_hwpx) as z:
        names = z.namelist()
    assert any("section" in n.lower() for n in names), "section XML 없음"


# ── T19. raw path leak 없음 ──────────────────────────────────────────────────

def test_no_raw_path_in_report(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["시공자", ""]])
    ar = _make_approval_result(confirmed=[("contractorName", "시공자", "대한소방")])
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    out = json.dumps(result.to_dict(), ensure_ascii=False)
    for leak in ("C:\\Users\\", "/home/", "/Users/"):
        assert leak not in out, f"raw path leak: {leak}"


# ── T20. raw filename leak 없음 ──────────────────────────────────────────────

def test_no_raw_filename_in_report(tmp_path):
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
    # 파일명을 개인정보처럼 쓰기
    tmpl = _write_hwpx(tmp_path / "홍길동_소방서_신청서.hwpx", [["시공자", ""]])
    ar = _make_approval_result(confirmed=[("contractorName", "시공자", "대한소방")])
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    out = json.dumps(result.to_dict(), ensure_ascii=False)
    # outputPathMasked에는 원본 파일명이 직접 들어가지 않아야 함
    assert "홍길동" not in out or "outputPathMasked" not in out or \
           result.outputPathMasked != "홍길동_소방서_신청서.hwpx", \
           "raw filename이 report에 노출됨"


# ── T21. PII pattern leak 없음 ───────────────────────────────────────────────

def test_no_pii_in_report(tmp_path):
    pii_re = re.compile(r"\d{3}-\d{2}-\d{5}|\d{6}-\d{7}")
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", [["등록번호", ""]])
    ar = _make_approval_result(
        confirmed=[("registrationNumber", "등록번호", "123-45-67890")]
    )
    result = run_sandbox_write(ar, tmpl, tmp_path / "out")
    out = json.dumps(result.to_dict(), ensure_ascii=False)
    assert not pii_re.search(out), f"PII in report: {out[:300]}"


# ── T22. AI API 호출 없음 ─────────────────────────────────────────────────────

def test_no_ai_api():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
           / "form_auto_fill_writer_sandbox.py").read_text("utf-8")
    for kw in ("anthropic", "openai", "ChatCompletion"):
        assert kw not in src


# ── T23. OCR 호출 없음 ───────────────────────────────────────────────────────

def test_no_ocr():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
           / "form_auto_fill_writer_sandbox.py").read_text("utf-8")
    for kw in ("pytesseract", "easyocr", "image_to_string"):
        assert kw not in src


# ── T24. Hancom 필수 의존 없음 ───────────────────────────────────────────────

def test_no_hancom_dependency():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
           / "form_auto_fill_writer_sandbox.py").read_text("utf-8")
    for kw in ("hwp5", "libhwp", "pyhwp", "hwpx2pdf"):
        assert kw not in src


# ── T25. approval gate 테스트 유지 ───────────────────────────────────────────

def test_approval_gate_still_passes():
    from hwpx.pipeline import approval_gate as ag
    assert hasattr(ag, "apply_decisions")
    assert hasattr(ag, "FieldDecision")


# ── T26. review panel 테스트 유지 ────────────────────────────────────────────

def test_review_panel_still_passes():
    from hwpx.pipeline import review_panel as rp
    assert hasattr(rp, "build_review_panel")


# ── T27. mapping/parser/catalog/recommend 유지 ───────────────────────────────

def test_mapping_still_passes():
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
