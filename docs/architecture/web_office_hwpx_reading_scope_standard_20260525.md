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

## 3A. Terminology Lock

The following terms have fixed meanings in this project:

| Term | Meaning | Current status |
| --- | --- | --- |
| Basic read | Backend can open HWPX, access required XML, and build the current Web Office model. | VERIFIED |
| Server API read | `/api/web-office/hwpx-load` returns a safe public payload under sandbox rules. | VERIFIED |
| Model read | Content is represented in `documentModel` for current workflows. | VERIFIED WITH LIMITS |
| UI payload read | Backend model can be converted into browser state. | PARTIAL |
| Visual read | Browser visually reproduces the original document layout. | NOT COMPLETE |
| Semantic full read | HWPX elements are parsed into meaningful internal representation with unsupported items inventoried. | NOT CLAIMED |
| Complete read | Semantic full read plus measured corpus coverage and regression gates. | FORBIDDEN TERM UNTIL R4 PASS |

The word "complete" must not be used for HWPX reading unless all R4 completion
criteria in this document are satisfied.

## 3B. Current Guarantee Matrix

| Capability | Guarantee level | Evidence required now | Current decision |
| --- | --- | --- | --- |
| Open HWPX package | Must work for verified fixture | Server load/health tests | PASS |
| Reject unsafe source path | Must reject absolute path | Backend route tests | PASS |
| Read package XML | Must work for required current paths | Load bridge/importer tests | PASS |
| Extract table/cell model | Must support current editor path | Runtime smoke/readback tests | PASS |
| Extract constrained paragraph model | Must support tested constrained paths | Paragraph tests where fixture exists | PARTIAL PASS |
| Preserve source during read/save | Must not mutate source | Hash/mtime and sandbox tests | PASS |
| Redact internal paths | Must hide raw output path | Route tests/runtime smoke | PASS |
| Render complete page layout | Must visually match original | Visual corpus audit | NOT CLAIMED |
| Render all styles | Must match style cascade | Style coverage audit | NOT CLAIMED |
| Read embedded images/shapes/charts/equations | Must inventory and represent elements | Corpus element audit | NOT CLAIMED |
| Read arbitrary user HWPX | Must pass representative corpus | Corpus matrix | NOT CLAIMED |
| Read HWP binary | Must convert or parse HWP first | Separate HWP pipeline | OUT OF SCOPE |

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

Minimum R4 completion criteria:

- at least one representative corpus with ordinary forms, table-heavy files,
  paragraph-heavy files, style-heavy files, image-bearing files, header/footer
  files, and known unsupported element fixtures
- every package part must be classified as supported, ignored-by-policy, or
  unsupported-with-warning
- every observed HWPX XML element family must be classified as parsed,
  preserved, displayed, ignored-by-policy, or unsupported-with-warning
- unsupported element handling must be deterministic and visible in the audit
  output
- UI fidelity claims must be separated from semantic parse claims
- regression tests must fail if a previously claimed supported category becomes
  unsupported
- the final report must state both coverage by category and residual risk

Until these criteria pass, the only permitted status is:

- `BASIC_READ_VERIFIED_FULL_READ_NOT_CLAIMED`

## 6A. Required Remediation Plan

The following remediation plan is mandatory before the project can upgrade the
HWPX read claim beyond the current baseline.

| Gap | Required remediation | Required artifact | Required gate |
| --- | --- | --- | --- |
| Limited corpus evidence | Build a representative HWPX corpus covering forms, tables, paragraphs, styles, images, headers/footers, and known unsupported cases. | corpus manifest JSON | Corpus manifest audit must pass. |
| Unknown XML element coverage | Inventory every observed package part and XML element family. | element coverage JSON and human report | Unknown elements must be classified before release. |
| Unsupported element visibility | Report unsupported or ignored-by-policy elements deterministically. | unsupported element report | No silent unsupported element loss in audit output. |
| UI fidelity uncertainty | Separate semantic read coverage from visual rendering coverage. | UI fidelity matrix | Visual claims must have screenshot or DOM evidence. |
| Regression risk | Convert newly approved coverage into automated tests. | regression tests and gate logs | Previously supported categories must fail the gate if regressed. |
| Server/local drift | Verify the final result on the server after local validation. | server verification report | Server health, structure drift, and HWPX load smoke must pass. |
| User-facing wording risk | Keep all reports aligned with the approved wording in section 7A. | report wording check | "Complete read" wording must remain blocked until R4 pass. |

Minimum remediation sequence:

1. Create or register the representative corpus.
2. Run package/XML inventory against the corpus.
3. Classify each observed package part and element family.
4. Add deterministic warnings for unsupported categories.
5. Add regression gates for every newly claimed supported category.
6. Run local verification.
7. Deploy or sync to the server only after local verification passes.
8. Run server verification and attach the result to the report.

The server is the final operating reference. A local pass is only a precheck;
the claim must not be upgraded unless the same claim is verified on the server.

## 6B. Current Remediation Audit Gate

The current remediation audit gate is:

- `scripts/ops/audit_web_office_hwpx_read_remediation.py`
- `tests/test_web_office_hwpx_read_remediation_audit.py`

The gate produces:

- `data/reports/web_office_hwpx_read_remediation/reading_remediation_report.json`
- `data/reports/web_office_hwpx_read_remediation/reading_remediation_summary.md`

The gate must verify:

- fixture corpus manifest exists
- checked-in HWPX fixtures are opened as ZIP packages
- XML entries are inventoried
- observed XML element families are classified as parsed for the current model,
  ignored by policy, or unsupported with warning
- unsupported element families are visible in the machine-readable report
- unsupported element families are grouped into impact categories with next
  actions
- Web Office RO model extraction succeeds
- render payload remains read-only
- source HWPX hash and mtime remain unchanged
- the report keeps `fullCompatibilityClaimed=false`
- the status remains `BASIC_READ_VERIFIED_FULL_READ_NOT_CLAIMED`

Passing this gate is not an R4 pass. It is only evidence that the remediation
plan is now executable and that unsupported coverage is no longer silent.

Current remediation audit category output:

- `text_style`
- `border_style`
- `page_layout`
- `numbering_outline`
- `note_annotation`
- `application_settings`
- `metadata_properties`
- `package_metadata`
- `embedded_control`
- `style_catalog`
- `style_compatibility`
- `revision_tracking`

Current `paragraph_layout` remediation status:

- `align`, `lineSpacing`, and `margin` are extracted from `Contents/header.xml`
  `paraPr` definitions into the read-only render payload as `styles.paraPrDefs`.
- margin child values `intent`, `left`, `right`, `prev`, and `next` are exposed
  with their raw HWPX `value` and `relative` attributes.
- `tabPrIDRef`, resolved `tabPr` auto-tab flags, `tabItems`, and
  `tabItemCount` are exposed from the referenced tab stop definition.
- `autoSpacing` is exposed with raw HWPX `eAsianEng` and `eAsianNum`
  attributes.
- `breakSetting` is exposed with raw HWPX line/word break and keep attributes.
- Body inline `lineBreak` elements are preserved as newline text in paragraph
  runs and exposed through the read-only render payload.
- Full visual rendering fidelity of tab stops is still not claimed until UI
  layout comparison fixtures cover the behavior.
- `paragraph_layout` is no longer present in the current unsupported category
  output for the checked-in fixture corpus.

Current `text_style` remediation status:

- `fontRef`, `ratio`, `relSz`, `bold`, `underline`, and `strikeout` are
  extracted from `Contents/header.xml` `charPr` definitions into
  `documentModel.styles.charPrDefs`.
- The read-only render payload exposes `styles.charPrDefs` by default, including
  raw `fontRef`, `ratio`, `relSz`, `underlineDef`, and `strikeoutDef` values
  plus boolean preview fields.
- `spacing` and `shadow` are also preserved from `charPr` definitions in
  `styles.charPrDefs`.
- `hp:fwSpace` is preserved as a fixed space in read-only paragraph/run text,
  including child tail text after the fixed-space marker.
- Header font `typeInfo` is preserved in `documentModel.styles.fontFaceDefs`
  and exposed in the read-only render payload as `styles.fontFaceDefs`.
- `offset` is preserved in `styles.charPrDefs` when it appears under `charPr`,
  but the same local name is still reported under `page_layout` when it appears
  under page border structures.
- `language` is classified as package metadata in the checked-in corpus.
- `case`, `default`, and `switch` are classified as `style_compatibility`
  because their compatibility branch-selection semantics are not yet claimed.
- Current-corpus `text_style` no longer appears as an unsupported category.
  Full text visual fidelity is still not claimed because style cascade,
  compatibility selection, and UI rendering comparison remain open.

Current `table_layout` remediation status:

- Table-level `inMargin` and `outMargin` are extracted from `hp:tbl` elements
  into `documentModel.tables[]` and the read-only render payload.
- Cell-level `cellMargin` is extracted from `hp:tc` elements into
  `documentModel.cells[]` and the read-only render payload.
- `table_layout` is no longer present in the current unsupported category output
  for the checked-in fixture corpus.
- Full table visual fidelity is still not claimed; border, fill, row/column
  sizing, and page layout interactions remain separate coverage targets.

The next implementation priority after the paragraph layout and first text
style/table layout passes is:

1. `style_compatibility`: case, default, switch
2. `page_layout`: colPr, grid, lineNumberShape, pageBorderFill, pagePr, secPr, sz
3. `border_style`: backSlash, border, bottomBorder, diagonal, leftBorder, rightBorder, slash, topBorder

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

Current baseline status value:

- `BASIC_READ_VERIFIED_FULL_READ_NOT_CLAIMED`

This status is intentionally stricter than saying "read complete". It means the
system is good enough for the current sandbox Web Office load workflow, while
remaining honest about missing full compatibility evidence.

## 7A. Required Wording in Reports and User-Facing Notes

Use:

- "Basic HWPX read is verified."
- "Server API load is verified."
- "Current Web Office model extraction is verified with scope limits."
- "Full HWPX compatibility is not claimed."
- "UI visual fidelity remains open."

Do not use:

- "HWPX read is complete."
- "All HWPX files are supported."
- "The UI fully reproduces HWPX."
- "The parser covers the whole HWPX spec."
- "User uploads are fully compatible."

If a short answer is required, use exactly:

> Basic HWPX read is verified; full compatibility and UI fidelity remain open.

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
