# HWPX Ops Directory Role Separation Standard 03

Date: 2026-05-24

Current HEAD: `77f8991`

Process:
- `HWPX-OPS-DIRECTORY-ROLE-SEPARATION-STANDARD-03`

## 1. Purpose

This standard freezes how `scripts/ops/` should be interpreted by role.

The goal is not to split the directory today.
The goal is to establish a stable classification model for existing and future files in `scripts/ops/`.

The role classes defined here are:
- audit
- gate
- repo_governance
- route_support
- reporting
- install_orchestration

## 2. Baseline

This standard depends on:
- `docs/architecture/hwpx_work_execution_operating_rules_20260524.md`
- `docs/reports/HWPX_APP_CURRENT_STATE_STANDARD_20260524.md`
- `docs/reports/HWPX_APP_ARCHITECTURE_CLASSIFICATION_STANDARD_01.md`
- `docs/reports/HWPX_FRONTEND_RUNTIME_VS_SMOKE_BOUNDARY_STANDARD_02.md`

Current repo head for this standard:
- `77f8991`

## 3. Current Ops Diagnosis

The current `scripts/ops/` directory carries multiple responsibility classes at once:
- audit scripts
- execution gates
- repo governance scripts
- API route support
- dashboard and summary builders
- local install and orchestration helpers

Current strengths:
- naming already communicates partial role intent
- `audit_*` and `gate_*` prefixes are widespread
- repo governance work is already systematically introduced
- route support scripts are recognizable by API route naming

Current risks:
- one physical directory currently hides several logical subdomains
- new files can be misclassified by convenience instead of role
- route support and governance support are visually adjacent
- install helpers and reporting builders are not physically separated

## 4. Role Classes

### 4.1 Audit

Definition:
- scripts that inspect behavior, verify contracts, or produce pass/fail audit output

Primary signals:
- `audit_*`

Allowed responsibilities:
- inspect implementation
- validate expected behavior
- run audit scenarios
- emit PII-safe summaries

Prohibited responsibilities:
- becoming runtime business logic
- executing production write
- performing repo move/delete/archive operations
- acting as browser-facing UI

Representative examples:
- `audit_hwpx_form_auto_fill_modules.py`
- `audit_hwpx_form_auto_fill_user_flow_closeout.py`
- `audit_hwpx_form_auto_fill_real_like_api_batch.py`

### 4.2 Gate

Definition:
- scripts that enforce allow/block/fail conditions

Primary signals:
- `gate_*`

Allowed responsibilities:
- safety enforcement
- pass/fail/block decisions
- contract guard rails
- structured gating output

Prohibited responsibilities:
- acting as business-domain runtime pipelines
- acting as report-only markdown containers
- executing physical repo moves as part of normal gate behavior

Representative examples:
- `gate_hwpx_form_auto_fill_fail_fast.py`
- `gate_hwpx_form_auto_fill_upload.py`
- `gate_hwpx_repo_manifest_drift_zero.py`

### 4.3 Repo governance

Definition:
- scripts that control repository structure, file classification, manifest drift, separation planning, and execution approval boundaries

Primary signals:
- `classify_*`
- `plan_*`
- `build_*manifest*`
- `repo_*`
- `separation_*`
- `run_hwpx_repo_*`
- `install_hwpx_repo_*`

Allowed responsibilities:
- classify repository files
- build or validate repo manifests
- prevent structure drift
- build separation plans
- hold execution behind approvals
- wire repo-local guard controls

Prohibited responsibilities:
- HWPX writer runtime implementation
- browser UI behavior
- unrelated local scratch behavior

Representative examples:
- `classify_hwpx_repo_inventory.py`
- `build_hwpx_repo_manifest_promotion_candidates.py`
- `gate_hwpx_repo_classification_contract.py`
- `gate_hwpx_repo_separation_final_execution_approval.py`
- `run_hwpx_repo_commit_guard.py`

### 4.4 Route support

Definition:
- scripts that define or support sandbox-safe API route contracts

Primary signals:
- `*_api_route.py`
- route or server naming related to browser/API request handling

Allowed responsibilities:
- define API contract
- expose safe route handlers
- shape request/response behavior
- preserve sandbox-only boundaries

Prohibited responsibilities:
- repo governance classification
- frontend rendering behavior
- local scratch artifact lifecycle

Representative examples:
- `hwpx_form_autofill_api_route.py`
- `hwpx_form_autofill_batch_api_route.py`
- `form_recommend_server.py`

### 4.5 Reporting

Definition:
- scripts that build dashboards, summaries, matrices, or audit history artifacts

Primary signals:
- `build_*dashboard*`
- `build_*summary*`
- history writers

Allowed responsibilities:
- aggregate results
- build dashboards
- write summary artifacts
- write safe audit history

Prohibited responsibilities:
- acting as runtime route handlers
- acting as repo move executors
- acting as browser component modules

Representative examples:
- `build_hwpx_form_auto_fill_gate_dashboard.py`
- `hwpx_form_auto_fill_module_audit_history.py`

### 4.6 Install and orchestration

Definition:
- scripts that install local controls or provide compact local execution entrypoints

Primary signals:
- `install_*`
- `run_*`
- `verify_*`

Allowed responsibilities:
- install local repo controls
- run compact helper flows
- invoke known validation entrypoints
- wire local hooks or persistent checks

Prohibited responsibilities:
- becoming long-lived business logic
- replacing gate logic with hidden side effects
- becoming product runtime API modules

Representative examples:
- `install_hwpx_form_auto_fill_persistent_gates.py`
- `install_hwpx_repo_guard_hooks.py`
- `run_hwpx_form_field_catalog.py`
- `verify_hwpx_form_auto_fill_individual.py`

## 5. Prefix and Naming Interpretation

Naming is a signal, not the full rule.

### 5.1 Prefix mapping

- `audit_*` -> `audit`
- `gate_*` -> `gate`
- `install_*` -> `install_orchestration`
- `run_*` -> `install_orchestration` or `repo_governance` depending on target
- `build_*` -> `reporting` or `repo_governance`
- `classify_*` -> `repo_governance`
- `plan_*` -> `repo_governance`
- `*_api_route.py` -> `route_support`

### 5.2 Override rule

If prefix and actual responsibility disagree, responsibility wins.

Example:
- a `build_*` file that constructs a repo classification candidate set is `repo_governance`, not generic reporting

## 6. New File Placement Rule

New files in `scripts/ops/` must be placed by role.

### 6.1 Placement guide

- verification and inspection -> `audit`
- blocking and enforced safety rules -> `gate`
- classification / manifest / separation / hook guard logic -> `repo_governance`
- API route support -> `route_support`
- dashboard / summary / matrix / history -> `reporting`
- local install / run / verify entrypoint -> `install_orchestration`

### 6.2 Placement prohibitions

Do not place:
- runtime pipeline logic in `scripts/ops/`
- browser UI helpers in `scripts/ops/`
- volatile scratch probes as governed `scripts/ops` modules
- production-only deployment logic under the current sandbox-only line

## 7. Runtime vs Control Boundary

The `scripts/ops/` directory is primarily a control and support surface.

### 7.1 Allowed direct runtime-adjacent role

Only route-support files may sit close to runtime request handling, and even then they must remain:
- sandbox-safe
- response-safe
- contract-driven

### 7.2 Control-only role

Audit, gate, governance, reporting, and installer files are control surfaces.

They may:
- inspect
- block
- aggregate
- wire

They should not:
- replace pipeline domain logic
- absorb browser runtime logic
- act as a hidden application core

## 8. Relationship to Repo Governance

This standard is not separate from repo governance.

It is compatible with and subordinate to:
- repo classification contract
- manifest promotion completion
- manifest drift zero requirement
- local hook guard workflow

Required current state:
- governed files remain classified
- manifest declarations remain explicit where required
- `stablePathMappedFiles == 0`
- `manifestPromotionCandidates == 0`

## 9. Relationship to Current Safety Model

The ops role structure must preserve:
- `SANDBOX_ONLY`
- `sourceMutationAllowed == false`
- no raw path leak
- no raw filename leak
- no PII leak
- no AI/OCR fallback
- no Hancom-only required execution path

If a new ops file weakens these constraints, it is a structural defect and a safety defect.

## 10. Current File Role Reading

The current directory may be read through these practical buckets:

### 10.1 Audit-heavy cluster

Files beginning with `audit_` form the largest visible cluster and should be treated as audit-only by default unless proven otherwise.

### 10.2 Gate-heavy cluster

Files beginning with `gate_` are enforcement boundaries and should remain declarative and blocking in nature.

### 10.3 Governance cluster

Repo classification, manifest, separation, and hook-control files should be read as a coherent governance slice even though they are not yet physically separated.

### 10.4 Route-support cluster

The autofill API route files are the `scripts/ops/` slice closest to browser-facing execution.

### 10.5 Reporting cluster

Dashboard builders, history writers, and matrix builders should be treated as summary emitters, not as runtime enforcers.

### 10.6 Install and orchestration cluster

Install and run helpers should remain thin orchestration layers and must not silently turn into business logic containers.

## 11. Future Split Priority

This standard does not split the directory now, but it defines future priority.

Priority 1:
- visually isolate repo governance files from generic audits

Priority 2:
- isolate route support from general governance and reporting files

Priority 3:
- isolate install/orchestration helpers from audit and gate files

Priority 4:
- formalize reporting builders as a clearer output-oriented slice

## 12. Pass Criteria

This standard is acceptable when:
- all six ops role classes are defined
- responsibilities and prohibitions are explicit
- prefix mapping exists
- new file placement rules exist
- future split priority exists
- no raw path, raw filename, or PII appears in the document

## 13. Final Statement

This document freezes how `scripts/ops/` should be interpreted before any physical directory reorganization begins.

It is a role contract, not a refactor.
