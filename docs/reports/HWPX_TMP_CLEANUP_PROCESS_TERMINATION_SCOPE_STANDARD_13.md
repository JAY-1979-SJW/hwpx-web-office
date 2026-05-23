# HWPX Tmp Cleanup Process Termination Scope Standard 13

Date: 2026-05-24

Current HEAD: `a9add6f`

Process:
- `HWPX-TMP-CLEANUP-PROCESS-TERMINATION-SCOPE-STANDARD-13`

## 1. Purpose

This standard freezes how process termination scope should be interpreted before any termination proposal is made.

It does not terminate processes.
It defines:
- observe-only scope
- unknown-risk scope
- minimum conditions for a terminate-candidate proposal

## 2. Baseline

This standard depends on:
- `docs/reports/HWPX_TMP_CLEANUP_PROCESS_STABILIZATION_STANDARD_12.md`
- `docs/reports/HWPX_TMP_CLEANUP_LOCK_TRIAGE_STANDARD_09.md`

Current repo head for this standard:
- `a9add6f`

Current process observation context:
- multiple active `python` processes are visible
- some are recent
- some are older and still unresolved
- direct ownership of each process is not yet proven

## 3. Observe-Only Scope

Observe-only processes are the default safe class.

They include processes that are:
- recently started
- plausibly related to the current or recent session
- not yet clearly separable from current work
- not clearly tied to the failing tmp delete targets

Rule:
- observe-only processes must not be proposed for termination in the first pass

## 4. Unknown-Risk Scope

Unknown-risk processes are processes whose role is still too unclear.

They include processes that are:
- older lingering processes
- not directly attributable to the current cleanup attempt
- potentially related to unrelated or earlier work

Rule:
- unknown-risk processes must remain outside immediate termination scope until evidence improves

## 5. Terminate-Candidate Minimum Conditions

A process may be proposed as a terminate-candidate only when all of the following become true:

1. there is a stronger reason to connect it to tmp lock behavior
2. it can be separated from current active work
3. it is not needed to preserve the current session state
4. it is not merely unknown-risk by age alone
5. a separate termination approval step is prepared

## 6. Current Conservative Scope Rule

At the current stage, the default scope is conservative:
- recent visible processes remain observe-only
- unclear older processes remain unknown-risk
- no concrete terminate-candidate is finalized yet

This means:
- termination scope is intentionally narrower than suspicion scope

## 7. Scope Escalation Rule

Moving a process from:
- observe-only -> terminate-candidate
or
- unknown-risk -> terminate-candidate

requires:
- new evidence
- a fresh report in the current conversation
- a separate approval request

## 8. Security Rule

This scope standard must remain safe:
- no raw absolute path leakage when prohibited by process
- no raw filename leakage when prohibited by process
- no PII leakage

It must also avoid unsupported certainty about individual process ownership.

## 9. Pass Criteria

This standard is acceptable when:
- observe-only scope is defined
- unknown-risk scope is defined
- terminate-candidate minimum conditions are defined
- conservative scope rule is defined
- no raw path, raw filename, or PII appears in the document

## 10. Final Statement

This document freezes the safe termination proposal boundary before any later process termination action is considered.

It is a scope contract, not a termination operation.
