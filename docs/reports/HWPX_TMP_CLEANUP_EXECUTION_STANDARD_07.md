# HWPX Tmp Cleanup Execution Standard 07

Date: 2026-05-24

Current HEAD: `acf8ba9`

Process:
- `HWPX-TMP-CLEANUP-EXECUTION-STANDARD-07`

## 1. Purpose

This standard freezes how an approved `tmp/` cleanup should be executed.

It does not run cleanup in this step.
It defines:
- exact target type
- preserve protections
- pre-execution checklist
- execution order
- failure handling
- result reporting

## 2. Baseline

This standard depends on:
- `docs/reports/HWPX_VOLATILE_ARTIFACT_HANDLING_STANDARD_04.md`
- `docs/reports/HWPX_HOLD_AND_CLEANUP_PROCEDURE_STANDARD_05.md`
- `docs/reports/HWPX_TMP_CLEANUP_SCOPE_STANDARD_06.md`

Current repo head for this standard:
- `acf8ba9`

Current `tmp/` scope interpretation:

Delete-candidate:
- `hook_smoke`
- `hook_smoke_contract`
- `hook_smoke_drift`
- `hook_smoke_new_file`

Preserve-candidate:
- `hook_runtime`

## 3. Execution Target Rule

An approved cleanup execution may target only the currently declared delete-candidates:
- `hook_smoke`
- `hook_smoke_contract`
- `hook_smoke_drift`
- `hook_smoke_new_file`

It must not widen itself implicitly.

If a new `tmp/` path appears, it is out of scope until:
- it is re-surveyed
- it is classified
- a new or revised approval is obtained

## 4. Preserve Protection Rule

The current preserve-candidate is:
- `hook_runtime`

This path must not be deleted under the first approved tmp cleanup execution unless:
- a revised scope is shown in the current conversation
- deletion of `hook_runtime` is explicitly approved

Preserve protection also applies to:
- any path newly found to be active or recently reused
- any path whose role is unclear at execution time

## 5. Execution Exclusion Rule

The cleanup execution must exclude:
- `hook_runtime`
- any path outside `tmp/`
- any newly appeared unclassified `tmp/` path
- any path suspected to be tied to current active work

## 6. Pre-Execution Checklist

Before actual cleanup runs, the current conversation must include:

1. current `git status --short`
2. current top-level `tmp/` listing
3. delete-candidate list
4. preserve-candidate list
5. exclusion list
6. approval scope confirmation

The cleanup must not proceed until this checklist is shown and the approved scope still matches reality.

## 7. Execution Order

The execution order must be:

1. report current dirty state
2. report `tmp/` top-level state
3. confirm delete targets
4. confirm preserve targets
5. execute deletion only on approved delete targets
6. verify resulting `tmp/` state
7. verify resulting `git status --short`
8. report results

## 8. Failure Handling Rule

If cleanup fails for any target:
- do not report cleanup as fully successful
- report failed targets explicitly
- treat failed targets as remaining hold until a later decision

If the preserve-candidate is touched unexpectedly:
- stop and report immediately
- do not continue as if the run were valid

## 9. Result Reporting Rule

After cleanup execution, the report must include:
- attempted delete targets
- successful deletions
- failed deletions
- preserved targets
- remaining holds
- resulting `git status --short`

Short success-only reporting is not sufficient.

## 10. Safety Rule

Cleanup execution reporting must remain safe:
- no raw absolute path leakage when prohibited by process
- no raw filename leakage when prohibited by process
- no PII leakage

The execution standard remains subordinate to:
- `piiLeak == 0`
- `rawPathLeak == 0`
- `rawFilenameLeak == 0`

## 11. Out-of-Scope Rule

This cleanup execution standard does not authorize:
- `docs/devlog/` cleanup
- `logs/change_history.jsonl` cleanup
- `data/reports/` cleanup
- any cleanup outside `tmp/`

Those require separate scope and approval.

## 12. Pass Criteria

This standard is acceptable when:
- delete targets are explicit
- preserve targets are explicit
- exclusions are explicit
- pre-execution checklist is explicit
- execution order is explicit
- failure handling is explicit
- no raw path, raw filename, or PII appears in the document

## 13. Final Statement

This document freezes the execution rule for an approved first-pass `tmp/` cleanup.

It is an execution contract, not the cleanup run itself.
