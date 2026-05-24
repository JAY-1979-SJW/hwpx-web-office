# HWPX Editor Backend Runtime Smoke Baseline 46

Date: 2026-05-25

## Scope

This baseline freezes the next backend gate for the HWPX browser editor.

The target is not frontend UI. The target is a real backend runtime process:

- start FastAPI/ASGI app from `scripts.hwpx.web_office.editor_api_route:app`
- call HTTP `GET /api/web-office/health`
- call HTTP `POST /api/web-office/hwpx-load`
- call HTTP `POST /api/web-office/cell-save-apply`
- write a sandbox output HWPX
- read the output HWPX back and confirm the edited cell text
- keep the source HWPX hash and mtime unchanged
- keep public HTTP responses free of absolute local paths

## Hard Gates

The runtime smoke is PASS only when all gates pass:

1. `health.status == SUCCESS`
2. `hwpx-load.status == SUCCESS`
3. load response includes `documentModel.cells`, `sourceDocumentHash`, and safe project-relative `sourcePath`
4. save response returns `status == SUCCESS`
5. save response returns `data.verdict == PASS`
6. save response returns `data.outputCreated == true`
7. save response returns `data.verify7Verdict == PASS`
8. save response does not expose `outputPath`
9. sandbox output file exists in the configured runtime output directory
10. readback cell text equals the submitted edit value
11. source fixture SHA-256 and mtime are unchanged
12. absolute source path requests are rejected

## Verification Command

```powershell
python scripts/ops/verify_web_office_editor_backend_runtime_smoke.py
```

Expected terminal verdict:

```text
PASS_HWPX_EDITOR_BACKEND_RUNTIME_SMOKE
```

## Files Governed By This Baseline

- `scripts/hwpx/web_office/editor_api_route.py`
- `scripts/hwpx/web_office/editor_file_bridge.py`
- `scripts/hwpx/web_office/save_apply_bridge.py`
- `scripts/ops/verify_web_office_editor_backend_runtime_smoke.py`
- `tests/test_web_office_writer_readback_backend_runtime_smoke.py`

## Promotion Rule

Frontend UI wiring must not proceed as complete until this backend runtime
baseline passes. The frontend may call only the API routes frozen here.
