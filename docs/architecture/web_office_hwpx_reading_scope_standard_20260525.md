# Web Office HWPX Reading Scope Standard

Date: 2026-05-25
Status: ACTIVE STANDARD
Task: WEB-OFFICE-HWPX-READING-SCOPE-STANDARD-20260525
Baseline lock: `baseline/web-office-operational-20260525`

## 1. Purpose

This standard defines what "HWPX read support" means for the current Web Office
baseline.

The main rule is:

> Basic HWPX load/read is verified. Full HWPX specification compatibility is not
> yet claimed. UI reproduction remains a separate coverage target.

This distinction prevents treating successful file load as complete HWPX
rendering or complete HWPX semantic coverage.

## 2. Reading Levels

### Level R1: Package and XML Access

Meaning:

- HWPX package can be opened by the backend.
- Required internal XML parts can be accessed.
- The backend can reject unsafe source path forms.

Current status: VERIFIED for the locked sandbox baseline.

Evidence:

- `/api/web-office/hwpx-load` returns `SUCCESS` on the verified server fixture.
- Absolute source paths are rejected by backend tests.
- Server health reports `SANDBOX_ONLY` and `sourceMutationAllowed=false`.

### Level R2: Basic Document Model Extraction

Meaning:

- The backend can extract the current Web Office document model needed by the
  browser editor.
- Table/cell-oriented content is available for the current editor workflow.
- Paragraph data needed by constrained paragraph tests is available in the
  supported paths.

Current status: VERIFIED WITH SCOPE LIMITS.

Evidence:

- `scripts/hwpx/web_office/ro_view_importer.py`
- `scripts/hwpx/web_office/document_model.py`
- `scripts/hwpx/web_office/render_payload.py`
- backend route and runtime smoke tests
- Web Office server health and structure drift pass

### Level R3: UI Render Payload

Meaning:

- Extracted backend model can be transformed into browser-facing payload.
- Browser UI can render the supported editor state.

Current status: PARTIAL.

Verified:

- real HWPX load into editor payload
- table/cell display data used by current browser workflow
- success/failure/loading state handling

Not yet complete:

- full page layout reproduction
- complete style fidelity
- image, shape, chart, formula, footnote, endnote, header/footer visual
  reproduction
- Hancom-like visual parity

### Level R4: Full HWPX Semantic Read Compatibility

Meaning:

- Every relevant HWPX element is parsed, represented, and preserved
  semantically.
- Unsupported elements are inventoried and reported explicitly.
- Coverage is measured across a representative corpus, not only one fixture.

Current status: NOT CLAIMED.

This level requires a separate coverage audit before it can be marked verified.

## 3. Current Approved Claim

The approved statement for the locked baseline is:

> Web Office supports verified sandbox HWPX load/read for the current backend
> document model and UI payload. It does not yet claim complete HWPX
> specification read compatibility or complete UI visual reproduction.

Do not use the following statement:

> HWPX read is complete.

Approved shorter wording:

> Basic HWPX read is verified; full compatibility and UI fidelity remain open.

## 4. Current Supported Read Surface

Supported in the locked baseline:

- safe project-relative HWPX source path loading
- backend package/XML read path
- current document model extraction for Web Office
- table/cell-oriented editor payload
- constrained paragraph data paths used by existing tests
- public response path redaction
- source immutability during load/save flows
- sandbox-only runtime health verification

## 5. Current Non-Claims

The locked baseline does not claim:

- complete HWPX XML schema coverage
- complete section/page layout reconstruction
- complete style cascade fidelity
- complete font, color, border, fill, line, spacing, and paragraph property
  reproduction
- complete header/footer, footnote, endnote, annotation, field, control,
  equation, chart, drawing, shape, image, OLE, or embedded object support
- complete browser-side HWPX package read
- arbitrary user-upload HWPX compatibility
- HWP/HWP binary compatibility
- Hancom-equivalent visual rendering

## 6. Required Future Audit Before Upgrading the Claim

To upgrade from R2/R3 partial support to R4 full compatibility, a future task
must produce a coverage audit with:

- representative HWPX corpus manifest
- package part inventory
- XML element inventory
- document model field coverage
- UI render coverage
- unsupported element list
- error and fallback behavior
- per-fixture pass/fail matrix
- final percentage or category coverage summary

Required output artifacts:

- machine-readable coverage JSON
- human-readable coverage report
- tests or gates that fail when claimed coverage regresses

## 7. Pass Criteria for Current Baseline

The current baseline remains valid when:

- `/api/web-office/hwpx-load` returns `SUCCESS` for the verified safe fixture
- runtime mode remains `SANDBOX_ONLY`
- `sourceMutationAllowed == false`
- structure drift audit passes
- server monitor reports `HEALTHY`
- security log audit reports zero suspicious signals
- `systemctl --failed` reports zero failed units
- documentation continues to distinguish basic read support from full HWPX
  compatibility

## 8. Change Control

Any change that expands the read claim must update this standard and include
new coverage evidence.

Any UI claim must state whether it is:

- data extraction support,
- browser payload support,
- visual rendering support, or
- full visual fidelity support.

These are separate claims and must not be merged into one "read complete"
statement.
