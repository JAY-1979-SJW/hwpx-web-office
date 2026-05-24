# HWPX Tmp Cleanup Lock Evidence Standard 15

Date: 2026-05-24

Current HEAD: `28a580e`

Process:
- `HWPX-TMP-CLEANUP-LOCK-EVIDENCE-STANDARD-15`

## 1. Purpose

This standard freezes the evidence threshold required before stronger lock conclusions or termination-candidate escalation may be made.

It does not terminate processes.
It does not retry cleanup.
It defines:
- weak evidence
- medium evidence
- strong evidence
- process-lock evidence expectations
- sync-lock evidence expectations
- terminate-candidate escalation expectations

## 2. Baseline

This standard depends on:
- `docs/reports/HWPX_TMP_CLEANUP_LOCK_TRIAGE_STANDARD_09.md`
- `docs/reports/HWPX_TMP_CLEANUP_PROCESS_TERMINATION_SCOPE_STANDARD_13.md`
- `docs/reports/HWPX_TMP_CLEANUP_RETRY_PREREQUISITE_STANDARD_10.md`

Current repo head for this standard:
- `28a580e`

Current cleanup state:
- tmp cleanup retry remains blocked
- process-lock is still the strongest current candidate
- sync-lock remains a secondary candidate
- no termination candidate has been proposed yet

## 3. Evidence Levels

### 3.1 Weak evidence

Definition:
- indirect conditions that suggest a cause but do not identify a reliable actor-path relationship

Typical examples:
- multiple active `python` processes are visible
- `tmp/` deletion returns access denied
- the repository lives under a OneDrive-backed path

Meaning:
- enough to name candidates
- not enough to justify termination-candidate escalation

### 3.2 Medium evidence

Definition:
- stronger contextual linkage between a process family, timing, and tmp artifact generation or lock behavior

Typical examples:
- process start-time clustering closely matches tmp artifact generation timing
- the same lock pattern appears repeatedly around the same type of run
- lock pressure appears correlated with one narrowed process window

Meaning:
- enough to justify tighter triage and narrower candidate review
- still not automatically enough for termination action

### 3.3 Strong evidence

Definition:
- a stable, repeatable, and more direct relationship between a process family and the lock behavior on the specific tmp residue

Typical examples:
- repeated runs show the same candidate process group and same locked residue pattern
- process stabilization or controlled change clearly affects the lock result
- the candidate range narrows consistently across repeated observations

Meaning:
- sufficient basis for a termination-candidate proposal
- still requires separate approval before action

## 4. Process-Lock Evidence Rule

To strengthen a process-lock claim, multiple elements should converge:
- active process presence
- temporal proximity to tmp artifact creation
- repeatable lock pattern
- narrowing of likely process ownership

Current state assessment:
- weak evidence

Reason:
- process presence is visible
- timing correlation exists loosely
- but direct per-process linkage remains unresolved

## 5. Sync-Lock Evidence Rule

To strengthen a sync-lock claim, multiple elements should converge:
- OneDrive-backed workspace context
- simultaneous denial across multiple text-like or report-like files
- lock persistence not clearly reduced by process quiescence
- repeatable timing overlap with sync-style file activity

Current state assessment:
- weak to medium candidate

Reason:
- OneDrive path exists
- multiple text/json/md artifacts were denied
- but direct sync-phase evidence is still incomplete

## 6. Permission Evidence Rule

To strengthen a plain permission claim, look for:
- explicit read-only or restrictive attribute behavior
- consistent denial independent of process or sync changes
- repeatable failure even after process pressure is reduced

Current state assessment:
- weaker than process-lock and sync-lock

Reason:
- archive-like attributes were observed
- obvious read-only evidence was not observed

## 7. Terminate-Candidate Escalation Rule

A process or process family may move toward terminate-candidate status only when:
- evidence rises beyond weak
- process linkage narrows
- unrelated current-work risk decreases
- the candidate can be explained as safer to target than to continue observing

Current state:
- escalation threshold not yet met

## 8. Evidence Deficiency Rule

Evidence is still insufficient when:
- processes are visible but not attributable
- tmp artifact ownership remains indirect
- sync-lock and process-lock are not yet cleanly separated
- repeated observations do not yet narrow the actor enough

Current state:
- evidence deficiency still applies

## 9. Security Rule

This standard must remain safe:
- no raw absolute paths when prohibited by process
- no raw filenames when prohibited by process
- no PII

It must also avoid false certainty about individual process ownership.

## 10. Pass Criteria

This standard is acceptable when:
- weak, medium, and strong evidence are defined
- process-lock evidence expectations are defined
- sync-lock evidence expectations are defined
- terminate-candidate escalation expectations are defined
- evidence deficiency is defined
- no raw path, raw filename, or PII appears in the document

## 11. Final Statement

This document freezes the evidence standard required before stronger tmp lock claims or termination-candidate escalation can be made.

It is an evidence contract, not a cleanup retry or process action.
