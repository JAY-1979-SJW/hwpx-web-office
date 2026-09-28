"""Audit drift between the Web Office app structure document and repo reality."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
APP_STRUCTURE_DOC = ROOT / "docs" / "architecture" / "web_office_app_structure_20260525.md"
BACKEND_STANDARD_DOC = ROOT / "docs" / "architecture" / "web_office_backend_structure_standard_20260525.md"
API_ROUTE = ROOT / "scripts" / "hwpx" / "web_office" / "editor_api_route.py"
LOAD_BRIDGE = ROOT / "frontend" / "web_office_viewer" / "real_file_load_save_bridge.mjs"
SAVE_BRIDGE = ROOT / "frontend" / "web_office_viewer" / "save_apply_bridge.mjs"

PASS_VERDICT = "PASS_WEB_OFFICE_APP_STRUCTURE_DRIFT_AUDIT"
FAIL_VERDICT = "FAIL_WEB_OFFICE_APP_STRUCTURE_DRIFT_AUDIT"

REQUIRED_PATHS = [
    "frontend/web_office_viewer/index.html",
    "frontend/web_office_viewer/editor_ui_bridge.mjs",
    "frontend/web_office_viewer/cell_edit_state.mjs",
    "frontend/web_office_viewer/para_edit_state.mjs",
    "frontend/web_office_viewer/edit_command.mjs",
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/format_charpr_matcher.mjs",
    "frontend/web_office_viewer/real_file_load_save_bridge.mjs",
    "frontend/web_office_viewer/save_apply_bridge.mjs",
    "scripts/hwpx/web_office/editor_api_route.py",
    "scripts/hwpx/web_office/editor_file_bridge.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    "scripts/hwpx/web_office/render_payload.py",
    "scripts/hwpx/web_office/document_model.py",
    "scripts/hwpx/web_office/save_apply_bridge.py",
    "scripts/hwpx/web_office/cell_save_pipeline.py",
    "scripts/hwpx/web_office/cell_save_verify7.py",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/ops/verify_web_office_editor_backend_runtime_smoke.py",
    "scripts/ops/verify_web_office_server_monitor.py",
    "scripts/ops/deploy_web_office_to_server.ps1",
    "scripts/ops/install_web_office_server_monitor_cron.py",
    "scripts/ops/start_web_office_server_monitor.ps1",
    "scripts/ops/stop_web_office_server_monitor.ps1",
]

REQUIRED_ENDPOINTS = [
    "GET /api/web-office/health",
    "POST /api/web-office/hwpx-load",
    # WEB-OFFICE-UPLOAD-01: 브라우저 파일선택/드래그 업로드(sandbox 수신, 내용해시
    # 저장, 사용자 경로 미접근). 통제된 업로드 — 확장자/zip/크기 검증 후 로드.
    "POST /api/web-office/hwpx-upload",
    "POST /api/web-office/cell-save-apply",
    # WEB-OFFICE-PARA-EDIT-SAVE-01: 문단 편집 저장(§4.2 header/footer 텍스트,
    # §4.3 editInPlace 포함) - cell-save-apply 와 동일 계약의 문단판.
    "POST /api/web-office/para-save-apply",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-01: 서식 속성 변경(§4.1 조건부 허용,
    # 기존 charPr 매칭 또는 append-only 신규 charPr).
    "POST /api/web-office/apply-format",
    # WEB-OFFICE-AI-FILL-PLAN-01: AI 자동채움 계획 수립(§4.5 드라이 런) - 기입 전
    # 단계, ai-fill 과 별개 엔드포인트.
    "POST /api/web-office/fill-plan",
    # WEB-OFFICE-COORD-LAYOUT-01: lineseg 좌표 레이아웃(한컴 없이) 엔드포인트.
    "POST /api/web-office/hwpx-layout",
    # WEB-OFFICE-TRUTH-01: 한컴 실렌더 페이지 배경('원본 그대로' 하이브리드
    # 표시). 한컴 미설치 환경은 404 → 좌표 렌더 폴백.
    "GET /api/web-office/truth-page",
    # WEB-OFFICE-AI-FILL-01: AI 자동채움(§9 Claude Code CLI Haiku) · 사업자등록증 OCR.
    "POST /api/web-office/ai-fill",
    "POST /api/web-office/source-extract",
    # WEB-OFFICE-CATALOG-01: 서식 카탈로그 검색/매칭/분류(read-only SQLite).
    "GET /api/web-office/catalog-stats",
    "GET /api/web-office/catalog-categories",
    "GET /api/web-office/catalog-institutions",
    "POST /api/web-office/catalog-search",
    "POST /api/web-office/catalog-match",
    "POST /api/web-office/catalog-by-category",
    "POST /api/web-office/catalog-ai-search",
    # WEB-OFFICE-CONVERT-01: 온디맨드 서식 준비(HWP→한컴 COM 변환) + 산출물 다운로드.
    "POST /api/web-office/prepare-form",
    "GET /api/web-office/download/{filename}",
]

REQUIRED_SERVER_TOKENS = [
    "haehan-app",
    "/home/ubuntu/apps/hwpx-web-office",
    "http://127.0.0.1:8767/api/web-office/health",
    "hwpx-web-office-monitor",
]

REQUIRED_HOLD_TOKENS = [
    "production write",
    "direct browser HWPX package parsing",
    "direct browser HWPX writing",
    "uncontrolled user file upload",
    "arbitrary source path selection",
    "endpoint expansion",
]


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _check(findings: list[dict[str, Any]], code: str, ok: bool, detail: str) -> None:
    if not ok:
        findings.append({"code": code, "detail": detail})


def _route_decorators(source: str) -> set[str]:
    routes: set[str] = set()
    for method, path in re.findall(r'@app\.(get|post)\("([^"]+)"\)', source):
        routes.add(f"{method.upper()} {path}")
    return routes


def audit() -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    app_doc = _read(APP_STRUCTURE_DOC)
    backend_doc = _read(BACKEND_STANDARD_DOC)
    api_source = _read(API_ROUTE)
    load_bridge = _read(LOAD_BRIDGE)
    save_bridge = _read(SAVE_BRIDGE)

    _check(findings, "APP_STRUCTURE_DOC_MISSING", bool(app_doc), _rel(APP_STRUCTURE_DOC))
    _check(findings, "BACKEND_STANDARD_DOC_MISSING", bool(backend_doc), _rel(BACKEND_STANDARD_DOC))
    _check(findings, "API_ROUTE_MISSING", bool(api_source), _rel(API_ROUTE))

    for path in REQUIRED_PATHS:
        _check(findings, "REQUIRED_PATH_MISSING", (ROOT / path).is_file(), path)
        _check(findings, "REQUIRED_PATH_NOT_DOCUMENTED", path in app_doc, path)

    routes = _route_decorators(api_source)
    for endpoint in REQUIRED_ENDPOINTS:
        _check(findings, "ENDPOINT_NOT_DOCUMENTED", endpoint in app_doc, endpoint)
        _check(findings, "ENDPOINT_NOT_IN_BACKEND_STANDARD", endpoint in backend_doc, endpoint)
        _check(findings, "ENDPOINT_NOT_IMPLEMENTED", endpoint in routes, endpoint)

    unexpected_routes = sorted(route for route in routes if route not in REQUIRED_ENDPOINTS)
    for route in unexpected_routes:
        findings.append({"code": "UNEXPECTED_ENDPOINT_IMPLEMENTED", "detail": route})

    _check(findings, "STATIC_MOUNT_MISSING", 'app.mount(' in api_source and '"/web-office"' in api_source, "app.mount /web-office")
    _check(findings, "MODE_NOT_SANDBOX_ONLY", 'MODE = "SANDBOX_ONLY"' in api_source, _rel(API_ROUTE))
    _check(findings, "SOURCE_MUTATION_NOT_BLOCKED", '"sourceMutationAllowed": False' in api_source, _rel(API_ROUTE))
    _check(findings, "OUTPUT_PATH_STRIP_MISSING", 'safe.pop("outputPath", None)' in api_source, _rel(API_ROUTE))
    _check(findings, "LOAD_BRIDGE_ENDPOINT_DRIFT", '"/api/web-office/hwpx-load"' in load_bridge, _rel(LOAD_BRIDGE))
    _check(findings, "SAVE_BRIDGE_ENDPOINT_DRIFT", '"/api/web-office/cell-save-apply"' in save_bridge, _rel(SAVE_BRIDGE))

    for token in REQUIRED_SERVER_TOKENS:
        _check(findings, "SERVER_BASELINE_TOKEN_MISSING", token in app_doc, token)
    for token in REQUIRED_HOLD_TOKENS:
        _check(findings, "HOLD_TOKEN_MISSING", token in app_doc, token)

    verdict = PASS_VERDICT if not findings else FAIL_VERDICT
    return {
        "schemaVersion": "web_office_app_structure_drift_audit_v1",
        "verdict": verdict,
        "appStructureDoc": _rel(APP_STRUCTURE_DOC),
        "backendStandardDoc": _rel(BACKEND_STANDARD_DOC),
        "requiredPaths": len(REQUIRED_PATHS),
        "implementedEndpoints": sorted(routes),
        "findings": findings,
        "summary": {
            "failures": len(findings),
            "unexpectedEndpoints": len(unexpected_routes),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    payload = audit()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
