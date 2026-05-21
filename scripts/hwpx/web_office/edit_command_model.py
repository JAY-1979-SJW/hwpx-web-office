"""EditCommand v1 — CELL-EDIT MVP-A.

forward/inverse 동반, expectedBefore 검증. 본 모듈은 writer / output 을
일절 호출하지 않으며 dry-run plan 산출만 담당한다.
"""
from __future__ import annotations
import datetime as _dt
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


COMMAND_TYPE_SET_CELL_TEXT = "SET_CELL_TEXT"
SUPPORTED_TYPES = {COMMAND_TYPE_SET_CELL_TEXT}

STATUS_PENDING = "PENDING"
STATUS_VALIDATED = "VALIDATED"
STATUS_REJECTED = "REJECTED"


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass
class EditCommand:
    commandId: str
    commandType: str
    targetId: str           # cellId (예: cell_t_s0_001_r0_c0)
    targetKind: str         # "cell"
    before: str
    after: str
    expectedBefore: str
    forward: dict[str, Any]
    inverse: dict[str, Any]
    createdAt: str
    sourceDocumentHash: str
    status: str = STATUS_PENDING

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cell_coord_from_cell_id(cell_id: str) -> tuple[str, int, int]:
    """cell_{tableId}_r{row}_c{col} → (tableId, row, col).

    tableId 자체에 '_' 가 들어가므로 뒤에서부터 분리한다.
    """
    if not cell_id.startswith("cell_"):
        raise ValueError(f"invalid cellId: {cell_id}")
    rest = cell_id[len("cell_"):]
    # 뒤에서 _c{col} 분리
    c_idx = rest.rfind("_c")
    r_idx = rest.rfind("_r", 0, c_idx)
    if c_idx < 0 or r_idx < 0:
        raise ValueError(f"unparseable cellId: {cell_id}")
    table_id = rest[:r_idx]
    row = int(rest[r_idx + 2: c_idx])
    col = int(rest[c_idx + 2:])
    return table_id, row, col


def make_set_cell_text_command(
    *, cell_id: str, table_index: int,
    before: str, after: str,
    source_document_hash: str,
    expected_before: str | None = None,
) -> EditCommand:
    """SET_CELL_TEXT EditCommand 생성. value 가 같으면 None 반환.

    forward / inverse 는 apply_edit_plan 의 set_cells fragment 와
    호환되는 dict 만 만들고, 본 함수는 그 plan 을 실행하지 않는다.
    """
    if before == after:
        # 값이 동일하면 command 미생성
        raise ValueError("before == after — no command should be created")
    _, row, col = _cell_coord_from_cell_id(cell_id)
    expected = expected_before if expected_before is not None else before
    fwd = {"set_cells": [{"table": table_index, "row": row, "col": col,
                                          "value": after}]}
    inv = {"set_cells": [{"table": table_index, "row": row, "col": col,
                                          "value": before}]}
    return EditCommand(
        commandId=str(uuid.uuid4()),
        commandType=COMMAND_TYPE_SET_CELL_TEXT,
        targetId=cell_id,
        targetKind="cell",
        before=before,
        after=after,
        expectedBefore=expected,
        forward=fwd,
        inverse=inv,
        createdAt=_now_iso(),
        sourceDocumentHash=source_document_hash,
        status=STATUS_PENDING,
    )


def validate_against_current(command: EditCommand,
                                                    current_value: str) -> bool:
    """expectedBefore 와 현재 cell 값이 일치하는지 확인.

    불일치 시 status='REJECTED' 로 마킹. 단, 본 함수는 EditCommand 객체를
    수정하지 않고 boolean 만 반환한다 (불변성 유지). 호출자가 상태 갱신.
    """
    return command.expectedBefore == current_value


def apply_forward(value_before: str, command: EditCommand) -> str:
    """forward 적용 시뮬레이션 — 실제 writer 호출 없음. 셀 값만 갱신."""
    if not validate_against_current(command, value_before):
        raise ValueError(
            f"expectedBefore mismatch: expected={command.expectedBefore!r} "
            f"got={value_before!r}")
    return command.after


def apply_inverse(value_now: str, command: EditCommand) -> str:
    """inverse 적용 시뮬레이션 — 셀을 before 로 되돌림."""
    if value_now != command.after:
        raise ValueError(
            f"inverse cannot apply: current={value_now!r} after={command.after!r}")
    return command.before
