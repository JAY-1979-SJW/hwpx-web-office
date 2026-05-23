# HWPX Frontend Runtime vs Smoke Boundary Standard 02

Date: 2026-05-24

Current HEAD: `7a0824d`

Process:
- `HWPX-FRONTEND-RUNTIME-VS-SMOKE-BOUNDARY-STANDARD-02`

## 1. Purpose

This standard classifies the current frontend surface in `frontend/web_office_viewer/` by role.

The goal is not to move files now.
The goal is to freeze how frontend files should be interpreted:
- runtime surface
- smoke surface
- self-test surface
- reusable component surface
- prototype or experimental support surface
- sample or support artifact surface

## 2. Baseline

This standard depends on:
- `docs/architecture/hwpx_work_execution_operating_rules_20260524.md`
- `docs/reports/HWPX_APP_CURRENT_STATE_STANDARD_20260524.md`
- `docs/reports/HWPX_APP_ARCHITECTURE_CLASSIFICATION_STANDARD_01.md`

Current repo head for this standard:
- `7a0824d`

## 3. Current Frontend Diagnosis

The current frontend tree contains multiple roles in one directory family:
- browser-facing runtime helpers
- smoke pages
- E2E verification surfaces
- self-test scripts
- reusable components
- editor or viewer primitives
- sample payload support artifacts

This is acceptable for the current validation-focused repository phase, but it is not yet a clean role-separated frontend structure.

Current strengths:
- many files are already partially self-describing by name
- smoke files use `smoke`
- self-test files use `self_test` or similar patterns
- reusable components are already separated into `components/`

Current risks:
- runtime entry and smoke entry can be confused
- top-level browser files are too visually flat
- experimental helpers and reusable runtime helpers are not yet clearly separated

## 4. Frontend Role Classes

The frontend area is classified into the following six role classes.

### 4.1 Runtime surface

Definition:
- files that directly support viewer/editor/browser runtime behavior

Allowed responsibilities:
- rendering
- browser state updates
- UI interaction handling
- safe API payload display
- runtime helper logic

Prohibited responsibilities:
- audit generation
- repo governance decisions
- file classification policy
- production write orchestration
- raw path or raw filename disclosure

Representative examples:
- `viewer_core.mjs`
- `para_edit_runtime.mjs`
- `edit_command.mjs`
- `para_edit_command.mjs`

### 4.2 Smoke surface

Definition:
- files used to verify browser rendering, route wiring, batch rendering, or E2E state handling

Allowed responsibilities:
- smoke rendering
- test-server or mock-server API interaction
- UI state validation
- visible verification surfaces for contracts

Prohibited responsibilities:
- becoming the default production-facing entrypoint
- being treated as reusable runtime primitives
- carrying business governance rules that belong in backend gates

Representative examples:
- `form_autofill_browser_smoke.html`
- `form_autofill_browser_smoke.mjs`
- `form_autofill_real_like_batch_smoke.html`
- `form_autofill_real_like_batch_smoke.mjs`
- `render_smoke.mjs`
- `runtime_smoke.mjs`
- `para_edit_apply_format_smoke.mjs`
- `para_edit_structure_smoke.mjs`

### 4.3 Self-test surface

Definition:
- files that let a developer quickly probe one localized frontend behavior

Allowed responsibilities:
- local verification
- narrow behavioral probe
- isolated edit-state or runtime-state checking

Prohibited responsibilities:
- acting as user-facing entrypoints
- acting as general-purpose shared component modules

Representative examples:
- `cell_edit_self_test.mjs`
- `para_edit_self_test.mjs`
- `para_edit_browser_self_test.mjs`

### 4.4 Reusable component surface

Definition:
- shared UI blocks that may be composed into larger browser surfaces

Allowed responsibilities:
- display logic
- props-based state projection
- composable UI behavior

Prohibited responsibilities:
- smoke-only hardcoded scenarios
- backend governance decisions
- direct embedding of audit assumptions

Representative examples:
- `components/FormAutoFillWorkspace.tsx`
- `components/WebOfficeViewer.tsx`
- `components/WebOfficePayloadSummary.tsx`
- `components/WebOfficeParagraphEditor.tsx`

### 4.5 Prototype or experimental runtime support

Definition:
- lower-level browser helpers or experimental editor/viewer runtime files that are not pure reusable component surfaces

Allowed responsibilities:
- primitive runtime editing support
- formatting helpers
- state normalizers
- feature-probe helpers

Prohibited responsibilities:
- policy enforcement that belongs to gates
- permanent report generation
- product governance logic

Representative examples:
- `format_charpr_matcher.mjs`
- `para_edit_normalizer.mjs`
- `cell_edit_state.mjs`
- `para_edit_state.mjs`

### 4.6 Sample or support artifacts

Definition:
- safe sample payloads and lightweight support resources used for local verification

Allowed responsibilities:
- sample rendering input
- local safe payload reference
- support shell resource

Prohibited responsibilities:
- real user data
- PII-bearing payloads
- source-path-bearing payloads

Representative examples:
- `payload.sample.json`
- `index.html`

## 5. Entrypoint Standard

Frontend entrypoints must be interpreted by type.

### 5.1 Runtime entry

A runtime entry is a browser surface intended to host actual viewer/editor behavior.

Current rule:
- runtime entry files must not be confused with smoke pages
- runtime entry naming should avoid `smoke` and `self_test`

### 5.2 Smoke entry

A smoke entry is a verification surface.

Current rule:
- files containing `smoke` in the name are smoke entry candidates
- smoke entries must stay visibly smoke-specific

### 5.3 Self-test entry

A self-test entry is a local probe surface.

Current rule:
- self-test files must remain developer-only support surfaces
- they must not be promoted implicitly into production-like entry status

### 5.4 Non-entry component or helper

Current rule:
- files in `components/` are non-entry by default
- helper `.mjs` files without page semantics are non-entry by default

## 6. Naming Standard

Frontend naming must communicate role.

### 6.1 Required naming signals

- smoke surfaces should contain `smoke`
- self-test surfaces should contain `self_test`, `self-test`, or an equally explicit probe signal
- sample artifacts should contain `sample` where practical
- reusable components should use stable role-oriented names

### 6.2 Naming prohibitions

Avoid:
- generic names for smoke files that look like production entrypoints
- hidden test-only behavior inside generic runtime filenames
- sample payloads named like real business payloads

## 7. Placement Standard

Current placement rules inside the existing frontend tree:

### 7.1 `components/`

Reserved for:
- reusable component surfaces

Not for:
- smoke pages
- self-test entry files
- audit-only helpers

### 7.2 Top-level `frontend/web_office_viewer/`

Currently contains mixed roles, but they should still be interpreted by class:
- runtime helper files
- smoke entry files
- self-test entry files
- support artifacts

Future separation direction:
- smoke entry files should become candidates for a dedicated smoke-oriented sub-area
- self-test files should become candidates for a dedicated self-test-oriented sub-area

## 8. File Role Matrix

### 8.1 Runtime-oriented files

- `viewer_core.mjs`
- `edit_command.mjs`
- `para_edit_command.mjs`
- `para_edit_runtime.mjs`
- `cell_edit_state.mjs`
- `para_edit_state.mjs`
- `para_edit_normalizer.mjs`

### 8.2 Smoke-oriented files

- `form_autofill_browser_smoke.html`
- `form_autofill_browser_smoke.mjs`
- `form_autofill_real_like_batch_smoke.html`
- `form_autofill_real_like_batch_smoke.mjs`
- `render_smoke.mjs`
- `runtime_smoke.mjs`
- `para_edit_apply_format_smoke.mjs`
- `para_edit_ime_live_smoke.mjs`
- `para_edit_structure_smoke.mjs`
- `format_charpr_matcher_smoke.mjs`

### 8.3 Self-test-oriented files

- `cell_edit_self_test.mjs`
- `para_edit_self_test.mjs`
- `para_edit_browser_self_test.mjs`

### 8.4 Reusable components

- `components/FormAutoFillWorkspace.tsx`
- `components/WebOfficeCellEditor.tsx`
- `components/WebOfficeFormatPreview.tsx`
- `components/WebOfficeFormatToolbar.tsx`
- `components/WebOfficeParagraphBlock.tsx`
- `components/WebOfficeParagraphEditor.tsx`
- `components/WebOfficePayloadSummary.tsx`
- `components/WebOfficeTableBlock.tsx`
- `components/WebOfficeViewer.tsx`

### 8.5 Sample/support artifacts

- `payload.sample.json`
- `index.html`

## 9. Prohibited Mixing

The following mixtures are structurally discouraged and should be avoided in future work:

1. smoke-specific browser logic hidden inside reusable runtime helpers
2. self-test scripts being treated as canonical browser entrypoints
3. component files carrying smoke-only mock assumptions
4. frontend files carrying repo governance or audit-only logic
5. support payloads being treated as real-user or production data

## 10. Future Separation Priority

This standard does not move files, but it defines future priority.

Priority 1:
- separate smoke entry files from general frontend runtime files

Priority 2:
- separate self-test entry files from general runtime helpers

Priority 3:
- distinguish prototype helpers from long-lived runtime helpers

Priority 4:
- reduce top-level flatness in `frontend/web_office_viewer/`

## 11. Security Boundary

Frontend role classification remains subordinate to the current application safety baseline.

Mandatory frontend-safe conditions:
- `SANDBOX_ONLY`
- no raw path in DOM
- no raw filename in DOM
- no PII payload exposure
- no production write surface
- no source overwrite surface
- no final deploy surface

Any frontend file that weakens these rules should be treated as both a structural and security defect.

## 12. Pass Criteria

This standard is acceptable when:
- frontend role classes are defined
- entrypoint classes are defined
- naming and placement rules are explicit
- runtime vs smoke distinction is explicit
- future separation priority is explicit
- no raw path, raw filename, or PII appears in the document

## 13. Final Statement

This document freezes how the current frontend tree should be interpreted before any actual frontend directory reorganization begins.

It is a boundary contract, not a refactor.
