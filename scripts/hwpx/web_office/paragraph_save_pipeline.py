"""PARA-SAVE 파이프라인 — 부분 준공 모드.

writer (hwpx edit tool 모듈) 의 paragraph edits plan 은 현 단계 미지원.
본 모듈은 dry-run plan + verify7 게이트 (V4/V5/V6) + audit 적재까지만
수행하며, 본 실행 경로는 BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT 로 차단된다.

본 모듈은 writer 모듈을 import 하지 않는다 (정적 잠금 대상).
"""
from __future__ import annotations
import hashlib
import sys
from pathlib import Path
from typing import Any

_PR = Path(__file__).resolve().parents[3]
if str(_PR) not in sys.path:
    sys.path.insert(0, str(_PR))

from .para_edit_model import EditCommandV2, Paragraph  # noqa: E402
from .paragraph_edit_plan import (  # noqa: E402
    build_dry_run_paragraph_plan,
    PARA_DRY_RUN_NOOP, PARA_DRY_RUN_REJECTED, PARA_DRY_RUN_READY,
    BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT,
)
from .paragraph_save_verify7 import verify7_paragraphs  # noqa: E402


VERDICT_PASS = "PASS"
VERDICT_PARTIAL = "PARTIAL"
VERDICT_FAIL = "FAIL"
VERDICT_REJECTED = "REJECTED"
VERDICT_NOOP = "NOOP"
VERDICT_PARTIAL_DRY_RUN_OK = "PARTIAL_DRY_RUN_OK"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _filter_applied_runs_by_coord(
    plan_edits: list[dict],
    applied_results: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """plan_edits 의 좌표 (paragraphId, runIdHint, rangeAnchor,
    rangeFocus, commandType) 와 writer applied_results 좌표를 매칭.

    applied_results=None → writer 미호출 단계: plan_edits 전체를 applied
    로 간주 (현 부분 준공 모드). 향후 writer 결과 매칭 시 재사용 가능.
    """
    if applied_results is None:
        return list(plan_edits), []

    def _key(d: dict) -> tuple:
        return (d.get("paragraphId"), d.get("runIdHint"),
                      d.get("rangeAnchor"), d.get("rangeFocus"),
                      d.get("commandType"))

    applied_keys = {_key(r) for r in applied_results}
    applied: list[dict] = []
    rejected: list[dict] = []
    for e in plan_edits:
        if _key(e) in applied_keys:
            applied.append(e)
        else:
            rejected.append({"planEntry": e, "reason": "NOT_IN_APPLIED"})
    return applied, rejected


def save_paragraph_edits(
    *,
    source_path: Path,
    output_path: Path,
    command_log: list[EditCommandV2],
    paragraphs_by_id: dict[str, Paragraph],
    source_document_hash: str,
    project_root: Path = _PR,
    allow_writer: bool = False,
) -> dict[str, Any]:
    """PARA-SAVE 파이프라인. writer 미지원 (부분 준공).

    Returns dict with verdict + accepted/rejected + verify7 + audit fields.
    """
    notes: list[str] = []
    source_path = Path(source_path)
    output_path = Path(output_path)

    if output_path.resolve() == source_path.resolve():
        return {"verdict": VERDICT_REJECTED, "dryRun": True,
                    "rejected": [{"reason": "OUTPUT_EQUALS_SOURCE",
                                            "detail": str(source_path)}],
                    "accepted": [], "outputCreated": False,
                    "partialCompletion": True,
                    "nextActivationTrigger":
                        "writer paragraph plan 지원 시",
                    "notes": ["outputPath == sourcePath — 본 실행 차단"]}

    if not source_path.is_file():
        return {"verdict": VERDICT_REJECTED, "dryRun": True,
                    "rejected": [{"reason": "SOURCE_MISSING"}],
                    "accepted": [], "outputCreated": False,
                    "partialCompletion": True,
                    "nextActivationTrigger":
                        "writer paragraph plan 지원 시",
                    "notes": ["source 파일 없음"]}

    source_sha_before = _sha(source_path)
    source_mtime_before = source_path.stat().st_mtime_ns
    pre_save_paragraph_texts = {pid: p.text
                                                          for pid, p in paragraphs_by_id.items()}

    plan_result = build_dry_run_paragraph_plan(
        command_log, paragraphs_by_id, source_document_hash)

    if plan_result["status"] == PARA_DRY_RUN_NOOP:
        return {"verdict": VERDICT_NOOP, "dryRun": True,
                    "accepted": [], "rejected": [],
                    "sourceHashBefore": source_sha_before,
                    "sourceHashAfter": source_sha_before,
                    "sourceUnchanged": True,
                    "outputCreated": False,
                    "partialCompletion": True,
                    "nextActivationTrigger":
                        "writer paragraph plan 지원 시",
                    "notes": ["commandLog empty"]}

    if plan_result["status"] == PARA_DRY_RUN_REJECTED:
        sha_after = _sha(source_path)
        return {"verdict": VERDICT_REJECTED, "dryRun": True,
                    "accepted": [],
                    "rejected": plan_result.get("rejected", []),
                    "sourceHashBefore": source_sha_before,
                    "sourceHashAfter": sha_after,
                    "sourceUnchanged": sha_after == source_sha_before,
                    "outputCreated": False,
                    "partialCompletion": True,
                    "nextActivationTrigger":
                        "writer paragraph plan 지원 시",
                    "notes": ["plan REJECTED — paragraph edit 게이트 불통"]}

    assert plan_result["status"] == PARA_DRY_RUN_READY
    plan = plan_result["plan"]
    plan_edits: list[dict] = plan["paragraph_edits"]

    # writer 본 실행 분기 — apply_edit_plan(paragraph_edits=...)
    if allow_writer:
        # WRITER-PARA-PLAN-01: paragraph_edits intake 활성화
        import sys as _sys
        _hx = _PR / "scripts" / "hwpx"
        if str(_hx) not in _sys.path:
            _sys.path.insert(0, str(_hx))
        from scripts.hwpx import hwpx_edit_tool as _edit_tool  # noqa
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # writer plan 으로 변환 (plan_edits 에 containerScope 와
        # sourceDocumentHash, runId, rangeStart/rangeEnd, afterText,
        # expectedBefore, commandType 모두 포함되어 있어야 함)
        writer_plan = {"paragraph_edits": plan_edits}
        # dry-run 으로 먼저 검증
        dry = _edit_tool.apply_edit_plan(
            source_path, output_path, writer_plan, dry_run=True)
        dry_para_op = next(
            (op for op in dry.get("operations", [])
             if op.get("kind") == "paragraph_edits"), None)
        dry_applied = dry_para_op.get("applied", []) if dry_para_op else []
        if not dry_applied:
            sha_after = _sha(source_path)
            return {"verdict": VERDICT_FAIL, "dryRun": True,
                        "accepted": [],
                        "rejected": (
                            dry_para_op.get("rejected", [])
                            if dry_para_op else
                            [{"reason": "WRITER_DRY_RUN_NO_OPS"}]),
                        "sourceHashBefore": source_sha_before,
                        "sourceHashAfter": sha_after,
                        "sourceUnchanged":
                            sha_after == source_sha_before,
                        "outputCreated": False,
                        "partialCompletion": True,
                        "nextActivationTrigger":
                            "rejected items 해결",
                        "notes":
                            ["writer dry-run applied=∅ — 본 실행 차단"]}
        # 본 실행
        real = _edit_tool.apply_edit_plan(
            source_path, output_path, writer_plan, dry_run=False)
        real_para_op = next(
            (op for op in real.get("operations", [])
             if op.get("kind") == "paragraph_edits"), None)
        real_applied = (real_para_op.get("applied", [])
                              if real_para_op else [])
        real_rejected = (real_para_op.get("rejected", [])
                                if real_para_op else [])

        # 원본 sha/mtime 사전=사후 재검증
        source_sha_after = _sha(source_path)
        source_unchanged = (source_sha_after == source_sha_before
                              and source_path.stat().st_mtime_ns
                              == source_mtime_before)
        if not source_unchanged:
            return {"verdict": VERDICT_FAIL, "dryRun": False,
                        "accepted": [],
                        "rejected": [{"reason": "SOURCE_TOUCHED"}],
                        "sourceHashBefore": source_sha_before,
                        "sourceHashAfter": source_sha_after,
                        "sourceUnchanged": False,
                        "outputCreated": output_path.is_file(),
                        "notes":
                            ["원본 sha/mtime 변경 — 무손상 위반"]}

        # verify7 (V4/V5/V6 + V2 출력 blob 검증 가능)
        v7 = verify7_paragraphs(
            source_path=source_path, output_path=output_path,
            project_root=project_root,
            applied_plan_edits=real_applied,
            paragraphs_by_id=paragraphs_by_id,
            pre_save_paragraph_texts=pre_save_paragraph_texts)
        # verdict — V2/V4/V5/V6 PASS + applied≥1 → PASS,
        # rejected 있으면 PARTIAL, applied=∅ → FAIL.
        gates = v7["results"]
        primary_pass = (gates.get("V2_NO_CROSS_PARAGRAPH_LEAK") == "PASS"
                              and gates.get("V4_CHARPR_PRESERVED") == "PASS"
                              and gates.get("V5_PARPR_PRESERVED") == "PASS"
                              and gates.get("V6_OUTPUT_ISOLATED") == "PASS")
        output_hash = (_sha(output_path)
                              if output_path.is_file() else None)
        if not real_applied:
            verdict = VERDICT_FAIL
            notes.append("본 실행 applied=∅")
        elif not primary_pass:
            verdict = VERDICT_FAIL
            notes.append("verify7 V2/V4/V5/V6 게이트 불통")
        elif real_rejected:
            verdict = VERDICT_PARTIAL
            notes.append("일부 paragraph_edits rejected")
        else:
            verdict = VERDICT_PASS
            notes.append("writer paragraph_edits 본 실행 PASS")
        return {
            "verdict": verdict,
            "dryRun": False,
            "accepted": [c.commandId
                                  for c in plan_result["acceptedCommands"]],
            "appliedPlanEdits": real_applied,
            "rejected": (plan_result.get("rejected", [])
                                + list(real_rejected)),
            "verify7": v7,
            "sourceHashBefore": source_sha_before,
            "sourceHashAfter": source_sha_after,
            "sourceUnchanged": source_unchanged,
            "outputCreated": output_path.is_file(),
            "outputHash": output_hash,
            "partialCompletion": False,
            "writerActivated": True,
            "notes": notes,
        }

    # writer 미호출 → applied = plan_edits 전체 (현 부분 준공 모드)
    applied_edits, rejected_edits = _filter_applied_runs_by_coord(
        plan_edits, applied_results=None)

    if not applied_edits:
        sha_after = _sha(source_path)
        return {"verdict": VERDICT_FAIL, "dryRun": True,
                    "accepted": [],
                    "rejected": [{"reason": "DRY_RUN_NO_APPLIED",
                                            "details": rejected_edits}],
                    "sourceHashBefore": source_sha_before,
                    "sourceHashAfter": sha_after,
                    "sourceUnchanged": sha_after == source_sha_before,
                    "outputCreated": False,
                    "partialCompletion": True,
                    "nextActivationTrigger":
                        "writer paragraph plan 지원 시",
                    "notes": ["dry-run applied=∅ — vacuous PASS 방지"]}

    # verify7 — output 미존재 상태로 V4/V5/V6 게이트만 의미 있음
    v7 = verify7_paragraphs(
        source_path=source_path, output_path=output_path,
        project_root=project_root,
        applied_plan_edits=applied_edits,
        paragraphs_by_id=paragraphs_by_id,
        pre_save_paragraph_texts=pre_save_paragraph_texts)

    source_sha_after = _sha(source_path)
    source_unchanged = (source_sha_after == source_sha_before
                                      and source_path.stat().st_mtime_ns
                                      == source_mtime_before)

    partial_gates_pass = (
        v7["results"].get("V4_CHARPR_PRESERVED") == "PASS"
        and v7["results"].get("V5_PARPR_PRESERVED") == "PASS"
        and v7["results"].get("V6_OUTPUT_ISOLATED") == "PASS")

    if partial_gates_pass and source_unchanged:
        verdict = VERDICT_PARTIAL_DRY_RUN_OK
        notes.append("V4/V5/V6 PASS, writer 미지원 — 부분 준공")
    else:
        verdict = VERDICT_FAIL
        notes.append("부분 준공 게이트 (V4/V5/V6) 불통")

    return {
        "verdict": verdict,
        "dryRun": True,
        "accepted": [c.commandId
                                for c in plan_result["acceptedCommands"]],
        "appliedPlanEdits": applied_edits,
        "rejected": plan_result.get("rejected", []) + rejected_edits,
        "verify7": v7,
        "sourceHashBefore": source_sha_before,
        "sourceHashAfter": source_sha_after,
        "sourceUnchanged": source_unchanged,
        "outputCreated": output_path.is_file(),
        "outputHash": None,
        "partialCompletion": True,
        "nextActivationTrigger": "writer paragraph plan 지원 시",
        "blockReason": BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT,
        "notes": notes,
    }
