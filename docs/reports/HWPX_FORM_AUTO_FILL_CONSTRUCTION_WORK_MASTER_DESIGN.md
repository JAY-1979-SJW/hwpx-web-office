# HWPX Form Auto Fill Construction Work Master Design

Process: HWPX-FORM-AUTO-FILL-CONSTRUCTION-WORK-MASTER-DESIGN

Baseline commit: d95dcac

Design verdict target: PASS_HWPX_FORM_AUTO_FILL_CONSTRUCTION_WORK_MASTER_DESIGN

## Purpose

This document defines the whole-system design for using the completed HWPX form auto-fill line with building construction work documents. It is a design and verification layer only. It does not enable production writing, source overwrite, real user file intake, AI fallback, OCR fallback, final deploy, or any required Hancom dependency.

The current operational boundary stays:

recommend -> parse -> map -> review -> approve -> sandbox write -> readback -> download review -> final export gate -> batch API -> browser E2E.

Every step remains SANDBOX_ONLY and sourceMutationAllowed false.

## Construction Work Scope

Allowed construction-work inputs are sanitized synthetic or sanitized real-like HWPX packages that resemble building construction forms but do not contain real user data.

The design covers these construction document families:

- Building construction start and completion forms
- Construction contract summary forms
- Building permit summary forms
- Supervision and inspection summary forms
- Attachment checklist forms
- Quantity, area, schedule, and cost summary forms
- Review, approval, readback, download, export, batch, API, and browser result boards

This process does not certify legal compliance. External law, local government policy, and submission rule checks must be reviewed separately before real use.

## Construction Data Model

The construction work data model is divided into seven zones. A field can advance only when its zone gate and the shared security gates pass.

### Z01 Project Identity

Representative fields:

- projectName
- siteName
- documentType
- permitNumber
- location
- address
- buildingType

Rules:

- address and location are review-required because they may reveal real sites.
- permitNumber is review-required and can be blocked if it resembles a personal or sensitive identifier.
- raw source path and raw source filename are never stored or displayed.

### Z02 Parties And Roles

Representative fields:

- ownerName
- contractorName
- supervisorName
- designerName
- responsiblePerson
- licenseNumber

Rules:

- person names are review-required and must be masked or synthetic in reports.
- contractorName can proceed only from approved fields.
- licenseNumber requires human approval and PII screening.

### Z03 Schedule And Phase

Representative fields:

- startDate
- endDate
- completionDate
- durationDays
- phase
- inspectionDate

Rules:

- dates must be normalized before writing.
- inconsistent start, end, or completion dates are blocked for review.
- durationDays is generated only when source evidence is approved.

### Z04 Size Quantity Cost

Representative fields:

- amount
- quantity
- floorArea
- buildingArea
- floors
- structureType

Rules:

- amount and quantity fields are review-required.
- unit and format mismatch blocks auto-write.
- source evidence must be retained as masked metadata only.

### Z05 Attachments And Evidence

Representative evidence groups:

- construction contract
- building permit summary
- start report summary
- completion report summary
- supervision report summary
- design drawing index
- building register summary
- license certificate summary

Rules:

- missing required attachment blocks writing.
- attachment names are display names only; raw filenames are prohibited.
- evidence payloads may contain maskedValue or valueHash, never approvedValue raw text.

### Z06 Safety And Compliance Gate

Required checks:

- SANDBOX_ONLY mode
- sourceMutationAllowed false
- output copy only
- output path never equals source path
- targetLocation confidence at least 0.80
- approvedFields at least 1
- missingRequired equals 0
- needsReviewRemaining equals 0
- attachmentsMissing equals 0
- readbackFail equals 0
- sourceMutation equals 0
- unexpectedMutation equals 0
- PII leak equals 0
- raw path leak equals 0
- raw filename leak equals 0

### Z07 Batch API Browser Gate

Required checks:

- limit 1, 5, and 10 supported
- only READY_FOR_SANDBOX_WRITE files are written
- blocked files are not written and include clear reasons
- API health, run, and result endpoints stay SANDBOX_ONLY
- browser buttons send mode SANDBOX_ONLY and sourceMutationAllowed false
- failure states are never rendered as success
- production write, source overwrite, final deploy, AI API, and OCR endpoints are not called

## End To End Architecture

### Input Layer

The input layer accepts only sanitized synthetic or real-like construction samples. A future upload gate must run before any real user file is accepted.

Required input checks:

- package structure valid
- section XML present
- table, cell, and paragraph counts available
- PII risk false
- raw path risk false
- raw filename risk false
- real user file flag false

### Recognition Layer

The recognition layer reads form labels and construction document sections.

Required recognition checks:

- field catalog includes construction-relevant labels
- parser identifies labels, tables, cells, and paragraphs
- mapper resolves targetLocation with confidence at least 0.80
- ambiguous or low-confidence targets are blocked

### Review Layer

The review layer separates auto-fill-ready fields from fields that need human review.

Required review checks:

- auto-fill-ready section visible
- needs-review section visible
- missing-required section visible
- required-attachments section visible
- blocked reasons visible and PII-safe

### Approval Layer

The approval layer is the only path to writer eligibility.

Writer button enabled only when:

- approvalStatus is READY_FOR_WRITER
- writerEligible is true
- approvedFields is at least 1
- missingRequired is 0
- needsReviewRemaining is 0
- attachmentsMissing is 0
- mode is SANDBOX_ONLY

All blocked states keep the writer disabled.

### Writer Layer

The writer layer creates a sandbox copy only.

Required writer checks:

- sourceMutationAllowed false
- source hash unchanged
- source mtime unchanged
- output path does not equal source path
- only approved fields are written
- no production write route is called
- no source overwrite route is called

### Readback Layer

The readback layer confirms that written values match approved safe values.

Required readback checks:

- readbackFail 0 for success
- readback mismatch fails the file
- source mutation fails the file
- output broken fails the file
- failure states are not downloadable as success

### Download And Final Export Layer

The download and final export layer produces review payloads only.

Required export checks:

- download review visible only for safe output copies
- final export enabled only after accepted review state
- final deploy endpoint remains prohibited
- report payloads contain masked identifiers only

### Batch API Browser Layer

The batch API browser layer exposes summarized sandbox batch execution.

Required API/browser checks:

- health endpoint is safe
- run endpoint forces SANDBOX_ONLY
- result endpoint returns sanitized summaries
- batchId may be displayed
- raw path, raw filename, and PII are never returned or rendered

## Gate Map

The construction design is controlled by existing module and zone gates.

| Gate Area | Existing Control | Required Verdict |
| --- | --- | --- |
| Field mapping | module audit | PASS_HWPX_FORM_AUTO_FILL_MODULE_AUDITS |
| Review and approval | module audit | PASS_HWPX_FORM_AUTO_FILL_MODULE_AUDITS |
| Writer and readback | module audit | PASS_HWPX_FORM_AUTO_FILL_MODULE_AUDITS |
| Download and export | module audit | PASS_HWPX_FORM_AUTO_FILL_MODULE_AUDITS |
| Batch API browser | module audit | PASS_HWPX_FORM_AUTO_FILL_MODULE_AUDITS |
| Input parse zone | zone gate | PASS_HWPX_FORM_AUTO_FILL_ZONE_GATES |
| Review approval zone | zone gate | PASS_HWPX_FORM_AUTO_FILL_ZONE_GATES |
| Writer readback zone | zone gate | PASS_HWPX_FORM_AUTO_FILL_ZONE_GATES |
| Download export zone | zone gate | PASS_HWPX_FORM_AUTO_FILL_ZONE_GATES |
| Batch API browser zone | zone gate | PASS_HWPX_FORM_AUTO_FILL_ZONE_GATES |
| Closeout security zone | zone gate | PASS_HWPX_FORM_AUTO_FILL_ZONE_GATES |

## PASS Verdict Baseline

Accepted baseline verdicts:

- PASS_HWPX_FORM_AUTO_FILL_WRITER_USER_FLOW_CLOSEOUT
- PASS_HWPX_FORM_AUTO_FILL_INDIVIDUAL_VERIFICATION
- PASS_HWPX_FORM_AUTO_FILL_MODULE_AUDITS
- PASS_HWPX_FORM_AUTO_FILL_ZONE_GATES

Historical writer line verdicts:

- PASS_HWPX_FORM_AUTO_FILL_WRITER_API_ROUTE_AND_FRONTEND
- PASS_HWPX_FORM_AUTO_FILL_WRITER_BROWSER_SMOKE
- PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_FILE_PREFLIGHT
- PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_SANDBOX_BATCH
- PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_BROWSER_BATCH
- PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_API_BATCH
- PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_API_BROWSER_E2E

## Prohibited Scope

The following remains prohibited for construction work:

- real user source file input
- files containing personal information
- source HWPX overwrite
- production write
- source overwrite endpoint
- final deploy endpoint
- operational repository or customer document update
- mode other than SANDBOX_ONLY
- AI API fallback
- OCR fallback
- required Hancom dependency
- reports containing raw absolute paths
- reports containing raw filenames
- reports containing raw personal information
- treating readbackFail, sourceMutation, unexpectedMutation, or security leak as success

## Promotion Criteria

Before any real user construction document can be considered, all of the following must pass:

1. At least 30 sanitized construction-like real-like samples pass batch validation.
2. readbackFail remains 0.
3. sourceMutation remains 0.
4. unexpectedMutation remains 0.
5. PII, raw path, and raw filename leak counts remain 0.
6. Every blocked file has a clear blocked reason.
7. A user file upload gate is implemented separately.
8. A personal information detection and block gate is implemented separately.
9. Construction document policy mapping is reviewed separately.
10. Operational save and deploy gates stay disabled until separately approved.

## Current Decision

The construction work master design is acceptable only as a SANDBOX_ONLY planning and verification layer. The next engineering step should be the upload gate, because real construction documents must be rejected or sanitized before they reach preflight, writer, batch, API, or browser flows.

