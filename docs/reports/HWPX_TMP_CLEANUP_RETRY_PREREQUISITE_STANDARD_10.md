# HWPX Tmp Cleanup Retry Prerequisite Standard 10

Date: 2026-05-24

Current HEAD: `0e64d9a`

Process:
- `HWPX-TMP-CLEANUP-RETRY-PREREQUISITE-STANDARD-10`

## 1. Purpose

This standard freezes the preconditions required before any retry of the failed `tmp/` cleanup may be attempted.

It does not retry cleanup.
It defines:
- retry allow conditions
- retry block conditions
- pre-retry checks
- pre-retry reporting
- re-approval procedure

## 2. Baseline

This standard depends on:
- `docs/reports/HWPX_TMP_CLEANUP_SCOPE_STANDARD_06.md`
- `docs/reports/HWPX_TMP_CLEANUP_EXECUTION_STANDARD_07.md`
- `docs/reports/HWPX_TMP_CLEANUP_LOCK_TRIAGE_STANDARD_09.md`
- `docs/reports/HWPX_HOLD_AND_CLEANUP_PROCEDURE_STANDARD_05.md`

Current repo head for this standard:
- `0e64d9a`

Current diagnosed failure context:
- first-pass cleanup failed with access denied
- `process-lock` is the strongest candidate
- `sync-lock` is the secondary candidate

## 3. Retry Allow Conditions

A retry may be considered only when all of the following are true:

1. the delete-candidate list still matches the approved scope
2. the preserve-candidate `hook_runtime` still exists and is still excluded
3. recent active `python` process pressure has been re-checked
4. no new unclassified `tmp/` top-level entries have appeared
5. the current `tmp/` state has been shown again in the current conversation
6. the retry scope has been approved again

## 4. Retry Block Conditions

A retry must not be attempted when any of the following are true:

1. the preserve-candidate state is unclear
2. multiple active processes still suggest current file-handle contention
3. new unclassified `tmp/` entries appear
4. the delete-candidate list no longer matches the approved scope
5. the current conversation has not been updated with the latest status
6. explicit retry approval has not been obtained

## 5. Required Pre-Retry Checks

Before retry is requested, re-check:
- `git status --short`
- `tmp/` top-level listing
- delete-candidate existence
- preserve-candidate existence
- current active `python` processes
- any visible change in lock symptoms

## 6. Required Pre-Retry Report

Before retry approval is requested, the current conversation must include:

1. current dirty status
2. current `tmp/` state
3. delete-candidate list
4. preserve-candidate list
5. current process observation
6. retry allow/block decision
7. requested retry scope

## 7. Re-Approval Procedure

The retry approval procedure must be:

1. show the current retry prerequisite standard or summarize it
2. show the current state re-check
3. show whether allow conditions are satisfied
4. show whether any block condition is still active
5. request retry approval
6. only after approval, execute retry

## 8. Preserve Safety Rule

The preserve-candidate remains:
- `hook_runtime`

Retry is blocked if:
- `hook_runtime` disappears unexpectedly
- `hook_runtime` changes role
- `hook_runtime` is proposed for deletion without a revised scope and approval

## 9. Security Rule

Retry prerequisite reporting must remain safe:
- no raw absolute path leakage when prohibited by process
- no raw filename leakage when prohibited by process
- no PII leakage

This standard remains subordinate to:
- `piiLeak == 0`
- `rawPathLeak == 0`
- `rawFilenameLeak == 0`

## 10. Pass Criteria

This standard is acceptable when:
- retry allow conditions are explicit
- retry block conditions are explicit
- pre-retry checks are explicit
- pre-retry report contents are explicit
- re-approval procedure is explicit
- no raw path, raw filename, or PII appears in the document

## 11. Final Statement

This document freezes the prerequisites that must be satisfied before any retry of the failed `tmp/` cleanup may proceed.

It is a retry precondition contract, not a retry run.
