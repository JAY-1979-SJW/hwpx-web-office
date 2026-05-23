# HWPX App Current State Standard

Date: 2026-05-24

Current HEAD: `04f7763`

Document purpose:
- Freeze the current application baseline as an engineering standard.
- Record what the app is allowed to do now.
- Record what remains blocked.
- Record the mandatory quality, security, and repository governance rules that already exist in code.

This document is based on the current repo implementation, manifests, closeout reports, and active gate scripts. It is a current-state standard, not a future roadmap.

## 1. Application Definition

The current application is an HWPX form auto-fill line with browser, API, pipeline, audit, and repository governance layers.

Closed user flow:

`recommend -> parse -> map -> review -> approve -> sandbox write -> readback -> download review -> final export gate -> batch API -> browser E2E`

Current baseline closeout:
- `PASS_HWPX_FORM_AUTO_FILL_WRITER_USER_FLOW_CLOSEOUT`
- baseline commit recorded in the closeout: `ad53a0f`

Current repo head for this standard:
- `04f7763`

## 2. System Boundary

The current app is not a production writer.

It is a controlled validation and sandbox execution line with the following hard boundary:
- mode is `SANDBOX_ONLY`
- source mutation is disabled
- real user file use is blocked
- PII-bearing file use is blocked
- production write is blocked
- source overwrite is blocked
- final deploy is blocked
- AI fallback is blocked
- OCR fallback is blocked
- required Hancom dependency is blocked

## 3. Current Functional Scope

The current implementation supports:
- sanitized synthetic HWPX samples
- sanitized real-like HWPX samples
- browser rendering for review and batch result pages
- API-triggered real-like batch execution
- sandbox copy writing only
- readback verification
- download review payload generation
- final export candidate payload generation
- batch limits `1`, `5`, and `10`
- browser/API E2E with test or mock routing
- audit and closeout reporting with PII-safe output

The current implementation does not support:
- operational customer document update
- real-user upload to writer path
- production output persistence
- direct source HWPX overwrite
- deploy/apply to final operational repository
- automated AI/OCR escape hatch

## 4. Module Standard

The current audited application line is organized as 10 declared modules.

### 4.1 Declared modules

1. `field_mapping`
2. `review_panel`
3. `approval_gate`
4. `writer_sandbox`
5. `readback_hardening`
6. `download_review`
7. `final_export_gate`
8. `api_batch`
9. `api_browser_e2e`
10. `user_flow_closeout`

### 4.2 Zone grouping

The current modules are partitioned into 6 active zones:
- `input_parse`
- `review_approval`
- `writer_readback`
- `download_export`
- `batch_api_browser`
- `closeout_security`

### 4.3 Module-to-zone contract

- `field_mapping` -> `input_parse`
- `review_panel` -> `review_approval`
- `approval_gate` -> `review_approval`
- `writer_sandbox` -> `writer_readback`
- `readback_hardening` -> `writer_readback`
- `download_review` -> `download_export`
- `final_export_gate` -> `download_export`
- `api_batch` -> `batch_api_browser`
- `api_browser_e2e` -> `batch_api_browser`
- `user_flow_closeout` -> `closeout_security`

### 4.4 Mandatory module properties

Every declared module in the active auto-fill line must satisfy:
- allowed mode is `SANDBOX_ONLY`
- `sourceMutationAllowed == false`
- `rawPayloadAllowed == false`
- `piiPayloadAllowed == false`
- upstream/downstream links must resolve to known modules
- endpoint list must stay within the communication manifest

## 5. Communication Standard

The current communication contract is defined in `scripts/ops/hwpx_form_auto_fill_module_communication_manifest.json`.

### 5.1 Global contract

- mode: `SANDBOX_ONLY`
- source mutation allowed: `false`
- raw payload allowed: `false`
- PII payload allowed: `false`

Allowed payload kinds:
- `maskedValue`
- `valueHash`
- `displayName`
- `outputFileId`
- `finalExportId`
- `batchId`
- `status`
- `blockedReason`
- `summaryCounts`

Forbidden endpoint classes:
- `production-write`
- `source-overwrite`
- `final-deploy`
- `ai-api`
- `ocr-api`
- `hancom-only`

### 5.2 Allowed active endpoints

The active line is limited to these named endpoint purposes:
- `write-sandbox`
- `batch-health`
- `real-like-sandbox`
- `batch-result`

Any new endpoint added to the line must be:
- declared in the communication manifest
- sandbox-safe
- non-production
- non-source-overwriting
- non-PII-leaking

## 6. Writer Execution Standard

The current writer line is approval-gated and sandbox-only.

### 6.1 Writer enablement

Writer execution is permitted only after the review and approval chain yields the writer-ready state. The active design requires:
- explicit review completion
- explicit approval state
- no unresolved missing required values
- no unresolved review backlog
- no unresolved attachment backlog
- sandbox-only mode

### 6.2 Writer execution outcome rules

Success is valid only when all of the following remain true:
- writer status indicates success
- `readbackFail == 0`
- `sourceMutation == 0`
- `unexpectedMutation == 0`
- security leak counts remain `0`

The following outcomes must never be rendered or returned as success:
- readback failure
- source mutation failure
- unexpected mutation
- output broken state
- security leak state

## 7. Upload Gate Standard

The upload gate is the front-door safety contract before preflight or writer access.

### 7.1 Allowed upload condition

Accepted upload requests require:
- `mode == SANDBOX_ONLY`
- `sourceMutationAllowed == false`
- `realUserFile == false`
- `declaredSanitized == true`
- package kind in:
  - `HWPX_PACKAGE`
  - `SANITIZED_REAL_LIKE_PACKAGE`
  - `SYNTHETIC_PACKAGE`
- `sourcePathHint != outputPathHint`
- no raw absolute path pattern
- no raw filename pattern
- no PII pattern

### 7.2 Mandatory block conditions

The upload gate must block:
- non-sandbox mode
- source mutation enabled request
- real user file flag
- unsanitized sample
- unsupported package kind
- output equals source
- raw path risk
- raw filename risk
- PII risk

## 8. Browser and API Standard

The current app includes browser pages and batch API wiring, but they remain under sandbox and test-scope restrictions.

### 8.1 Browser obligations

Browser surfaces must:
- render review/batch summaries from safe payloads
- show sandbox-only constraints
- show blocked and failed states distinctly
- never show failure states as success
- never expose raw path
- never expose raw filename
- never expose PII in DOM or console

### 8.2 API obligations

The batch API must:
- keep mode fixed to `SANDBOX_ONLY`
- keep `sourceMutationAllowed` false
- support limits `1`, `5`, `10`
- reject non-sandbox mode
- reject real-user-file requests
- fail on readback failure
- fail on source mutation
- fail on unexpected mutation
- fail on security leak
- never return raw path
- never return raw filename
- never return PII

## 9. Security Standard

The current app security baseline is defined by code and audit output, not by policy text alone.

### 9.1 Mandatory zero-leak rule

The following counters must remain zero in summaries, responses, reports, and console-safe output:
- `piiLeak`
- `rawPathLeak`
- `rawFilenameLeak`

### 9.2 Absolute prohibitions

The current app must not:
- call AI APIs
- call OCR APIs
- require Hancom-only runtime for the closed auto-fill line
- emit raw absolute source path
- emit raw filename
- emit personal information patterns

### 9.3 Approved disclosure forms

The current line is allowed to expose only sanitized identifiers such as:
- display-safe names
- masked values
- hashes
- output ids
- export ids
- batch ids
- summary counts

## 10. Quality Gate Standard

The app already has layered gates. They are not optional.

### 10.1 Fail-fast gate

Current integrated gate verdict:
- `PASS_HWPX_FORM_AUTO_FILL_FAIL_FAST_GATE`

Recorded summary:
- steps total: `7`
- steps passed: `7`
- steps failed: `0`
- modules: `10`
- zones: `6`

The current fail-fast flow covers:
1. persistent gate installation
2. module audits
3. module audit history
4. zone gates derived from module audit
5. upload gate
6. construction work master design audit
7. gate dashboard

### 10.2 Persistent gate layer

Current persistent gate verdict:
- `PASS_HWPX_FORM_AUTO_FILL_PERSISTENT_GATES_INSTALLED`

Recorded summary:
- modules: `10`
- zones: `6`
- communications: `10`
- failed checks: `0`

The persistent layer requires:
- module audit manifest
- zone gate manifest
- communication manifest
- cross-manifest consistency
- global sandbox-only mode
- source mutation disabled
- raw payload disabled
- PII payload disabled
- unsafe endpoint classes globally forbidden

### 10.3 Module audit history and contract

Module logs are part of the standard.

Every module audit entry must carry a stable audit contract including:
- `moduleId`
- `zone`
- `verdict`
- `runId`
- `timestampUtc`
- `checks`
- `security`

Run-id log artifacts may be generated for verification, but operational commit policy still excludes volatile run logs from normal commits.

## 11. Repository Governance Standard

The repo now has active structure governance in addition to feature gates.

### 11.1 Classification contract

Current repo classification contract verdict:
- `PASS_HWPX_REPO_CLASSIFICATION_CONTRACT_GATE`

Recorded summary:
- tracked files: `988`
- governed existing files: `89`
- new files: `0`
- existing failures: `0`
- new failures: `0`
- stable path mapped files: `0`
- manifest promotion candidates: `0`

This means:
- governed files are classified
- manifest declaration is the active resolution source for the promoted line
- drift back to path-based inference is not currently allowed

### 11.2 Manifest drift zero rule

The repo standard now requires:
- `stablePathMappedFiles == 0`
- `manifestPromotionCandidates == 0`

If either becomes non-zero again, that is governance drift and should fail the relevant gate.

### 11.3 New and existing file classification

Governed repo files must not remain unassigned in the active governed scope.

New governed files must satisfy:
- known zone
- known module relationship when required
- known classification outcome
- no `UNKNOWN_REVIEW_REQUIRED`

Existing governed files must continue to satisfy the same structure contract.

## 12. Hook and Precheck Standard

The repo has a local hook line installed.

### 12.1 Hook path

Current local Git hook path:
- `.githooks`

### 12.2 Installed hook files

- `.githooks/pre-commit`
- `.githooks/pre-push`

### 12.3 Hook purpose

`pre-commit` is intended to stop commits when:
- new file classification fails
- repo classification contract fails
- manifest promotion candidate build fails
- manifest drift zero check fails

`pre-push` is intended to stop push/precheck when:
- integrated fail-fast gate fails

### 12.4 Operational caution

Hook execution is repo-local and should remain:
- fast enough for developer feedback
- PII-safe in stdout/stderr
- free of raw path/raw filename exposure in normal summary output

## 13. Known Hold and Dirty Baseline Standard

The current working convention explicitly recognizes non-product hold items.

Known hold classes:
- `logs/change_history.jsonl`
- `docs/devlog/*.md`
- top-level volatile report outputs

These are not product artifacts and should not be mixed into scoped engineering commits unless the process explicitly says so.

## 14. Release Readiness Standard

The app is not in production release readiness for real user input.

### 14.1 Current readiness statement

Current readiness is:
- acceptable for sanitized synthetic validation
- acceptable for sanitized real-like sample validation
- acceptable for sandbox batch/API/browser verification
- not acceptable for uncontrolled real user upload
- not acceptable for production write
- not acceptable for deploy/apply

### 14.2 Promotion gate before broader use

Before broader rollout, the current standard requires at minimum:
1. at least 30 sanitized real-like samples passing batch validation
2. `readbackFail == 0`
3. `sourceMutation == 0`
4. `unexpectedMutation == 0`
5. `piiLeak == 0`
6. `rawPathLeak == 0`
7. `rawFilenameLeak == 0`
8. clear blocked reason recording for every blocked file
9. a separate user upload gate
10. a separate PII detect-and-block gate
11. production save/deploy paths still disabled until separately approved

## 15. Current Engineering Decisions

The current application standard freezes these decisions:
- the active auto-fill line remains sandbox-only
- safety is enforced in code, manifests, tests, and audit scripts
- module and zone structure is declared, not inferred ad hoc
- repo governance is part of runtime safety, not separate from it
- writer success is impossible without readback and mutation safety
- browser and API surfaces are treated as security boundaries, not just UI
- hook-based local guard rails are part of developer workflow

## 16. Immediate Next Priority

The most sensible next step is not production rollout.

The next priority should be one of:
- strengthen the upload gate toward real-user pre-ingress blocking
- document and verify the hook smoke and precheck operational path
- reduce or clean volatile `tmp/` and devlog hold handling without weakening audit traceability

## 17. Standard Use Rule

This document should be used as:
- a baseline for future tasks
- a review checklist for new feature requests
- a rejection basis for unsafe mode expansion
- a repository governance reference for new files, new modules, and new endpoints

Any change that violates this standard should be treated as a design change and must not be merged casually.

## 18. Execution Approval Rule

All future work in this repository follows the execution control rule documented in:

- `docs/architecture/hwpx_work_execution_operating_rules_20260524.md`

The mandatory operating rule is:
- every distinct work item must have its own task standard
- the task standard must be shown first
- the user must explicitly approve it
- only then may implementation, test expansion, staging, or commit work begin

Investigation and standard writing are allowed before approval.
Implementation is not allowed before approval.
