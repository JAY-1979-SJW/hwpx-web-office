# HWPX Repo Inventory Classification

- verdict: PASS_HWPX_REPO_INVENTORY_CLASSIFICATION
- baseline: 8c51000
- scope: tracked_files_only
- total files: 932
- legacy experiment files: 147
- unknown review required files: 1
- security: pii=0 rawPath=0 rawFilename=0

## Categories
- ACTIVE_AUTOFILL: 18
- ACTIVE_HWPX_CORE: 184
- AUDIT_GATE: 118
- CONFIG_BUILD: 2
- FRONTEND_VIEWER: 28
- LEGACY_EXPERIMENT: 147
- REPORT_DOC: 269
- TEST_FIXTURE: 2
- TEST_ONLY: 163
- UNKNOWN_REVIEW_REQUIRED: 1

## Zones
- batch_api_browser: 9
- browser_ui: 28
- closeout_security: 145
- docs_reports: 269
- download_export: 4
- hwpx_core: 207
- input_parse: 12
- review_approval: 4
- test_support: 30
- unassigned: 220
- writer_readback: 4

## Next Separation
- classification only; do not move or delete files
- review LEGACY_EXPERIMENT and UNKNOWN_REVIEW_REQUIRED before any split
- protect ACTIVE_AUTOFILL, AUDIT_GATE, and FRONTEND_VIEWER with fail-fast gates
- archive only after import and test impact review
