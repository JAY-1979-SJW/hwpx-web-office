# HWPX Editor Frontend Backend Wire Baseline 47

Date: 2026-05-25

## Scope

This baseline freezes the frontend-to-backend contract for the HWPX browser
editor. It does not approve a full visual editor UI yet.

The frontend may only:

- call `POST /api/web-office/hwpx-load`
- unwrap the backend API envelope
- build editor state from `data.documentModel`
- create browser-side `SET_CELL_TEXT` commandLog entries
- call `POST /api/web-office/cell-save-apply`
- unwrap the backend save envelope

The frontend must not write HWPX files, choose local output paths, call writer
modules, or expose absolute local paths.

## PASS Conditions

1. Load endpoint is fixed to `/api/web-office/hwpx-load`
2. Save endpoint is fixed to `/api/web-office/cell-save-apply`
3. Load request includes `operation=HWPX_EDITOR_LOAD` and project-relative `sourcePath`
4. Load response accepts backend envelope shape: `status=SUCCESS`, `data.verdict=PASS`
5. Editor state is created only from `data.documentModel`
6. Cell edit produces `SET_CELL_TEXT` in `commandLog`
7. Save request includes `operation`, `sourcePath`, `sourceDocumentHash`, `commandLog`
8. Save response accepts backend envelope shape: `status=SUCCESS`, `data.verdict=PASS`
9. Frontend bridge has no direct writer, filesystem, output path, or HWPX package logic
10. Backend runtime smoke 46 still passes

## Verification Commands

```powershell
node frontend/web_office_viewer/real_file_load_save_bridge_self_test.mjs
python -m pytest tests/test_web_office_browser_smoke_frontend_backend_wire_baseline.py -q
python scripts/ops/verify_web_office_editor_backend_runtime_smoke.py
```

Expected verdicts:

```text
HWPX-EDITOR-FRONTEND-BACKEND-WIRE-47 PASS
PASS_HWPX_EDITOR_BACKEND_RUNTIME_SMOKE
```

## Promotion Rule

Actual UI wiring can proceed only after this baseline passes. UI work must call
the fixed backend routes through the bridge modules governed here.
