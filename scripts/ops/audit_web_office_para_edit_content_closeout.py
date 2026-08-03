"""WEB-OFFICE-PARA-EDIT-CONTENT-CLOSEOUT-01 준공검사.

PARA-EDIT 내용 편집 3종 (TYPE_TEXT / REPLACE_TEXT_RANGE /
DELETE_TEXT_RANGE) × (cell / body) × (single-run / multi-run) 전 범위
부분 준공 동결의 정적 검증.

본 audit 는 새로운 HWPX output 을 만들지 않고, 회귀 자재의 존재 +
시방서 등기 문구 + 차단 범위 흔적 없음만 정적으로 검증한다.
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
                   "web_office_para_edit_content_closeout.md")
# 좌표조회 수리 준공 후 갱신 (334d665 → b9782a5) — ro_view_importer._find_cell_elem
# 이 셀 문단을 격자주소가 아닌 셀 순번으로 찾도록 교정.
# 셀 텍스트 손실·중첩 표 중복 수리 준공 후 재갱신 (b9782a5 → 3f94c2a) —
# hp:t 인라인 tail 유실 + 중첩 표 내용 중복 제거. 정당 변경 확인 후 재고정.
BASELINE_COMMIT = "cbe8cce"  # WebOfficeCell.tableIndex 계약 필드 준공 후 갱신 (b992ad6 → cbe8cce)

# 회귀 자재 (테스트 파일) — 모두 존재해야 한다.
REQUIRED_TESTS = [
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

# 시공 자재 — 모두 존재해야 한다.
REQUIRED_SOURCES = [
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    "scripts/hwpx/hwpx_paragraph_ops.py",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01:
    # para_edit_state.mjs / para_edit_command.mjs 본 LOCKED 에서 제거.
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]

# 본 commit 이후 무수정 잠금. WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-
# CHARPR-01: ApplyFormat 활성화 트리거로 para_edit_model /
# paragraph_edit_plan / paragraph_writer_adapter / paragraph_save_verify7
# / para_edit_e2e_pipeline / hwpx_paragraph_ops 는 본 LOCKED 에서 제거됨
# (허용 범위: APPLY_FORMAT command + run charPr 교체 primitive 한정).
LOCKED_FILES_VS_BASELINE = [
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01:
    # para_edit_state.mjs (applyFormatToSelection) 와 para_edit_command.mjs
    # (_applyFormat) 는 본 LOCKED 에서 제거.
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]

# 시방서 문구 — 완료/차단 범위 명시 잠금
DOC_REQUIRED_PHRASES_IN_SCOPE = [
    "SET_CELL_TEXT", "TYPE_TEXT",
    "REPLACE_TEXT_RANGE", "DELETE_TEXT_RANGE",
    "single-run cell", "single-run body",
    "multi-run cell", "multi-run body",
    "V1_RANGE_POSITION_OK", "V2_NO_CROSS_PARAGRAPH_LEAK",
    "V3_UNTOUCHED_RUNS_PRESERVED", "V4_CHARPR_PRESERVED",
    "V5_PARPR_PRESERVED", "V6_OUTPUT_ISOLATED",
    "V7_READBACK_MATCH",
    "IME", "compositionend",
    "POLICY_ANCHOR_CHARPR", "POLICY_FOCUS_CHARPR",
    "POLICY_REQUIRES_REVIEW",
    "OUTPUT_EQUALS_SOURCE", "UNSAFE_RUN_CHILDREN",
    "NEW_CHARPR_INTRODUCED",
]
DOC_REQUIRED_PHRASES_OUT_OF_SCOPE = [
    "ApplyFormat", "paragraph add / delete",
    "table structure", "image / stamp / signature",
    "AI 자동 입력", "원본 HWPX 직접 수정",
    "POLICY_CARET_RIGHT",
]

# 차단 범위가 코드에 우발 활성화된 흔적 없음 (정적 grep)
FORBIDDEN_SOURCE_PATTERNS = [
    (r"def\s+apply_paragraph_add\b", "paragraph add 함수 우발 도입"),
    (r"def\s+apply_paragraph_delete\b", "paragraph delete 함수 우발 도입"),
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01:
    # APPLY_FORMAT 활성화 — apply_format / make_apply_format_command 패턴
    # 차단 해제. create_char_pr (신규 charPr 생성) 는 여전히 차단.
    (r"def\s+create_char_pr\b", "신규 charPr 생성 함수 우발 도입"),
    (r"def\s+add_table_row\b", "table row add 함수 우발 도입"),
    (r"def\s+delete_table_row\b", "table row delete 함수 우발 도입"),
    (r"def\s+insert_image\b", "image insert 함수 우발 도입"),
    (r"POLICY_CARET_RIGHT", "POLICY_CARET_RIGHT enum 우발 도입"),
]
FORBIDDEN_SCAN_TARGETS = [
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/hwpx_paragraph_ops.py",
]

FORBIDDEN_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
]


def _check_required_doc() -> list[dict]:
    findings: list[dict] = []
    if not CLOSEOUT_DOC.is_file():
        findings.append({"code": "MISSING_DOC", "level": "FAIL",
                          "detail": str(CLOSEOUT_DOC.relative_to(PR))})
        return findings
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in DOC_REQUIRED_PHRASES_IN_SCOPE:
        if phrase not in src:
            findings.append({"code": "DOC_IN_SCOPE_PHRASE_MISSING",
                              "level": "FAIL", "detail": phrase})
    for phrase in DOC_REQUIRED_PHRASES_OUT_OF_SCOPE:
        if phrase not in src:
            findings.append({"code": "DOC_OUT_OF_SCOPE_PHRASE_MISSING",
                              "level": "FAIL", "detail": phrase})
    if BASELINE_COMMIT not in src:
        findings.append({"code": "DOC_BASELINE_MISSING",
                          "level": "FAIL",
                          "detail": (f"closeout doc 에 baseline "
                                            f"{BASELINE_COMMIT} 미명시")})
    return findings


def _check_required_files() -> list[dict]:
    findings: list[dict] = []
    for rel in REQUIRED_TESTS:
        p = PR / rel
        if not p.is_file():
            findings.append({"code": "MISSING_TEST", "level": "FAIL",
                              "detail": rel})
    for rel in REQUIRED_SOURCES:
        p = PR / rel
        if not p.is_file():
            findings.append({"code": "MISSING_SOURCE", "level": "FAIL",
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


def _check_forbidden_features() -> list[dict]:
    findings: list[dict] = []
    for rel in FORBIDDEN_SCAN_TARGETS:
        p = PR / rel
        if not p.is_file():
            continue
        src = p.read_text(encoding="utf-8")
        for pat, label in FORBIDDEN_SOURCE_PATTERNS:
            if re.search(pat, src):
                findings.append({"code": "FORBIDDEN_FEATURE_PRESENT",
                                  "level": "FAIL",
                                  "detail": f"{rel}: {label} ({pat})"})
    return findings


def _check_audit_no_writer_calls() -> list[dict]:
    findings: list[dict] = []
    me = Path(__file__).read_text(encoding="utf-8")
    for sym in FORBIDDEN_WRITER_SYMBOLS:
        if re.search(sym, me):
            findings.append({"code": "AUDIT_FORBIDDEN_WRITER_CALL",
                              "level": "FAIL", "detail": sym})
    return findings


# 핵심 회귀 테스트 파일에 multi-run / IME 시나리오 함수가 실제로
# 정의되어 있는지 정적 grep
COVERAGE_PROBES = {
    "tests/test_web_office_para_edit_multi_run.py": [
        r"def\s+test_cell_multi_run_replace",
        r"def\s+test_cell_multi_run_delete",
        r"def\s+test_body_multi_run_replace",
        r"def\s+test_body_multi_run_delete",
    ],
    "tests/test_web_office_para_edit_type_multi_run.py": [
        r"def\s+test_cell_multi_run_type_text_inside_r1",
        r"def\s+test_cell_multi_run_type_text_boundary",
        r"def\s+test_cell_multi_run_type_text_paragraph_end",
        r"def\s+test_body_multi_run_type_text_inside_r1",
    ],
    "tests/test_web_office_para_edit_ime_live.py": [
        r"def\s+test_composition_end_creates_single_type_text",
        r"def\s+test_type_text_contract_aligned",
    ],
    "tests/test_web_office_body_paragraph_writer.py": [
        r"def\s+test_body_type_text_v1_to_v7",
        r"def\s+test_body_replace_text_range_v1_to_v7",
        r"def\s+test_body_delete_text_range_v1_to_v7",
    ],
    "tests/test_web_office_para_edit_e2e_full_closeout.py": [
        r"def\s+test_all_three_scenarios_v1_to_v7_pass",
    ],
}


def _check_coverage_probes() -> list[dict]:
    findings: list[dict] = []
    for rel, patterns in COVERAGE_PROBES.items():
        p = PR / rel
        if not p.is_file():
            findings.append({"code": "COVERAGE_FILE_MISSING",
                              "level": "FAIL", "detail": rel})
            continue
        src = p.read_text(encoding="utf-8")
        for pat in patterns:
            if not re.search(pat, src):
                findings.append({"code": "COVERAGE_PROBE_MISSING",
                                  "level": "FAIL",
                                  "detail": f"{rel}: {pat}"})
    return findings


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_required_doc())
    findings.extend(_check_required_files())
    findings.extend(_check_locked_files())
    findings.extend(_check_forbidden_features())
    findings.extend(_check_coverage_probes())
    findings.extend(_check_audit_no_writer_calls())
    fail = [f for f in findings if f["level"] == "FAIL"]
    warn = [f for f in findings if f["level"] == "WARN"]
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-CONTENT-CLOSEOUT-01",
        "baseline": BASELINE_COMMIT,
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
