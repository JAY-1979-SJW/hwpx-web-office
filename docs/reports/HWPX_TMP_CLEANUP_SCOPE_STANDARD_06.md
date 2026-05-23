# HWPX Tmp Cleanup Scope Standard 06

Date: 2026-05-24

Current HEAD: `e10965f`

Process:
- `HWPX-TMP-CLEANUP-SCOPE-STANDARD-06`

## 1. Purpose

This standard freezes the cleanup scope interpretation for the current `tmp/` area.

It does not delete anything.
It defines:
- what exists in `tmp/`
- what is a likely delete candidate
- what should be preserved temporarily
- what should remain on hold until a later approved cleanup run

## 2. Baseline

This standard depends on:
- `docs/reports/HWPX_VOLATILE_ARTIFACT_HANDLING_STANDARD_04.md`
- `docs/reports/HWPX_HOLD_AND_CLEANUP_PROCEDURE_STANDARD_05.md`

Current repo head for this standard:
- `e10965f`

Current `tmp/` top-level entries observed:
- `hook_runtime`
- `hook_smoke`
- `hook_smoke_contract`
- `hook_smoke_drift`
- `hook_smoke_new_file`

Observed file count under `tmp/` during this scope survey:
- `23`

## 3. Current Tmp Diagnosis

The current `tmp/` contents appear to be local verification residue related to hook and guard smoke work.

Observed pattern:
- hook-related runtime scratch
- hook-related smoke output
- contract smoke residue
- drift smoke residue
- new-file gate smoke residue

No deletion is performed in this process.

## 4. Classification Model

### 4.1 Delete candidate

Definition:
- local scratch or one-off smoke residue with no current baseline role

In the current `tmp/` survey, the following top-level directories are delete-candidate by default pending final cleanup approval:
- `hook_smoke`
- `hook_smoke_contract`
- `hook_smoke_drift`
- `hook_smoke_new_file`

Reason:
- their names indicate verification residue
- they are under `tmp/`
- they are not governed artifacts

### 4.2 Preserve candidate

Definition:
- local scratch that may still be useful to understand the most recent ongoing guard execution flow

In the current `tmp/` survey, the following top-level directory is preserve-candidate by default:
- `hook_runtime`

Reason:
- it is the most recently touched directory
- it may reflect the most recent hook runtime experimentation
- it should not be swept without a separate cleanup approval and a quick re-check

### 4.3 Hold candidate

Definition:
- content whose deletion risk is not yet fully justified even though it is still volatile

Current hold-candidate interpretation:
- no extra hold-only path is declared yet beyond the preserve-candidate class
- if active runtime probing is still suspected, preserve-candidate should remain untouched until cleanup execution is separately approved

## 5. Cleanup Exclusion Rule

The following must be excluded from the first cleanup execution pass unless re-approved:
- the most recently touched runtime-support residue
- any file or directory still suspected to be connected to current or very recent execution
- any item whose role is unclear

For the current observed `tmp/` tree, the default exclusion is:
- `hook_runtime`

## 6. Cleanup Inclusion Rule

The following may be proposed in a future approved cleanup run:
- clear smoke-only residue
- clear one-off guard verification residue
- clear expired local scratch trees that are no longer referenced by the current task flow

For the current observed `tmp/` tree, the default inclusion candidates are:
- `hook_smoke`
- `hook_smoke_contract`
- `hook_smoke_drift`
- `hook_smoke_new_file`

## 7. Required Recheck Before Actual Cleanup

Before any future cleanup execution, re-check:
- last write times
- whether `hook_runtime` is still needed
- whether any new tmp entries were added after this scope standard
- whether any path inside `tmp/` has been promoted into a governed artifact by exception

## 8. Cleanup Scope Summary

Current scope summary:

Delete-candidate groups:
- `hook_smoke`
- `hook_smoke_contract`
- `hook_smoke_drift`
- `hook_smoke_new_file`

Preserve-candidate groups:
- `hook_runtime`

Known restrictions:
- no actual deletion in this process
- no cleanup outside `tmp/`
- no cleanup of `docs/devlog/`
- no cleanup of `logs/change_history.jsonl`

## 9. Security Rule

This scope standard remains subordinate to the artifact safety baseline.

The standard must not expose:
- raw absolute paths
- raw filenames when prohibited by process
- PII

This document uses only safe top-level directory names already visible as local scratch identifiers.

## 10. Pass Criteria

This standard is acceptable when:
- the current `tmp/` top-level scope is listed
- delete/preserve interpretation is defined
- cleanup exclusions are defined
- no actual cleanup is performed
- no raw path, raw filename, or PII appears in the document

## 11. Final Statement

This document freezes the scope interpretation for the current `tmp/` tree before any approved cleanup execution begins.

It is a scope contract, not a cleanup action.
