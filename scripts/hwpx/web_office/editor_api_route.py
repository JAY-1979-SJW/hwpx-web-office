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
from .para_save_apply_bridge import apply_para_save_request
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


_INPLACE_OK_VERDICTS = {"PASS", "PARTIAL", "DRY_RUN_OK"}


def _apply_in_place_if_requested(
    result: dict[str, Any], *, source_rel: str, project_root: Path,
) -> str:
    """대표님 지시(2026-07-24 정책 개정) — "원본을 직접 수정하는 방식으로
    해야 한다"(원본 무수정 원칙의 명시적 폐기, 이 기능 한정).

    검증(verify7 등)은 기존 그대로 sandbox 출력에 대해 수행한 뒤,
    PASS/PARTIAL/DRY_RUN_OK 로 확인된 결과물만 원본 파일에 그대로
    덮어쓴다 — "검증 안 된 내용을 원본에 바로 쓰는" 것이 아니라
    "검증까지 끝난 결과를 원본에 반영"하는 순서를 지킨다. 반환값은
    다음 편집이 이어받을 sourcePath(원본 그대로, 새 사본 아님).
    """
    out_path_str = result.get("outputPath")
    if not out_path_str or result.get("verdict") not in _INPLACE_OK_VERDICTS:
        return source_rel
    out_path = Path(out_path_str)
    if not out_path.is_file():
        return source_rel
    # §4.4 — 읽기 전용 자산(카탈로그 템플릿 등)은 절대 in-place 로 덮지
    # 않는다. 원본 직접 수정은 사용자 소유 문서에만 허용한다. 여기서 막지
    # 않으면 카탈로그 서식(채움의 원천 라이브러리)이 편집 저장 한 번에
    # 사라진다. 사본(out_path)은 지우지 않고 그대로 돌려준다.
    from .read_only_zones import is_read_only, zone_of
    if is_read_only(source_rel):
        result["editedInPlace"] = False
        result["inPlaceRefused"] = "READ_ONLY_ZONE"
        result["readOnlyZone"] = zone_of(source_rel)
        return source_rel
    src_path = (project_root / source_rel).resolve()
    import shutil
    shutil.copyfile(out_path, src_path)
    try:
        out_path.unlink()
    except OSError:
        pass
    result["outputPath"] = str(src_path)
    result["editedInPlace"] = True
    return source_rel


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
    if request.get("editInPlace") and result.get("verdict") in {
            "PASS", "DRY_RUN_OK", "NOOP"}:
        _apply_in_place_if_requested(
            result, source_rel=request.get("sourcePath"),
            project_root=project_root)
    public_result = _strip_public_paths(result)
    if result.get("verdict") in {"PASS", "DRY_RUN_OK", "NOOP"}:
        return _envelope("SUCCESS", public_result)
    return _envelope("FAILED", public_result, [{
        "code": result.get("reason", result.get("verdict", "SAVE_REJECTED")),
        "message": result.get("reason", result.get("verdict", "")),
    }])


def call_para_save_apply(
    request: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """문단 편집 저장 — 브라우저 편집기가 쓰는 경로.

    셀 저장(/cell-save-apply)은 SET_CELL_TEXT 만 받는다. 브라우저는 문단
    명령(TYPE_TEXT 등)을 만들므로 별도 경로가 필요하다.
    """
    out_dir = output_dir if output_dir is not None else _api_output_dir()

    def _load(rel: str) -> dict[str, Any]:
        env = call_hwpx_load(
            {"operation": "HWPX_EDITOR_LOAD", "sourcePath": rel},
            project_root=project_root)
        return (env or {}).get("data") or {}

    result = apply_para_save_request(
        request, project_root=project_root, output_dir=out_dir,
        load_document=_load)
    if request.get("editInPlace") and result.get("verdict") in {
            "PASS", "PARTIAL", "PARTIAL_DRY_RUN_OK", "DRY_RUN_OK", "NOOP"}:
        _apply_in_place_if_requested(
            result, source_rel=request.get("sourcePath"),
            project_root=project_root)
    public_result = _strip_public_paths(result)
    if result.get("verdict") in {"PASS", "PARTIAL", "PARTIAL_DRY_RUN_OK",
                                 "DRY_RUN_OK", "NOOP"}:
        # 다음 편집이 이어받을 sourcePath — editInPlace 면 원본 그대로
        # (같은 경로에 이미 반영됨), 아니면 기존처럼 새 sandbox 산출물로
        # 체이닝. writer 미실행(NOOP/DRY_RUN)이면 outputPath 가 없어
        # sourcePath 도 원본 그대로 둔다.
        #
        # 실측(2026-07-24)으로 발견한 결함: editedInPlace 분기에서
        # public_result["sourcePath"] 를 아예 안 채우고 있었다 — 응답에
        # sourcePath 자체가 없으니 프런트의 "if (d.sourcePath) { 재로딩 }"
        # 가드가 통째로 건너뛰어져, 저장 후 documentModel 이 갱신되지
        # 않고 영원히 예전 상태로 남았다(화면에 "겹침"으로 나타난 결함의
        # 근본 원인 — 좌표는 새로 받아오는데 문단 텍스트만 옛날 것).
        if result.get("editedInPlace"):
            public_result["sourcePath"] = request.get("sourcePath")
        elif result.get("outputCreated") and result.get("outputPath"):
            out_path = Path(result["outputPath"])
            public_result["sourcePath"] = out_path.resolve().relative_to(
                project_root.resolve()).as_posix()
        return _envelope("SUCCESS", public_result)
    return _envelope("FAILED", public_result, [{
        "code": result.get("reason", result.get("verdict", "SAVE_REJECTED")),
        "message": str(result.get("reason") or result.get("verdict") or ""),
    }])


def call_apply_format(
    request: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """서식(글꼴/크기/색상/굵게/기울임/밑줄) 편집 — CLAUDE.md §4.1.

    브라우저는 overrides(무엇을 바꿀지)만 보낸다. 실제 charPr id 해석
    (기존 매칭 탐색 또는 append-only 신규 생성)은 서버가 담당한다 —
    클라이언트가 임의 id 를 지정하면 검증(신규 charPr 생성 정책)을
    우회할 수 있다.
    """
    from .editor_file_bridge import _resolve_project_hwpx
    from .apply_format_bridge import resolve_and_apply_format

    try:
        source_path, source_rel = _resolve_project_hwpx(
            project_root, request.get("sourcePath"))
    except ValueError as exc:
        return _envelope("FAILED", {"verdict": "REJECTED"}, [{
            "code": "INVALID_SOURCE_PATH", "message": str(exc)}])

    paragraph_id = request.get("paragraphId")
    overrides = request.get("overrides")
    if not paragraph_id or not isinstance(overrides, dict) or not overrides:
        return _envelope("FAILED", {"verdict": "REJECTED"}, [{
            "code": "INVALID_REQUEST",
            "message": "paragraphId 와 overrides(비어있지 않은 dict) 필요"}])

    out_dir = output_dir if output_dir is not None else _api_output_dir()
    out_path = out_dir / f"applyformat_{uuid.uuid4().hex[:12]}.hwpx"
    try:
        result = resolve_and_apply_format(
            source_path=source_path, output_path=out_path,
            paragraph_id=str(paragraph_id),
            range_anchor=int(request.get("rangeAnchor", 0)),
            range_focus=int(request.get("rangeFocus", 0)),
            overrides=overrides,
            tmp_dir=out_dir,
        )
    except ValueError as exc:
        return _envelope("FAILED", {"verdict": "REJECTED"}, [{
            "code": "APPLY_FORMAT_ERROR", "message": str(exc)}])

    if result.get("verdict") != "PASS":
        return _envelope("FAILED", _strip_public_paths(result), [{
            "code": "APPLY_FORMAT_REJECTED",
            "message": str(result.get("rejected") or result.get("verdict"))}])

    public = _strip_public_paths(result)
    if request.get("editInPlace") and out_path.is_file():
        # 대표님 지시(2026-07-24 정책 개정) — 검증까지 끝난 sandbox 결과를
        # 원본 파일에 그대로 덮어쓴다. sourcePath 는 원본 그대로 유지.
        import shutil
        shutil.copyfile(out_path, source_path)
        try:
            out_path.unlink()
        except OSError:
            pass
        public["sourcePath"] = source_rel
        public["editedInPlace"] = True
    else:
        # 다음 편집이 이어받을 새 sourcePath(sandbox 산출물) — 원본은 무수정.
        new_rel = out_path.resolve().relative_to(
            project_root.resolve()).as_posix()
        public["sourcePath"] = new_rel
    return _envelope("SUCCESS", public)


def call_fill_plan(request: dict[str, Any],
                   *, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """채움 계획 — 무엇을 자동으로 넣고 무엇을 물어볼지.

    프로필은 요청이 실어 보낸다(서버에 저장하지 않는다). 개인정보를 서버가
    보관하지 않는 설계라 주민등록번호 같은 고유식별정보 처리 책임이 생기지
    않는다. 값을 만들어내지 않으며, 모르는 칸은 질문 목록으로만 돌려준다.
    """
    from .form_fill_planner import plan_fill
    from .form_input_schema import build_input_schema
    rel = request.get("sourcePath")
    if not isinstance(rel, str) or not rel:
        return _envelope("FAILED", {"verdict": "REJECTED",
                                    "reason": "SOURCE_PATH_MISSING"},
                         [{"code": "SOURCE_PATH_MISSING", "message": "sourcePath 필요"}])
    env = call_hwpx_load({"operation": "HWPX_EDITOR_LOAD", "sourcePath": rel},
                         project_root=project_root)
    data = (env or {}).get("data") or {}
    if data.get("verdict") != "PASS":
        return env
    schema = build_input_schema(data["documentModel"], data["renderPayload"],
                                name=request.get("name") or Path(rel).name,
                                field_count=None)
    plan = plan_fill(schema["inputs"], request.get("profile") or {},
                     history=request.get("history") or {})
    return _envelope("SUCCESS", {
        "docType": schema["docType"],
        "formKind": schema["formKind"],
        "cleanName": schema["cleanName"],
        "inputCount": schema["inputCount"],
        "applicantCount": schema["applicantCount"],
        "officeCount": schema["officeCount"],
        "sensitiveCount": schema["sensitiveCount"],
        "autoFill": plan["autoFill"],
        "questions": plan["questions"],
        # 관계자(관공서) 칸 — 민원인이 채우지 않는다. 뷰어에서 구분 표시하고
        # 사용자가 '내 칸/남의 칸'을 알 수 있게 목록을 실어 보낸다(예전엔
        # 버려서 패널이 못 봤다). 좌표만 주고 값은 없다.
        "skipped": [{"label": s.get("label"), "paragraphId": s.get("paragraphId"),
                     "role": s.get("role"), "tableIndex": s.get("tableIndex"),
                     "row": s.get("row"), "col": s.get("col")}
                    for s in plan.get("skipped", [])],
        "autoFillCount": plan["autoFillCount"],
        "questionCount": plan["questionCount"],
        "officeCount": len(plan.get("skipped", [])),
        "coverage": round(plan["coverage"], 3),
    })


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
    return _envelope("SUCCESS", search(
        str(request.get("query") or ""),
        limit=int(request.get("limit") or 20),
        institution=request.get("institution") or None))


def call_catalog_institutions() -> dict[str, Any]:
    """기관/부처 목록(서식 수 포함) — 카탈로그 UI 필터용."""
    from .catalog_search import institutions
    return _envelope("SUCCESS", institutions())


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
        # 대표님 지시(2026-07-24 정책 개정) — True 면 검증 통과한 결과를
        # sandbox 사본이 아니라 원본 파일에 직접 반영한다.
        editInPlace: bool = False

    class FillPlanRequest(BaseModel):
        sourcePath: str
        name: str | None = None
        profile: dict[str, Any] = {}
        history: dict[str, str] = {}

    class ParaSaveApplyRequest(BaseModel):
        operation: str
        sourcePath: str
        sourceDocumentHash: str | None = None
        commandLog: list[dict[str, Any]] = []
        requestId: str | None = None
        dryRunOnly: bool = False
        editInPlace: bool = False

    class HwpxLayoutRequest(BaseModel):
        sourcePath: str

    class ApplyFormatRequest(BaseModel):
        sourcePath: str
        paragraphId: str
        rangeAnchor: int = 0
        rangeFocus: int = 0
        overrides: dict[str, Any] = {}
        editInPlace: bool = False

    class AiFillRequest(BaseModel):
        fields: list[dict[str, Any]] = []
        sourceData: dict[str, Any] | None = None

    class SourceExtractRequest(BaseModel):
        imagePath: str
        docType: str | None = None

    class CatalogSearchRequest(BaseModel):
        query: str = ""
        limit: int = 20
        institution: str | None = None

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

    # 정적 자원(no-cache) — 브라우저가 .mjs/.html 을 휴리스틱 캐시해 코드
    # 갱신이 화면에 반영되지 않는 문제를 차단한다. no-cache 는 매 요청
    # 재검증(304 활용)이라 성능 손실은 미미하고 항상 최신 코드가 실린다.
    @app.middleware("http")
    async def _static_no_cache(request, call_next):
        resp = await call_next(request)
        if request.url.path.startswith("/web-office"):
            resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp

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

    @app.post("/api/web-office/fill-plan")
    def fill_plan(req: FillPlanRequest) -> dict[str, Any]:
        return call_fill_plan(req.model_dump())

    @app.post("/api/web-office/para-save-apply")
    def para_save_apply(req: ParaSaveApplyRequest) -> dict[str, Any]:
        return call_para_save_apply(req.model_dump())

    @app.post("/api/web-office/hwpx-layout")
    def hwpx_layout(req: HwpxLayoutRequest) -> dict[str, Any]:
        return call_hwpx_layout(req.model_dump())

    @app.post("/api/web-office/apply-format")
    def apply_format(req: ApplyFormatRequest) -> dict[str, Any]:
        return call_apply_format(req.model_dump())

    @app.post("/api/web-office/ai-fill")
    def ai_fill(req: AiFillRequest) -> dict[str, Any]:
        return call_ai_fill(req.model_dump())

    @app.post("/api/web-office/source-extract")
    def source_extract(req: SourceExtractRequest) -> dict[str, Any]:
        return call_source_extract(req.model_dump())

    @app.get("/api/web-office/truth-page")
    def truth_page(src: str, page: int = 1):
        """한컴 실렌더 페이지 PNG — '원본 그대로' 표시 모드 배경.

        src 는 프로젝트-상대 .hwpx 만 허용(경로 탈출 차단). 한컴 미설치/
        실패 시 404 → 뷰어는 좌표(로직) 렌더로 폴백한다."""
        from .hancom_layout_refresh import render_truth_pages
        root = PROJECT_ROOT.resolve()
        req = Path(str(src))
        if req.is_absolute():
            return JSONResponse(status_code=404,
                                content={"error": "ABS_PATH"})
        cand = (root / req).resolve()
        if root not in cand.parents or cand.suffix.lower() != ".hwpx" \
                or not cand.is_file():
            return JSONResponse(status_code=404,
                                content={"error": "NOT_FOUND"})
        out_dir = render_truth_pages(cand, project_root=root)
        if out_dir is None:
            return JSONResponse(status_code=404,
                                content={"error": "TRUTH_UNAVAILABLE"})
        png = out_dir / f"p{int(page)}.png"
        if not png.is_file():
            return JSONResponse(status_code=404,
                                content={"error": "PAGE_OUT_OF_RANGE"})
        # 원본 직접 수정(§4.3) 이후 sourcePath 가 편집마다 바뀌지 않고
        # 그대로 유지되므로, 브라우저가 이 URL(?src=<같은 경로>)을 예전
        # 응답(수정 전 사진)으로 캐시해버리면 편집 후에도 낡은 배경 위에
        # 새 텍스트가 겹쳐 보이는 "겹침"이 생긴다(실측 확인 — 화면에서
        # 같은 줄이 두 번 보이던 결함의 원인). out_dir 자체가 내용 해시
        # 기준이라 서버 캐시는 정확하지만, 브라우저 HTTP 캐시가 문제이므로
        # 명시적으로 매번 재검증하도록 강제한다.
        return FileResponse(str(png), media_type="image/png",
                            headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

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

    @app.get("/api/web-office/catalog-institutions")
    def catalog_institutions() -> dict[str, Any]:
        return call_catalog_institutions()

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
