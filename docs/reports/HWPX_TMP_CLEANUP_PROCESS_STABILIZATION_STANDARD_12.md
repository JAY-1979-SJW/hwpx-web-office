# HWPX Tmp Cleanup Process Stabilization Standard 12

Date: 2026-05-24

Current HEAD: `6685419`

Process:
- `HWPX-TMP-CLEANUP-PROCESS-STABILIZATION-STANDARD-12`

## 1. Purpose

This standard freezes how process stabilization should be interpreted before any future tmp cleanup retry is attempted.

It does not terminate processes.
It defines:
- observe-only process criteria
- terminate-candidate process criteria
- unknown-risk process criteria
- pre-termination checklist
- termination approval procedure
- post-stabilization recheck expectations

## 2. Baseline

This standard depends on:
- `docs/reports/HWPX_TMP_CLEANUP_EXECUTION_STANDARD_07.md`
- `docs/reports/HWPX_TMP_CLEANUP_LOCK_TRIAGE_STANDARD_09.md`
- `docs/reports/HWPX_TMP_CLEANUP_RETRY_PREREQUISITE_STANDARD_10.md`

Current repo head for this standard:
- `6685419`

Current cleanup retry condition:
- `BLOCKED_BY_PROCESS_LOCK`

Observed current process context:
- multiple active `python` processes remain visible
- some are recent and may overlap with hook or tmp smoke activity

## 3. Process Classes

### 3.1 Observe-only process

Definition:
- a process that may still be relevant to current or recent work and must not be terminated without stronger evidence

Typical signals:
- current-session or near-current start time
- unclear relationship to tmp cleanup artifacts
- possible overlap with recent verification work

Rule:
- observe-only processes are not termination candidates by default

### 3.2 Terminate-candidate process

Definition:
- a process that may be contributing to the tmp cleanup lock condition and may become eligible for termination only after explicit additional review and approval

Typical signals:
- repeated overlap with cleanup lock timing
- apparent connection to hook-smoke or tmp residue generation
- no active need established for current work

Rule:
- terminate-candidate does not mean terminate-now
- it means “may be proposed for termination in a later approved step”

### 3.3 Unknown-risk process

Definition:
- a process whose role is insufficiently understood and therefore must be treated as protected from termination

Typical signals:
- unclear origin
- older lingering state with no proven cleanup relationship
- possible unrelated work overlap

Rule:
- unknown-risk processes remain non-terminable until their role becomes clearer

## 4. Pre-Termination Checklist

Before any future process termination is proposed, the current conversation must include:

1. current `python` process list
2. recent process start-time pattern
3. current `tmp/` state
4. preserve target confirmation
5. process classification
   - observe-only
   - terminate-candidate
   - unknown-risk
6. termination risk statement
7. termination scope request

## 5. Termination Approval Procedure

The required procedure for any later termination proposal is:

1. show the current process stabilization standard or summarize it
2. show the latest process list
3. show which processes are only being observed
4. show which processes are being proposed as terminate-candidates
5. show the risk of terminating them
6. request explicit approval
7. only after approval, attempt termination

## 6. Post-Stabilization Recheck

If a later approved stabilization step occurs, recheck:
- current `python` process state
- current `tmp/` top-level state
- delete-candidate persistence
- preserve-candidate persistence
- retry readiness state

The expected result is not automatic cleanup success.
The expected result is a better basis for retry readiness judgment.

## 7. Current Safe Interpretation

Based on the current repository state, the safest interpretation is:
- recent active `python` processes should remain observe-only until separately justified
- any process with unclear role should remain unknown-risk
- terminate-candidate classification requires a separate explicit review step

## 8. Security Rule

This stabilization standard remains subordinate to the cleanup safety baseline.

It must not expose:
- raw absolute paths when prohibited by process
- raw filenames when prohibited by process
- PII

It must also avoid overstating certainty where only partial process evidence is available.

## 9. Pass Criteria

This standard is acceptable when:
- observe-only criteria are defined
- terminate-candidate criteria are defined
- unknown-risk criteria are defined
- pre-termination checklist is defined
- approval procedure is defined
- post-stabilization recheck is defined
- no raw path, raw filename, or PII appears in the document

## 10. Final Statement

This document freezes the process-stabilization interpretation that must exist before any later termination or retry-preparation step is approved.

It is a stabilization contract, not a termination action.
