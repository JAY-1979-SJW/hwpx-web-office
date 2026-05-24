"""Real HWPX load/save bridge for the browser editor.

The load side returns a render payload plus the editor document model needed by
cell_edit_state.mjs. The save side reuses save_apply_bridge.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .render_payload import build_render_payload
from .ro_view_importer import import_hwpx_as_ro_view
from .save_apply_bridge import apply_cell_save_request


_PR = Path(__file__).resolve().parents[3]


def _resolve_project_hwpx(project_root: Path, source_path: Any) -> tuple[Path, str]:
    if not isinstance(source_path, str) or not source_path:
        raise ValueError("sourcePath is required")
    requested = Path(source_path)
    if requested.is_absolute():
        raise ValueError("sourcePath must be project-relative")
    candidate = (project_root / requested).resolve()
    root = project_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("sourcePath escapes project root")
    if candidate.suffix.lower() != ".hwpx":
        raise ValueError("sourcePath must point to .hwpx")
    if not candidate.is_file():
        raise ValueError("sourcePath does not exist")
    rel = candidate.relative_to(root).as_posix()
    return candidate, rel


def _sanitize_document_model(doc_dict: dict[str, Any], source_rel: str) -> dict[str, Any]:
    clean = deepcopy(doc_dict)
    clean["sourceDocumentPath"] = source_rel
    return clean


def _sanitize_render_payload(payload: dict[str, Any], source_rel: str) -> dict[str, Any]:
    clean = deepcopy(payload)
    clean.setdefault("sourceRef", {})
    clean["sourceRef"]["path"] = source_rel
    return clean


def load_hwpx_for_editor(
    request: dict[str, Any],
    *,
    project_root: Path = _PR,
) -> dict[str, Any]:
    """Load a project-relative HWPX into browser editor contract payloads."""
    if not isinstance(request, dict):
        return {"verdict": "REJECTED", "reason": "REQUEST_NOT_OBJECT"}
    if request.get("operation") != "HWPX_EDITOR_LOAD":
        return {"verdict": "REJECTED", "reason": "UNSUPPORTED_OPERATION"}
    try:
        source_path, source_rel = _resolve_project_hwpx(
            project_root, request.get("sourcePath"))
    except ValueError as exc:
        return {"verdict": "REJECTED", "reason": "INVALID_REQUEST",
                "detail": str(exc)}

    doc = import_hwpx_as_ro_view(source_path)
    document_model = _sanitize_document_model(doc.to_dict(), source_rel)
    render_payload = _sanitize_render_payload(build_render_payload(doc), source_rel)
    cells = document_model.get("cells") or []
    header_cells = [c for c in cells if c.get("headerCell") is True]
    return {
        "operation": "HWPX_EDITOR_LOAD",
        "verdict": "PASS",
        "sourcePath": source_rel,
        "documentId": document_model["documentId"],
        "sourceDocumentHash": document_model["sourceDocumentHash"],
        "documentModel": document_model,
        "renderPayload": render_payload,
        "summary": {
            "sections": len(document_model.get("sections") or []),
            "blocks": len(document_model.get("blocks") or []),
            "tables": len(document_model.get("tables") or []),
            "cells": len(cells),
            "headerCells": len(header_cells),
            "warnings": len(document_model.get("warnings") or []),
        },
    }


def load_and_apply_cell_save(
    load_request: dict[str, Any],
    save_request: dict[str, Any],
    *,
    project_root: Path = _PR,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Testable vertical slice: load a real file, then apply browser commands."""
    load_response = load_hwpx_for_editor(load_request, project_root=project_root)
    if load_response.get("verdict") != "PASS":
        return {"verdict": "REJECTED", "load": load_response, "save": None}
    save_response = apply_cell_save_request(
        save_request, project_root=project_root, output_dir=output_dir)
    return {
        "operation": "HWPX_EDITOR_LOAD_SAVE",
        "verdict": "PASS" if save_response.get("verdict") == "PASS" else "FAIL",
        "load": load_response,
        "save": save_response,
    }
