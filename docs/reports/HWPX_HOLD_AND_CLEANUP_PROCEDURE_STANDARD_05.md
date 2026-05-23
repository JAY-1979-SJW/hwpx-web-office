# HWPX Hold and Cleanup Procedure Standard 05

Date: 2026-05-24

Current HEAD: `37b4eaa`

Process:
- `HWPX-HOLD-AND-CLEANUP-PROCEDURE-STANDARD-05`

## 1. Purpose

This standard freezes the operating procedure for hold handling and cleanup handling.

It does not execute cleanup.
It defines:
- when to declare hold
- when cleanup needs a separate task
- what must be reported before cleanup
- how approval must be obtained before cleanup

## 2. Baseline

This standard depends on:
- `docs/architecture/hwpx_work_execution_operating_rules_20260524.md`
- `docs/reports/HWPX_APP_CURRENT_STATE_STANDARD_20260524.md`
- `docs/reports/HWPX_VOLATILE_ARTIFACT_HANDLING_STANDARD_04.md`

Current repo head for this standard:
- `37b4eaa`

Current known hold examples:
- `docs/devlog/*.md`
- `tmp/`

Related paths:
- `logs/change_history.jsonl`
- `data/reports/`

## 3. Hold Declaration Rule

### 3.1 When to declare hold

An artifact should be declared as hold when all or most of the following are true:
- it is outside the current approved task scope
- it is not required to complete the current approved task
- it is a local, hook-generated, or run-generated residue
- removing it would require a separate decision or cleanup process

### 3.2 Examples

Typical hold examples under the current repository workflow:
- `docs/devlog/*.md`
- `tmp/`
- `logs/change_history.jsonl`

### 3.3 Hold reporting rule

When hold exists, the current conversation report must state:
- what remains on hold
- why it is on hold
- why it is not part of the scoped change set

## 4. Immediate Cleanup Prohibition Rule

Cleanup must not happen immediately just because the worktree is dirty.

Do not clean up immediately when:
- governed status is unclear
- the artifact falls outside the current approved scope
- removal risk is unclear
- the artifact may serve as evidence of another process
- there is no explicit cleanup approval

## 5. Cleanup Requires a Separate Task

Cleanup is treated as its own governed task when it involves:
- deleting files
- mass clearing temporary outputs
- pruning report trees
- removing hook-generated or tool-generated residues
- changing hold handling behavior

Cleanup must not be bundled casually into:
- feature work
- runtime changes
- architecture standards
- test refactors

## 6. Cleanup Start Conditions

Cleanup may begin only when all of the following are true:
- the target artifacts have been classified
- governed artifacts have been excluded
- the planned cleanup scope has been written down
- the current conversation has a cleanup report
- explicit approval has been obtained

## 7. Required Pre-Cleanup Report

Before cleanup starts, the current conversation must include:

1. cleanup task name
2. target artifact list
3. artifact classification for each target
   - governed
   - volatile
   - known-hold
4. delete candidates
5. preserve candidates
6. current dirty status
7. risks and unknowns
8. approval request scope

## 8. Cleanup Approval Procedure

The required procedure is:

1. show cleanup standard or cleanup task scope in the current conversation
2. show the target list
3. show delete vs preserve classification
4. show risks and holds
5. request approval
6. only after approval, execute the cleanup
7. report post-cleanup results

## 9. Cleanup Scope Isolation Rule

Cleanup must remain isolated from unrelated execution.

Do not mix cleanup with:
- feature implementation
- API changes
- frontend changes
- gate logic changes
- manifest changes
- repo classification changes

If cleanup is needed during another task, pause and open a dedicated cleanup standard or cleanup scope.

## 10. Path-Specific Procedure Priority

### 10.1 `tmp/`

Classification:
- volatile scratch

Procedure priority:
- earliest cleanup candidate

Preconditions:
- verify it is not actively used by the current approved work
- verify no governed artifact has been written there by exception

### 10.2 `docs/devlog/`

Classification:
- known-hold

Procedure priority:
- after `tmp/`

Preconditions:
- confirm it is hook-generated or local dev residue
- confirm it is not acting as approved governed documentation

### 10.3 `logs/change_history.jsonl`

Classification:
- known-hold local trace

Procedure priority:
- policy review before deletion

Preconditions:
- confirm it is not required by an approved logging process
- confirm cleanup scope explicitly includes it

### 10.4 `data/reports/`

Classification:
- mixed generated area

Procedure priority:
- after classification review

Preconditions:
- separate governed reports from volatile run outputs
- confirm no approved baseline report is being deleted

## 11. Post-Cleanup Report Rule

If cleanup is approved and executed later, the completion report must include:
- starting dirty status
- target list
- deleted items
- preserved items
- hold items left untouched
- resulting `git status --short`
- any residual risk

## 12. Security Rule

Cleanup procedures remain subordinate to the security baseline.

Never allow cleanup reporting to expose:
- raw absolute paths when prohibited by process
- raw filenames when prohibited by process
- PII patterns

Required safe state:
- `piiLeak == 0`
- `rawPathLeak == 0`
- `rawFilenameLeak == 0`

## 13. Pass Criteria

This standard is acceptable when:
- hold declaration conditions are defined
- cleanup start conditions are defined
- pre-cleanup report contents are defined
- cleanup approval steps are defined
- path-specific procedure priority is defined
- no raw path, raw filename, or PII appears in the document

## 14. Final Statement

This document freezes how cleanup must be prepared, approved, and reported before any actual cleanup task is executed.

It is a procedure contract, not a cleanup run.
