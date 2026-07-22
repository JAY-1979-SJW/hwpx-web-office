"""WEB-OFFICE-PARA-EDIT-SAVE-VERIFY7-01 계약 테스트.

14 시나리오 + audit. writer paragraph plan 미지원 → 부분 준공 게이트.
"""
from __future__ import annotations
import hashlib
import sqlite3
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.hwpx.web_office.hwpx_sample_source import (  # noqa: E402
    resolve_sample as resolve_hwpx_fixture)

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.hwpx.web_office.para_edit_model import (  # noqa: E402
    Paragraph, ParaTextRun, ParagraphTarget,
    make_type_text_command, make_replace_text_range_command,
    make_delete_text_range_command,
)
from scripts.hwpx.web_office.edit_command_model import (  # noqa: E402
    make_set_cell_text_command)
from scripts.hwpx.web_office.paragraph_edit_plan import (  # noqa: E402
    build_dry_run_paragraph_plan,
    PARA_DRY_RUN_NOOP, PARA_DRY_RUN_REJECTED, PARA_DRY_RUN_READY,
    REASON_EXPECTED_BEFORE_MISMATCH_PARAGRAPH,
    REASON_SOURCE_HASH_MISMATCH, REASON_UNSUPPORTED_TYPE,
    BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT,
)
from scripts.hwpx.web_office.paragraph_save_pipeline import (  # noqa: E402
    save_paragraph_edits, _filter_applied_runs_by_coord,
    VERDICT_PARTIAL_DRY_RUN_OK, VERDICT_REJECTED, VERDICT_FAIL,
    VERDICT_NOOP, VERDICT_PASS, VERDICT_PARTIAL,
)
from scripts.hwpx.web_office.paragraph_save_audit import (  # noqa: E402
    append_para_save_audit_record)
from scripts.ops.audit_web_office_para_edit_save_verify7 import (  # noqa: E402
    audit as run_audit)


SRC_HASH = "deadbeef" * 8


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ── fixture helpers ────────────────────────────────────────────

def _make_para(pid: str, runs: list[tuple[str, str, str | None]],
                              par_pr: str | None = "parPr0") -> Paragraph:
    return Paragraph(
        paragraphId=pid, parPrIDRef=par_pr,
        runs=[ParaTextRun(runId=rid, text=t, charPrIDRef=cpr)
                      for rid, t, cpr in runs])


def _target(pid: str) -> ParagraphTarget:
    return ParagraphTarget(paragraphId=pid, containerKind="block",
                                                  containerId="b0",
                                                  sourceSha256=SRC_HASH)


def _hwpx_fixture() -> Path | None:
    """표본 HWPX — 레거시 corpus DB 가 없으면 카탈로그에서 고른다.

    이 파일의 테스트는 문단을 합성해서 쓰므로(_make_para) 표본의 내부
    구조에는 의존하지 않는다. 저장 대상 원본 파일로만 필요하다.
    """
    return resolve_hwpx_fixture()


FIXTURE = _hwpx_fixture()
need_fx = pytest.mark.skipif(FIXTURE is None, reason="hwpx fixture missing")


def _common_paragraphs() -> dict[str, Paragraph]:
    p1 = _make_para("p1", [("p1_run0", "안녕 하세요", "cp0")])
    p2 = _make_para("p2", [("p2_run0", "원본 보존 문단", "cp0")])
    return {"p1": p1, "p2": p2}


# ── 1. TYPE_TEXT 단건 ───────────────────────────────────────────

@need_fx
def test_01_type_text_partial_dry_run_ok(tmp_path):
    paras = _common_paragraphs()
    cmd = make_type_text_command(
        target=_target("p1"), paragraph=paras["p1"],
        caret_offset=2, insert_text="ABC",
        source_document_hash=SRC_HASH)
    out = tmp_path / "p_t01.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd], paragraphs_by_id=paras,
        source_document_hash=SRC_HASH)
    assert res["verdict"] == VERDICT_PARTIAL_DRY_RUN_OK, res
    r = res["verify7"]["results"]
    assert r["V4_CHARPR_PRESERVED"] == "PASS"
    assert r["V5_PARPR_PRESERVED"] == "PASS"
    assert r["V6_OUTPUT_ISOLATED"] == "PASS"
    assert r["V1_RANGE_POSITION_OK"] == "FAIL"
    assert r["V2_NO_CROSS_PARAGRAPH_LEAK"] == "FAIL"
    assert r["V3_UNTOUCHED_RUNS_PRESERVED"] == "FAIL"
    assert r["V7_READBACK_MATCH"] == "FAIL"
    assert len(res["accepted"]) == 1
    assert res["outputCreated"] is False


# ── 2. REPLACE_TEXT_RANGE ──────────────────────────────────────

@need_fx
def test_02_replace_text_range_partial(tmp_path):
    paras = _common_paragraphs()
    cmd = make_replace_text_range_command(
        target=_target("p1"), paragraph=paras["p1"],
        range_anchor=0, range_focus=2, after_text="HI",
        source_document_hash=SRC_HASH)
    assert cmd.expectedBefore == paras["p1"].text[0:2]
    out = tmp_path / "p_t02.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd], paragraphs_by_id=paras,
        source_document_hash=SRC_HASH)
    assert res["verdict"] == VERDICT_PARTIAL_DRY_RUN_OK
    assert res["verify7"]["results"]["V4_CHARPR_PRESERVED"] == "PASS"


# ── 3. DELETE_TEXT_RANGE ───────────────────────────────────────

@need_fx
def test_03_delete_text_range_partial(tmp_path):
    paras = _common_paragraphs()
    cmd = make_delete_text_range_command(
        target=_target("p1"), paragraph=paras["p1"],
        range_anchor=0, range_focus=2,
        source_document_hash=SRC_HASH)
    out = tmp_path / "p_t03.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd], paragraphs_by_id=paras,
        source_document_hash=SRC_HASH)
    assert res["verdict"] == VERDICT_PARTIAL_DRY_RUN_OK


# ── 4. 동일 텍스트 다른 paragraph cross-match 차단 ──────────────

def test_04_same_text_different_paragraph_no_cross_match():
    # plan 좌표 매칭이 paragraphId 를 키로 포함하는지 검증
    plan_edits = [
        {"paragraphId": "p1", "runIdHint": None,
          "rangeAnchor": 0, "rangeFocus": 1, "commandType": "TYPE_TEXT"},
        {"paragraphId": "p2", "runIdHint": None,
          "rangeAnchor": 0, "rangeFocus": 1, "commandType": "TYPE_TEXT"},
    ]
    applied_results = [
        {"paragraphId": "p1", "runIdHint": None,
          "rangeAnchor": 0, "rangeFocus": 1, "commandType": "TYPE_TEXT"},
    ]
    applied, rejected = _filter_applied_runs_by_coord(
        plan_edits, applied_results)
    assert len(applied) == 1
    assert applied[0]["paragraphId"] == "p1"
    assert len(rejected) == 1
    assert rejected[0]["planEntry"]["paragraphId"] == "p2"


# ── 5. untouched paragraph 보존 검증 (사전 스냅샷) ─────────────

@need_fx
def test_05_untouched_paragraph_preserved_snapshot(tmp_path):
    paras = _common_paragraphs()
    pre_text_p2 = paras["p2"].text
    cmd = make_type_text_command(
        target=_target("p1"), paragraph=paras["p1"],
        caret_offset=0, insert_text="X",
        source_document_hash=SRC_HASH)
    out = tmp_path / "p_t05.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd], paragraphs_by_id=paras,
        source_document_hash=SRC_HASH)
    # p2 의 원본 텍스트는 paragraphs_by_id 가 가진 그대로
    assert paras["p2"].text == pre_text_p2
    assert res["verdict"] == VERDICT_PARTIAL_DRY_RUN_OK


# ── 6. applyCharPrIDRef ⊆ 원본 (V4 PASS) ───────────────────────

@need_fx
def test_06_charpr_subset_v4_pass(tmp_path):
    paras = _common_paragraphs()
    cmd = make_type_text_command(
        target=_target("p1"), paragraph=paras["p1"],
        caret_offset=0, insert_text="Z",
        source_document_hash=SRC_HASH)
    out = tmp_path / "p_t06.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd], paragraphs_by_id=paras,
        source_document_hash=SRC_HASH)
    assert res["verify7"]["results"]["V4_CHARPR_PRESERVED"] == "PASS"


# ── 7. parPrIDRef 무변경 (V5 PASS) ─────────────────────────────

@need_fx
def test_07_parpr_preserved_v5_pass(tmp_path):
    paras = _common_paragraphs()
    cmd = make_type_text_command(
        target=_target("p1"), paragraph=paras["p1"],
        caret_offset=1, insert_text="!",
        source_document_hash=SRC_HASH)
    out = tmp_path / "p_t07.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd], paragraphs_by_id=paras,
        source_document_hash=SRC_HASH)
    assert res["verify7"]["results"]["V5_PARPR_PRESERVED"] == "PASS"


# ── 8. expectedBefore mismatch ─────────────────────────────────

@need_fx
def test_08_expected_before_mismatch_rejected(tmp_path):
    paras = _common_paragraphs()
    cmd = make_replace_text_range_command(
        target=_target("p1"), paragraph=paras["p1"],
        range_anchor=0, range_focus=2, after_text="HI",
        source_document_hash=SRC_HASH)
    # paragraphs_by_id 의 p1 텍스트를 바꿔치기 → expectedBefore mismatch
    altered = {"p1": _make_para("p1",
                                                          [("p1_run0", "다른텍스트", "cp0")]),
                          "p2": paras["p2"]}
    out = tmp_path / "p_t08.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd], paragraphs_by_id=altered,
        source_document_hash=SRC_HASH)
    assert res["verdict"] == VERDICT_REJECTED
    reasons = [r["reason"] for r in res["rejected"]]
    assert REASON_EXPECTED_BEFORE_MISMATCH_PARAGRAPH in reasons


# ── 9. sourceDocumentHash mismatch ─────────────────────────────

@need_fx
def test_09_source_hash_mismatch_rejected(tmp_path):
    paras = _common_paragraphs()
    cmd = make_type_text_command(
        target=_target("p1"), paragraph=paras["p1"],
        caret_offset=0, insert_text="x",
        source_document_hash=SRC_HASH)
    out = tmp_path / "p_t09.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd], paragraphs_by_id=paras,
        source_document_hash="cafef00d" * 8)
    assert res["verdict"] == VERDICT_REJECTED
    reasons = [r["reason"] for r in res["rejected"]]
    assert REASON_SOURCE_HASH_MISMATCH in reasons


# ── 10. applied=∅ → REJECTED/FAIL ──────────────────────────────

@need_fx
def test_10_all_invalid_no_applied(tmp_path):
    paras = _common_paragraphs()
    # SET_CELL_TEXT 명령을 섞어서 모두 UNSUPPORTED_TYPE 으로 reject
    cmd = make_set_cell_text_command(
        cell_id="cell_t_s0_000_r0_c0", table_index=0,
        before="x", after="y", source_document_hash=SRC_HASH)
    out = tmp_path / "p_t10.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd], paragraphs_by_id=paras,
        source_document_hash=SRC_HASH)
    assert res["verdict"] in {VERDICT_REJECTED, VERDICT_FAIL}
    assert res["outputCreated"] is False
    reasons = [r["reason"] for r in res["rejected"]]
    assert REASON_UNSUPPORTED_TYPE in reasons


# ── 11. outputPath == sourcePath → REJECTED ────────────────────

@need_fx
def test_11_output_equals_source_rejected():
    paras = _common_paragraphs()
    cmd = make_type_text_command(
        target=_target("p1"), paragraph=paras["p1"],
        caret_offset=0, insert_text="x",
        source_document_hash=SRC_HASH)
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=FIXTURE,
        command_log=[cmd], paragraphs_by_id=paras,
        source_document_hash=SRC_HASH)
    assert res["verdict"] == VERDICT_REJECTED
    reasons = [r["reason"] for r in res["rejected"]]
    assert "OUTPUT_EQUALS_SOURCE" in reasons
    assert res["outputCreated"] is False


# ── 12. 원본 sha/mtime 무변경 ──────────────────────────────────

@need_fx
def test_12_source_sha_mtime_unchanged(tmp_path):
    paras = _common_paragraphs()
    before_sha = _sha(FIXTURE)
    before_mtime = FIXTURE.stat().st_mtime_ns
    cmd = make_type_text_command(
        target=_target("p1"), paragraph=paras["p1"],
        caret_offset=0, insert_text="X",
        source_document_hash=SRC_HASH)
    out = tmp_path / "p_t12.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd], paragraphs_by_id=paras,
        source_document_hash=SRC_HASH)
    assert _sha(FIXTURE) == before_sha
    assert FIXTURE.stat().st_mtime_ns == before_mtime
    assert res["sourceUnchanged"] is True


# ── 13. allow_writer=True → writer 본 실행 경로 진입 ──────────
# (WRITER-PARA-PLAN-01 활성화 이후) paragraph_edits 지원으로 더 이상
# BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT 게이트로 차단되지 않고, writer
# 본 실행 분기 (PASS / PARTIAL / FAIL — verify7 결과 의존) 로 진입한다.

@need_fx
def test_13_allow_writer_true_enters_writer_path(tmp_path):
    paras = _common_paragraphs()
    cmd = make_type_text_command(
        target=_target("p1"), paragraph=paras["p1"],
        caret_offset=0, insert_text="X",
        source_document_hash=SRC_HASH)
    out = tmp_path / "p_t13.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd], paragraphs_by_id=paras,
        source_document_hash=SRC_HASH, allow_writer=True)
    # 1) 더 이상 BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT 가 아니다
    assert res.get("blockReason") != BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT
    # 2) verdict 는 writer 본 실행 경로의 결과 집합 중 하나
    #    (가공 fixture 좌표는 실제 HWPX 와 일반적으로 매칭되지 않으므로
    #     FAIL/REJECTED/PARTIAL 가 정상, PASS 도 허용)
    assert res["verdict"] in {
        VERDICT_PASS, VERDICT_PARTIAL, VERDICT_FAIL, VERDICT_REJECTED,
    }
    # 3) 원본 sha/mtime 무손상 — 본 실행이라도 source 는 절대 건드리지 않음
    assert res["sourceUnchanged"] is True


# ── 14. audit log 적재 ─────────────────────────────────────────

@need_fx
def test_14_audit_log_appended(tmp_path):
    paras = _common_paragraphs()
    cmd = make_type_text_command(
        target=_target("p1"), paragraph=paras["p1"],
        caret_offset=0, insert_text="X",
        source_document_hash=SRC_HASH)
    out = tmp_path / "p_t14.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd], paragraphs_by_id=paras,
        source_document_hash=SRC_HASH)
    jsonl = tmp_path / "audit.jsonl"
    p = append_para_save_audit_record(
        save_result=res, command_log=[cmd],
        source_path=FIXTURE, output_path=out, jsonl_path=jsonl)
    assert p.is_file()
    text = jsonl.read_text(encoding="utf-8").strip()
    assert text
    import json as _json
    rec = _json.loads(text.splitlines()[0])
    assert rec["task"] == "WEB-OFFICE-PARA-EDIT-SAVE-VERIFY7-01"
    assert rec["partialCompletion"] is True
    assert rec["nextActivationTrigger"]


# ── 추가 게이트 ────────────────────────────────────────────────

def test_audit_script_returns_pass():
    out = run_audit()
    assert out["verdict"] == "PASS", out


def test_no_paragraph_writer_import_in_modules():
    """writer import 는 허용 allowlist 모듈에서만 가능.

    WRITER-PARA-PLAN-01 활성화 이후 paragraph_save_pipeline 은 writer
    분기 활성화를 위해 hwpx_edit_tool 을 (allow_writer 분기 내부에서만)
    import 한다. paragraph_writer_adapter 는 paragraph plan 자재 자체.
    그 외 plan/verify7/audit 모듈은 여전히 writer import 금지.
    """
    forbidden_files = (
        "scripts/hwpx/web_office/paragraph_edit_plan.py",
        "scripts/hwpx/web_office/paragraph_save_verify7.py",
        "scripts/hwpx/web_office/paragraph_save_audit.py",
    )
    for rel in forbidden_files:
        src = (PR / rel).read_text(encoding="utf-8")
        assert "hwpx_edit_tool" not in src, rel
        assert "apply_edit_plan" not in src, rel


def test_cell_save_pipeline_untouched():
    src = (PR / "scripts/hwpx/web_office/"
                              "cell_save_pipeline.py").read_text(encoding="utf-8")
    # MVP-A 회로 핵심 토큰 무손상
    assert "save_cell_edits" in src
    assert "verify7" in src


def test_noop_when_empty_command_log(tmp_path):
    """commandLog 비어있으면 NOOP."""
    if FIXTURE is None:
        pytest.skip("fixture missing")
    out = tmp_path / "p_noop.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[], paragraphs_by_id=_common_paragraphs(),
        source_document_hash=SRC_HASH)
    assert res["verdict"] == VERDICT_NOOP
    assert res["outputCreated"] is False
