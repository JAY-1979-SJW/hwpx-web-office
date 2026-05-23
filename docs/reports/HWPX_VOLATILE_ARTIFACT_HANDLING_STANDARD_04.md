# HWPX Volatile Artifact Handling Standard 04

Date: 2026-05-24

Current HEAD: `d63ce6a`

Process:
- `HWPX-VOLATILE-ARTIFACT-HANDLING-STANDARD-04`

## 1. Purpose

This standard freezes how non-runtime artifacts should be interpreted and handled in this repository.

It distinguishes:
- governed artifacts
- volatile artifacts
- known-hold artifacts

The goal is not immediate cleanup.
The goal is to fix the policy for commit, hold, cleanup, and long-term reference treatment.

## 2. Baseline

This standard depends on:
- `docs/architecture/hwpx_work_execution_operating_rules_20260524.md`
- `docs/reports/HWPX_APP_CURRENT_STATE_STANDARD_20260524.md`
- `docs/reports/HWPX_APP_ARCHITECTURE_CLASSIFICATION_STANDARD_01.md`
- `docs/reports/HWPX_FRONTEND_RUNTIME_VS_SMOKE_BOUNDARY_STANDARD_02.md`
- `docs/reports/HWPX_OPS_DIRECTORY_ROLE_SEPARATION_STANDARD_03.md`

Current repo head for this standard:
- `d63ce6a`

Known current hold classes:
- `docs/devlog/*.md`
- `tmp/`

Additional artifact paths that need policy classification:
- `data/reports/`
- `logs/change_history.jsonl`

## 3. Artifact Classes

### 3.1 Governed artifact

Definition:
- an artifact that serves as approved repository guidance, closeout evidence, or stable engineering reference

Typical examples:
- approved standards in `docs/reports/`
- approved closeout documents
- approved architecture documents
- approved policy documents

Primary properties:
- stable reference value
- commit-eligible when approved
- suitable as future task baseline

### 3.2 Volatile artifact

Definition:
- an artifact whose value is primarily tied to one run, one local probe, or one temporary verification session

Typical examples:
- temporary debug output
- scratch probe output
- transient generated run artifacts
- execution-time helper output

Primary properties:
- not a long-term source of truth
- usually commit-forbidden
- normally cleanup-eligible

### 3.3 Known-hold artifact

Definition:
- an artifact outside the scope of the current task that may legitimately remain in the worktree without being part of the approved change set

Typical examples:
- `docs/devlog/*.md`
- `logs/change_history.jsonl`
- task-external local residue explicitly called out in reports

Primary properties:
- reported explicitly
- not mixed into scoped commits
- cleaned up only under a separate approved task if needed

## 4. Path Policy

### 4.1 `docs/reports/`

Primary class:
- governed artifact

Allowed contents:
- approved standards
- approved closeouts
- approved architecture reports
- approved process baselines

Not appropriate by default:
- one-off debug traces
- highly volatile run-id-only outputs
- scratch-only experiment artifacts

Interpretation rule:
- `docs/reports/` is the preferred home for stable human-readable engineering reference

### 4.2 `data/reports/`

Primary class:
- generated artifact area

Default interpretation:
- volatile unless explicitly promoted by process

Allowed contents:
- machine-readable summaries
- generated audit outputs
- safe run artifacts
- debug and verification outputs

Restrictions:
- raw path, raw filename, and PII are never allowed
- real user document output is never allowed

Interpretation rule:
- treat `data/reports/` as generated first, governed only by explicit exception

### 4.3 `docs/devlog/`

Primary class:
- known-hold artifact

Interpretation:
- local or hook-generated trace content
- not product source of truth
- not a normal commit target for scoped engineering work

Policy:
- report its presence
- do not silently mix it into task commits

### 4.4 `tmp/`

Primary class:
- volatile artifact

Interpretation:
- scratch workspace
- local smoke residue
- temporary probes

Policy:
- commit forbidden
- no baseline authority
- cleanup allowed only under approved cleanup scope

### 4.5 `logs/change_history.jsonl`

Primary class:
- known-hold artifact

Interpretation:
- local trace file
- not product behavior definition
- not normal scoped commit content

Policy:
- exclude from regular task commits
- mention in reports when dirty

## 5. Commit Policy

### 5.1 Commit-allowed

Allowed when approved:
- governed standards
- governed closeout documents
- governed architecture reports
- governed policy reports
- PII-safe stable reference artifacts

### 5.2 Commit-forbidden

Forbidden by default:
- `tmp/*`
- `docs/devlog/*`
- `logs/change_history.jsonl`
- raw-path-bearing reports
- raw-filename-bearing reports
- PII-bearing reports
- one-off debug traces
- run-id-only volatile output without explicit promotion

### 5.3 Promotion exception rule

A generated artifact may be treated as governed only if:
- it is explicitly approved as a baseline artifact
- it is PII-safe
- it is path-safe
- it is intended for long-term reference rather than local residue

## 6. Hold Policy

Hold policy exists to stop unrelated residue from contaminating scoped work.

### 6.1 When to mark as known hold

Use known-hold status when:
- the artifact is outside the task scope
- the artifact is local or hook-generated
- the artifact is not required to complete the approved task
- deleting it would be a separate cleanup concern

### 6.2 Hold reporting rule

Known-hold artifacts must be:
- called out in completion reports
- excluded from scoped commits
- treated as non-product residue unless separately promoted

## 7. Cleanup Policy

### 7.1 Cleanup is a separate task

Cleanup is not bundled casually with feature or standards work.

Before cleanup begins:
- the target artifacts must be classified
- the cleanup scope must be approved
- governed artifacts must be excluded

### 7.2 Cleanup prohibitions

Do not:
- delete artifacts just because they are dirty
- treat all generated files as disposable without classification
- mix cleanup with unrelated implementation work

## 8. Report Classification Rule

Generated reports must be interpreted by purpose, not only by path.

### 8.1 Governed report indicators

Common indicators:
- approved standard
- approved closeout
- stable policy reference
- architecture baseline

### 8.2 Volatile report indicators

Common indicators:
- debug-only intent
- scratch-run intent
- machine-generated transient run output
- local validation support with no baseline role

## 9. Security Rule for Artifacts

All artifact classes remain subordinate to the security baseline.

Never allowed in governed or volatile artifacts:
- raw absolute paths
- raw filenames when prohibited by the process
- personal information patterns
- real user document payloads

Required safe state:
- `piiLeak == 0`
- `rawPathLeak == 0`
- `rawFilenameLeak == 0`

## 10. Practical Reading of Current Known Paths

### 10.1 `docs/reports/`

Read as:
- stable human-readable baseline area

### 10.2 `data/reports/`

Read as:
- generated output area with mostly volatile status unless promoted

### 10.3 `docs/devlog/`

Read as:
- hook or local dev residue held outside scoped commits

### 10.4 `tmp/`

Read as:
- scratch area only

### 10.5 `logs/change_history.jsonl`

Read as:
- local trace residue, not standard task output

## 11. Future Policy Priority

This standard does not perform cleanup, but it defines what should happen next.

Priority 1:
- define an approved cleanup process for `tmp/`

Priority 2:
- define a separate hold-management policy for `docs/devlog/`

Priority 3:
- clarify promotion criteria for `data/reports/` outputs that might become stable references

Priority 4:
- decide whether `logs/change_history.jsonl` should remain a permanent hold or move under a stricter local-only rule

## 12. Pass Criteria

This standard is acceptable when:
- governed / volatile / known-hold classes are defined
- path-specific rules are defined
- commit policy is defined
- hold policy is defined
- cleanup policy is defined
- no raw path, raw filename, or PII appears in the document

## 13. Final Statement

This document freezes how artifact classes should be interpreted before any cleanup or retention refactor begins.

It is a handling policy, not a cleanup execution task.
