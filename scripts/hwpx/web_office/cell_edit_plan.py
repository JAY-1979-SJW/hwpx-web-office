"""commandLog → dry-run edit plan 변환 + save 게이트.

본 모듈은 writer 모듈을 일절 import 하지 않는다. writer 본 실행은
별도 공정 (CELL-SAVE-HWPX-VERIFY7-01) 에서만 가능.
"""
from __future__ import annotations
from typing import Any

from .edit_command_model import (
    EditCommand, COMMAND_TYPE_SET_CELL_TEXT,
    validate_against_current,
)


SAVE_DRY_RUN_NOOP = "NOOP"
SAVE_DRY_RUN_REJECTED = "REJECTED"
SAVE_DRY_RUN_READY = "READY"


def _current_cell_text(document_model: dict, cell_id: str) -> str:
    """document_model 의 cells 리스트에서 cellId 의 현재 text 추출.

    document_model 은 RO-VIEW WebOfficeDocumentModel.to_dict() 또는
    동등 구조 (cells: list[dict with cellId, text]).
    """
    for c in document_model.get("cells", []):
        if c.get("cellId") == cell_id:
            return c.get("text", "")
    raise KeyError(f"cell not found in document_model: {cell_id}")


def validate_command_log(
    command_log: list[EditCommand],
    document_model: dict,
    source_document_hash: str,
) -> dict[str, Any]:
    """command 들을 순서대로 시뮬레이션하면서 expectedBefore 일치 검증.

    실제 writer 는 호출하지 않는다. 셀 텍스트는 in-memory 사본에서만
    갱신한다 (apply_forward 시뮬레이션).
    """
    rejected: list[dict[str, Any]] = []
    accepted: list[EditCommand] = []
    # in-memory 사본 — 변환 도중 같은 셀에 여러 명령이 있을 때 chain 검증
    snapshot: dict[str, str] = {
        c.get("cellId"): c.get("text", "")
        for c in document_model.get("cells", [])}

    for cmd in command_log:
        if cmd.commandType not in {COMMAND_TYPE_SET_CELL_TEXT}:
            rejected.append({"commandId": cmd.commandId,
                                      "reason": "UNSUPPORTED_TYPE",
                                      "detail": cmd.commandType})
            continue
        if cmd.sourceDocumentHash != source_document_hash:
            rejected.append({"commandId": cmd.commandId,
                                      "reason": "SOURCE_HASH_MISMATCH",
                                      "detail": cmd.sourceDocumentHash})
            continue
        cell_id = cmd.targetId
        if cell_id not in snapshot:
            rejected.append({"commandId": cmd.commandId,
                                      "reason": "TARGET_CELL_NOT_FOUND",
                                      "detail": cell_id})
            continue
        current = snapshot[cell_id]
        if not validate_against_current(cmd, current):
            rejected.append({"commandId": cmd.commandId,
                                      "reason": "EXPECTED_BEFORE_MISMATCH",
                                      "detail": {
                                          "expected": cmd.expectedBefore,
                                          "current": current}})
            continue
        snapshot[cell_id] = cmd.after
        accepted.append(cmd)

    return {
        "accepted": accepted,
        "rejected": rejected,
        "finalSnapshot": snapshot,
    }


def build_dry_run_edit_plan(
    command_log: list[EditCommand],
    document_model: dict,
    source_document_hash: str,
) -> dict[str, Any]:
    """commandLog → set_cells 형태의 dry-run plan 산출.

    - command_log 비면 status=NOOP, plan=None
    - sourceDocumentHash 불일치 시 status=REJECTED
    - expectedBefore 불일치 시 status=REJECTED (해당 command 만 제외)
    - 정상 진행 시 status=READY, plan={"set_cells": [...]}, dryRun=True

    plan 은 dry_run=True 로 apply_edit_plan 에 넘길 수 있는 형태이지만
    본 모듈은 apply_edit_plan 을 호출하지 않는다.
    """
    if not command_log:
        return {"status": SAVE_DRY_RUN_NOOP,
                    "reason": "commandLog empty",
                    "plan": None, "dryRun": True}

    result = validate_command_log(command_log, document_model,
                                                          source_document_hash)
    accepted: list[EditCommand] = result["accepted"]
    rejected = result["rejected"]

    if not accepted:
        return {"status": SAVE_DRY_RUN_REJECTED,
                    "reason": "no command accepted",
                    "rejected": rejected, "plan": None, "dryRun": True}

    # 같은 셀에 여러 명령이 있으면 마지막 명령의 after 만 plan 에 반영
    by_cell: dict[str, dict[str, Any]] = {}
    for cmd in accepted:
        # forward.set_cells 는 길이 1 (make_set_cell_text_command 보장)
        sc = cmd.forward["set_cells"][0]
        by_cell[cmd.targetId] = {"table": sc["table"], "row": sc["row"],
                                                  "col": sc["col"], "value": sc["value"]}
    set_cells = list(by_cell.values())

    plan = {"set_cells": set_cells}
    return {
        "status": SAVE_DRY_RUN_READY,
        "plan": plan,
        "dryRun": True,
        "acceptedCount": len(accepted),
        "rejectedCount": len(rejected),
        "rejected": rejected,
        "sourceDocumentHash": source_document_hash,
    }


# 본 모듈은 writer / apply_edit_plan 을 절대 호출하지 않는다.
# 호출 자체를 차단하기 위해 import 도 하지 않는다 (정적 검사 잠금 대상).
