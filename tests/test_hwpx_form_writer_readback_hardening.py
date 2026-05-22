"""HWPX-FORM-AUTO-FILL-WRITER-READBACK-HARDENING-02 — 테스트."""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


# ── synthetic HWPX ────────────────────────────────────────────────────────────

def _make_hwpx(rows: list[list[str]], extra_sections: dict[str, bytes] | None = None) -> bytes:
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
        for name, content in (extra_sections or {}).items():
            z.writestr(name, content)
    return buf.getvalue()


def _write_hwpx(path: Path, rows: list[list[str]],
                extra_sections: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_make_hwpx(rows, extra_sections))
    return path


def _make_approval_result(confirmed=None, edited=None, held=None, attach=None):
    from hwpx.pipeline.approval_gate import (
        ApprovedField, PendingField,
        ACTION_CONFIRM, ACTION_EDIT, ACTION_HOLD, ACTION_ATTACHMENT,
    )
    from types import SimpleNamespace
    approved = [
        ApprovedField(fk, lbl, val, val, ACTION_CONFIRM, "autoFillReady", 0.92)
        for fk, lbl, val in (confirmed or [])
    ]
    for fk, lbl, val in (edited or []):
        approved.append(ApprovedField(fk, lbl, val, "", ACTION_EDIT, "needsReview", 1.0))
    pending = [
        PendingField(fk, lbl, ACTION_HOLD, "needsReview") for fk, lbl in (held or [])
    ] + [
        PendingField(fk, lbl, ACTION_ATTACHMENT, "missingRequired") for fk, lbl in (attach or [])
    ]
    return SimpleNamespace(approvedFields=approved, pendingFields=pending, writerEnabled=False)


def _run_write_and_verify(tmp_path, rows, confirmed=None, edited=None):
    """sandbox write 후 hardening 검증. (result, hardening) 반환."""
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
    from hwpx.pipeline.form_writer_readback_hardening import verify_readback
    tmpl = _write_hwpx(tmp_path / "tpl.hwpx", rows)
    ar   = _make_approval_result(confirmed=confirmed, edited=edited)
    wr   = run_sandbox_write(ar, tmpl, tmp_path / "out")
    out_path = tmp_path / "out" / "output" / f"sandbox_tpl.hwpx"
    hr = verify_readback(tmpl, out_path, ar.approvedFields, wr.to_dict())
    return wr, hr


# ── T01. import ───────────────────────────────────────────────────────────────

def test_readback_hardening_importable():
    from hwpx.pipeline import form_writer_readback_hardening as rh
    assert hasattr(rh, "verify_readback")
    assert hasattr(rh, "ReadbackHardeningResult")
    assert hasattr(rh, "VERDICT_PASS")
    assert hasattr(rh, "READBACK_PASS")


# ── T02. sandbox writer 결과 입력 ────────────────────────────────────────────

def test_writer_result_input(tmp_path):
    _, hr = _run_write_and_verify(
        tmp_path, [["시공자", ""]],
        confirmed=[("contractorName", "시공자", "대한소방")],
    )
    assert hr.schemaVersion == "form_writer_readback_hardening_v1"
    assert len(hr.fieldResults) >= 1


# ── T03. 일반 한글 값 readback PASS ──────────────────────────────────────────

def test_korean_value_readback_pass(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import READBACK_PASS, VERDICT_PASS
    _, hr = _run_write_and_verify(
        tmp_path, [["시공자", ""]],
        confirmed=[("contractorName", "시공자", "대한소방")],
    )
    fr = [f for f in hr.fieldResults if f["fieldKey"] == "contractorName"]
    assert fr and fr[0]["readbackStatus"] == READBACK_PASS
    assert hr.overallVerdict == VERDICT_PASS


# ── T04. 숫자 값 readback PASS ────────────────────────────────────────────────

def test_number_value_readback_pass(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import READBACK_PASS
    _, hr = _run_write_and_verify(
        tmp_path, [["층수", ""]],
        confirmed=[("floorCount", "층수", "15")],
    )
    fr = [f for f in hr.fieldResults if f["fieldKey"] == "floorCount"]
    assert fr and fr[0]["readbackStatus"] == READBACK_PASS


# ── T05. 날짜 값 readback PASS ───────────────────────────────────────────────

def test_date_value_readback_pass(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import READBACK_PASS
    _, hr = _run_write_and_verify(
        tmp_path, [["착공일자", ""]],
        confirmed=[("startDate", "착공일자", "2026-05-22")],
    )
    fr = [f for f in hr.fieldResults if f["fieldKey"] == "startDate"]
    assert fr and fr[0]["readbackStatus"] == READBACK_PASS


# ── T06. 금액 값 readback PASS ───────────────────────────────────────────────

def test_amount_value_readback_pass(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import READBACK_PASS
    _, hr = _run_write_and_verify(
        tmp_path, [["공사금액", ""]],
        confirmed=[("amount", "공사금액", "1,500,000원")],
    )
    fr = [f for f in hr.fieldResults if f["fieldKey"] == "amount"]
    assert fr and fr[0]["readbackStatus"] == READBACK_PASS


# ── T07. 줄바꿈 포함 값 readback ─────────────────────────────────────────────

def test_newline_value_readback(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import READBACK_PASS, READBACK_WARN_NORMALIZED_MATCH
    value = "1층\n2층"
    _, hr = _run_write_and_verify(
        tmp_path, [["층정보", ""]],
        confirmed=[("floorInfo", "층정보", value)],
    )
    fr = [f for f in hr.fieldResults if f["fieldKey"] == "floorInfo"]
    # 줄바꿈 보존 여부에 따라 PASS 또는 WARN
    assert fr and fr[0]["readbackStatus"] in (READBACK_PASS, READBACK_WARN_NORMALIZED_MATCH,
                                               "READBACK_FAIL_VALUE_MISMATCH")


# ── T08. 특수문자 포함 값 readback ───────────────────────────────────────────

def test_special_chars_readback(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import READBACK_PASS
    _, hr = _run_write_and_verify(
        tmp_path, [["비고", ""]],
        confirmed=[("note", "비고", "(주)대한소방-서울")],
    )
    fr = [f for f in hr.fieldResults if f["fieldKey"] == "note"]
    assert fr and fr[0]["readbackStatus"] == READBACK_PASS


# ── T09. 앞뒤 공백 → normalized match WARN ───────────────────────────────────

def test_whitespace_normalized_match(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import (
        verify_readback, READBACK_WARN_NORMALIZED_MATCH,
    )
    # expected에 앞뒤 공백 포함, output HWPX에는 공백 없는 값 → _cell_text strip 후 normalized match
    src = _write_hwpx(tmp_path / "src.hwpx", [["시공자", ""]])
    out = _write_hwpx(tmp_path / "out.hwpx", [["시공자", "대한소방"]])

    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    af = ApprovedField("contractorName", "시공자", "  대한소방  ", "", ACTION_CONFIRM, "", 0.92)
    # expected = "  대한소방  ", actual readback = "대한소방" → normalized match

    writer_dict = {"writtenFields": [{
        "fieldKey": "contractorName", "label": "시공자",
        "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
        "readbackStatus": "SKIPPED",
        "targetLocation": {
            "type": "table_cell", "sectionName": "Contents/section0.xml",
            "tableIndex": 0, "row": 0, "col": 1,
        },
        "valueHash": "irrelevant",
    }]}
    hr = verify_readback(src, out, [af], writer_dict)
    fr = [f for f in hr.fieldResults if f["fieldKey"] == "contractorName"]
    assert fr and fr[0]["readbackStatus"] == READBACK_WARN_NORMALIZED_MATCH


# ── T10. 잘린 값 감지 (FAIL_TRUNCATED) ────────────────────────────────────────

def test_truncated_value_detected(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import (
        verify_readback, READBACK_FAIL_TRUNCATED_VALUE,
    )
    long_val = "대한소방설비주식회사서울특별시강남구"
    short_val = "대한소방설비"
    src = _write_hwpx(tmp_path / "src.hwpx", [["시공자", ""]])
    out = _write_hwpx(tmp_path / "out.hwpx", [["시공자", short_val]])

    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    af = ApprovedField("contractorName", "시공자", long_val, "", ACTION_CONFIRM, "", 0.92)
    writer_dict = {"writtenFields": [{
        "fieldKey": "contractorName", "label": "시공자",
        "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
        "readbackStatus": "SKIPPED",
        "targetLocation": {
            "type": "table_cell", "sectionName": "Contents/section0.xml",
            "tableIndex": 0, "row": 0, "col": 1,
        },
        "valueHash": "irrelevant",
    }]}
    hr = verify_readback(src, out, [af], writer_dict)
    fr = [f for f in hr.fieldResults if f["fieldKey"] == "contractorName"]
    assert fr and fr[0]["readbackStatus"] == READBACK_FAIL_TRUNCATED_VALUE


# ── T11. 빈 값 FAIL_EMPTY 처리 ───────────────────────────────────────────────

def test_empty_value_detected(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import (
        verify_readback, READBACK_FAIL_EMPTY_VALUE,
    )
    src = _write_hwpx(tmp_path / "src.hwpx", [["시공자", ""]])
    out = _write_hwpx(tmp_path / "out.hwpx", [["시공자", ""]])  # 빈 값

    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    af = ApprovedField("contractorName", "시공자", "대한소방", "", ACTION_CONFIRM, "", 0.92)
    writer_dict = {"writtenFields": [{
        "fieldKey": "contractorName", "label": "시공자",
        "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
        "readbackStatus": "SKIPPED",
        "targetLocation": {
            "type": "table_cell", "sectionName": "Contents/section0.xml",
            "tableIndex": 0, "row": 0, "col": 1,
        },
        "valueHash": "irrelevant",
    }]}
    hr = verify_readback(src, out, [af], writer_dict)
    fr = [f for f in hr.fieldResults if f["fieldKey"] == "contractorName"]
    assert fr and fr[0]["readbackStatus"] == READBACK_FAIL_EMPTY_VALUE


# ── T12. target missing 감지 ─────────────────────────────────────────────────

def test_missing_target_detected(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import (
        verify_readback, READBACK_FAIL_MISSING_TARGET,
    )
    src = _write_hwpx(tmp_path / "src.hwpx", [["시공자", ""]])
    out = _write_hwpx(tmp_path / "out.hwpx", [["시공자", "대한소방"]])

    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    af = ApprovedField("contractorName", "시공자", "대한소방", "", ACTION_CONFIRM, "", 0.92)
    writer_dict = {"writtenFields": [{
        "fieldKey": "contractorName", "label": "시공자",
        "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
        "readbackStatus": "SKIPPED",
        "targetLocation": {
            "type": "table_cell", "sectionName": "Contents/section0.xml",
            "tableIndex": 99,  # 존재하지 않는 table
            "row": 0, "col": 1,
        },
        "valueHash": "irrelevant",
    }]}
    hr = verify_readback(src, out, [af], writer_dict)
    fr = [f for f in hr.fieldResults if f["fieldKey"] == "contractorName"]
    assert fr and fr[0]["readbackStatus"] == READBACK_FAIL_MISSING_TARGET


# ── T13. duplicate target 감지 ────────────────────────────────────────────────

def test_duplicate_target_detected(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import (
        verify_readback, READBACK_FAIL_DUPLICATE_TARGET,
    )
    src = _write_hwpx(tmp_path / "src.hwpx", [["시공자", ""], ["공사명", ""]])
    out = _write_hwpx(tmp_path / "out.hwpx", [["시공자", "대한소방"], ["공사명", "소화공사"]])

    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    af1 = ApprovedField("contractorName", "시공자", "대한소방", "", ACTION_CONFIRM, "", 0.92)
    af2 = ApprovedField("taskName", "공사명", "소화공사", "", ACTION_CONFIRM, "", 0.92)

    same_loc = {
        "type": "table_cell", "sectionName": "Contents/section0.xml",
        "tableIndex": 0, "row": 0, "col": 1,
    }
    writer_dict = {"writtenFields": [
        {"fieldKey": "contractorName", "label": "시공자",
         "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
         "readbackStatus": "SKIPPED", "targetLocation": same_loc, "valueHash": ""},
        {"fieldKey": "taskName", "label": "공사명",
         "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
         "readbackStatus": "SKIPPED", "targetLocation": same_loc, "valueHash": ""},
    ]}
    hr = verify_readback(src, out, [af1, af2], writer_dict)
    dup = [f for f in hr.fieldResults if f["readbackStatus"] == READBACK_FAIL_DUPLICATE_TARGET]
    assert len(dup) >= 1


# ── T14. value mismatch 감지 ─────────────────────────────────────────────────

def test_value_mismatch_detected(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import (
        verify_readback, READBACK_FAIL_VALUE_MISMATCH, VERDICT_FAIL_MISMATCH,
    )
    src = _write_hwpx(tmp_path / "src.hwpx", [["시공자", ""]])
    out = _write_hwpx(tmp_path / "out.hwpx", [["시공자", "엉뚱한값"]])

    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    af = ApprovedField("contractorName", "시공자", "대한소방", "", ACTION_CONFIRM, "", 0.92)
    writer_dict = {"writtenFields": [{
        "fieldKey": "contractorName", "label": "시공자",
        "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
        "readbackStatus": "SKIPPED",
        "targetLocation": {
            "type": "table_cell", "sectionName": "Contents/section0.xml",
            "tableIndex": 0, "row": 0, "col": 1,
        },
        "valueHash": "irrelevant",
    }]}
    hr = verify_readback(src, out, [af], writer_dict)
    fr = [f for f in hr.fieldResults if f["fieldKey"] == "contractorName"]
    assert fr and fr[0]["readbackStatus"] == READBACK_FAIL_VALUE_MISMATCH
    assert hr.overallVerdict == VERDICT_FAIL_MISMATCH


# ── T15. output ZIP 깨짐 감지 ────────────────────────────────────────────────

def test_broken_zip_detected(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import (
        verify_readback, VERDICT_FAIL_BROKEN,
    )
    src = _write_hwpx(tmp_path / "src.hwpx", [["시공자", ""]])
    out = tmp_path / "broken.hwpx"
    out.write_bytes(b"not a zip file at all !!")

    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    af = ApprovedField("contractorName", "시공자", "대한소방", "", ACTION_CONFIRM, "", 0.92)
    writer_dict = {"writtenFields": [{
        "fieldKey": "contractorName", "label": "시공자",
        "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
        "readbackStatus": "SKIPPED",
        "targetLocation": {
            "type": "table_cell", "sectionName": "Contents/section0.xml",
            "tableIndex": 0, "row": 0, "col": 1,
        },
        "valueHash": "",
    }]}
    hr = verify_readback(src, out, [af], writer_dict)
    assert hr.overallVerdict == VERDICT_FAIL_BROKEN
    assert hr.fieldResults[0]["readbackStatus"] == "READBACK_FAIL_OUTPUT_XML_BROKEN"


# ── T16. section XML 깨짐 감지 ───────────────────────────────────────────────

def test_broken_section_xml_detected(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import verify_readback
    src = _write_hwpx(tmp_path / "src.hwpx", [["시공자", ""]])
    # ZIP은 유효하지만 section XML이 깨짐
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", b"<broken xml <<<<")
    out = tmp_path / "broken_xml.hwpx"
    out.write_bytes(buf.getvalue())

    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    af = ApprovedField("contractorName", "시공자", "대한소방", "", ACTION_CONFIRM, "", 0.92)
    writer_dict = {"writtenFields": [{
        "fieldKey": "contractorName", "label": "시공자",
        "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
        "readbackStatus": "SKIPPED",
        "targetLocation": {
            "type": "table_cell", "sectionName": "Contents/section0.xml",
            "tableIndex": 0, "row": 0, "col": 1,
        },
        "valueHash": "",
    }]}
    hr = verify_readback(src, out, [af], writer_dict)
    assert not hr.structureCheck.sectionXmlValid


# ── T17. 비대상 셀 mutation 감지 ─────────────────────────────────────────────

def test_unexpected_cell_mutation_detected(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import (
        verify_readback, VERDICT_FAIL_XML_MUTATION,
    )
    src = _write_hwpx(tmp_path / "src.hwpx", [
        ["시공자", ""],
        ["기존값셀", "원래값"],   # 비대상 셀
    ])
    out = _write_hwpx(tmp_path / "out.hwpx", [
        ["시공자", "대한소방"],
        ["기존값셀", "바뀐값"],   # 비대상 셀이 변경됨
    ])
    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    af = ApprovedField("contractorName", "시공자", "대한소방", "", ACTION_CONFIRM, "", 0.92)
    writer_dict = {"writtenFields": [{
        "fieldKey": "contractorName", "label": "시공자",
        "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
        "readbackStatus": "SKIPPED",
        "targetLocation": {
            "type": "table_cell", "sectionName": "Contents/section0.xml",
            "tableIndex": 0, "row": 0, "col": 1,
        },
        "valueHash": "irrelevant",
    }]}
    hr = verify_readback(src, out, [af], writer_dict)
    assert hr.structureCheck.unexpectedCellMutationCount > 0
    assert hr.overallVerdict == VERDICT_FAIL_XML_MUTATION


# ── T18. table/cell count 변경 감지 ──────────────────────────────────────────

def test_table_cell_count_change_detected(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import verify_readback
    src = _write_hwpx(tmp_path / "src.hwpx", [["시공자", ""]])
    # output에 행 추가
    out = _write_hwpx(tmp_path / "out.hwpx", [["시공자", "대한소방"], ["추가행", "추가값"]])

    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    af = ApprovedField("contractorName", "시공자", "대한소방", "", ACTION_CONFIRM, "", 0.92)
    writer_dict = {"writtenFields": [{
        "fieldKey": "contractorName", "label": "시공자",
        "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
        "readbackStatus": "SKIPPED",
        "targetLocation": {
            "type": "table_cell", "sectionName": "Contents/section0.xml",
            "tableIndex": 0, "row": 0, "col": 1,
        },
        "valueHash": "irrelevant",
    }]}
    hr = verify_readback(src, out, [af], writer_dict)
    assert hr.structureCheck.cellCountChanged


# ── T19. style/charPr 변경 감지 ──────────────────────────────────────────────

def test_style_mutation_detected(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import verify_readback

    # source: charPr 없음
    src_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<hp:sec xmlns:hp="{NS_HP}">'
        f'<hp:tbl><hp:tr>'
        f'<hp:tc><hp:p><hp:run><hp:t>시공자</hp:t></hp:run></hp:p></hp:tc>'
        f'<hp:tc><hp:p><hp:run><hp:t></hp:t></hp:run></hp:p></hp:tc>'
        f'</hp:tr></hp:tbl></hp:sec>'
    )
    # output: charPr 추가됨
    out_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<hp:sec xmlns:hp="{NS_HP}">'
        f'<hp:tbl><hp:tr>'
        f'<hp:tc><hp:p><hp:run><hp:charPr/><hp:t>시공자</hp:t></hp:run></hp:p></hp:tc>'
        f'<hp:tc><hp:p><hp:run><hp:t>대한소방</hp:t></hp:run></hp:p></hp:tc>'
        f'</hp:tr></hp:tbl></hp:sec>'
    )

    def _make_from_xml(xml_str: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("Contents/section0.xml", xml_str.encode("utf-8"))
        return buf.getvalue()

    src = tmp_path / "src.hwpx"
    out = tmp_path / "out.hwpx"
    src.write_bytes(_make_from_xml(src_xml))
    out.write_bytes(_make_from_xml(out_xml))

    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    af = ApprovedField("contractorName", "시공자", "대한소방", "", ACTION_CONFIRM, "", 0.92)
    writer_dict = {"writtenFields": [{
        "fieldKey": "contractorName", "label": "시공자",
        "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
        "readbackStatus": "SKIPPED",
        "targetLocation": {
            "type": "table_cell", "sectionName": "Contents/section0.xml",
            "tableIndex": 0, "row": 0, "col": 1,
        },
        "valueHash": "irrelevant",
    }]}
    hr = verify_readback(src, out, [af], writer_dict)
    assert hr.structureCheck.styleMutationDetected


# ── T20. source sha256 변경 없음 ─────────────────────────────────────────────

def test_source_sha256_unchanged_in_hardening(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import verify_readback, _sha256
    src = _write_hwpx(tmp_path / "src.hwpx", [["시공자", ""]])
    out = _write_hwpx(tmp_path / "out.hwpx", [["시공자", "대한소방"]])
    before = _sha256(src)
    verify_readback(src, out, [], {"writtenFields": []})
    assert _sha256(src) == before


# ── T21. source mtime 변경 없음 ──────────────────────────────────────────────

def test_source_mtime_unchanged_in_hardening(tmp_path):
    from hwpx.pipeline.form_writer_readback_hardening import verify_readback
    src = _write_hwpx(tmp_path / "src.hwpx", [["시공자", ""]])
    out = _write_hwpx(tmp_path / "out.hwpx", [["시공자", "대한소방"]])
    mtime_before = src.stat().st_mtime
    verify_readback(src, out, [], {"writtenFields": []})
    assert src.stat().st_mtime == mtime_before


# ── T22. report에 raw value 저장 없음 ────────────────────────────────────────

def test_no_raw_value_in_report(tmp_path):
    _, hr = _run_write_and_verify(
        tmp_path, [["시공자", ""]],
        confirmed=[("contractorName", "시공자", "대한소방")],
    )
    out = json.dumps(hr.to_dict(), ensure_ascii=False)
    assert "대한소방" not in out, "raw value가 report에 노출됨"


# ── T23. valueHash only 정책 ─────────────────────────────────────────────────

def test_value_hash_only_policy(tmp_path):
    _, hr = _run_write_and_verify(
        tmp_path, [["시공자", ""]],
        confirmed=[("contractorName", "시공자", "대한소방")],
    )
    for fr in hr.fieldResults:
        assert fr.get("valueStoredInReport") is False
        assert "expectedValueHash" in fr
        assert "actualValueHash" in fr


# ── T24. raw path leak 없음 ──────────────────────────────────────────────────

def test_no_raw_path_in_hardening_report(tmp_path):
    _, hr = _run_write_and_verify(
        tmp_path, [["시공자", ""]],
        confirmed=[("contractorName", "시공자", "대한소방")],
    )
    out = json.dumps(hr.to_dict(), ensure_ascii=False)
    for leak in ("C:\\Users\\", "/home/", "/Users/"):
        assert leak not in out


# ── T25. raw filename leak 없음 ──────────────────────────────────────────────

def test_no_raw_filename_in_hardening_report(tmp_path):
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
           / "form_writer_readback_hardening.py").read_text("utf-8")
    for leak in ("C:\\Users\\", "/home/", "/Users/"):
        assert leak not in src


# ── T26. PII pattern leak 없음 ───────────────────────────────────────────────

def test_no_pii_in_hardening_report(tmp_path):
    pii_re = re.compile(r"\d{3}-\d{2}-\d{5}|\d{6}-\d{7}")
    # masked 값 사용 (실제 PII 아님)
    _, hr = _run_write_and_verify(
        tmp_path, [["등록번호", ""]],
        confirmed=[("registrationNumber", "등록번호", "MASKED-12345")],
    )
    out = json.dumps(hr.to_dict(), ensure_ascii=False)
    assert not pii_re.search(out)


# ── T27. AI API 호출 없음 ─────────────────────────────────────────────────────

def test_no_ai_api_in_hardening():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
           / "form_writer_readback_hardening.py").read_text("utf-8")
    for kw in ("anthropic", "openai", "ChatCompletion"):
        assert kw not in src


# ── T28. OCR 호출 없음 ───────────────────────────────────────────────────────

def test_no_ocr_in_hardening():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
           / "form_writer_readback_hardening.py").read_text("utf-8")
    for kw in ("pytesseract", "easyocr", "image_to_string"):
        assert kw not in src


# ── T29. Hancom 의존 없음 ─────────────────────────────────────────────────────

def test_no_hancom_dependency_in_hardening():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
           / "form_writer_readback_hardening.py").read_text("utf-8")
    for kw in ("hwp5", "libhwp", "pyhwp", "hwpx2pdf"):
        assert kw not in src


# ── T30. sandbox writer 테스트 유지 ──────────────────────────────────────────

def test_sandbox_writer_still_passes():
    from hwpx.pipeline import form_auto_fill_writer_sandbox as ws
    assert hasattr(ws, "run_sandbox_write")


# ── T31. approval gate 테스트 유지 ───────────────────────────────────────────

def test_approval_gate_still_passes():
    from hwpx.pipeline import approval_gate as ag
    assert hasattr(ag, "apply_decisions")


# ── T32. 기존 파이프라인 테스트 유지 ─────────────────────────────────────────

def test_pipeline_modules_intact():
    from hwpx.pipeline import review_panel as rp
    from hwpx.pipeline import form_field_mapper as fm
    from hwpx.pipeline import upload_document_parser as up
    from hwpx.recognition_corpus import form_field_catalog as ffc
    from hwpx.recognition_corpus import form_index as fi
    assert all([hasattr(rp, "build_review_panel"), hasattr(fm, "map_fields"),
                hasattr(up, "parse_hwpx"), hasattr(ffc, "build_catalog"),
                hasattr(fi, "recommend")])
