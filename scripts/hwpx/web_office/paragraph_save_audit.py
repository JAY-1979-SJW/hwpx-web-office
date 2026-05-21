"""PARA-SAVE audit log — append-only JSONL.

data/audit/web_office_para_save/{YYYY-MM-DD}.jsonl 에 한 줄 = 1 save 결과.
"""
from __future__ import annotations
import datetime as _dt
import json
from pathlib import Path
from typing import Any

from .para_edit_model import EditCommandV2


_PR = Path(__file__).resolve().parents[3]
AUDIT_DIR = _PR / "data/audit/web_office_para_save"


def _today_jsonl(today: _dt.date | None = None) -> Path:
    today = today or _dt.datetime.now(_dt.timezone.utc).date()
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    return AUDIT_DIR / f"{today.isoformat()}.jsonl"


def append_para_save_audit_record(
    *, save_result: dict[str, Any],
    command_log: list[EditCommandV2],
    source_path: Path,
    output_path: Path,
    jsonl_path: Path | None = None,
) -> Path:
    """save_paragraph_edits 결과를 audit JSONL 에 append."""
    applied_edits = save_result.get("appliedPlanEdits") or []
    paragraph_ids = sorted({e.get("paragraphId")
                                                    for e in applied_edits
                                                    if e.get("paragraphId")})
    run_id_hints = [e.get("runIdHint") for e in applied_edits]
    ranges = [{"paragraphId": e.get("paragraphId"),
                          "rangeAnchor": e.get("rangeAnchor"),
                          "rangeFocus": e.get("rangeFocus"),
                          "commandType": e.get("commandType")}
                        for e in applied_edits]

    rec = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "task": "WEB-OFFICE-PARA-EDIT-SAVE-VERIFY7-01",
        "commandIds": [c.commandId for c in command_log],
        "paragraphIds": paragraph_ids,
        "runIdHints": run_id_hints,
        "ranges": ranges,
        "sourcePath": str(source_path),
        "outputPath": str(output_path),
        "sourceHash": save_result.get("sourceHashBefore"),
        "sourceHashAfter": save_result.get("sourceHashAfter"),
        "outputHash": save_result.get("outputHash"),
        "dryRunResult": {"applied": len(applied_edits)},
        "verify7Result": (save_result.get("verify7") or {}).get("results"),
        "verify7Verdict": (save_result.get("verify7") or {}).get("verdict"),
        "appliedCount": len(save_result.get("accepted") or []),
        "rejectedCount": len(save_result.get("rejected") or []),
        "originalUnmodified": save_result.get("sourceUnchanged"),
        "outputCreated": save_result.get("outputCreated"),
        "verdict": save_result.get("verdict"),
        "partialCompletion": save_result.get("partialCompletion", True),
        "nextActivationTrigger": save_result.get(
            "nextActivationTrigger", "writer paragraph plan 지원 시"),
        "blockReason": save_result.get("blockReason"),
    }
    p = jsonl_path or _today_jsonl()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return p
