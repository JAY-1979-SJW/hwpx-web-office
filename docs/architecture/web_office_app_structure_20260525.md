# Web Office App Structure

Date: 2026-05-25
Status: ACTIVE APP STRUCTURE
Baseline HEAD: `07d4053`

## 1. Purpose

This document records the current Web Office app structure as an operational
map. It is intended to answer where each app responsibility lives, how browser
state reaches the backend, which backend modules may write sandbox outputs, and
which validation commands protect the structure.

This document does not approve production write, arbitrary user upload, direct
browser HWPX package parsing, or direct browser HWPX writing.

HWPX reading scope is defined separately in
`docs/architecture/web_office_hwpx_reading_scope_standard_20260525.md`. The
current app structure verifies basic sandbox load/read for the Web Office
document model and UI payload, but does not claim full HWPX specification
compatibility or complete Hancom-equivalent visual reproduction.

## 2. App Boundary

The Web Office app is a sandbox-only browser editor for HWPX files.

Approved runtime mode:

- `SANDBOX_ONLY`

Public API responses must keep:

- `mode == SANDBOX_ONLY`
- `sourceMutationAllowed == false`
- no public `outputPath`
- no absolute local filesystem path
- no production write capability

Server verification remains the final completion authority for Web Office work.

## 3. Runtime Layers

```text
Browser UI
  frontend/web_office_viewer/index.html
  frontend/web_office_viewer/editor_ui_bridge.mjs
  frontend/web_office_viewer/components/*.tsx

Browser state and command builders
  frontend/web_office_viewer/cell_edit_state.mjs
  frontend/web_office_viewer/para_edit_state.mjs
  frontend/web_office_viewer/edit_command.mjs
  frontend/web_office_viewer/para_edit_command.mjs
  frontend/web_office_viewer/format_charpr_matcher.mjs

Browser API bridges
  frontend/web_office_viewer/real_file_load_save_bridge.mjs
  frontend/web_office_viewer/save_apply_bridge.mjs

Backend HTTP API
  scripts/hwpx/web_office/editor_api_route.py

Backend load/read model
  scripts/hwpx/web_office/editor_file_bridge.py
  scripts/hwpx/web_office/ro_view_importer.py
  scripts/hwpx/web_office/render_payload.py
  scripts/hwpx/web_office/document_model.py

Backend edit/save pipelines
  scripts/hwpx/web_office/save_apply_bridge.py
  scripts/hwpx/web_office/cell_save_pipeline.py
  scripts/hwpx/web_office/cell_save_verify7.py
  scripts/hwpx/web_office/paragraph_save_pipeline.py
  scripts/hwpx/web_office/paragraph_save_verify7.py
  scripts/hwpx/web_office/paragraph_writer_adapter.py
  scripts/hwpx/web_office/para_edit_e2e_pipeline.py

Operational verification
  scripts/ops/verify_web_office_editor_backend_runtime_smoke.py
  scripts/ops/verify_web_office_server_monitor.py --include-structure-drift
  scripts/ops/deploy_web_office_to_server.ps1
  scripts/ops/audit_web_office_app_structure_drift.py
```

## 4. Request Flow

### Load Flow

```text
User clicks Load sample
  -> editor_ui_bridge.mjs
  -> real_file_load_save_bridge.mjs
  -> POST /api/web-office/hwpx-load
  -> editor_api_route.py
  -> editor_file_bridge.py
  -> ro_view_importer.py
  -> render_payload.py
  -> browser editor state
```

Load is limited to safe project-relative source paths. Absolute source paths
must be rejected.

### Cell Save Flow

```text
User edits a cell
  -> cell_edit_state.mjs appends commandLog
  -> save_apply_bridge.mjs builds CELL_SAVE_APPLY
  -> POST /api/web-office/cell-save-apply
  -> editor_api_route.py
  -> save_apply_bridge.py
  -> cell_save_pipeline.py
  -> cell_save_verify7.py
  -> sandbox output file
  -> public response without outputPath
```

The backend may write sandbox output files, but it must not mutate the source
file. The public API response must expose only safe output metadata such as
`outputFileName` and hashes.

### Paragraph Edit Flow

Paragraph edit functionality is represented by the paragraph and para-edit
modules under `scripts/hwpx/web_office`. Browser-side paragraph command state
must not call backend writer modules directly. Backend write execution remains
behind the save pipeline and verify gates.

## 5. Static Serving

The backend may mount the browser app at:

- `GET /web-office/`
- `GET /web-office/*`

The mounted directory is limited to:

- `frontend/web_office_viewer`

Static serving must not expand the API surface or serve files outside that
directory.

## 6. API Surface

The approved Web Office API surface is:

- `GET /api/web-office/health`
- `POST /api/web-office/hwpx-load`
- `POST /api/web-office/cell-save-apply`
- `POST /api/web-office/hwpx-layout` (lineseg 좌표 레이아웃, 한컴 없이 · read-only)

AI 자동채움 / 소스 추출 (WEB-OFFICE-AI-FILL-01, §9 Claude Code CLI Haiku only):

- `POST /api/web-office/ai-fill` (빈 입력칸 값 제안 · AI inject 필수, 자동 실행 금지)
- `POST /api/web-office/source-extract` (사업자등록증 등 소스 이미지 OCR · PII 마스킹)

서식 카탈로그 (WEB-OFFICE-CATALOG-01, read-only SQLite `mode=ro`):

- `GET /api/web-office/catalog-stats`
- `GET /api/web-office/catalog-categories`
- `POST /api/web-office/catalog-search`
- `POST /api/web-office/catalog-match`
- `POST /api/web-office/catalog-by-category`
- `POST /api/web-office/catalog-ai-search` (자연어 → 키워드 해석 후 검색)

온디맨드 서식 준비 / 다운로드 (WEB-OFFICE-CONVERT-01):

- `POST /api/web-office/prepare-form` (HWP→한컴 COM 변환 또는 HWPX 복사 → project sandbox `tmp/web_office_forms/`)
- `GET /api/web-office/download/{filename}` (편집 산출물 다운로드 · sandbox 한정)

Adding, removing, or renaming an endpoint requires a new task standard and
explicit approval.

## 7. Frontend Responsibilities

The browser frontend may:

- render the editor shell
- request a safe backend load
- build in-browser editor state from backend `documentModel`
- collect cell and paragraph commands in an append-only command log
- distinguish loading, success, blocked, and failed states
- submit save/apply requests to fixed backend endpoints

The browser frontend must not:

- parse HWPX ZIP packages directly
- write HWPX files directly
- choose local output paths
- call Python writer modules directly
- expose absolute paths, raw filenames, or PII
- show blocked or failed saves as success

## 8. Backend Responsibilities

The backend may:

- expose the approved API surface
- load safe project-relative fixtures
- create read-only render and document models
- translate browser command logs into backend save requests
- write only sandbox output files
- run verify/readback checks before reporting success
- serve the static frontend directory

The backend must not:

- allow source overwrite
- allow production write
- expose `outputPath` in public API responses
- accept absolute source paths
- bypass verify7/readback gates for save success
- expand runtime mode beyond `SANDBOX_ONLY`

## 9. Operational Files

Server baseline:

- alias: `haehan-app`
- path: `/home/ubuntu/apps/hwpx-web-office`
- health endpoint: `http://127.0.0.1:8767/api/web-office/health`
- monitor marker: `hwpx-web-office-monitor`

Operational scripts:

- `scripts/ops/deploy_web_office_to_server.ps1`
- `scripts/ops/audit_web_office_app_structure_drift.py`
- `scripts/ops/verify_web_office_server_monitor.py`
- `scripts/ops/install_web_office_server_monitor_cron.py`
- `scripts/ops/start_web_office_server_monitor.ps1`
- `scripts/ops/stop_web_office_server_monitor.ps1`
- `scripts/ops/audit_web_office_security_logs.py`

## 10. Validation Commands

Local structure and runtime checks:

```powershell
python -m pytest tests/test_web_office_writer_readback_backend_api_route.py tests/test_web_office_browser_smoke_frontend_backend_wire_baseline.py tests/test_web_office_editor_browser_smoke.py -q
python scripts/ops/audit_web_office_app_structure_drift.py
python scripts/ops/audit_web_office_security_logs.py --no-journal
python scripts/ops/verify_web_office_editor_backend_runtime_smoke.py
python scripts/ops/run_hwpx_repo_commit_guard.py
```

Server final check:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/ops/deploy_web_office_to_server.ps1
```

Minimum direct server check:

```bash
cd /home/ubuntu/apps/hwpx-web-office
python3 scripts/ops/verify_web_office_server_monitor.py --once --port 8767 --include-structure-drift
pgrep -af 'python3 scripts/ops/verify_web_office_server_monitor.py --interval'
crontab -l | grep hwpx-web-office-monitor
```

## 11. Pass Criteria

The app structure is valid when:

- this document matches the checked-in frontend/backend paths
- the approved API surface remains unchanged
- `editor_api_route.py` keeps `SANDBOX_ONLY`
- public save responses hide `outputPath`
- browser bridges use fixed backend endpoints
- app structure drift audit passes
- runtime monitor includes structure drift when requested
- read-only security log audit runs without firewall or allowlist changes
- backend runtime smoke passes
- frontend/backend wire smoke passes
- server deploy verification passes
- operational report artifact records validation and final status

## 12. Hold Items

The following remain on hold:

- production write
- direct browser HWPX package parsing
- direct browser HWPX writing
- uncontrolled user file upload
- arbitrary source path selection
- endpoint expansion beyond the approved API surface
- automatic blocking, firewall changes, or IP/port allowlist changes before a
  separate approved security policy task
