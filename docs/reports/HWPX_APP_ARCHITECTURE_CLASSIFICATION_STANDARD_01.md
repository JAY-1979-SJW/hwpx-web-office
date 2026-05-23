# HWPX App Architecture Classification Standard 01

Date: 2026-05-24

Current HEAD: `7a0824d`

Process:
- `HWPX-APP-ARCHITECTURE-CLASSIFICATION-STANDARD-01`

## 1. Purpose

This standard freezes the current repository structure as a classification baseline.

It answers these questions:
- which code belongs in which directory
- which roles are allowed in each area
- which mixed responsibilities are prohibited
- how runtime, browser smoke, gate, audit, and governance surfaces should be distinguished

This process does not move files or change runtime behavior.

## 2. Baseline

Current execution rules:
- each work item requires its own task standard
- implementation begins only after explicit approval
- reports and standards are shown in the current conversation before execution

Current confirmed system state:
- `PASS_HWPX_FORM_AUTO_FILL_WRITER_USER_FLOW_CLOSEOUT`
- `PASS_HWPX_FORM_AUTO_FILL_FAIL_FAST_GATE`
- `PASS_HWPX_FORM_AUTO_FILL_PERSISTENT_GATES_INSTALLED`
- `PASS_HWPX_REPO_CLASSIFICATION_CONTRACT_GATE`
- `PASS_HWPX_REPO_MANIFEST_DRIFT_ZERO_GATE`

Current governing references:
- `docs/reports/HWPX_APP_CURRENT_STATE_STANDARD_20260524.md`
- `docs/architecture/hwpx_work_execution_operating_rules_20260524.md`
- `scripts/ops/audit_hwpx_form_auto_fill_module_manifest.json`
- `scripts/ops/hwpx_form_auto_fill_module_communication_manifest.json`

## 3. Current Structure Diagnosis

The repository currently combines:
- runtime-like pipeline logic
- browser-facing smoke and test surfaces
- API route support scripts
- audit scripts
- gates
- repo governance scripts
- closeout and architecture documents
- volatile local artifacts

Current strengths:
- active module manifest
- active communication manifest
- active zone gates
- active fail-fast and persistent gates
- active repo classification contract
- active manifest drift zero rule

Current structural risks:
- `scripts/ops` holds too many role types in one directory
- `frontend/web_office_viewer` contains both viewer-like surfaces and smoke/test harness surfaces
- pipeline, gate, audit, and governance code are logically separated by naming, but not yet by directory role
- local volatile outputs still exist alongside governed content in the worktree

## 4. Scope

This standard classifies the following areas:
- `frontend/web_office_viewer/`
- `scripts/hwpx/pipeline/`
- `scripts/ops/`
- `docs/architecture/`
- `docs/reports/`
- `tests/`
- `data/reports/`
- `tmp/`
- `docs/devlog/`
- `.githooks/`

This standard does not:
- move files
- rename imports
- split packages
- change API behavior
- change browser behavior
- change writer logic

## 5. Directory Role Standard

### 5.1 `frontend/web_office_viewer/`

Allowed roles:
- browser-facing viewer or editor surface
- batch result rendering surface
- smoke and E2E browser harness surface
- UI-only runtime helpers

Prohibited roles:
- HWPX package mutation logic
- repo governance logic
- audit result generation
- filesystem-path handling logic
- production write orchestration

Internal classification standard:
- files named `*smoke*` are smoke or test presentation surfaces
- files under `components/` are reusable UI surfaces
- generic viewer/editor runtime files remain UI runtime helpers

Boundary rule:
- browser files may call safe HTTP endpoints or render payloads
- browser files must not directly implement writer, readback, or repo-governance policy

### 5.2 `scripts/hwpx/pipeline/`

Allowed roles:
- pipeline runtime logic
- domain flow orchestration
- parser, mapping, review, approval, writer, readback, download, export logic
- sandbox-safe execution logic

Prohibited roles:
- browser rendering code
- repo governance policy
- git hook installation
- report-only architecture governance
- unrelated local scratch automation

Boundary rule:
- pipeline code is runtime or domain logic first
- audit and gate code may inspect pipeline behavior, but pipeline code should not become an audit container

### 5.3 `scripts/ops/`

Allowed roles:
- audits
- gates
- report builders
- governance scripts
- route support or API contract support
- installation helpers for local repo controls

Prohibited roles:
- persistent application business logic that belongs in `scripts/hwpx/pipeline/`
- reusable browser UI logic
- volatile user-specific local scratch output

Mandatory logical subdivisions inside `scripts/ops`:
- `audit`
- `gate`
- `repo_governance`
- `reporting`
- `install_orchestration`
- `route_support`

Current implementation note:
- these roles still coexist in a single directory
- future refactoring may separate them physically
- until then, naming and manifest linkage are the minimum control surface

### 5.4 `docs/architecture/`

Allowed roles:
- operating rules
- structural rules
- layer boundaries
- architecture rationale

Prohibited roles:
- volatile run logs
- mutable local scratch notes
- generated test artifacts

### 5.5 `docs/reports/`

Allowed roles:
- closeout reports
- standards
- approved process outputs
- design and audit summaries

Prohibited roles:
- per-run volatile debug output
- raw operational log dumps
- unsafe payload dumps

### 5.6 `tests/`

Allowed roles:
- module tests
- gate tests
- API tests
- browser smoke and E2E tests
- repo governance tests

Prohibited roles:
- production runtime logic
- user-specific scratch content
- raw unsafe report fixtures containing PII or source paths

### 5.7 `data/reports/`

Allowed roles:
- generated report artifacts
- machine-readable audit output
- gate summaries
- debug summaries that remain PII-safe

Prohibited roles:
- source documents
- production output documents
- real user document snapshots

### 5.8 `tmp/`

Allowed roles:
- local scratch execution
- temporary smoke output
- operator-local non-governed runtime probes

Prohibited roles:
- governed product artifacts
- committed architectural baselines
- dependency for permanent repo logic

### 5.9 `docs/devlog/`

Allowed roles:
- local or hook-generated devlog hold artifacts

Prohibited roles:
- governed source of truth for runtime behavior
- required inputs for tests or gates

### 5.10 `.githooks/`

Allowed roles:
- local commit/push guard entrypoints
- repo-local developer workflow controls

Prohibited roles:
- runtime application logic
- API execution logic unrelated to repository guard workflow

## 6. Runtime vs Non-Runtime Boundary

### 6.1 Runtime-bearing areas

These areas are allowed to influence runtime behavior directly:
- `scripts/hwpx/pipeline/`
- route-support scripts that expose API contract behavior
- browser-facing files in `frontend/web_office_viewer/`

### 6.2 Non-runtime control areas

These areas exist to inspect, constrain, or document runtime behavior:
- `scripts/ops/audit*`
- `scripts/ops/gate*`
- repo governance scripts
- `docs/architecture/`
- `docs/reports/`

Rule:
- non-runtime control code may validate runtime behavior
- runtime code must not depend on volatile report outputs

## 7. Frontend Boundary Standard

The frontend area contains at least three distinct classes:

1. viewer/editor runtime support
2. smoke/E2E verification surfaces
3. component-level reusable UI building blocks

Required distinction:
- smoke pages must remain visibly classified as smoke or test surfaces
- reusable components should not embed smoke-only assumptions
- runtime helper files should not become audit or governance containers

Future separation priority:
- separate smoke-only entry pages from reusable runtime UI surfaces

## 8. `scripts/ops` Internal Role Classification

The current `scripts/ops` directory should be interpreted through these role lenses:

### 8.1 Audit

Files prefixed with `audit_`:
- verify behavior
- inspect contracts
- summarize pass/fail state
- must stay PII-safe

### 8.2 Gate

Files prefixed with `gate_`:
- enforce block/pass conditions
- stop unsafe states
- define operational boundaries

### 8.3 Repo governance

Files prefixed with or related to:
- `classify_`
- `build_*manifest*`
- `repo_*`
- `separation_*`

Role:
- classify repository structure
- constrain file placement
- prevent drift
- stage repo separation decisions without executing file moves

### 8.4 Install and orchestration

Files prefixed with `install_` or `run_`:
- wire local controls
- install persistent guard paths
- execute compact entry workflows

### 8.5 Route support

Files such as:
- `hwpx_form_autofill_api_route.py`
- `hwpx_form_autofill_batch_api_route.py`

Role:
- define API contract and sandbox-safe route behavior
- support browser/API verification

### 8.6 Reporting

Files such as dashboard or summary builders:
- aggregate gate status
- emit PII-safe reports

## 9. Module / Zone / Directory Mapping Standard

Current active mapping:

- `field_mapping`
  - zone: `input_parse`
  - directory center: `scripts/hwpx/pipeline/`

- `review_panel`
  - zone: `review_approval`
  - directory center: `scripts/hwpx/pipeline/`

- `approval_gate`
  - zone: `review_approval`
  - directory center: `scripts/hwpx/pipeline/`

- `writer_sandbox`
  - zone: `writer_readback`
  - directory center: `scripts/hwpx/pipeline/`

- `readback_hardening`
  - zone: `writer_readback`
  - directory center: `scripts/hwpx/pipeline/`

- `download_review`
  - zone: `download_export`
  - directory center: `scripts/hwpx/pipeline/`

- `final_export_gate`
  - zone: `download_export`
  - directory center: `scripts/hwpx/pipeline/`

- `api_batch`
  - zone: `batch_api_browser`
  - directory center: `scripts/ops/`

- `api_browser_e2e`
  - zone: `batch_api_browser`
  - directory center: `frontend/web_office_viewer/` plus supporting smoke pipeline/tests

- `user_flow_closeout`
  - zone: `closeout_security`
  - directory center: `docs/reports/` plus gate/audit support in `scripts/ops/`

Interpretation rule:
- a module may span source, tests, and audits
- but its runtime center of gravity must still be identifiable

## 10. New File Placement Rule

New files must be placed by role, not convenience.

### 10.1 Placement guide

- runtime domain logic -> `scripts/hwpx/pipeline/`
- browser UI or UI runtime helpers -> `frontend/web_office_viewer/`
- audit logic -> `scripts/ops/` with audit role
- gates and blockers -> `scripts/ops/` with gate role
- repo governance -> `scripts/ops/` with repo governance role
- architecture rule text -> `docs/architecture/`
- closeout or process report -> `docs/reports/`
- generated machine report -> `data/reports/`
- volatile local scratch -> `tmp/`

### 10.2 Placement prohibitions

Do not place:
- runtime pipeline logic in `tmp/`
- volatile scratch artifacts in `docs/reports/`
- governance rules in `frontend/`
- browser rendering logic in `scripts/hwpx/pipeline/`
- product runtime logic in `.githooks/`

## 11. Security and Structure Link

Structure is part of safety.

The architecture standard must remain compatible with:
- `SANDBOX_ONLY`
- `sourceMutationAllowed == false`
- no raw path leak
- no raw filename leak
- no PII leak
- no AI/OCR fallback
- no Hancom-only required path

A structurally misplaced file that weakens these boundaries should be treated as a governance defect.

## 12. Repo Governance Link

This standard is tied to repo governance.

Required aligned conditions:
- governed files must stay classified
- module declarations must remain explicit
- `stablePathMappedFiles == 0`
- `manifestPromotionCandidates == 0`

This means structure classification is not only documentary.
It is expected to remain enforceable by gates.

## 13. Structural Risks and Priority

Current highest-priority structural concerns:

1. `scripts/ops` role density is too high
2. frontend smoke/test surfaces and reusable UI surfaces are still in one directory tree
3. volatile local `tmp/` usage is not yet normalized as a governed scratch policy
4. `docs/devlog/` hold artifacts still accumulate outside product scope

Recommended future standard sequence:
- frontend runtime vs smoke boundary standard
- `scripts/ops` role separation standard
- volatile artifact handling standard

## 14. Pass Criteria

This architecture classification standard is acceptable when:
- top-level structure is classified by role
- each critical directory has allowed and prohibited roles
- runtime vs control surfaces are separated conceptually
- new file placement rules are explicit
- frontend, pipeline, and ops boundaries are explicit
- repo governance linkage is explicit
- no raw path, raw filename, or PII is exposed in the standard

## 15. Final Statement

This standard freezes where the current application logic belongs before any physical repository reorganization begins.

It is a structure contract, not a refactor.

Future file moves or directory splits should be evaluated against this standard before execution.
