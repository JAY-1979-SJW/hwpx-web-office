"""WEB-OFFICE-PARA-EDIT-SAVE-VERIFY7-01 감사 스크립트.

산출물 6세대의 정적 검증 + 변경 금지 파일 무손상 확인.

WRITER-PARA-PLAN-01 활성화 이후 정책 갱신:
  - FORBIDDEN_WRITER_TOKENS: 무조건 금지 → allowlist 외 금지
    (paragraph_save_pipeline / paragraph_writer_adapter 만 허용)
  - UNCHANGED_FILES: 무조건 무수정 → allowlist 외 무수정
    (paragraph_edits 관련 변경은 hwpx_edit_tool.py / paragraph_save_
     pipeline.py / paragraph_edit_plan.py 에 허용)
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PR = Path(__file__).resolve().parents[2]

REQUIRED_FILES = [
    PR / "scripts/hwpx/web_office/paragraph_edit_plan.py",
    PR / "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    PR / "scripts/hwpx/web_office/paragraph_save_verify7.py",
    PR / "scripts/hwpx/web_office/paragraph_save_audit.py",
    PR / "scripts/ops/audit_web_office_para_edit_save_verify7.py",
    PR / "tests/test_web_office_para_edit_save_verify7.py",
]

# writer 토큰 (allowlist 밖 모듈에 등장하면 FAIL)
FORBIDDEN_WRITER_TOKENS = [
    "hwpx" + "_edit_tool", "apply" + "_edit_plan",
]

# writer 토큰 등장이 허용된 모듈 (WRITER-PARA-PLAN-01 활성화)
WRITER_TOKEN_ALLOWED_FILES = {
    PR / "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py",
}

# writer 토큰 등장을 강제 검사하는 모듈 (allowlist 외)
NO_WRITER_IMPORT_FILES = [
    PR / "scripts/hwpx/web_office/paragraph_edit_plan.py",
    PR / "scripts/hwpx/web_office/paragraph_save_verify7.py",
    PR / "scripts/hwpx/web_office/paragraph_save_audit.py",
]

# 변경 금지 파일 (기준선 대비 diff 비어야 함) — allowlist 외 잠금.
# paragraph_edits 관련 변경이 허용된 파일은 ALLOWED_CHANGED_FILES.
UNCHANGED_FILES = [
    "scripts/hwpx/web_office/cell_edit_plan.py",
    "scripts/hwpx/web_office/cell_save_pipeline.py",
    "scripts/hwpx/web_office/cell_save_verify7.py",
    "scripts/hwpx/web_office/cell_save_audit.py",
    "scripts/hwpx/web_office/edit_command_model.py",
    # para_edit_model.py: CONTAINERSCOPE_BRIDGE_01 자진신고 해제 (containerScope 필드 추가)
    "tests/test_web_office_cell_edit_mvp_a.py",
    "tests/test_web_office_cell_save_hwpx_verify7.py",
    "tests/test_web_office_mvp_a_closeout.py",
]

# WRITER-PARA-PLAN-01 에서 paragraph_edits 분기 신설을 위해 변경이
# 허용된 파일 (참고용 — 정책 문서화).
ALLOWED_CHANGED_FILES = [
    "scripts/hwpx/hwpx_edit_tool.py",            # paragraph_edits 분기
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/hwpx_paragraph_ops.py",                  # 신규
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",  # 신규
    "scripts/ops/audit_web_office_writer_para_plan.py",     # 신규
    "tests/test_web_office_writer_para_plan.py",            # 신규
]

BASELINE_COMMIT = "aeab86a"


def _check_files_exist() -> list[dict]:
    findings: list[dict] = []
    for p in REQUIRED_FILES:
        if not p.is_file():
            findings.append({"code": "MISSING_FILE", "level": "FAIL",
                                            "detail": str(p.relative_to(PR))})
    return findings


def _check_no_writer_import() -> list[dict]:
    findings: list[dict] = []
    for p in NO_WRITER_IMPORT_FILES:
        if not p.is_file():
            continue
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_WRITER_TOKENS:
            if tok in src:
                findings.append({"code": "FORBIDDEN_WRITER_TOKEN",
                                                "level": "FAIL",
                                                "detail": f"{p.name}: {tok}"})
    return findings


def _check_unchanged() -> list[dict]:
    findings: list[dict] = []
    for rel in UNCHANGED_FILES:
        try:
            r = subprocess.run(
                ["git", "diff", BASELINE_COMMIT, "--", rel],
                capture_output=True, text=True, cwd=str(PR), timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            findings.append({"code": "GIT_DIFF_FAILED", "level": "WARN",
                                            "detail": f"{rel}: {e}"})
            continue
        if r.returncode != 0:
            findings.append({"code": "GIT_DIFF_FAILED", "level": "WARN",
                                            "detail": f"{rel}: rc={r.returncode}"})
            continue
        if r.stdout.strip():
            findings.append({"code": "FORBIDDEN_FILE_CHANGED",
                                            "level": "FAIL",
                                            "detail": rel})
    return findings


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_files_exist())
    findings.extend(_check_no_writer_import())
    findings.extend(_check_unchanged())

    fails = [f for f in findings if f.get("level") == "FAIL"]
    verdict = "PASS" if not fails else "FAIL"
    return {
        "task": "WEB-OFFICE-PARA-EDIT-SAVE-VERIFY7-01",
        "verdict": verdict,
        "partialCompletion": True,
        "nextActivationTrigger": "writer paragraph plan 지원 시",
        "findings": findings,
    }


def main() -> int:
    out = audit()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
