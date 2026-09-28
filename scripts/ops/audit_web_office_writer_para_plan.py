"""감리 — WRITER-PARA-PLAN-01 정적/동적 게이트.

- KNOWN_PLAN_KEYS 에 paragraph_edits 존재
- hwpx_edit_tool 에 paragraph_edits dispatch 존재
- hwpx_paragraph_ops / paragraph_writer_adapter 존재 + 핵심 export
- 변경 금지 파일들 baseline (295a8a3) 대비 무수정
- adapter / ops 가 cell mutation primitive (set_table_cell_text 등) 를
  호출하지 않음 (정적 grep)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_PR = Path(__file__).resolve().parents[2]


_LOCKED = [
    "scripts/hwpx/hwpx_table_ops.py",
    "scripts/hwpx/hwpx_writer_adapter.py",
    "scripts/hwpx/hwpx_package.py",
    "scripts/hwpx/web_office/cell_edit_plan.py",
    "scripts/hwpx/web_office/cell_save_pipeline.py",
    "scripts/hwpx/web_office/cell_save_verify7.py",
    "scripts/hwpx/web_office/cell_save_audit.py",
    "scripts/hwpx/web_office/edit_command_model.py",
    # para_edit_model.py: CONTAINERSCOPE_BRIDGE_01 자진신고 해제 (containerScope 필드 추가)
    "scripts/hwpx/web_office/para_edit_normalizer.py",
]
_BASELINE = "295a8a3"


def _check_known_plan_keys(edit_tool: str) -> list[dict]:
    findings: list[dict] = []
    if '"paragraph_edits"' not in edit_tool:
        findings.append({
            "code": "KNOWN_PLAN_KEYS_MISSING",
            "detail": "paragraph_edits not in KNOWN_PLAN_KEYS",
        })
    if "apply_paragraph_edits_plan" not in edit_tool:
        findings.append({
            "code": "DISPATCH_MISSING",
            "detail": "apply_paragraph_edits_plan not imported",
        })
    return findings


def _check_module_exports() -> tuple[list[dict], str, str]:
    findings: list[dict] = []
    for rel in (
        "scripts/hwpx/hwpx_paragraph_ops.py",
        "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    ):
        if not (_PR / rel).is_file():
            findings.append({"code": "MODULE_MISSING", "path": rel})

    ops_src = (
        (_PR / "scripts/hwpx/hwpx_paragraph_ops.py").read_text(encoding="utf-8")
        if (_PR / "scripts/hwpx/hwpx_paragraph_ops.py").is_file()
        else ""
    )
    for sym in (
        "find_paragraph_in_cell",
        "find_run_in_paragraph",
        "paragraph_text",
        "run_text",
        "apply_text_range_edit",
    ):
        if f"def {sym}" not in ops_src:
            findings.append({"code": "OPS_EXPORT_MISSING", "symbol": sym})

    adapter_src = (
        (_PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py").read_text(encoding="utf-8")
        if (_PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py").is_file()
        else ""
    )
    if "def apply_paragraph_edits_plan" not in adapter_src:
        findings.append({"code": "ADAPTER_EXPORT_MISSING", "symbol": "apply_paragraph_edits_plan"})
    return findings, ops_src, adapter_src


def _check_forbidden_cell_mutation(adapter_src: str, ops_src: str) -> list[dict]:
    findings: list[dict] = []
    forbidden = (
        "set_table_cell_text(",
        "editor.set_table",
        "set_cell_single_text(",
        "set_table_visual_cell_text(",
    )
    for src_name, src in (("adapter", adapter_src), ("ops", ops_src)):
        for f in forbidden:
            if f in src:
                findings.append({
                    "code": "FORBIDDEN_CELL_MUTATION_CALL",
                    "module": src_name,
                    "symbol": f,
                })
    return findings


def _check_locked_files_unchanged() -> list[dict]:
    findings: list[dict] = []
    for rel in _LOCKED:
        try:
            out = subprocess.run(
                ["git", "diff", _BASELINE, "--", rel],
                cwd=_PR,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if out.stdout.strip():
                findings.append({
                    "code": "LOCKED_FILE_TOUCHED",
                    "path": rel,
                    "diff_lines": len(out.stdout.splitlines()),
                })
        except (OSError, FileNotFoundError) as e:
            findings.append({"code": "GIT_DIFF_UNAVAILABLE", "path": rel, "detail": str(e)})
    return findings


def _check_pipeline_writer_activated() -> list[dict]:
    # pipeline 차단 분기 해제 — BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT
    # 가 allow_writer 분기 본문에서 제거되었는지 확인
    pipe_src = (_PR / "scripts/hwpx/web_office/paragraph_save_pipeline.py").read_text(
        encoding="utf-8"
    )
    if "writer paragraph_edits 본 실행" not in pipe_src:
        return [{"code": "PIPELINE_WRITER_NOT_ACTIVATED"}]
    return []


def audit() -> dict:
    findings: list[dict] = []

    edit_tool = (_PR / "scripts/hwpx/hwpx_edit_tool.py").read_text(encoding="utf-8")
    findings.extend(_check_known_plan_keys(edit_tool))

    module_findings, ops_src, adapter_src = _check_module_exports()
    findings.extend(module_findings)

    findings.extend(_check_forbidden_cell_mutation(adapter_src, ops_src))
    findings.extend(_check_locked_files_unchanged())
    findings.extend(_check_pipeline_writer_activated())

    verdict = "PASS" if not findings else "FAIL"
    return {"verdict": verdict, "findings": findings, "baseline": _BASELINE, "lockedFiles": _LOCKED}


def main() -> int:
    rep = audit()
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
