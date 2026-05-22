"""HWPX-EDIT-PLAN-WRITER-LIVE-EXPAND-PARAGRAPH-TEXT-01 테스트.

section-level 문단을 sandbox 사본에 한해 수정하는 live 확장 검증.
원본 fixture 무수정 / output 격리 / readback 강제.
"""
from __future__ import annotations

import hashlib
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"

METADATA_FORM = PROJECT_ROOT / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"


@pytest.fixture(scope="module")
def stages():
    from hwpx.pipeline import (
        generic_edit_plan_contract as c,
        generic_edit_plan_dry_run as d,
        generic_edit_plan_review_gate as g,
        generic_edit_plan_writer_adapter as a,
        generic_edit_plan_writer_executor_live_sandbox as live,
    )
    return {"contract": c, "dry_run": d, "gate": g, "adapter": a, "live": live}


def _build_fixture_with_paragraphs(tmp_path: Path,
                                       paragraph_texts: list[str]) -> tuple[Path, str]:
    """METADATA_FORM 사본 + section0 끝에 top-level <hp:p> append.

    return (sandbox 입력으로 사용할 fixture 경로, 그 파일의 sha256).
    원본 METADATA_FORM은 절대 건드리지 않는다.
    """
    ET.register_namespace("hp", NS_HP)
    dst = tmp_path / "fixture_with_paragraphs.hwpx"
    with zipfile.ZipFile(METADATA_FORM) as zin, \
         zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "Contents/section0.xml":
                root = ET.fromstring(data)
                for text in paragraph_texts:
                    p = ET.SubElement(root, f"{{{NS_HP}}}p")
                    run = ET.SubElement(p, f"{{{NS_HP}}}run")
                    t = ET.SubElement(run, f"{{{NS_HP}}}t")
                    t.text = text
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            zout.writestr(new_info, data)
    sha = hashlib.sha256(dst.read_bytes()).hexdigest()
    return dst, sha


def _set_paragraph_text_plan(stages, sha, section_idx, paragraph_idx,
                                  paragraph_key, expected_before, value,
                                  created_by="ai"):
    c = stages["contract"]
    plan = c.empty_plan_skeleton(
        plan_id="plan-pt", source_doc_hash=f"sha256:{sha}",
        created_by=created_by, created_at="2026-05-18T00:00:00Z",
    )
    target = {"sectionIndex": section_idx}
    if paragraph_idx is not None:
        target["paragraphIndex"] = paragraph_idx
    if paragraph_key is not None:
        target["paragraphKey"] = paragraph_key
    plan["operations"] = [{
        "operationId": "op-pt-1",
        "operationType": "setParagraphText",
        "target": target,
        "value": value,
        "preserveStyle": True,
        "expectedBefore": expected_before,
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "paragraph test",
    }]
    return plan


def _replace_text_run_plan(stages, sha, section_idx, paragraph_idx,
                                find, replace, expected_before,
                                created_by="ai"):
    c = stages["contract"]
    plan = c.empty_plan_skeleton(
        plan_id="plan-rtr", source_doc_hash=f"sha256:{sha}",
        created_by=created_by, created_at="2026-05-18T00:00:00Z",
    )
    plan["operations"] = [{
        "operationId": "op-rtr-1",
        "operationType": "replaceTextRun",
        "target": {"sectionIndex": section_idx,
                   "paragraphIndex": paragraph_idx},
        "value": {"find": find, "replace": replace},
        "preserveStyle": True,
        "expectedBefore": expected_before,
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "replace test",
    }]
    return plan


def _build_wcp(stages, plan, parsed_source):
    dr = stages["dry_run"].dry_run_edit_plan(plan, parsed_source)
    gate = stages["gate"].apply_review_decisions(dr, [])
    return stages["adapter"].build_writer_call_plan(plan, dr, gate)


def _parsed(path):
    from hwpx.parser import parse_hwpx_v2
    return parse_hwpx_v2(path)


def _paragraph_visible(zip_path: Path, section_idx: int, paragraph_idx: int) -> str:
    with zipfile.ZipFile(zip_path) as zf:
        sec_paths = sorted(n for n in zf.namelist()
                              if "section" in n and n.endswith(".xml"))
        raw = zf.read(sec_paths[section_idx])
    root = ET.fromstring(raw)
    ps = [c for c in list(root) if c.tag == f"{{{NS_HP}}}p"]
    TAG_T = f"{{{NS_HP}}}t"
    TAG_TBL = f"{{{NS_HP}}}tbl"
    p = ps[paragraph_idx]
    parts: list[str] = []
    def walk(e):
        if e.tag == TAG_TBL:
            return
        if e.tag == TAG_T and e.text:
            parts.append(e.text)
        for c in list(e):
            walk(c)
    for c in list(p):
        walk(c)
    return "".join(parts)


# ── T01: setParagraphText paragraphIndex 성공 ─────────────────────────────────

def test_set_paragraph_text_via_paragraph_index(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path,
                                                  ["원본 문단 A", "원본 문단 B"])
    # METADATA_FORM 기존 top-level p[0]은 빈 텍스트, 추가한 p[1]="원본 문단 A", p[2]="원본 문단 B"
    parsed = _parsed(src)
    plan = _set_paragraph_text_plan(
        stages, sha, section_idx=0, paragraph_idx=1, paragraph_key=None,
        expected_before="원본 문단 A", value="새로운 문단 A",
    )
    wcp = _build_wcp(stages, plan, parsed)
    assert wcp.readyForWriter is True

    output = tmp_path / "out_p_idx.hwpx"
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    mtime_before = src.stat().st_mtime
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED", res.to_dict()
    assert res.writerCalled is True
    assert output.exists()
    assert res.readback.targetCellsVerified == 1
    assert res.readback.divergences == []
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before
    assert src.stat().st_mtime == mtime_before
    # output paragraph 직접 확인
    assert _paragraph_visible(output, 0, 1) == "새로운 문단 A"
    # 비대상 paragraph는 보존
    assert _paragraph_visible(output, 0, 2) == "원본 문단 B"


# ── T02: setParagraphText paragraphKey 성공 ──────────────────────────────────

def test_set_paragraph_text_via_paragraph_key(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["문단X"])
    parsed = _parsed(src)
    plan = _set_paragraph_text_plan(
        stages, sha, section_idx=0, paragraph_idx=None,
        paragraph_key="p_s0_0001",
        expected_before="문단X", value="문단Y",
    )
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_p_key.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED"
    assert _paragraph_visible(output, 0, 1) == "문단Y"


# ── T03: expectedBefore mismatch ─────────────────────────────────────────────

def test_set_paragraph_text_expected_before_mismatch_blocks(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["진짜텍스트"])
    parsed = _parsed(src)
    plan = _set_paragraph_text_plan(
        stages, sha, 0, 1, None,
        expected_before="다른값", value="대체",
    )
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_mis.hwpx"
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "BLOCKED_EXPECTED_BEFORE_MISMATCH"
    assert res.writerCalled is False
    assert not output.exists()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before


# ── T04: target not found ────────────────────────────────────────────────────

def test_set_paragraph_text_target_not_found_blocks(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["X"])
    parsed = _parsed(src)
    plan = _set_paragraph_text_plan(
        stages, sha, 0, 999, None,
        expected_before="X", value="Y",
    )
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_nope.hwpx"
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "BLOCKED_TARGET_NOT_FOUND"
    assert res.writerCalled is False
    assert not output.exists()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before


# ── T05: sourceDocumentHash 누락 차단 ────────────────────────────────────────

def test_set_paragraph_text_source_hash_missing_blocks(stages, tmp_path):
    src, _ = _build_fixture_with_paragraphs(tmp_path, ["X"])
    parsed = _parsed(src)
    # plan을 직접 만들어 sourceDocumentHash를 비운다
    plan = stages["contract"].empty_plan_skeleton(
        "plan-no-hash", "", "ai", "now",
    )
    plan["operations"] = [{
        "operationId": "op", "operationType": "setParagraphText",
        "target": {"sectionIndex": 0, "paragraphIndex": 1},
        "value": "Y", "preserveStyle": True,
        "expectedBefore": "X", "riskLevel": "low",
        "requiresReview": False, "reason": "t",
    }]
    # contract 검증에서 schema invalid로 차단됨 → adapter 단계에서 readyForWriter=False
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_hash.hwpx"
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "BLOCKED_NOT_READY_FOR_WRITER"
    assert res.writerCalled is False
    assert not output.exists()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before


# ── T06: outputPath == sourcePath ────────────────────────────────────────────

def test_set_paragraph_text_output_equals_source_blocks(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["A"])
    parsed = _parsed(src)
    plan = _set_paragraph_text_plan(stages, sha, 0, 1, None,
                                          expected_before="A", value="B")
    wcp = _build_wcp(stages, plan, parsed)
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, src)
    assert res.verdict == "BLOCKED_UNSAFE_OUTPUT_PATH"
    assert any(f.code == "OUTPUT_OVERWRITES_SOURCE" for f in res.safetyFindings)
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before


# ── T07: 원본 sha256/mtime 무변경 (모든 케이스에서) ─────────────────────────

def test_source_unchanged_after_paragraph_writes(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["aaa", "bbb"])
    parsed = _parsed(src)
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    mtime_before = src.stat().st_mtime
    plan = _set_paragraph_text_plan(stages, sha, 0, 1, None,
                                          expected_before="aaa", value="xxx")
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_persist.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED"
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before
    assert src.stat().st_mtime == mtime_before
    # METADATA_FORM 원본도 무변경
    sha_meta_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    assert sha_meta_before  # 확인용


# ── T08: readback text 정확 일치 ────────────────────────────────────────────

def test_set_paragraph_text_readback_exact_match(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["원본"])
    parsed = _parsed(src)
    plan = _set_paragraph_text_plan(stages, sha, 0, 1, None,
                                          expected_before="원본",
                                          value="검증된변경값")
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_rb.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED"
    assert _paragraph_visible(output, 0, 1) == "검증된변경값"


# ── T09: 대상 외 문단 보존 ──────────────────────────────────────────────────

def test_set_paragraph_text_preserves_other_paragraphs(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path,
                                                  ["aaa", "bbb", "ccc"])
    parsed = _parsed(src)
    plan = _set_paragraph_text_plan(stages, sha, 0, 2, None,
                                          expected_before="bbb", value="BBB!")
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_preserve.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED"
    assert _paragraph_visible(output, 0, 1) == "aaa"
    assert _paragraph_visible(output, 0, 2) == "BBB!"
    assert _paragraph_visible(output, 0, 3) == "ccc"


# ── T10: replaceTextRun 성공 ─────────────────────────────────────────────────

def test_replace_text_run_single_t_replaces(stages, tmp_path):
    text = "공사기간 2026.02.01 종료"
    src, sha = _build_fixture_with_paragraphs(tmp_path, [text])
    parsed = _parsed(src)
    plan = _replace_text_run_plan(stages, sha, 0, 1,
                                       find="2026.02.01", replace="2026.03.01",
                                       expected_before=text)
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_rtr.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED", res.to_dict()
    assert _paragraph_visible(output, 0, 1) == "공사기간 2026.03.01 종료"


# ── T11: find not found ─────────────────────────────────────────────────────

def test_replace_text_run_find_not_found_blocks(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["hello world"])
    parsed = _parsed(src)
    plan = _replace_text_run_plan(stages, sha, 0, 1,
                                       find="missing", replace="x",
                                       expected_before="hello world")
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_nf.hwpx"
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "BLOCKED_FIND_TEXT_NOT_FOUND"
    assert not output.exists()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before


# ── T12: find 2회 이상 → ambiguous ──────────────────────────────────────────

def test_replace_text_run_ambiguous_blocks(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["foo bar foo"])
    parsed = _parsed(src)
    plan = _replace_text_run_plan(stages, sha, 0, 1,
                                       find="foo", replace="X",
                                       expected_before="foo bar foo")
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_amb.hwpx"
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "BLOCKED_AMBIGUOUS_TEXT_RUN"
    assert not output.exists()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before


# ── T13: replaceTextRun expectedBefore mismatch ─────────────────────────────

def test_replace_text_run_expected_before_mismatch_blocks(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["actual text"])
    parsed = _parsed(src)
    plan = _replace_text_run_plan(stages, sha, 0, 1,
                                       find="text", replace="X",
                                       expected_before="WRONG")
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_mis2.hwpx"
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "BLOCKED_EXPECTED_BEFORE_MISMATCH"
    assert not output.exists()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before


# ── T14: find 빈 문자열 ─────────────────────────────────────────────────────

def test_replace_text_run_empty_find_blocks(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["abc"])
    parsed = _parsed(src)
    plan = _replace_text_run_plan(stages, sha, 0, 1,
                                       find="", replace="X",
                                       expected_before="abc")
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_empty_find.hwpx"
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "BLOCKED_INVALID_FIND_TEXT"
    assert not output.exists()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before


# ── T15: replace 빈 문자열 허용 (삭제 치환) ─────────────────────────────────

def test_replace_text_run_empty_replace_allowed_as_deletion(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["prefix-DELETE-suffix"])
    parsed = _parsed(src)
    plan = _replace_text_run_plan(stages, sha, 0, 1,
                                       find="-DELETE-", replace="",
                                       expected_before="prefix-DELETE-suffix")
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_del.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED"
    assert _paragraph_visible(output, 0, 1) == "prefixsuffix"


# ── T16: replaceTextRun readback ────────────────────────────────────────────

def test_replace_text_run_readback_matches(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["start 2025 end"])
    parsed = _parsed(src)
    plan = _replace_text_run_plan(stages, sha, 0, 1,
                                       find="2025", replace="2026",
                                       expected_before="start 2025 end")
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_rb2.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED"
    assert res.readback.targetCellsVerified == 1
    assert _paragraph_visible(output, 0, 1) == "start 2026 end"


# ── T17: replaceTextRun 후 원본 무변경 ──────────────────────────────────────

def test_replace_text_run_source_unchanged(stages, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["a-OLD-b"])
    parsed = _parsed(src)
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    mtime_before = src.stat().st_mtime
    plan = _replace_text_run_plan(stages, sha, 0, 1,
                                       find="OLD", replace="NEW",
                                       expected_before="a-OLD-b")
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_inv.hwpx"
    stages["live"].execute_writer_call_plan_live_sandbox(wcp, src, output)
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before
    assert src.stat().st_mtime == mtime_before


# ── T18: setCellText 회귀 (METADATA_FORM 셀 편집은 기존 테스트 회귀) ────────

def test_set_cell_text_regression_under_extension(stages, tmp_path):
    """확장 후에도 셀 텍스트 편집은 그대로 동작."""
    from hwpx.parser import parse_hwpx_v2
    parsed = parse_hwpx_v2(METADATA_FORM)
    target = None
    for t in parsed.tables:
        for c in t.cells:
            if c.normalizedText == "교육기관대행갱신신청서":
                target = (t.tableId, c); break
        if target: break
    t_id, cell = target
    sha = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    plan = stages["contract"].empty_plan_skeleton(
        "plan-cell-reg", f"sha256:{sha}", "ai", "now")
    plan["operations"] = [{
        "operationId": "op", "operationType": "setCellText",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": "회귀확인", "preserveStyle": True,
        "expectedBefore": cell.normalizedText, "riskLevel": "low",
        "requiresReview": False, "reason": "reg",
    }]
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_cell_reg.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, METADATA_FORM, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED"


# ── T19: setCellHorizontalAlign 회귀 ───────────────────────────────────────

def test_align_regression_under_extension(stages, tmp_path):
    from hwpx.parser import parse_hwpx_v2
    parsed = parse_hwpx_v2(METADATA_FORM)
    target = None
    for t in parsed.tables:
        for c in t.cells:
            if c.normalizedText == "교육기관대행갱신신청서":
                target = (t.tableId, c); break
        if target: break
    t_id, cell = target
    sha = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    plan = stages["contract"].empty_plan_skeleton(
        "plan-h-reg", f"sha256:{sha}", "ai", "now")
    plan["operations"] = [{
        "operationId": "op-h", "operationType": "setCellHorizontalAlign",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": "RIGHT", "preserveStyle": True,
        "expectedBefore": cell.horizontalAlign, "riskLevel": "low",
        "requiresReview": False, "reason": "reg",
    }]
    wcp = _build_wcp(stages, plan, parsed)
    output = tmp_path / "out_h_reg.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, METADATA_FORM, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED"


# ── T20: unsupported operation 차단 유지 ────────────────────────────────────

def test_setcellfillcolor_still_unsupported_in_live(stages, tmp_path):
    from hwpx.parser import parse_hwpx_v2
    parsed = parse_hwpx_v2(METADATA_FORM)
    target = None
    for t in parsed.tables:
        for c in t.cells:
            if c.normalizedText == "교육기관대행갱신신청서":
                target = (t.tableId, c); break
        if target: break
    t_id, cell = target
    plan = stages["contract"].empty_plan_skeleton(
        "plan-fill-still", "sha256:abc", "ai", "now")
    plan["operations"] = [{
        "operationId": "op-fill", "operationType": "setCellFillColor",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": "#FFFF00", "preserveStyle": True,
        "expectedBefore": cell.fillColor, "riskLevel": "low",
        "requiresReview": False, "reason": "still review",
    }]
    dr = stages["dry_run"].dry_run_edit_plan(plan, parsed)
    gate = stages["gate"].apply_review_decisions(dr, [{
        "decisionId": "d", "planId": plan["planId"], "operationId": "op-fill",
        "reviewer": "x", "decision": "APPROVE", "reason": "y",
        "decidedAt": "now",
    }])
    wcp = stages["adapter"].build_writer_call_plan(plan, dr, gate)
    output = tmp_path / "out_still_fill.hwpx"
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, METADATA_FORM, output)
    assert res.verdict == "BLOCKED_UNSUPPORTED_LIVE_OPERATION"
    assert not output.exists()
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before


# ── T21: object_cell_mapper / confirmation gate 충돌 없음 ───────────────────

def test_object_cell_mapper_does_not_invoke_writer(stages, tmp_path):
    """object-cell mapper와 confirmation gate 호출 중 writer가 호출되지 않는다."""
    from hwpx.parser import object_cell_mapper, object_cell_confirmation_gate
    call_log: list = []
    orig = stages["live"].execute_writer_call_plan_live_sandbox

    def _trap(*a, **k):
        call_log.append("live"); return orig(*a, **k)

    # mapper / confirmation gate 동작이 live executor를 호출하지 않음을 확인
    r = object_cell_mapper.map_objects_to_cells_with_geometry(METADATA_FORM)
    object_cell_confirmation_gate.apply_geometric_confirmation(r, [])
    assert call_log == []


# ── T22: ALLOWED_LIVE_OPERATION_TYPES에 paragraph ops 포함 확인 ─────────────

def test_allowed_live_operation_types_includes_paragraph_ops(stages):
    live = stages["live"]
    assert "setParagraphText" in live.ALLOWED_LIVE_OPERATION_TYPES
    assert "replaceTextRun" in live.ALLOWED_LIVE_OPERATION_TYPES
    assert "setCellFillColor" not in live.ALLOWED_LIVE_OPERATION_TYPES
