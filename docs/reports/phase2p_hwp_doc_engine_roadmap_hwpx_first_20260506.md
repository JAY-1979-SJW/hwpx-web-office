# PHASE2P HWP/HWPX Parser Completion Roadmap — HWPX-First Architecture
## Strategic Pivot & 12-Phase Implementation Plan

**Generated**: 2026-05-06T10:00:00Z  
**Phase**: PHASE2P Parser Completion (Strategic Roadmap Lock)  
**Work Mode**: Planning & Strategic Design (No Code Changes)  
**Verdict**: 🔵 **ROADMAP_LOCKED_HWPX_FIRST_STRATEGY**

---

## Executive Summary

### Strategic Pivot Rationale

Previous roadmap (P2P1) was centered on **HWP binary → RHWP HTML rendering → table extraction**. This approach faced two fundamental limitations:

1. **HTML rendering variability**: RHWP's `renderPageHtml()` output varies significantly across HWP variants, making reliable cell-level extraction inconsistent
2. **Information loss**: HTML representation loses original table structure metadata, requiring heuristic parsing

**New strategy**: **HWPX XML as primary format**, leveraging:
- ✅ **Structured XML**: `hp:tbl` / `hp:tr` / `hp:tc` / `hp:t` elements preserve exact table semantics
- ✅ **ZIP archive**: HWPX is ZIP+XML, simple and deterministic parsing
- ✅ **Namespace preservation**: XML namespaces (`hp:`) provide unambiguous element identification
- ✅ **Fallback conversion**: HWP → HWPX conversion as upstream stage (preflight), not parser responsibility

### Key Decision Matrix

| Aspect | Previous (RHWP HTML) | New (HWPX XML) |
|--------|---------------------|-----------------|
| **Primary Format** | HWP binary | HWPX (ZIP+XML) |
| **Text Extraction** | @ohah/hwpjs + RHWP fallback | HWPX XML structure |
| **Table Structure** | HTML regex parsing | XML element navigation |
| **Cell Extraction** | HTML table tag analysis | `hp:tr/hp:tc` iteration |
| **Reliability** | Medium (HTML variability) | High (XML schema) |
| **Scope of Parser** | Full HWP handling | HWPX focus only |
| **HWP Handling** | Direct parsing attempt | Convert to HWPX first |

### Completion Criteria

#### HWPX Parser (Primary Deliverable)
- ✅ Parse HWPX (ZIP+XML) structure reliably
- ✅ Extract text via `hp:t` elements
- ✅ Extract tables via `hp:tbl` navigation (12-field rows[][])
- ✅ Structure blocks/paragraphs from section content
- ✅ Auto-split sections where applicable
- ✅ Extract bidding conditions via pattern matching
- ✅ Support template field writing (write-once)
- ✅ Round-trip validation (save/reopen)

#### HWPX Writer (Secondary Deliverable)
- ✅ Modify HWPX XML in-place
- ✅ Write form field values into `hp:t` elements
- ✅ Preserve XML structure and namespaces
- ✅ Support save-and-reopen round-trip
- ✅ Validate modified HWPX on load

#### HWP Handling Policy
- **Primary**: Use `/parse-upload` multipart endpoint if HWP file
- **Fallback 1**: Attempt `@ohah/hwpjs` parser
- **Fallback 2**: Attempt RHWP HTML rendering (current)
- **Fallback 3**: Enqueue for HWP → HWPX conversion service (future phase)

---

## Architectural Overview

### Parser Stack (HWPX-First)

```
Input: file.hwp or file.hwpx
  ↓
[Routing Decision]
  ├─ Extension = .hwpx → [HWPX Parser Direct]
  ├─ Extension = .hwp  → [Try @ohah/hwpjs]
  │                      ↓
  │                   [Success?]
  │                   ├─ Yes → [Output]
  │                   └─ No  → [Try RHWP]
  │                             ↓
  │                          [Success?]
  │                          ├─ Yes → [Output]
  │                          └─ No  → [Queue for HWP→HWPX Conversion]
  └─ Other → [Error: unsupported]

[HWPX Parser Direct]
  ├─ Load ZIP structure
  ├─ Extract content.hpf or section*.xml
  ├─ Parse hp:t elements (text)
  ├─ Parse hp:tbl elements (tables)
  ├─ Parse hp:* block structure
  ├─ Apply conditions extraction
  └─ Output: tables[], blocks[], sections[], conditions[]

[Output]
  ├─ text (full concatenated)
  ├─ text_preview (300 chars)
  ├─ text_length
  ├─ tables[] (12-field rows[][])
  ├─ blocks[] (paragraphs + metadata)
  ├─ sections[] (split sections)
  ├─ conditions[] (bidding condition patterns)
  ├─ parser (hwpx-xml | ohah-hwpjs | rhwp-wasm)
  └─ warnings/errors
```

### Writer Stack (HWPX-Template)

```
Input: file.hwpx + {field_name: value} dict
  ↓
[Load HWPX]
  ├─ Extract ZIP
  ├─ Parse section*.xml
  └─ Locate hp:t elements with matching names
  ↓
[Write Values]
  ├─ Iterate hp:fld:code (form field references)
  ├─ Locate corresponding hp:t elements
  ├─ Write values maintaining XML structure
  ├─ Preserve namespaces and attributes
  └─ Mark modified
  ↓
[Save HWPX]
  ├─ Repackage ZIP
  ├─ Update section*.xml
  ├─ Close and write
  ↓
[Validate Round-Trip]
  ├─ Reopen saved file
  ├─ Verify written values present
  ├─ Verify XML structure intact
  └─ Report success/failure
```

---

## 12-Phase Roadmap

### Phase Structure

Each phase includes:
- **Objective**: What is being completed
- **Scope**: What code/modules are affected
- **Success Criteria**: Measurable completion conditions
- **Effort**: Estimated hours/complexity
- **Dependencies**: What must complete first
- **Next Phase Trigger**: What condition moves to next phase

---

### P2P1: HWPX XML Table Extraction Design ✅ COMPLETED

**Status**: ✅ Completed in prior session

**Objective**: Define `tables[].rows[][]` schema and extraction strategy for HWPX XML

**Deliverables**:
- ✅ 12-field schema definition (table_id, row_count, col_count, source, block_index, rows, cell.text, cell.row, cell.col, cell.rowspan, cell.colspan, cell.is_header)
- ✅ HWPX XML extraction strategy via `/<hp:tbl[^>]*>.*?<\/hp:tbl>/gs`
- ✅ RHWP HTML extraction strategy via `/<table[^>]*>.*?<\/table>/gs` (deferred to post-completion)
- ✅ Partial_success/warning policy documented
- ✅ Test criteria: 14 points across 5 fixtures
- ✅ Blocks integration plan

**Completeness**: 100%  
**Next**: P2P2 (implementation)

---

### P2P2: HWPX XML Table Extraction Implementation

**Objective**: Implement HWPX `hp:tbl` / `hp:tr` / `hp:tc` navigation for `tables[].rows[][]` extraction

**Scope**: 
- `services/hwp-doc-engine/src/parser.ts` — add `extractHwpxTables(xml)` function
- `api/schemas/document.py` — populate `tables` field (currently `[]`)
- Update `_map_hwp_doc_engine_response()` to include `tables`

**Success Criteria**:
- ✅ Parse HWPX XML `hp:tbl` elements
- ✅ Navigate `hp:tr` (rows) and `hp:tc` (cells) hierarchy
- ✅ Extract text via `hp:t` child elements
- ✅ Detect `rowspan`/`colspan` attributes
- ✅ Identify header rows via context or attributes
- ✅ Populate all 12 required fields
- ✅ Return `tables: [{table_id, row_count, col_count, source: "hwpx-xml", rows: [[]]}]`
- ✅ Test: all 5 fixtures pass extraction with non-empty rows[][]
- ✅ Test: table_detected=true correlates with tables.length > 0
- ✅ npm build PASS
- ✅ pytest PASS (including all existing tests)
- ✅ No errors in warnings/errors arrays

**Effort**: 6-8 hours (XML parsing + cell iteration + test fixtures)

**Dependencies**: P2P1 (completed)

**Fixtures**: 
- repair_specimen_form.hwpx (existing)
- Phase2e sample HWPX files (to be confirmed)

**Deployment**: Code committed but NOT DEPLOYED (await P2P12)

**Next Trigger**: Successful test pass on all 5 fixtures with tables[].length > 0

---

### P2P3: HWPX Blocks & Paragraphs Structuring

**Objective**: Structure extracted text into blocks (semantic units) and paragraphs, preserving spatial relationships

**Scope**:
- `services/hwp-doc-engine/src/parser.ts` — add `structureHwpxBlocks(xml)` function
- `api/schemas/document.py` — populate `blocks` field (currently `[]`)

**Success Criteria**:
- ✅ Identify `hp:p` (paragraph) and `hp:tbl` (table) elements as block units
- ✅ Assign block_index based on document order
- ✅ Preserve spatial metadata (page, column, position hints if available)
- ✅ Link tables to block_index for location context
- ✅ Return `blocks: [{block_index, block_type, text, table_id_if_applicable, position_metadata}]`
- ✅ Paragraph count matches expected structural breakdown
- ✅ Test: repair_specimen_form.hwpx yields 20-50 blocks
- ✅ Test: table blocks linked to corresponding tables[]

**Effort**: 5-6 hours (block identification + indexing + linking)

**Dependencies**: P2P2 (tables extraction complete)

**Deployment**: Code committed but NOT DEPLOYED

**Next Trigger**: Block count and table linking verified on all fixtures

---

### P2P4: HWPX Sections Auto-Split

**Objective**: Automatically split HWPX content into logical sections (e.g., 공고, 유의사항, 평가기준) where appropriate

**Scope**:
- `services/hwp-doc-engine/src/parser.ts` — add `splitHwpxSections(blocks)` function
- `api/schemas/document.py` — populate `sections` field (currently `{}`)

**Success Criteria**:
- ✅ Identify section boundaries via heading patterns (e.g., "제1장", "별도기준", etc.)
- ✅ Group blocks into named sections
- ✅ Preserve block_index within sections for reconstruction
- ✅ Return `sections: {section_name: {blocks: [...], tables: [...]}}`
- ✅ Test: repair_specimen_form.hwpx correctly splits into 3-5 sections
- ✅ Test: blocks and tables remain linked across sections

**Effort**: 4-5 hours (heading detection + section grouping)

**Dependencies**: P2P3 (blocks structuring complete)

**Deployment**: Code committed but NOT DEPLOYED

**Next Trigger**: Section boundaries correctly identified on all fixtures

---

### P2P5: HWPX Conditions Extraction Improvement

**Objective**: Enhance condition pattern matching for bidding conditions (region_limit, license_required, award_method, etc.) with HWPX-specific optimizations

**Scope**:
- `services/hwp-doc-engine/src/conditions.ts` — improve pattern matching rules
- `api/services/document_parse_service.py` — update condition mapping

**Success Criteria**:
- ✅ Detect region limits with 90%+ accuracy (e.g., "서울특별시", "경기도")
- ✅ Detect license requirements (e.g., "건설사업관리기술자")
- ✅ Detect award methods (e.g., "최저가", "적격심사", "종합심사")
- ✅ Detect post-settlement clauses (e.g., "사후정산")
- ✅ Detect site explanation requirements
- ✅ Detect joint bidding/split execution clauses
- ✅ Detect A-value mentions
- ✅ Return `conditions: [{condition_key, condition_value, confidence_rule, evidence_text}]`
- ✅ Test: all 5 fixtures yield expected conditions

**Effort**: 4-5 hours (pattern refinement + test iteration)

**Dependencies**: P2P2 or P2P3 (text extraction available)

**Deployment**: Code committed but NOT DEPLOYED

**Next Trigger**: Condition extraction accuracy validated on all fixtures

---

### P2P6: HWP → HWPX Conversion Fallback (Preflight)

**Objective**: Design and validate HWP-to-HWPX conversion as fallback pathway; does NOT implement conversion itself, only design/preflight

**Scope**:
- Evaluate Hancom CLi tools or LibreOffice UNO API
- Document conversion command-line interface
- Test feasibility on 3-5 HWP samples
- Define preflight checklist and success criteria

**Success Criteria**:
- ✅ Identify working conversion tool (Hancom CLI or equivalent)
- ✅ Document conversion command: `hancom convert --input x.hwp --output x.hwpx`
- ✅ Test conversion on 3+ HWP files, validate output HWPX is parseable
- ✅ Document conversion limitations and error handling
- ✅ Design preflight: check for Hancom CLI availability, disk space, temp dir
- ✅ Document output schema: JSON with conversion status, output path, timing
- ✅ Identify service boundaries (conversion as separate async queue vs. inline)

**Deliverables**:
- Design document: HWP→HWPX conversion service architecture
- Preflight checklist: prerequisites, tool versions, resource requirements
- Test report: conversion success rate on sample HWP files

**Effort**: 6-8 hours (tool evaluation + testing + documentation)

**Dependencies**: None (can be done in parallel)

**Deployment**: Design and documentation only; implementation deferred

**Next Trigger**: Conversion service design approved and validated

---

### P2P7: HWP → HWPX Conversion Integration

**Objective**: Integrate conversion service into parser pipeline; route HWP failures to conversion queue

**Scope**:
- `services/hwp-doc-engine/src/parser.ts` — update `parseHwp()` to enqueue conversion on fallback exhaustion
- `api/services/document_parse_service.py` — add conversion queue polling logic

**Success Criteria**:
- ✅ HWP file triggers conversion if @ohah/hwpjs and RHWP both fail
- ✅ Conversion status tracked (pending, processing, complete, failed)
- ✅ Converted HWPX automatically fed to HWPX parser
- ✅ Return `parser: "hwpx-xml-converted-from-hwp"` when conversion succeeds
- ✅ Add `conversion_time_ms` to output metadata
- ✅ Test: HWP files that fail direct parsing are queued and converted
- ✅ Test: Converted HWPX successfully parsed with tables extracted

**Effort**: 5-6 hours (queue integration + status polling)

**Dependencies**: P2P2 (HWPX parser complete), P2P6 (conversion service designed)

**Deployment**: Code committed but NOT DEPLOYED

**Next Trigger**: HWP→HWPX pipeline tested on 3+ samples

---

### P2P8: HWPX Template Field-Write Preflight

**Objective**: Design and validate HWPX in-place modification for form field writing; preflight only

**Scope**:
- Evaluate HWPX ZIP structure modification approach
- Locate form field references in section*.xml (`hp:fld:code` elements)
- Design cell-write algorithm preserving XML structure
- Preflight round-trip validation

**Success Criteria**:
- ✅ Identify form field location in HWPX XML (example: `검토자`, `기술자급수`)
- ✅ Design write algorithm: parse XML → locate hp:t → modify text → serialize XML
- ✅ Document namespace preservation requirements
- ✅ Design round-trip test: write field → save → reopen → verify value present
- ✅ Identify potential XML structure changes that would break compatibility
- ✅ Document backup/rollback strategy for template modification

**Deliverables**:
- Design document: HWPX template field-write architecture
- Preflight validation: 2-3 template samples with different field types
- Round-trip test protocol

**Effort**: 5-6 hours (XML structure analysis + preflight testing)

**Dependencies**: P2P3 or P2P4 (blocks/sections understanding useful but not required)

**Deployment**: Design and documentation only; implementation deferred

**Next Trigger**: Field-write design approved and preflight tests pass

---

### P2P9: HWPX Template Write Smoke Testing

**Objective**: Implement HWPX template field-write and validate on 3+ templates

**Scope**:
- `services/hwp-doc-engine/src/hwpx-writer.ts` — new module for HWPX modification
- `api/services/document_parse_service.py` — add write_hwpx_fields() method

**Success Criteria**:
- ✅ Write single field to HWPX template
- ✅ Write multiple fields in one operation
- ✅ Preserve XML structure and namespaces
- ✅ Handle field names with spaces and Korean characters
- ✅ Generate backup before write
- ✅ Save modified HWPX to new file (default) or in-place (optional)
- ✅ Test: 3+ templates, each with 3-5 field writes
- ✅ Test: All fields remain after save-and-reopen cycle
- ✅ npm build PASS, pytest PASS

**Effort**: 6-7 hours (writer implementation + multi-template smoke test)

**Dependencies**: P2P8 (design complete)

**Deployment**: Code committed but NOT DEPLOYED

**Next Trigger**: All 3+ templates verify written fields survive save/reopen

---

### P2P10: HWPX Save/Reopen Round-Trip Validation

**Objective**: Comprehensive validation that HWPX modifications survive save-and-reopen, with edge cases

**Scope**:
- Test round-trip on templates with:
  - Large field values (1000+ characters)
  - Special characters (한글, 숫자, 기호)
  - Multiple rewrites (write → save → read → write again)
  - Mixed field types (text, numeric, list)

**Success Criteria**:
- ✅ Small field (<100 chars) survives reopen unchanged
- ✅ Large field (1000+ chars) survives reopen unchanged
- ✅ Special characters (한글 etc.) preserved exactly
- ✅ Multiple rewrites succeed without corruption
- ✅ Fields written in different order still survive
- ✅ XML namespaces and structure verified after reopen
- ✅ Test: 5+ round-trip cycles on each of 3 templates
- ✅ Zero data loss or corruption across all tests

**Effort**: 4-5 hours (test design + multi-cycle validation)

**Dependencies**: P2P9 (write implementation complete)

**Deployment**: Test code committed, documentation updated

**Next Trigger**: All round-trip tests pass with zero data loss

---

### P2P11: HWPX Common API Closeout

**Objective**: Final API contract review and documentation for HWPX parser/writer

**Scope**:
- `api/services/document_parse_service.py` — finalize DocumentParseResponse schema
- API documentation: request/response contracts for /parse, /parse-upload, future /write endpoints
- Error handling and status codes standardized

**Success Criteria**:
- ✅ ParseOutput interface complete and documented
- ✅ tables[], blocks[], sections[], conditions[] fields all populated and documented
- ✅ Error codes standardized (hwp_parser_exception, empty_text, invalid_hwp_container, etc.)
- ✅ HTTP status codes mapped (200 success, 400 bad request, 415 unsupported type, 500 server error)
- ✅ Response schema versioned (schemaVersion in all responses)
- ✅ Writer API contract designed (POST /write-fields request/response)
- ✅ API documentation generated

**Effort**: 3-4 hours (documentation + contract review)

**Dependencies**: P2P2 through P2P10 (all implementations complete)

**Deployment**: Documentation committed, no code changes required

**Next Trigger**: API contract approved and documented

---

### P2P12: HWPX Parser/Writer Final Deployment Readiness

**Objective**: Comprehensive preflight before deployment; defer actual deployment to future phase

**Scope**:
- Full smoke test suite: 15+ fixtures across HWP, HWPX, error scenarios
- Performance baseline: parsing speed, table extraction time, write latency
- Security audit: path traversal, XML bomb (billion laughs), external entity injection
- Documentation: setup, configuration, troubleshooting, rollback procedure

**Success Criteria**:
- ✅ All 15+ fixtures parse successfully (text_length > 0, ok=true)
- ✅ Table extraction succeeds where tables present (tables.length > 0)
- ✅ Block structuring correct (blocks.length > 0)
- ✅ Conditions extraction complete (conditions.length > 0 where applicable)
- ✅ Template writing succeeds on 3+ templates
- ✅ Round-trip validation passes (written values persist)
- ✅ Parse time < 2 seconds for typical document (< 5MB)
- ✅ Table extraction < 1 second per 100 cells
- ✅ No XML bomb vulnerabilities (implement entity limit)
- ✅ No path traversal in file operations
- ✅ Deployment documentation complete
- ✅ Rollback procedure tested and documented

**Deliverables**:
- Final preflight report: P2P2-P2P11 completion status
- Performance metrics and baselines
- Security audit results
- Deployment and rollback documentation
- Known limitations and edge cases documented

**Effort**: 6-8 hours (comprehensive testing + documentation)

**Dependencies**: P2P2 through P2P11 (all phases complete)

**Deployment**: 🚫 **DEFERRED** — Code reviewed and documented, but actual deployment blocked pending:
- User sign-off on test results
- Security review approval
- Production readiness assessment

**Next Trigger**: Deployment approval decision (separate from this roadmap)

---

## Items in Hold / Deprecated Status

### 🔴 RHWP HTML Table Extraction (Deferred)

**Status**: ⏸️ **DEFERRED TO POST-COMPLETION SUPPLEMENTARY PHASE**

**Rationale**: 
- HWPX XML extraction provides more reliable cell-level data
- RHWP HTML rendering is fallback-only for HWP binary handling
- Once HWPX completion is solid (P2P1-P2P12), RHWP HTML extraction can be revisited as enhancement

**Reactivation Criteria**:
- P2P12 deployment complete and stable (2+ weeks operational)
- Business requirement for HWP-specific table extraction capabilities
- Resource availability for post-completion work

**Current Status in Code**:
- `detectTableFromRhwpHtml()` regex exists but unused
- `parseWithRhwpFallback()` returns `table_detected=true` but empty `tables[]`
- RHWP extraction code should NOT be written until P2P12 completion

---

### 🔴 Hancom Worker (Deprecated)

**Status**: 🚫 **MAINTAIN DEFUNCT STATUS**

**Rationale**:
- Hancom Worker API is unreliable for headless environments
- HWP→HWPX conversion via CLI tool (P2P6) is more robust
- No active maintenance or new feature support

**Current Status**: Not referenced in active codebase

---

### 🔴 hwp5txt (Linux Support)

**Status**: ⏸️ **LINUX SUPPLEMENTARY CANDIDATE ONLY**

**Rationale**:
- hwp5txt is Linux-only tool with limited Windows support
- Windows deployment (current environment) uses Node.js/TypeScript stack
- Can be revisited if future Linux deployment required

**Current Status**: Not referenced in active codebase

---

## Deployment & Deferral Policy

### ✅ Code Committed, NOT DEPLOYED

**Phases**: P2P2 through P2P11

**Policy**:
- Code is committed and tested in main branch
- npm build PASS, pytest PASS
- Features are **NOT exposed** to users or consumers
- API endpoints remain at previous version
- Feature flags or separate branch deployment **not required** (simpler to maintain)
- Actual deployment deferred to P2P12+ decision gate

**Rationale**:
- Keeps work organized and reviewable
- Prevents incomplete features from reaching users
- Allows incremental verification before deployment
- Clear separation between "implementation complete" and "live in production"

### 🚫 Deployment Deferred Until P2P12+

**Decision Gate**: After P2P12 preflight completion, separate deployment decision required

**Gating Factors**:
1. User sign-off on test results
2. Security review completion
3. Production readiness assessment
4. Performance baseline acceptance

---

## Next Implementation Task

### Task: BID-HWP-DOC-API-P2P2-HWPX-XML-TABLE-EXTRACTION

**Priority**: IMMEDIATE (next after roadmap lock)

**Objective**: 
Implement HWPX XML table extraction via `hp:tbl` / `hp:tr` / `hp:tc` navigation, populating `tables[].rows[][]` with 12 required fields per P2P1 schema.

**Scope**:
- `services/hwp-doc-engine/src/parser.ts` — add `extractHwpxTables(xml)` function
- Update `parseHwpx()` to call new extraction function
- Test on 5 fixtures (repair_specimen_form.hwpx + 4 others)

**Success Criteria** (from P2P2 definition above):
- ✅ tables[].rows[][] populated with exact row/cell data
- ✅ All 12 fields present and correct
- ✅ source="hwpx-xml" 
- ✅ table_detected=true correlates with tables.length > 0
- ✅ npm build PASS, pytest PASS

**Fixtures**:
- `C:\Users\skyjw\OneDrive\문서\카카오톡 받은 파일\HWP 문서\repair_specimen_form.hwpx`
- (+ 4 additional fixtures to be confirmed from phase2e samples)

**Estimated Duration**: 6-8 hours

**Do NOT Deploy After Completion**: Code committed but remains unexposed pending P2P12

---

## Current Status Summary

| Phase | Status | Completeness | Notes |
|-------|--------|--------------|-------|
| **P2P1** | ✅ COMPLETED | 100% | Table schema + extraction strategy designed |
| **P2P2** | 🔵 READY TO START | 0% | Next implementation task |
| **P2P3-P2P11** | ⏳ QUEUED | 0% | Awaiting upstream completion |
| **P2P12** | ⏳ QUEUED | 0% | Final preflight + deployment readiness |
| **Deployment** | 🚫 DEFERRED | N/A | Decision gate after P2P12 |

---

## Risks & Mitigations

### Risk 1: HWPX Format Variations

**Risk**: Different Hancom versions may produce HWPX variants with different XML structures

**Mitigation**:
- P2P2 includes testing on 5 diverse fixtures
- Preflight (P2P12) expands to 15+ fixtures
- Unknown structures logged as warnings, not failures
- Fallback to HWP parsing if HWPX parse fails

### Risk 2: Table Structure Edge Cases

**Risk**: Complex tables (merged cells, nested tables, irregular structures) may not extract cleanly

**Mitigation**:
- rowspan/colspan explicitly detected and populated
- Partial extraction acceptable with warnings (partial_success policy)
- Edge cases documented as known limitations
- RHWP HTML extraction (post-completion) can supplement where needed

### Risk 3: Template Field Modification Corruption

**Risk**: Modifying HWPX XML may corrupt or lose formatting

**Mitigation**:
- P2P8 includes extensive preflight testing
- P2P10 includes 5+ round-trip cycles per template
- Backup created before write
- Zero-tolerance policy for data loss (all tests must pass)

### Risk 4: Conversion Service Availability

**Risk**: HWP→HWPX conversion tool may not be available on all systems

**Mitigation**:
- P2P6 identifies specific tool and requirements
- Preflight (P2P12) documents prerequisites
- Graceful degradation: unsupported HWP files reported as "conversion_pending" status
- Documentation includes setup and troubleshooting

---

## Timeline Estimate

| Phase | Duration | Notes |
|-------|----------|-------|
| **P2P1** | COMPLETED | Prior session |
| **P2P2** | 6-8h | Implementation + 5-fixture testing |
| **P2P3** | 5-6h | Block structuring |
| **P2P4** | 4-5h | Section auto-split |
| **P2P5** | 4-5h | Conditions extraction |
| **P2P6** | 6-8h | Conversion service preflight |
| **P2P7** | 5-6h | Conversion integration |
| **P2P8** | 5-6h | Template write preflight |
| **P2P9** | 6-7h | Template write implementation |
| **P2P10** | 4-5h | Round-trip validation |
| **P2P11** | 3-4h | API closeout |
| **P2P12** | 6-8h | Final deployment readiness |
| **TOTAL** | ~60-75h | Approximately 2-3 weeks (160h capacity) |

---

## Document Info

- **Path**: docs/reports/phase2p_hwp_doc_engine_roadmap_hwpx_first_20260506.md
- **Generated**: 2026-05-06T10:00:00Z
- **Phase**: PHASE2P (Parser Completion Roadmap Lock)
- **Verdict**: ROADMAP_LOCKED_HWPX_FIRST_STRATEGY
- **Work Mode**: Planning & Strategic Design
- **Status**: Ready for implementation start
- **Next Task**: BID-HWP-DOC-API-P2P2-HWPX-XML-TABLE-EXTRACTION

---

## Approval Checklist

- [x] HWPX-first strategy rationale documented
- [x] Completion criteria for parser and writer defined
- [x] HWP fallback policy clarified
- [x] 12-phase implementation roadmap locked
- [x] Hold/deprecated items classified
- [x] Next implementation task (P2P2) identified
- [x] Deployment deferral policy established
- [x] Risks and mitigations documented
- [x] Timeline estimate provided
- [x] Document generated and committed (before STOP)

---

## 최종 판정

### 🔵 VERDICT: ROADMAP_LOCKED_HWPX_FIRST_STRATEGY

**상태**:
- ✅ HWPX-first 아키텍처로 완전히 재정의됨
- ✅ 12-phase 구현 로드맵 확정
- ✅ P2P1 (설계) 완료, P2P2-P2P12 구현 준비 완료
- ✅ RHWP HTML 추출 → 후속 보완 단계로 재분류
- ✅ HWP 처리 정책 (변환 후 파싱) 확정
- ✅ 배포 유예 정책 (P2P12+ 의사결정) 확정

**권장조치**:
1. ✅ 이 로드맵 문서 커밋 (작업 중)
2. ✅ P2P2 구현 작업 시작 (다음 작업)
3. ⏳ P2P2-P2P12 순차적 진행
4. 🚫 P2P12 완료 후 배포 의사결정 필요

