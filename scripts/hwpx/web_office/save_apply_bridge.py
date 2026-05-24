"""Browser save/apply bridge for Web Office cell edits.

This module is the narrow contract between browser-side commandLog payloads
and the already gated HWPX writer pipeline. It intentionally supports only
CELL_SAVE_APPLY for SET_CELL_TEXT commands.
"""
from __future__ import annotations

import re
import tempfile
import uuid
from dataclasses import fields
from pathlib import Path
from typing import Any

from .cell_save_pipeline import save_cell_edits
from .edit_command_model import EditCommand


_PR = Path(__file__).resolve().parents[3]
_ALLOWED_OPERATION = "CELL_SAVE_APPLY"
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_EDIT_COMMAND_FIELDS = {f.name for f in fields(EditCommand)}


def _safe_request_id(value: Any) -> str:
    if isinstance(value, str) and _SAFE_ID_RE.fullmatch(value):
        return value
    return uuid.uuid4().hex


def _resolve_project_hwpx(project_root: Path, source_path: Any) -> Path:
    if not isinstance(source_path, str) or not source_path:
        raise ValueError("sourcePath is required")
    if Path(source_path).is_absolute():
        raise ValueError("sourcePath must be project-relative")
    candidate = (project_root / source_path).resolve()
    root = project_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("sourcePath escapes project root")
    if candidate.suffix.lower() != ".hwpx":
        raise ValueError("sourcePath must point to .hwpx")
    return candidate


def _command_from_payload(item: Any) -> EditCommand:
    if not isinstance(item, dict):
        raise ValueError("commandLog entries must be objects")
    missing = _EDIT_COMMAND_FIELDS - set(item)
    if missing:
        raise ValueError(f"commandLog entry missing fields: {sorted(missing)}")
    extra = set(item) - _EDIT_COMMAND_FIELDS
    if extra:
        raise ValueError(f"commandLog entry has extra fields: {sorted(extra)}")
    return EditCommand(**{k: item[k] for k in _EDIT_COMMAND_FIELDS})


def apply_cell_save_request(
    request: dict[str, Any],
    *,
    project_root: Path = _PR,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Apply a browser commandLog through the backend cell save pipeline.

    The request accepts only:
    - operation: CELL_SAVE_APPLY
    - sourcePath: project-relative .hwpx path
    - sourceDocumentHash: hash echoed by the browser document model
    - commandLog: list of EditCommand dictionaries
    - dryRunOnly: optional bool
    - requestId: optional safe identifier for output naming
    """
    if not isinstance(request, dict):
        return {"verdict": "REJECTED", "reason": "REQUEST_NOT_OBJECT"}
    if request.get("operation") != _ALLOWED_OPERATION:
        return {"verdict": "REJECTED", "reason": "UNSUPPORTED_OPERATION"}
    if not isinstance(request.get("dryRunOnly", False), bool):
        return {"verdict": "REJECTED", "reason": "DRY_RUN_ONLY_NOT_BOOL"}

    try:
        source_path = _resolve_project_hwpx(project_root, request.get("sourcePath"))
        commands = [_command_from_payload(c) for c in request.get("commandLog", [])]
    except (TypeError, ValueError) as exc:
        return {"verdict": "REJECTED", "reason": "INVALID_REQUEST",
                "detail": str(exc)}

    requested_hash = request.get("sourceDocumentHash")
    if requested_hash and any(c.sourceDocumentHash != requested_hash
                              for c in commands):
        return {"verdict": "REJECTED", "reason": "COMMAND_HASH_MISMATCH"}

    request_id = _safe_request_id(request.get("requestId"))
    out_root = Path(output_dir) if output_dir is not None else (
        Path(tempfile.gettempdir()) / "hwpx_web_office_save_apply")
    output_path = out_root / f"{request_id}.hwpx"

    result = save_cell_edits(
        source_path=source_path,
        output_path=output_path,
        command_log=commands,
        project_root=project_root,
        dry_run_only=request.get("dryRunOnly", False),
    )
    verify7 = result.get("verify7") or {}
    return {
        "operation": _ALLOWED_OPERATION,
        "requestId": request_id,
        "verdict": result.get("verdict"),
        "dryRun": result.get("dryRun"),
        "acceptedCount": len(result.get("accepted") or []),
        "rejected": result.get("rejected") or [],
        "sourceUnchanged": result.get("sourceUnchanged"),
        "outputCreated": result.get("outputCreated"),
        "outputHash": result.get("outputHash"),
        "outputFileName": output_path.name if result.get("outputCreated") else None,
        "outputPath": str(output_path) if result.get("outputCreated") else None,
        "verify7Verdict": verify7.get("verdict"),
        "notes": result.get("notes") or [],
    }
