# Web Office Backend Full Function Audit

Date: 2026-05-25
Task: WEB-OFFICE-BACKEND-FULL-FUNCTION-AUDIT-55
Status: AUDIT COMPLETE WITH ONE BASELINE-AUDIT FINDING
Baseline tag: baseline/web-office-sandbox-20260525
Baseline commit: f1f55b8

## 1. Purpose

This report audits the current Web Office backend function surface after the
backend structure standard was locked.

The audit did not change backend code, route contracts, source fixtures, or
production write behavior.

## 2. Classification Legend

- ACTIVE_VERIFIED: implemented and verified by local tests or runtime smoke.
- ACTIVE_PARTIAL: implemented for a constrained scope, with known limits.
- SMOKE_ONLY: covered by smoke/runtime verification but not full unit matrix.
- TEST_ONLY: helper or scenario path mainly exercised from tests.
- BLOCKED: intentionally blocked by safety or scope gate.
- LEGACY_OR_HOLD: retained for earlier pipeline context, not current active API.
- UNCLEAR_REVIEW_REQUIRED: insufficient evidence for activation.

## 3. Backend Function Inventory

| Area | Primary files | Classification | Evidence |
| --- | --- | --- | --- |
| API health/load/save route | `scripts/hwpx/web_office/editor_api_route.py` | ACTIVE_VERIFIED | `call_health`, `call_hwpx_load`, `call_cell_save_apply`, FastAPI static mount tests, runtime smoke |
| Real HWPX editor load bridge | `scripts/hwpx/web_office/editor_file_bridge.py` | ACTIVE_VERIFIED | real fixture load, safe project-relative path policy, render/document model payload tests |
| Browser command save bridge | `scripts/hwpx/web_office/save_apply_bridge.py` | ACTIVE_VERIFIED | commandLog validation, project-relative `.hwpx` source policy, output path hidden at API route |
| Cell save pipeline | `scripts/hwpx/web_office/cell_save_pipeline.py` | ACTIVE_VERIFIED | real writer apply, verify7, readback, source hash/mtime preservation |
| Cell dry-run plan | `scripts/hwpx/web_office/cell_edit_plan.py` | ACTIVE_VERIFIED | expectedBefore/hash/target validation through cell save tests |
| Cell verify7 | `scripts/hwpx/web_office/cell_save_verify7.py` | ACTIVE_VERIFIED | V1-V7 gate tests when fixture is available |
| Cell save audit writer | `scripts/hwpx/web_office/cell_save_audit.py` | ACTIVE_VERIFIED | audit append test through cell verify7 suite |
| RO-view importer | `scripts/hwpx/web_office/ro_view_importer.py` | ACTIVE_VERIFIED | shared parser for load, save readback, paragraph E2E selection |
| Document model | `scripts/hwpx/web_office/document_model.py` | ACTIVE_VERIFIED | used by importer/render payload; covered through load and E2E paths |
| Render payload builder | `scripts/hwpx/web_office/render_payload.py` | ACTIVE_VERIFIED | load bridge payload contract tests |
| Edit command model | `scripts/hwpx/web_office/edit_command_model.py` | ACTIVE_VERIFIED | browser save command tests and cell pipeline tests |
| Paragraph command model | `scripts/hwpx/web_office/para_edit_model.py` | ACTIVE_VERIFIED | paragraph save/E2E command construction tests |
| Paragraph normalizer | `scripts/hwpx/web_office/para_edit_normalizer.py` | ACTIVE_PARTIAL | supporting module; indirect coverage through paragraph command paths |
| Paragraph dry-run plan | `scripts/hwpx/web_office/paragraph_edit_plan.py` | ACTIVE_VERIFIED | paragraph validation tests for type/replace/delete/hash/before mismatch |
| Paragraph save pipeline default path | `scripts/hwpx/web_office/paragraph_save_pipeline.py` | ACTIVE_PARTIAL | default `allow_writer=False` returns partial dry-run gate and does not create output |
| Paragraph save pipeline writer path | `scripts/hwpx/web_office/paragraph_save_pipeline.py` | ACTIVE_VERIFIED for constrained scope | `allow_writer=True` E2E tests cover cell containerScope, single-run type/replace/delete output/readback |
| Paragraph writer adapter | `scripts/hwpx/web_office/paragraph_writer_adapter.py` | ACTIVE_PARTIAL | constrained to supported cell/body scope cases; multi-run/body unsupported paths remain guarded |
| Paragraph verify7 | `scripts/hwpx/web_office/paragraph_save_verify7.py` | ACTIVE_VERIFIED for constrained scope | paragraph save and E2E tests cover preservation/readback gates where fixture available |
| Paragraph save audit writer | `scripts/hwpx/web_office/paragraph_save_audit.py` | ACTIVE_VERIFIED | audit append test in paragraph save suite |
| Paragraph E2E pipeline | `scripts/hwpx/web_office/para_edit_e2e_pipeline.py` | ACTIVE_VERIFIED for constrained scope | type/replace/delete E2E tests and closeout tests when fixture is available |
| Browser/static serving | `frontend/web_office_viewer/*` mounted by backend | SMOKE_ONLY | route/static serving tests and browser smoke from prior baseline |

## 4. Active API Boundary

The current public backend surface remains:

- `GET /api/web-office/health`
- `POST /api/web-office/hwpx-load`
- `POST /api/web-office/cell-save-apply`
- static frontend mount at `/web-office/`

No production write API, upload API, arbitrary local file API, or direct browser
HWPX write API is active.

## 5. Verification Results

Commands executed from the repository root:

```powershell
python -m pytest tests\test_web_office_writer_readback_backend_api_route.py tests\test_web_office_writer_readback_real_file_load_save_bridge.py tests\test_web_office_writer_readback_save_apply_bridge.py tests\test_hwpx_backend_rwedit_baseline.py -q
```

Result: `11 passed`

```powershell
python -m pytest tests\test_web_office_cell_save_hwpx_verify7.py -q
```

Result: `1 passed, 12 skipped`

```powershell
python -m pytest tests\test_web_office_para_edit_save_verify7.py tests\test_web_office_para_edit_e2e_integration.py -q
```

Result: `5 passed, 28 skipped`

```powershell
python scripts\ops\verify_web_office_editor_backend_runtime_smoke.py
```

Result: `PASS_HWPX_EDITOR_BACKEND_RUNTIME_SMOKE`

Runtime smoke checks that passed:

- health endpoint success
- real HWPX load success
- load includes cells
- safe project-relative source path
- cell save success
- backend writer verdict PASS
- output created in sandbox
- verify7 PASS
- public API hides `outputPath`
- output file exists
- readback matches edit value
- source hash and mtime unchanged
- absolute paths hidden from public response
- absolute source path rejected

## 6. Full Selected Regression Result

The combined selected regression command:

```powershell
python -m pytest tests\test_web_office_writer_readback_backend_api_route.py tests\test_web_office_writer_readback_real_file_load_save_bridge.py tests\test_web_office_writer_readback_save_apply_bridge.py tests\test_hwpx_backend_rwedit_baseline.py tests\test_web_office_cell_save_hwpx_verify7.py tests\test_web_office_para_edit_save_verify7.py tests\test_web_office_para_edit_e2e_integration.py tests\test_web_office_para_edit_e2e_full_closeout.py -q
```

Result: `1 failed, 21 passed, 44 skipped`

Failure:

- `tests/test_web_office_para_edit_e2e_full_closeout.py::test_audit_script_pass`
- audit script: `scripts/ops/audit_web_office_para_edit_e2e_full_closeout.py`
- reason: `LOCKED_FILE_CHANGED` against old baseline `619f2e0`
- affected locked paths reported by that audit:
  - `scripts/hwpx/web_office/ro_view_importer.py`
  - `scripts/hwpx/web_office/document_model.py`

Interpretation:

This is a stale prior-closeout baseline finding, not a current API load/save
runtime failure. `git diff` shows no working tree edits for those files at the
current baseline; the audit compares current HEAD against an older commit
`619f2e0`. The current runtime smoke and active backend API tests pass.

## 7. Findings

### FINDING-01: Prior closeout audit baseline is stale

Severity: MEDIUM

The paragraph E2E full closeout audit still locks selected files against
baseline `619f2e0`. Current HEAD includes later accepted changes to
`ro_view_importer.py` and `document_model.py`, so the audit reports
`LOCKED_FILE_CHANGED`.

Required decision:

- either update the closeout audit baseline after a separate approval standard,
- or keep it as a known failing historical lock until paragraph closeout is
reopened.

### FINDING-02: Local corpus-dependent tests are partially skipped

Severity: LOW

Several cell and paragraph tests depend on `data/recognition_corpus/corpus.sqlite3`
and local HWPX corpus availability. In this workspace, many such tests were
skipped. The fixed fixture API path and runtime smoke still passed.

Required decision:

- keep current fixture-dependent behavior,
- or create a deterministic checked-in paragraph/cell fixture set for broader
always-on coverage.

## 8. Current Backend Status

The Web Office backend is suitable to remain locked as a sandbox-only baseline
for:

- health/load/save route serving
- real HWPX load into editor payload
- browser commandLog to backend cell save
- sandbox output creation
- cell verify7/readback validation
- source immutability checks
- public path redaction
- constrained paragraph E2E writer/readback paths

The backend is not yet suitable to unlock for:

- production write
- arbitrary user upload/source selection
- direct browser-side HWPX writing
- unbounded paragraph editing
- multi-run paragraph editing
- final deployment mode

## 9. Commit Recommendation

Commit this audit report as documentation evidence.

Do not update the stale paragraph closeout audit baseline in the same commit.
That should be a separate approved task because it changes the meaning of a
prior lock gate.
