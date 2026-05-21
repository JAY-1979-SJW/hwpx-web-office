"""CELL-SAVE 파이프라인.

commandLog → dry-run plan → apply_edit_plan(dry_run=True) → LOCK_01
필터 → verify7 게이트 → PASS 시에만 본 실행 → readback 감사.

본 모듈에서만 hwpx_edit_tool 을 import 한다 (CELL-EDIT MVP-A 모듈은
import 하지 않음 — 책임 분리).
"""
from __future__ import annotations
import hashlib
import sys
from pathlib import Path
from typing import Any

_PR = Path(__file__).resolve().parents[3]
if str(_PR) not in sys.path:
    sys.path.insert(0, str(_PR))
if str(_PR / "scripts/hwpx") not in sys.path:
    sys.path.insert(0, str(_PR / "scripts/hwpx"))

from scripts.hwpx import hwpx_edit_tool as _edit_tool  # noqa: E402
from scripts.ops.claude_inline_full_integration_demo import (  # noqa: E402
    _filter_applied_cells_by_coord, _summarize_apply_text,
)
from .edit_command_model import EditCommand  # noqa: E402
from .cell_edit_plan import (  # noqa: E402
    build_dry_run_edit_plan, SAVE_DRY_RUN_NOOP, SAVE_DRY_RUN_REJECTED,
    SAVE_DRY_RUN_READY,
)
from .ro_view_importer import import_hwpx_as_ro_view  # noqa: E402
from .cell_save_verify7 import verify7  # noqa: E402


VERDICT_PASS = "PASS"
VERDICT_PARTIAL = "PARTIAL"
VERDICT_FAIL = "FAIL"
VERDICT_REJECTED = "REJECTED"
VERDICT_NOOP = "NOOP"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save_cell_edits(
    *, source_path: Path, output_path: Path,
    command_log: list[EditCommand],
    project_root: Path = _PR,
    dry_run_only: bool = False,
) -> dict[str, Any]:
    """commandLog 를 안전 게이트를 거쳐 sandbox output 으로 산출.

    Returns
    -------
    dict with keys:
        verdict       : PASS / PARTIAL / FAIL / REJECTED / NOOP
        dryRun        : 본 실행 여부 (dry_run_only=True 면 항상 True)
        accepted      : applied EditCommand 목록 (좌표 매칭 통과)
        rejected      : reasons[]
        verify7       : dict (verdict + V1~V7 + findings) or None
        sourceHashBefore / After / Unchanged
        outputCreated : bool
        outputHash    : str | None
        notes         : list[str]
    """
    notes: list[str] = []
    source_path = Path(source_path)
    output_path = Path(output_path)

    # 입력 안전 게이트 — outputPath != sourcePath, sandbox 하위
    if output_path.resolve() == source_path.resolve():
        return {"verdict": VERDICT_REJECTED,
                    "dryRun": True,
                    "rejected": [{"reason": "OUTPUT_EQUALS_SOURCE",
                                            "detail": str(source_path)}],
                    "notes": ["outputPath == sourcePath — 본 실행 차단"]}

    if not source_path.is_file():
        return {"verdict": VERDICT_REJECTED,
                    "dryRun": True,
                    "rejected": [{"reason": "SOURCE_MISSING"}]}

    source_sha_before = _sha(source_path)
    source_mtime_before = source_path.stat().st_mtime_ns

    # 1) DocumentModel 빌드 (read-only)
    doc = import_hwpx_as_ro_view(source_path)
    doc_dict = {
        "cells": [{"cellId": c.cellId, "text": c.text} for c in doc.cells],
    }
    pre_save_cell_texts = {c.cellId: c.text for c in doc.cells}

    # 2) dry-run plan (CELL-EDIT MVP-A 게이트)
    plan_result = build_dry_run_edit_plan(
        command_log, doc_dict, source_sha_before)

    if plan_result["status"] == SAVE_DRY_RUN_NOOP:
        return {"verdict": VERDICT_NOOP,
                    "dryRun": True,
                    "rejected": [],
                    "accepted": [],
                    "sourceHashBefore": source_sha_before,
                    "sourceHashAfter": source_sha_before,
                    "sourceUnchanged": True,
                    "outputCreated": False,
                    "notes": ["commandLog empty"]}

    if plan_result["status"] == SAVE_DRY_RUN_REJECTED:
        return {"verdict": VERDICT_REJECTED,
                    "dryRun": True,
                    "rejected": plan_result.get("rejected", []),
                    "accepted": [],
                    "sourceHashBefore": source_sha_before,
                    "sourceHashAfter": _sha(source_path),
                    "sourceUnchanged": _sha(source_path) == source_sha_before,
                    "outputCreated": False,
                    "notes": ["plan REJECTED at MVP-A gate"]}

    assert plan_result["status"] == SAVE_DRY_RUN_READY
    plan = plan_result["plan"]

    # 3) apply_edit_plan dry-run — operations 시뮬레이션
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dry = _edit_tool.apply_edit_plan(
        source_path, output_path, plan, dry_run=True)
    set_cells = plan["set_cells"]
    applied_cells, rejected_cells = _filter_applied_cells_by_coord(
        set_cells, dry.get("operations", []))
    summary_dry = _summarize_apply_text(
        set_cells, applied_cells, rejected_cells)

    # applied=∅ → 본 실행 차단 (vacuous PASS 방지)
    if not applied_cells:
        return {"verdict": VERDICT_FAIL,
                    "dryRun": True,
                    "rejected": [{"reason": "DRY_RUN_NO_APPLIED",
                                            "summary": summary_dry,
                                            "details": rejected_cells}],
                    "accepted": [],
                    "sourceHashBefore": source_sha_before,
                    "sourceHashAfter": _sha(source_path),
                    "sourceUnchanged": _sha(source_path) == source_sha_before,
                    "outputCreated": False,
                    "notes": ["dry-run produced 0 applied — writer 본 실행 차단"]}

    # 좌표 → EditCommand 매핑 (accepted commands 만 verify7 입력으로)
    coord_to_cmd: dict[tuple[int, int, int], EditCommand] = {}
    for cmd in command_log:
        sc = cmd.forward["set_cells"][0]
        coord_to_cmd[(sc["table"], sc["row"], sc["col"])] = cmd
    accepted_commands = [
        coord_to_cmd[(sc["table"], sc["row"], sc["col"])]
        for sc in applied_cells if (sc["table"], sc["row"], sc["col"])
                                                  in coord_to_cmd]

    if dry_run_only:
        return {"verdict": "DRY_RUN_OK",
                    "dryRun": True,
                    "accepted": [c.commandId for c in accepted_commands],
                    "rejected": rejected_cells,
                    "summary": summary_dry,
                    "sourceHashBefore": source_sha_before,
                    "sourceHashAfter": _sha(source_path),
                    "sourceUnchanged": _sha(source_path) == source_sha_before,
                    "outputCreated": False,
                    "notes": ["dry_run_only=True — writer 본 실행 생략"]}

    # 4) writer 본 실행 — sandbox 출력
    real = _edit_tool.apply_edit_plan(
        source_path, output_path, plan, dry_run=False)
    # 본 실행 후에도 LOCK_01 필터로 재검증
    applied_cells2, rejected_cells2 = _filter_applied_cells_by_coord(
        set_cells, real.get("operations", []))
    summary_real = _summarize_apply_text(
        set_cells, applied_cells2, rejected_cells2)

    # 5) verify7 게이트
    v7 = verify7(
        source_path=source_path, output_path=output_path,
        project_root=project_root,
        accepted_commands=accepted_commands,
        pre_save_cell_texts=pre_save_cell_texts,
        source_sha_before=source_sha_before,
        source_mtime_before=source_mtime_before)

    output_sha = _sha(output_path) if output_path.is_file() else None
    source_sha_after = _sha(source_path)
    source_unchanged = (source_sha_after == source_sha_before
                                      and source_path.stat().st_mtime_ns
                                      == source_mtime_before)

    if v7["verdict"] != "PASS":
        verdict = VERDICT_FAIL
        notes.append("verify7 FAIL — output 생성됐으나 PASS 게이트 불통")
    elif applied_cells2 and len(applied_cells2) == len(set_cells):
        verdict = VERDICT_PASS
    elif applied_cells2:
        verdict = VERDICT_PARTIAL
        notes.append("일부 op rejected — PARTIAL")
    else:
        verdict = VERDICT_FAIL
        notes.append("본 실행 후에도 applied=∅")

    return {
        "verdict": verdict,
        "dryRun": False,
        "accepted": [c.commandId for c in accepted_commands],
        "rejected": rejected_cells2,
        "summaryDry": summary_dry,
        "summaryReal": summary_real,
        "verify7": v7,
        "sourceHashBefore": source_sha_before,
        "sourceHashAfter": source_sha_after,
        "sourceUnchanged": source_unchanged,
        "outputCreated": output_path.is_file(),
        "outputHash": output_sha,
        "notes": notes,
    }
