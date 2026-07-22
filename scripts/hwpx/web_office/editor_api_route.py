"""Backend API route for the Web Office HWPX editor.

Endpoints:
    GET  /api/web-office/health
    POST /api/web-office/hwpx-load
    POST /api/web-office/cell-save-apply

The public HTTP response must not expose absolute filesystem paths. The lower
level writer bridge keeps outputPath for local tests; this route removes it.
"""
from __future__ import annotations

import hashlib
import io
import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from .editor_file_bridge import load_hwpx_for_editor
from .save_apply_bridge import apply_cell_save_request


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_VERSION = "web_office_editor_api_v1"
MODE = "SANDBOX_ONLY"

try:
    from fastapi import FastAPI, File, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse
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


def _api_output_dir() -> Path:
    # verify7 V6 은 프로젝트 내 sandbox(tmp/·data/drafts·data/audit) 출력만 인정한다.
    # 시스템 temp(예: ESTsoft CreatorTemp)는 격리 게이트를 통과 못 함.
    configured = os.environ.get("HWPX_WEB_OFFICE_API_OUTPUT_DIR")
    out = (Path(configured) if configured
           else PROJECT_ROOT / "tmp" / "web_office_edits")
    out.mkdir(parents=True, exist_ok=True)
    return out


# 업로드 상한(위장/DoS 방지). 필요 시 환경변수로 조정.
UPLOAD_MAX_BYTES = int(
    os.environ.get("HWPX_WEB_OFFICE_UPLOAD_MAX_BYTES", str(30 * 1024 * 1024)))


def _api_upload_dir() -> Path:
    # 업로드 sandbox — 프로젝트 내부라 hwpx-load 경계검증을 통과한다.
    configured = os.environ.get("HWPX_WEB_OFFICE_API_UPLOAD_DIR")
    out = (Path(configured) if configured
           else PROJECT_ROOT / "tmp" / "web_office_uploads")
    out.mkdir(parents=True, exist_ok=True)
    return out


def call_hwpx_upload(filename: str, content: bytes,
                     *, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """브라우저가 업로드한 HWPX 바이트를 sandbox 에 받아 로드.

    보안 설계 — 서버는 사용자 PC 경로에 일절 접근하지 않는다. 브라우저가
    사용자 동의(파일 선택/드래그)로 보낸 바이트만 받아 sandbox 에만 기록하고,
    저장 파일명은 내용 해시로 생성한다(사용자 파일명 신뢰 안 함 → 경로주입
    차단). 로드는 hwpx-load 와 동일 파이프라인이라 원본 무수정 원칙 유지.
    """
    name = str(filename or "").strip()
    if not name.lower().endswith(".hwpx"):
        return _envelope(
            "FAILED", {"verdict": "REJECTED", "reason": "NOT_HWPX"},
            [{"code": "NOT_HWPX",
              "message": "HWPX(.hwpx) 파일만 업로드할 수 있습니다."}])
    if not content:
        return _envelope(
            "FAILED", {"verdict": "REJECTED", "reason": "EMPTY_FILE"},
            [{"code": "EMPTY_FILE", "message": "빈 파일입니다."}])
    if len(content) > UPLOAD_MAX_BYTES:
        cap_mb = UPLOAD_MAX_BYTES // (1024 * 1024)
        return _envelope(
            "FAILED", {"verdict": "REJECTED", "reason": "FILE_TOO_LARGE"},
            [{"code": "FILE_TOO_LARGE",
              "message": f"파일이 너무 큽니다(최대 {cap_mb}MB)."}])
    # HWPX 는 zip 컨테이너 — 유효 zip 아니면 거부(확장자만 바꾼 위장 차단)
    if not zipfile.is_zipfile(io.BytesIO(content)):
        return _envelope(
            "FAILED", {"verdict": "REJECTED", "reason": "NOT_A_ZIP"},
            [{"code": "NOT_A_ZIP",
              "message": "유효한 HWPX 파일이 아닙니다(zip 컨테이너 아님)."}])
    # 안전한 저장 파일명 — 내용 sha256(사용자 파일명 미신뢰 → 경로 traversal 차단)
    digest = hashlib.sha256(content).hexdigest()[:16]
    safe_path = _api_upload_dir() / f"upload_{digest}.hwpx"
    if not safe_path.exists():
        safe_path.write_bytes(content)
    rel = safe_path.resolve().relative_to(project_root.resolve()).as_posix()
    # 동일 로드 파이프라인 재사용 — 프로젝트 상대경로라 경계검증을 통과한다.
    return call_hwpx_load(
        {"operation": "HWPX_EDITOR_LOAD", "sourcePath": rel},
        project_root=project_root)


def call_cell_save_apply(
    request: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    out_dir = output_dir if output_dir is not None else _api_output_dir()
    result = apply_cell_save_request(
        request, project_root=project_root, output_dir=out_dir)
    public_result = _strip_public_paths(result)
    if result.get("verdict") in {"PASS", "DRY_RUN_OK", "NOOP"}:
        return _envelope("SUCCESS", public_result)
    return _envelope("FAILED", public_result, [{
        "code": result.get("reason", result.get("verdict", "SAVE_REJECTED")),
        "message": result.get("reason", result.get("verdict", "")),
    }])


def call_ai_fill(request: dict[str, Any]) -> dict[str, Any]:
    """AI 서식 자동채움 — Claude CLI(Haiku)로 입력칸 값 제안. §7/§9 준수.

    request.sourceData 가 있으면 실제 소스 값을 라벨에 매핑(예시 아님)."""
    from .ai_form_fill import propose_values
    fields = request.get("fields") or []
    source_data = request.get("sourceData") or None
    result = propose_values(fields, source_data=source_data)
    if result.get("ok"):
        return _envelope("SUCCESS", result)
    return _envelope("FAILED", result, [{
        "code": result.get("error", "AI_FILL_FAILED"),
        "message": result.get("detail", result.get("error", "")),
    }])


def call_source_extract(request: dict[str, Any]) -> dict[str, Any]:
    """소스 문서(사업자등록증 등) 이미지에서 Claude 비전으로 값 추출. §4/§9 준수.

    응답에는 마스킹 미리보기만 노출하고, 실제 값(source)은 채움용으로 함께 반환."""
    from .ai_source_extract import extract_source, masked_preview
    image_path = str(request.get("imagePath") or "")
    doc_type = str(request.get("docType") or "사업자등록증")
    result = extract_source(image_path, doc_type=doc_type)
    if result.get("ok"):
        result["maskedPreview"] = masked_preview(result.get("source", {}))
        return _envelope("SUCCESS", result)
    return _envelope("FAILED", result, [{
        "code": result.get("error", "SOURCE_EXTRACT_FAILED"),
        "message": result.get("detail", result.get("error", "")),
    }])


def call_catalog_stats() -> dict[str, Any]:
    from .catalog_search import stats
    return _envelope("SUCCESS", stats())


def call_catalog_search(request: dict[str, Any]) -> dict[str, Any]:
    from .catalog_search import search
    return _envelope("SUCCESS", search(str(request.get("query") or ""),
                                       limit=int(request.get("limit") or 20)))


def call_catalog_match(request: dict[str, Any]) -> dict[str, Any]:
    """업로드 서식을 카탈로그와 대조 → 이게 무슨 서식인지 분류."""
    from .catalog_search import match_form
    return _envelope("SUCCESS", match_form(
        fingerprint=request.get("fingerprint"),
        field_labels=request.get("fieldLabels") or [],
        limit=int(request.get("limit") or 5)))


def call_catalog_categories() -> dict[str, Any]:
    from .catalog_search import categories
    return _envelope("SUCCESS", categories())


def call_catalog_by_category(request: dict[str, Any]) -> dict[str, Any]:
    from .catalog_search import by_category
    return _envelope("SUCCESS", by_category(str(request.get("domain") or ""),
                                            limit=int(request.get("limit") or 40)))


def call_prepare_form(request: dict[str, Any]) -> dict[str, Any]:
    """서식을 편집 가능한 HWPX로 준비(HWP면 한컴 변환). formId 또는 sourcePath."""
    from .form_prepare import prepare_form
    src = request.get("sourcePath")
    form_id = request.get("formId")
    if not src and form_id is not None:
        try:
            import sqlite3
            from .catalog_search import CATALOG
            con = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True, timeout=5)
            row = con.execute("SELECT source_path FROM forms WHERE form_id=?",
                              (int(form_id),)).fetchone()
            con.close()
            if row:
                src = row[0]
        except Exception as e:  # noqa: BLE001
            return _envelope("FAILED", {"ok": False, "error": "CATALOG_LOOKUP_FAIL"},
                             [{"code": "CATALOG_LOOKUP_FAIL", "message": str(e)[:120]}])
    if not src:
        return _envelope("FAILED", {"ok": False, "error": "NO_SOURCE"},
                         [{"code": "NO_SOURCE", "message": "sourcePath or formId required"}])
    result = prepare_form(str(src))
    if result.get("ok"):
        return _envelope("SUCCESS", result)
    return _envelope("FAILED", result, [{
        "code": result.get("error", "PREPARE_FAILED"),
        "message": result.get("detail", result.get("error", ""))}])


def call_catalog_ai_search(request: dict[str, Any]) -> dict[str, Any]:
    """AI 의미 검색 — 자연어 → Claude 키워드 해석 → 카탈로그 매칭. §9 준수."""
    from .ai_catalog_search import semantic_search
    result = semantic_search(str(request.get("query") or ""),
                             limit=int(request.get("limit") or 20))
    if result.get("ok"):
        return _envelope("SUCCESS", result)
    return _envelope("FAILED", result, [{
        "code": result.get("error", "AI_SEARCH_FAILED"),
        "message": result.get("error", "")}])


def call_hwpx_layout(request: dict[str, Any],
                     *, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """lineseg 좌표 레이아웃(한컴 없이 원본 배치 재현용). read-only."""
    from .coordinate_layout import build_layout
    result = build_layout(request, project_root=project_root)
    if result.get("verdict") == "PASS":
        return _envelope("SUCCESS", result)
    return _envelope("FAILED", result, [{
        "code": result.get("reason", "LAYOUT_REJECTED"),
        "message": result.get("reason", ""),
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

    class HwpxLayoutRequest(BaseModel):
        sourcePath: str

    class AiFillRequest(BaseModel):
        fields: list[dict[str, Any]] = []
        sourceData: dict[str, Any] | None = None

    class SourceExtractRequest(BaseModel):
        imagePath: str
        docType: str | None = None

    class CatalogSearchRequest(BaseModel):
        query: str = ""
        limit: int = 20

    class CatalogMatchRequest(BaseModel):
        fingerprint: str | None = None
        fieldLabels: list[str] = []
        limit: int = 5

    class CatalogByCategoryRequest(BaseModel):
        domain: str
        limit: int = 40

    class CatalogAiSearchRequest(BaseModel):
        query: str = ""
        limit: int = 20

    class PrepareFormRequest(BaseModel):
        formId: int | None = None
        sourcePath: str | None = None


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

    @app.post("/api/web-office/hwpx-upload")
    async def hwpx_upload(file: UploadFile = File(...)) -> dict[str, Any]:
        """브라우저 파일선택/드래그로 올린 HWPX 를 sandbox 에 받아 로드.
        누구나 자기 파일을 업로드해 볼 수 있다(서버는 사용자 경로 미접근)."""
        content = await file.read()
        return call_hwpx_upload(file.filename or "", content)

    @app.post("/api/web-office/cell-save-apply")
    def cell_save_apply(req: CellSaveApplyRequest) -> dict[str, Any]:
        return call_cell_save_apply(req.model_dump())

    @app.post("/api/web-office/hwpx-layout")
    def hwpx_layout(req: HwpxLayoutRequest) -> dict[str, Any]:
        return call_hwpx_layout(req.model_dump())

    @app.post("/api/web-office/ai-fill")
    def ai_fill(req: AiFillRequest) -> dict[str, Any]:
        return call_ai_fill(req.model_dump())

    @app.post("/api/web-office/source-extract")
    def source_extract(req: SourceExtractRequest) -> dict[str, Any]:
        return call_source_extract(req.model_dump())

    @app.get("/api/web-office/download/{filename}")
    def download(filename: str):
        """편집본(sandbox) HWPX 다운로드. 경로 안전: output_dir 밖 접근 차단."""
        out_dir = _api_output_dir().resolve()
        target = (out_dir / filename).resolve()
        if not str(target).startswith(str(out_dir)) or not target.is_file():
            return JSONResponse(status_code=404, content={"error": "OUTPUT_NOT_FOUND"})
        return FileResponse(str(target), filename=Path(filename).name,
                            media_type="application/octet-stream")

    @app.get("/api/web-office/catalog-stats")
    def catalog_stats() -> dict[str, Any]:
        return call_catalog_stats()

    @app.post("/api/web-office/catalog-search")
    def catalog_search(req: CatalogSearchRequest) -> dict[str, Any]:
        return call_catalog_search(req.model_dump())

    @app.post("/api/web-office/catalog-match")
    def catalog_match(req: CatalogMatchRequest) -> dict[str, Any]:
        return call_catalog_match(req.model_dump())

    @app.get("/api/web-office/catalog-categories")
    def catalog_categories() -> dict[str, Any]:
        return call_catalog_categories()

    @app.post("/api/web-office/catalog-by-category")
    def catalog_by_category(req: CatalogByCategoryRequest) -> dict[str, Any]:
        return call_catalog_by_category(req.model_dump())

    @app.post("/api/web-office/catalog-ai-search")
    def catalog_ai_search(req: CatalogAiSearchRequest) -> dict[str, Any]:
        return call_catalog_ai_search(req.model_dump())

    @app.post("/api/web-office/prepare-form")
    def prepare_form_ep(req: PrepareFormRequest) -> dict[str, Any]:
        return call_prepare_form(req.model_dump())

    if FRONTEND_DIR.is_dir():
        app.mount(
            "/web-office",
            StaticFiles(directory=str(FRONTEND_DIR), html=True),
            name="web-office",
        )

    return app


app = create_app()
