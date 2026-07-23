"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-CLOSEOUT-01 준공검사.

ApplyFormat (existing charPr) 부분 준공 동결의 정적 검증.
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))

CLOSEOUT_DOC = (PR / "docs/architecture/"
                   "web_office_para_edit_applyformat_existing_charpr_closeout.md")
# 좌표조회 수리 준공 후 갱신 (334d665 → b9782a5) — ro_view_importer._find_cell_elem
# 이 셀 문단을 격자주소가 아닌 셀 순번으로 찾도록 교정.
# 셀 텍스트 손실·중첩 표 중복 수리 준공 후 재갱신 (b9782a5 → 3f94c2a) —
# hp:t 인라인 tail 유실 + 중첩 표 내용 중복 제거. 정당 변경 확인 후 재고정.
BASELINE_COMMIT = "6111a9e"  # lineseg 보존 로직 준공 후 갱신 (517849c -> 6111a9e)

REQUIRED_DOC_PHRASES_IN_SCOPE = [
    "CT_APPLY_FORMAT", "make_apply_format_command",
    "apply_charpr_to_range_existing",
    "single-run", "multi-run", "full-run", "partial-run",
    "cell", "block",
    "paragraph.text 무변경",
    "header.xml 무변경",
    "신규 charPr 생성",
    "TARGET_CHARPR_NOT_IN_HEADER",
    "V1_RANGE_POSITION_OK", "V2_NO_CROSS_PARAGRAPH_LEAK",
    "V3_UNTOUCHED_RUNS_PRESERVED", "V4_CHARPR_PRESERVED",
    "V5_PARPR_PRESERVED", "V6_OUTPUT_ISOLATED",
    "V7_READBACK_MATCH",
    "OUTPUT_EQUALS_SOURCE", "UNSAFE_RUN_CHILDREN",
    "EMPTY_RANGE", "sourceDocumentHash",
    "beforeSegments", "restoreSegments",
]
REQUIRED_DOC_PHRASES_OUT_OF_SCOPE = [
    "toolbar UI 완성",
    "bold/italic/color/fontSize",
    "paragraph add/delete",
    "table structure",
    "image/stamp/signature",
    "AI 자동 입력",
    "원본 HWPX 직접 수정",
    "POLICY_CARET_RIGHT",
    "문서 전체 스타일 일괄 변경",
]

# 97c4095 ApplyFormat 시공 자재 — 본 closeout 시점에 무수정
LOCKED_FILES_VS_BASELINE = [
    "scripts/hwpx/hwpx_paragraph_ops.py",
    "scripts/hwpx/hwpx_edit_tool.py",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    "scripts/hwpx/web_office/charpr_inventory.py",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01:
    # para_edit_command.mjs (_applyFormat / _applyFormatInverse) 와
    # para_edit_state.mjs (applyFormatToSelection) 는 본 LOCKED 에서 제거됨.
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]

# 회귀 자재 (테스트 파일) — 모두 존재해야 한다
REQUIRED_TESTS = [
    "tests/test_web_office_para_edit_applyformat_existing_charpr.py",
    "tests/test_web_office_para_edit_format_charpr_inventory.py",
    "tests/test_web_office_para_edit_content_closeout.py",
    "tests/test_web_office_para_edit_e2e_full_closeout.py",
    "tests/test_web_office_para_type_text_contract.py",
    "tests/test_web_office_para_edit_e2e_integration.py",
    "tests/test_web_office_para_edit_model.py",
    "tests/test_web_office_para_adapter_applycharpr.py",
    "tests/test_web_office_para_readback_parser.py",
    "tests/test_web_office_para_edit_save_verify7.py",
    "tests/test_web_office_para_edit_container_scope_bridge.py",
    "tests/test_web_office_writer_para_plan.py",
    "tests/test_web_office_para_edit_ime_live.py",
    "tests/test_web_office_body_paragraph_writer.py",
    "tests/test_web_office_para_edit_multi_run.py",
    "tests/test_web_office_para_edit_type_multi_run.py",
]

# 차단 범위가 코드에 우발 활성화된 흔적 없음
FORBIDDEN_SOURCE_PATTERNS = [
    (r"def\s+create_char_pr\b", "신규 charPr 생성 함수 우발 도입"),
    (r"def\s+apply_paragraph_add\b", "paragraph add 함수 우발 도입"),
    (r"def\s+apply_paragraph_delete\b", "paragraph delete 함수 우발 도입"),
    (r"def\s+add_table_row\b", "table row add 함수 우발 도입"),
    (r"def\s+delete_table_row\b", "table row delete 함수 우발 도입"),
    (r"def\s+insert_image\b", "image insert 함수 우발 도입"),
    (r"POLICY_CARET_RIGHT", "POLICY_CARET_RIGHT enum 우발 도입"),
    (r"package\.entries\[[^\]]*header\.xml[^\]]*\]\s*=",
      "header.xml write 경로 우발 도입"),
]
FORBIDDEN_SCAN_TARGETS = [
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/hwpx_paragraph_ops.py",
    "scripts/hwpx/web_office/charpr_inventory.py",
]

# APPLY_FORMAT 활성화 신호 (정적 잠금)
REQUIRED_SOURCE_PATTERNS = [
    (PR / "scripts/hwpx/web_office/para_edit_model.py",
      [r"CT_APPLY_FORMAT\s*=", r"def\s+make_apply_format_command\("]),
    (PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py",
      [r'"APPLY_FORMAT"', r"apply_charpr_to_range_existing\(",
        r"REASON_TARGET_CHARPR_NOT_IN_HEADER",
        r"_read_header_char_pr_ids\("]),
    (PR / "scripts/hwpx/hwpx_paragraph_ops.py",
      [r"def\s+apply_charpr_to_range_existing\(",
        r"STATUS_TARGET_CHARPR_NOT_IN_HEADER"]),
    (PR / "frontend/web_office_viewer/para_edit_command.mjs",
      [r"CT_APPLY_FORMAT", r"makeApplyFormatCommand"]),
]

FORBIDDEN_AUDIT_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
    r"\.write_xml\(",
]


def _check_required_doc() -> list[dict]:
    findings: list[dict] = []
    if not CLOSEOUT_DOC.is_file():
        findings.append({"code": "MISSING_DOC", "level": "FAIL",
                          "detail": str(CLOSEOUT_DOC.relative_to(PR))})
        return findings
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in REQUIRED_DOC_PHRASES_IN_SCOPE:
        if phrase not in src:
            findings.append({"code": "DOC_IN_SCOPE_PHRASE_MISSING",
                              "level": "FAIL", "detail": phrase})
    for phrase in REQUIRED_DOC_PHRASES_OUT_OF_SCOPE:
        if phrase not in src:
            findings.append({"code": "DOC_OUT_OF_SCOPE_PHRASE_MISSING",
                              "level": "FAIL", "detail": phrase})
    if BASELINE_COMMIT not in src:
        findings.append({"code": "DOC_BASELINE_MISSING",
                          "level": "FAIL",
                          "detail": f"baseline {BASELINE_COMMIT}"})
    # 회귀 자재 파일명이 closeout 문서에 인용됐는지
    for rel in REQUIRED_TESTS:
        name = Path(rel).name
        if name not in src:
            findings.append({"code": "DOC_TEST_FILE_NOT_LISTED",
                              "level": "FAIL", "detail": name})
    return findings


def _check_required_tests() -> list[dict]:
    findings: list[dict] = []
    for rel in REQUIRED_TESTS:
        if not (PR / rel).is_file():
            findings.append({"code": "MISSING_TEST", "level": "FAIL",
                              "detail": rel})
    return findings


def _check_locked_files() -> list[dict]:
    findings: list[dict] = []
    for rel in LOCKED_FILES_VS_BASELINE:
        try:
            r = subprocess.run(
                ["git", "diff", BASELINE_COMMIT, "--", rel],
                capture_output=True, text=True, cwd=str(PR), timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            findings.append({"code": "GIT_DIFF_FAILED", "level": "WARN",
                              "detail": f"{rel}: {e}"})
            continue
        if r.returncode != 0:
            findings.append({"code": "GIT_DIFF_RC", "level": "WARN",
                              "detail": f"{rel}: rc={r.returncode}"})
            continue
        if r.stdout.strip():
            findings.append({"code": "LOCKED_FILE_CHANGED",
                              "level": "FAIL", "detail": rel})
    return findings


def _check_required_source_patterns() -> list[dict]:
    findings: list[dict] = []
    for path, patterns in REQUIRED_SOURCE_PATTERNS:
        if not path.is_file():
            findings.append({"code": "SOURCE_MISSING", "level": "FAIL",
                              "detail": str(path.relative_to(PR))})
            continue
        src = path.read_text(encoding="utf-8")
        for pat in patterns:
            if not re.search(pat, src):
                findings.append({"code": "REQUIRED_PATTERN_MISSING",
                                  "level": "FAIL",
                                  "detail":
                                      f"{path.relative_to(PR)}: {pat}"})
    return findings


def _check_forbidden_source_patterns() -> list[dict]:
    findings: list[dict] = []
    for rel in FORBIDDEN_SCAN_TARGETS:
        p = PR / rel
        if not p.is_file():
            continue
        src = p.read_text(encoding="utf-8")
        for pat, label in FORBIDDEN_SOURCE_PATTERNS:
            if re.search(pat, src):
                findings.append({"code": "FORBIDDEN_PATTERN_PRESENT",
                                  "level": "FAIL",
                                  "detail":
                                      f"{rel}: {label} ({pat})"})
    return findings


def _check_audit_no_writer_calls() -> list[dict]:
    findings: list[dict] = []
    me = Path(__file__).read_text(encoding="utf-8")
    for sym in FORBIDDEN_AUDIT_WRITER_SYMBOLS:
        if re.search(sym, me):
            findings.append({"code": "AUDIT_FORBIDDEN_WRITER_CALL",
                              "level": "FAIL", "detail": sym})
    return findings


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_required_doc())
    findings.extend(_check_required_tests())
    findings.extend(_check_locked_files())
    findings.extend(_check_required_source_patterns())
    findings.extend(_check_forbidden_source_patterns())
    findings.extend(_check_audit_no_writer_calls())
    fail = [f for f in findings if f["level"] == "FAIL"]
    warn = [f for f in findings if f["level"] == "WARN"]
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-APPLYFORMAT-"
                          "EXISTING-CHARPR-CLOSEOUT-01",
        "baseline": BASELINE_COMMIT,
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
