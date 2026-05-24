# HWPX Browser Editor Current State Audit 23

## 1. Current Baseline

- Current HEAD: `3e53b07`
- Scope:
  - `frontend/web_office_viewer/*`
  - `frontend/web_office_viewer/components/*`
  - browser editor related tests
  - related Python web-office editor pipeline references

This audit is a product-state report. It does not authorize implementation,
runtime changes, endpoint changes, or cleanup work.

## 2. Product Surface Summary

The current browser editor surface is split across three layers:

1. read-only viewer surface
2. browser edit-state and edit-command surface
3. smoke, self-test, and E2E verification surface

The implementation is not empty. The paragraph editing line is materially more
advanced than the cell editing line. The product entry surface is still less
clear than the verification surface.

## 3. Read-Only Viewer Status

Primary files:

- `frontend/web_office_viewer/index.html`
- `frontend/web_office_viewer/viewer_core.mjs`
- `frontend/web_office_viewer/components/WebOfficeViewer.tsx`
- `frontend/web_office_viewer/components/WebOfficeParagraphBlock.tsx`
- `frontend/web_office_viewer/components/WebOfficeTableBlock.tsx`
- `frontend/web_office_viewer/components/WebOfficePayloadSummary.tsx`

Observed state:

- `index.html` is explicitly a read-only viewer prototype
- `WebOfficeViewer.tsx` rejects editable payloads
- the current main surface is still viewer-first, not editor-first

Status:

- `USABLE`

## 4. Paragraph Editing Status

Primary files:

- `frontend/web_office_viewer/para_edit_state.mjs`
- `frontend/web_office_viewer/para_edit_command.mjs`
- `frontend/web_office_viewer/para_edit_runtime.mjs`
- `frontend/web_office_viewer/para_edit_normalizer.mjs`
- `frontend/web_office_viewer/components/WebOfficeParagraphEditor.tsx`

Observed state:

- paragraph edit state exists
- command path exists
- composition and range state are modeled
- browser-side runtime handlers exist
- `contenteditable=true` is intentionally forbidden
- the editor is routed through a command/state-machine path

Important limitation:

- browser paragraph editing does not directly perform writer/save/output apply

Related evidence:

- `tests/test_web_office_para_edit_*`
- `scripts/hwpx/web_office/para_edit_model.py`
- `scripts/hwpx/web_office/para_edit_e2e_pipeline.py`

Status:

- `USABLE` for edit-model and command-path validation
- `PARTIAL` for product-grade browser editing workflow

## 5. Cell Editing Status

Primary files:

- `frontend/web_office_viewer/cell_edit_state.mjs`
- `frontend/web_office_viewer/components/WebOfficeCellEditor.tsx`
- `frontend/web_office_viewer/cell_edit_self_test.mjs`

Observed state:

- read-only / select / edit mode transitions exist
- a browser cell editor input exists for `CELL_EDIT`
- commit and cancel callbacks exist

Important limitation:

- evidence for a full browser product workflow is weaker than paragraph editing
- test and model depth appear shallower than paragraph editing

Status:

- `PARTIAL`

## 6. Format Editing Status

Primary files:

- `frontend/web_office_viewer/components/WebOfficeFormatToolbar.tsx`
- `frontend/web_office_viewer/components/WebOfficeFormatPreview.tsx`
- `frontend/web_office_viewer/format_charpr_matcher.mjs`
- `frontend/web_office_viewer/para_edit_apply_format_smoke.mjs`

Observed state:

- format toolbar and preview surface exist
- format matching helpers exist
- validation evidence is heavily smoke-oriented

Status:

- `PARTIAL`
- `SMOKE_ONLY` for some validation paths

## 7. Save and Apply Status

Current evidence shows:

- browser edit surface exists
- command/state handling exists
- validation assets exist

But current browser-side evidence does not show:

- a clearly closed product flow from edit -> save -> apply -> reread

Status:

- `UNCLEAR`

## 8. Verification Surface Status

Verification assets are extensive.

Representative files:

- `render_smoke.mjs`
- `runtime_smoke.mjs`
- `cell_edit_self_test.mjs`
- `para_edit_self_test.mjs`
- `para_edit_browser_self_test.mjs`
- `para_edit_apply_format_smoke.mjs`
- `para_edit_ime_live_smoke.mjs`
- `para_edit_structure_smoke.mjs`
- browser editor structure and architecture tests
- many `tests/test_web_office_para_edit_*`

Interpretation:

- the repository has a stronger verification surface than product-entry surface
- the paragraph editing line is supported by meaningful test and E2E assets

Status:

- `USABLE` as verification infrastructure

## 9. Functional Classification

### 9-1. USABLE

- read-only viewer
- paragraph edit model / state / command validation line
- browser verification surface for paragraph editing

### 9-2. PARTIAL

- paragraph editing as a product-facing browser experience
- cell editing
- format editing

### 9-3. SMOKE_ONLY

- several browser smoke and self-test surfaces
- some formatting and IME/structure validation paths

### 9-4. UNCLEAR

- product-grade browser editor entrypoint
- closed save/apply/reread browser workflow
- cell editing maturity relative to paragraph editing

## 10. Product Blockers

Primary blockers:

1. the editor entry surface is less clear than the smoke/test surface
2. save/apply linkage is not clearly closed at the browser product level
3. cell editing maturity appears behind paragraph editing
4. format editing evidence is still validation-heavy rather than workflow-heavy

## 11. Current Product Judgment

The browser editor is not an empty prototype.

It is more accurate to describe the current state as:

- viewer line: usable
- paragraph editing line: technically advanced and well-verified
- product browser editor: still partially formed
- smoke and self-test assets: stronger than user-facing editor surface

## 12. Recommended Next Work

Recommended next task:

- `HWPX-BROWSER-EDITOR-FUNCTION-GAP-REPORT-24`

Reason:

- the next highest-value step is to convert this audit into a gap report with
  `USABLE / PARTIAL / BLOCKED / SMOKE_ONLY / UNCLEAR` by workflow
- that creates a cleaner priority basis than continuing broad structural audits

## 13. Security Rule

This report must remain PII-safe.

Forbidden:

- real user HWPX input
- PII-containing samples
- raw path disclosure outside approved repository-relative references
- raw filename disclosure that exceeds approved safe references

## 14. Completion Criteria

Pass conditions:

1. browser editor product surface summarized
2. viewer / paragraph / cell / format lines classified
3. verification-vs-product distinction documented
4. blockers documented
5. next task recommended
6. no code changes performed
7. no PII, raw path, or raw filename leak

Final verdict target:

- `PASS_HWPX_BROWSER_EDITOR_CURRENT_STATE_AUDIT`
