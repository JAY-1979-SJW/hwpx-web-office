# HWPX Tmp Cleanup Lock Triage Standard 09

Date: 2026-05-24

Current HEAD: `eecec37`

Process:
- `HWPX-TMP-CLEANUP-LOCK-TRIAGE-STANDARD-09`

## 1. Purpose

This standard freezes the triage interpretation for the failed `tmp/` cleanup attempt.

It does not retry cleanup.
It classifies likely causes of deletion failure before any retry is attempted.

## 2. Baseline

This standard depends on:
- `docs/reports/HWPX_TMP_CLEANUP_EXECUTION_STANDARD_07.md`
- `docs/reports/HWPX_HOLD_AND_CLEANUP_PROCEDURE_STANDARD_05.md`

Current repo head for this standard:
- `eecec37`

Immediate prior cleanup result:
- `FAIL_HWPX_TMP_CLEANUP_EXECUTION`

Failed delete targets:
- `tmp/hook_smoke`
- `tmp/hook_smoke_contract`
- `tmp/hook_smoke_drift`
- `tmp/hook_smoke_new_file`

Preserve target:
- `tmp/hook_runtime`

## 3. Observed Symptoms

Observed during the failed cleanup run:
- delete attempts returned `Access denied`
- both files and parent directories failed removal
- the `tmp/` top-level structure did not change after the attempt

Observed current `tmp/` top-level entries:
- `hook_runtime`
- `hook_smoke`
- `hook_smoke_contract`
- `hook_smoke_drift`
- `hook_smoke_new_file`

Observed current file count under `tmp/` in the earlier scope survey:
- `23`

Observed current process situation:
- multiple `python` processes remain active
- several were started recently around the cleanup and hook-smoke phases

Observed current attribute situation:
- files show archive attribute
- no direct read-only indicator was observed in the attribute listing

Observed path context:
- the repository is located under a OneDrive path

## 4. Triage Candidate Classes

### 4.1 Process-lock candidate

Definition:
- a process still holds file handles or directory handles, blocking deletion

Why it is plausible here:
- multiple `python` processes are active
- failed files are hook and guard output artifacts
- some failed paths are recent runtime smoke outputs

Current assessment:
- strong candidate

### 4.2 Sync-lock candidate

Definition:
- OneDrive or similar sync behavior temporarily holds files or directories

Why it is plausible here:
- the repository path is under OneDrive
- multiple text/json/md artifacts were denied together
- the failures span different files and subdirectories, not one single isolated file

Current assessment:
- moderate candidate

### 4.3 Permission candidate

Definition:
- filesystem permission or attribute state blocks deletion

Why it is less likely here:
- the attribute listing did not show a read-only marker
- the pattern looks broader than one single permission mismatch

Current assessment:
- weaker candidate than process-lock and sync-lock

## 5. Current Best-Fit Diagnosis

The current best-fit diagnosis is:

1. `process-lock` is the primary candidate
2. `sync-lock` is the secondary candidate
3. plain `permission` is a lower-confidence candidate

This is based on:
- active `python` processes
- hook/runtime related filenames
- deletion failures on active-looking local scratch outputs
- OneDrive-backed workspace path

## 6. Required Triage Checks Before Retry

Before any future cleanup retry, check:

1. whether active `python` processes related to hook smoke have ended
2. whether `tmp/` last-write activity has settled
3. whether the same files still deny deletion after process quieting
4. whether `hook_runtime` is still needed
5. whether any new `tmp/` entries were created after this triage

## 7. Retry Preconditions

A cleanup retry should not be attempted until:
- process-lock suspicion has been revisited
- preserve target status has been re-confirmed
- the current `tmp/` inventory is shown again in the conversation
- the retry scope is shown again in the conversation
- explicit retry approval is obtained

## 8. Retry Prohibitions

Do not retry cleanup by default with:
- forced deletion outside approved scope
- preserve-target deletion
- implicit deletion of new unclassified `tmp/` paths
- simultaneous cleanup of `docs/devlog/`
- simultaneous cleanup of `logs/change_history.jsonl`

## 9. Security Rule

This triage report remains subordinate to the repository safety baseline.

It must not expose:
- raw prohibited path output
- raw prohibited filename output
- PII

This document uses only safe relative identifiers already used in prior approved cleanup standards.

## 10. Pass Criteria

This standard is acceptable when:
- process-lock candidate is defined
- sync-lock candidate is defined
- permission candidate is defined
- current best-fit diagnosis is stated
- retry preconditions are stated
- no raw path, raw filename, or PII appears in the document

## 11. Final Statement

This document freezes the lock-triage interpretation for the failed first-pass `tmp/` cleanup attempt before any retry execution is approved.

It is a triage contract, not a retry run.
