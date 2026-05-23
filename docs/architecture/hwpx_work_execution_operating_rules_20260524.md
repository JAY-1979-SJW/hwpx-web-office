# HWPX Work Execution Operating Rules

Date: 2026-05-24

Status: CONFIRMED

Purpose:
- Freeze the execution control rule for all future work in this repository.
- Require written task standards before implementation.
- Require explicit user approval before code, test, or structural execution begins.

## RULE-01: Every work item requires its own task standard

Before any implementation work starts, a task-specific standard must be written.

The task standard is required for:
- code changes
- new files
- file moves
- file deletions
- test expansion
- route wiring
- UI changes
- gate changes
- audit script changes
- repo classification or manifest changes
- deployment-related review work

Exceptions:
- short factual inspection
- status reporting
- reading existing files for investigation
- writing or updating the task standard itself

## RULE-02: No implementation before approval

Implementation must not begin before the user explicitly approves the task standard.

Not allowed before approval:
- editing product code
- adding test files
- adding scripts
- changing manifests
- running long validations for the new task
- staging or committing task changes

Allowed before approval:
- investigation
- architecture review
- baseline check
- criteria drafting
- risk identification
- task standard writing

## RULE-03: One task, one standard

Each distinct task must have its own standard.

The following must not be mixed into one task without explicit user approval:
- unrelated modules
- unrelated zones
- unrelated repo governance work
- runtime changes and documentation-only changes in the same execution scope

If the scope expands materially, a new or revised task standard must be presented and approved again.

## RULE-04: Mandatory sections for every task standard

Every task standard must include:
1. task name
2. baseline
3. purpose
4. current state summary
5. implementation scope
6. absolute prohibitions
7. input/output contract
8. security standard
9. validation/test standard
10. audit standard
11. deliverables
12. pass criteria
13. completion report format
14. approval-required execution statement

## RULE-05: Approval must be explicit

Approval must be explicit in the conversation.

Valid approval examples:
- direct approval statement
- direct instruction to proceed after the standard is shown
- explicit acceptance of the standard or process

Invalid approval examples:
- silence
- topic change without approval
- ambiguous interest
- approval of a different task

## RULE-06: Work must stay inside the approved standard

Once approved, execution must stay inside the approved standard.

If execution requires:
- broader scope
- additional files outside scope
- new endpoints
- new security exceptions
- new runtime dependencies
- changed pass criteria

then work must pause and a revised task standard must be presented for approval.

## RULE-07: Report progress continuously during execution

During execution, status must be reported continuously.

Operational reporting rule:
- no long silent execution window
- if work continues, progress must be reported periodically in the conversation
- long-running commands must be accompanied by intermediate status updates

## RULE-08: Repo governance changes also require approval

The following are governed changes and require a task standard plus approval:
- module manifest updates
- communication manifest updates
- zone manifest updates
- file classification gate changes
- manifest drift rules
- hook/precheck rule changes
- repo separation rules

## RULE-09: This rule overrides informal “just do it” execution

Even when the user asks to continue generally, implementation still requires:
- a task-specific standard
- explicit approval for that task

This rule is intended to keep execution auditable, bounded, and reviewable.

## RULE-10: Standard documents are part of the engineering control surface

Task standards are not informal notes.

They serve as:
- execution boundary
- review checklist
- audit basis
- pass/fail contract
- completion reporting baseline

Any work performed outside this structure should be treated as non-compliant process.
