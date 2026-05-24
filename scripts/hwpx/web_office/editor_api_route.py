"""Backend API route for the Web Office HWPX editor.

Endpoints:
    GET  /api/web-office/health
    POST /api/web-office/hwpx-load
    POST /api/web-office/cell-save-apply

The public HTTP response must not expose absolute filesystem paths. The lower
level writer bridge keeps outputPath for local tests; this route removes it.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .editor_file_bridge import load_hwpx_for_editor
from .save_apply_bridge import apply_cell_save_request


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_VERSION = "web_office_editor_api_v1"
MODE = "SANDBOX_ONLY"

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel

    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    FastAPI = object  # type: ignore
    BaseModel = object  # type: ignore


FRONTEND_DIR = PROJECT_ROOT / "frontend" / "web_office_viewer"


def _request_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


def _envelope(status: str, data: dict[str, Any],
              errors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "requestId": _request_id(),
        "status": status,
        "mode": MODE,
        "sourceMutationAllowed": False,
        "data": data,
        "errors": errors or [],
    }


def _strip_public_paths(response: dict[str, Any]) -> dict[str, Any]:
    safe = dict(response)
    safe.pop("outputPath", None)
    return safe


def call_health() -> dict[str, Any]:
    return _envelope("SUCCESS", {
        "loadEndpoint": "/api/web-office/hwpx-load",
        "saveEndpoint": "/api/web-office/cell-save-apply",
        "pipelineReady": True,
    })


def call_hwpx_load(request: dict[str, Any],
                   *, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    result = load_hwpx_for_editor(request, project_root=project_root)
    if result.get("verdict") == "PASS":
        return _envelope("SUCCESS", result)
    return _envelope("FAILED", result, [{
        "code": result.get("reason", "LOAD_REJECTED"),
        "message": result.get("detail", result.get("reason", "")),
    }])


def call_cell_save_apply(
    request: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    out_dir = output_dir
    if out_dir is None:
        configured = os.environ.get("HWPX_WEB_OFFICE_API_OUTPUT_DIR")
        out_dir = (Path(configured) if configured
                   else Path(tempfile.gettempdir())
                   / "hwpx_web_office_api_outputs")
    result = apply_cell_save_request(
        request, project_root=project_root, output_dir=out_dir)
    public_result = _strip_public_paths(result)
    if result.get("verdict") in {"PASS", "DRY_RUN_OK", "NOOP"}:
        return _envelope("SUCCESS", public_result)
    return _envelope("FAILED", public_result, [{
        "code": result.get("reason", result.get("verdict", "SAVE_REJECTED")),
        "message": result.get("reason", result.get("verdict", "")),
    }])


if _FASTAPI_AVAILABLE:
    class EditorLoadRequest(BaseModel):
        operation: str
        sourcePath: str

    class CellSaveApplyRequest(BaseModel):
        operation: str
        sourcePath: str
        sourceDocumentHash: str | None = None
        commandLog: list[dict[str, Any]] = []
        requestId: str | None = None
        dryRunOnly: bool = False


def create_app() -> Any:
    if not _FASTAPI_AVAILABLE:
        return None

    app = FastAPI(title="HWPX Web Office Editor API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/web-office/health")
    def health() -> dict[str, Any]:
        return call_health()

    @app.post("/api/web-office/hwpx-load")
    def hwpx_load(req: EditorLoadRequest) -> dict[str, Any]:
        return call_hwpx_load(req.model_dump())

    @app.post("/api/web-office/cell-save-apply")
    def cell_save_apply(req: CellSaveApplyRequest) -> dict[str, Any]:
        return call_cell_save_apply(req.model_dump())

    if FRONTEND_DIR.is_dir():
        app.mount(
            "/web-office",
            StaticFiles(directory=str(FRONTEND_DIR), html=True),
            name="web-office",
        )

    return app


app = create_app()
