"""PARA-EDIT commandLog → dry-run paragraph save plan 변환 + 게이트.

본 모듈은 writer (hwpx edit tool 모듈) 를 일절 import 하지 않는다.
paragraph_edits 형태의 plan 만 산출하며, writer 본 실행은 현 단계
지원되지 않는다 (BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT — §11-5 부분 준공).
"""
from __future__ import annotations
import copy
from typing import Any

from .para_edit_model import (
    EditCommandV2, Paragraph,
    CT_TYPE_TEXT, CT_REPLACE_TEXT_RANGE, CT_DELETE_TEXT_RANGE,
    CT_APPLY_FORMAT,
    PARA_COMMAND_TYPES,
    apply_command_to_paragraph, validate_charpr_preserved,
    validate_parpr_preserved, validate_expected_before,
    validate_source_document_hash,
)


PARA_DRY_RUN_NOOP = "NOOP"
PARA_DRY_RUN_REJECTED = "REJECTED"
PARA_DRY_RUN_READY = "READY"

BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT = "BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT"

# reject 사유
REASON_UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
REASON_SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
REASON_TARGET_PARAGRAPH_NOT_FOUND = "TARGET_PARAGRAPH_NOT_FOUND"
REASON_EXPECTED_BEFORE_MISMATCH_PARAGRAPH = (
    "EXPECTED_BEFORE_MISMATCH_PARAGRAPH")
REASON_PARPR_MISMATCH = "PARPR_MISMATCH"
REASON_CHARPR_NEW_INTRODUCED = "CHARPR_NEW_INTRODUCED"


# 본 공정에서 paragraph save plan 으로 변환 가능한 commandType
_SUPPORTED = {CT_TYPE_TEXT, CT_REPLACE_TEXT_RANGE, CT_DELETE_TEXT_RANGE,
                          CT_APPLY_FORMAT}


def _clone_para(p: Paragraph) -> Paragraph:
    return copy.deepcopy(p)


def validate_para_command_log(
    command_log: list[EditCommandV2],
    paragraphs_by_id: dict[str, Paragraph],
    source_document_hash: str,
) -> dict[str, Any]:
    """paragraph 명령들을 순서대로 in-memory 시뮬레이션하면서 chain 검증."""
    rejected: list[dict[str, Any]] = []
    accepted: list[EditCommandV2] = []
    snapshot: dict[str, Paragraph] = {
        pid: _clone_para(p) for pid, p in paragraphs_by_id.items()}

    for cmd in command_log:
        if cmd.commandType not in _SUPPORTED:
            rejected.append({"commandId": cmd.commandId,
                                                    "reason": REASON_UNSUPPORTED_TYPE,
                                                    "detail": cmd.commandType})
            continue
        if not validate_source_document_hash(cmd, source_document_hash):
            rejected.append({"commandId": cmd.commandId,
                                                    "reason": REASON_SOURCE_HASH_MISMATCH,
                                                    "detail": cmd.sourceDocumentHash})
            continue
        pid = cmd.forward.get("paragraphId")
        para = snapshot.get(pid)
        if para is None:
            rejected.append({"commandId": cmd.commandId,
                                                    "reason": REASON_TARGET_PARAGRAPH_NOT_FOUND,
                                                    "detail": pid})
            continue
        if not validate_expected_before(cmd, para):
            rejected.append({
                "commandId": cmd.commandId,
                "reason": REASON_EXPECTED_BEFORE_MISMATCH_PARAGRAPH,
                "detail": {"expected": cmd.expectedBefore,
                                          "paragraphText": para.text}})
            continue
        try:
            after_para = apply_command_to_paragraph(para, cmd)
        except Exception as e:  # noqa: BLE001
            rejected.append({"commandId": cmd.commandId,
                                                    "reason": "APPLY_FAILED",
                                                    "detail": str(e)})
            continue
        if not validate_parpr_preserved(para, after_para):
            rejected.append({"commandId": cmd.commandId,
                                                    "reason": REASON_PARPR_MISMATCH,
                                                    "detail": {
                                                        "before": para.parPrIDRef,
                                                        "after": after_para.parPrIDRef}})
            continue
        # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01:
        # APPLY_FORMAT 은 paragraph 의 원본 charPr 집합에 없던 (header
        # 에는 존재하는) id 로의 교체를 허용한다. header 존재 검증은
        # writer adapter 가 담당한다.
        if (cmd.commandType != CT_APPLY_FORMAT
                and not validate_charpr_preserved(para, after_para)):
            rejected.append({"commandId": cmd.commandId,
                                                    "reason": REASON_CHARPR_NEW_INTRODUCED,
                                                    "detail": {
                                                        "origCharPr": sorted(
                                                            str(x) for x in
                                                            para.char_pr_set()),
                                                        "afterCharPr": sorted(
                                                            str(x) for x in
                                                            after_para.char_pr_set())}})
            continue
        snapshot[pid] = after_para
        accepted.append(cmd)

    return {"accepted": accepted, "rejected": rejected,
                  "finalSnapshot": snapshot}


def _container_scope_from_target(target: dict | None) -> dict | None:
    """EditCommandV2.target → writer paragraph_edits containerScope.

    우선순위:
      1) target.containerScope 가 dict 이면 그대로 사용 (RO-VIEW 발급 shape).
         cell 인 경우 paragraphIndex/runIndex 기본값 0 채움.
      2) 없으면 target.containerKind + cellCoord ({table,row,col,...}) 에서
         derive (legacy).
      3) "block" 은 그대로 통과 (writer 측에서 reject 한다).
      4) 둘 다 없으면 None (호출자 측에서 reject).
    """
    if not target:
        return None
    # 1) target.containerScope (RO-VIEW shape) 우선
    scope = target.get("containerScope")
    if isinstance(scope, dict) and scope.get("kind"):
        out = dict(scope)
        if out.get("kind") == "cell":
            out.setdefault("paragraphIndex", 0)
            out.setdefault("runIndex", 0)
        return out
    # 2) legacy derive
    kind = target.get("containerKind")
    if kind == "cell":
        coord = target.get("cellCoord") or {}
        derived: dict = {"kind": "cell"}
        for src, dst in (("table", "tableIndex"), ("row", "rowIndex"),
                                ("col", "colIndex"),
                                ("paragraphIndex", "paragraphIndex"),
                                ("runIndex", "runIndex")):
            if src in coord:
                derived[dst] = coord[src]
        derived.setdefault("paragraphIndex", 0)
        derived.setdefault("runIndex", 0)
        return derived
    if kind == "block":
        return {"kind": "block"}
    return None


def _command_to_plan_entry(cmd: EditCommandV2) -> dict[str, Any]:
    fwd = cmd.forward
    ct = cmd.commandType
    scope = _container_scope_from_target(cmd.target)
    entry: dict[str, Any] = {
        "commandId": cmd.commandId,
        "paragraphId": fwd["paragraphId"],
        "runId": fwd.get("runId") or f"{fwd['paragraphId']}_run0",
        "commandType": ct,
        "expectedBefore": cmd.expectedBefore,
        "sourceDocumentHash": cmd.sourceDocumentHash,
        "containerScope": scope,
    }
    if ct == CT_TYPE_TEXT:
        co = fwd["caretOffset"]
        entry.update({
            "rangeAnchor": co, "rangeFocus": co,
            "rangeStart": co, "rangeEnd": co,
            "caretOffset": co,
            "insertText": fwd["insertText"],
            "afterText": fwd["insertText"],
            "applyCharPrIDRef": fwd.get("inheritCharPrIDRef"),
            "runIdHint": None,
        })
    elif ct == CT_REPLACE_TEXT_RANGE:
        entry.update({
            "rangeAnchor": fwd["rangeAnchor"],
            "rangeFocus": fwd["rangeFocus"],
            "rangeStart": fwd["rangeAnchor"],
            "rangeEnd": fwd["rangeFocus"],
            "afterText": fwd["afterText"],
            "applyCharPrIDRef": fwd.get("applyCharPrIDRef"),
            "runIdHint": None,
        })
    elif ct == CT_DELETE_TEXT_RANGE:
        entry.update({
            "rangeAnchor": fwd["rangeAnchor"],
            "rangeFocus": fwd["rangeFocus"],
            "rangeStart": fwd["rangeAnchor"],
            "rangeEnd": fwd["rangeFocus"],
            "deletedText": fwd["deletedText"],
            "afterText": "",
            "applyCharPrIDRef": fwd.get("deletedCharPrIDRef"),
            "runIdHint": None,
        })
    elif ct == CT_APPLY_FORMAT:
        entry.update({
            "rangeAnchor": fwd["rangeAnchor"],
            "rangeFocus": fwd["rangeFocus"],
            "rangeStart": fwd["rangeAnchor"],
            "rangeEnd": fwd["rangeFocus"],
            "targetCharPrIDRef": fwd["targetCharPrIDRef"],
            "beforeSegments": fwd.get("beforeSegments", []),
            "runIdHint": None,
        })
    return entry


def build_dry_run_paragraph_plan(
    command_log: list[EditCommandV2],
    paragraphs_by_id: dict[str, Paragraph],
    source_document_hash: str,
) -> dict[str, Any]:
    """paragraph 명령 → paragraph_edits plan.

    status: NOOP | REJECTED | READY.
    writer 미지원 — 본 plan 은 dry-run + audit 용도로만 쓰인다.
    """
    if not command_log:
        return {"status": PARA_DRY_RUN_NOOP,
                    "reason": "commandLog empty",
                    "plan": None, "dryRun": True}

    result = validate_para_command_log(
        command_log, paragraphs_by_id, source_document_hash)
    accepted: list[EditCommandV2] = result["accepted"]
    rejected = result["rejected"]
    if not accepted:
        return {"status": PARA_DRY_RUN_REJECTED,
                    "reason": "no paragraph command accepted",
                    "rejected": rejected,
                    "plan": None, "dryRun": True}

    paragraph_edits = [_command_to_plan_entry(c) for c in accepted]
    plan = {"paragraph_edits": paragraph_edits}
    return {
        "status": PARA_DRY_RUN_READY,
        "plan": plan, "dryRun": True,
        "acceptedCount": len(accepted),
        "rejectedCount": len(rejected),
        "rejected": rejected,
        "acceptedCommands": accepted,
        "finalSnapshot": result["finalSnapshot"],
        "sourceDocumentHash": source_document_hash,
        "writerSupported": False,
        "blockReason": BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT,
    }


# 본 모듈은 writer 본 실행 (apply edit plan) 을 절대 호출하지 않는다.
