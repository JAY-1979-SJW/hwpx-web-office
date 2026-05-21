"""CELL-SAVE audit log — append-only JSONL.

data/audit/web_office_cell_save/{YYYY-MM-DD}.jsonl 에 한 줄 = 1 save 결과.
"""
from __future__ import annotations
import datetime as _dt
import json
from pathlib import Path
from typing import Any

from .edit_command_model import EditCommand


_PR = Path(__file__).resolve().parents[3]
AUDIT_DIR = _PR / "data/audit/web_office_cell_save"


def _today_jsonl(today: _dt.date | None = None) -> Path:
    today = today or _dt.datetime.now(_dt.timezone.utc).date()
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    return AUDIT_DIR / f"{today.isoformat()}.jsonl"


def append_save_audit_record(
    *, save_result: dict[str, Any],
    command_log: list[EditCommand],
    source_path: Path,
    output_path: Path,
    jsonl_path: Path | None = None,
) -> Path:
    """save_cell_edits 결과를 audit JSONL 에 append."""
    rec = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "task": "WEB-OFFICE-CELL-SAVE-HWPX-VERIFY7-01",
        "commandIds": [c.commandId for c in command_log],
        "targetIds": [c.targetId for c in command_log],
        "sourcePath": str(source_path),
        "outputPath": str(output_path),
        "sourceHash": save_result.get("sourceHashBefore"),
        "sourceHashAfter": save_result.get("sourceHashAfter"),
        "outputHash": save_result.get("outputHash"),
        "dryRunResult": {
            "summaryDry": save_result.get("summaryDry"),
        },
        "verify7Result": (save_result.get("verify7") or {}).get(
            "results"),
        "verify7Verdict": (save_result.get("verify7") or {}).get(
            "verdict"),
        "appliedCount": len(save_result.get("accepted") or []),
        "rejectedCount": len(save_result.get("rejected") or []),
        "originalUnmodified": save_result.get("sourceUnchanged"),
        "outputCreated": save_result.get("outputCreated"),
        "verdict": save_result.get("verdict"),
    }
    p = jsonl_path or _today_jsonl()
    with p.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return p
