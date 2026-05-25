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

## RULE-08: All standards and reports must be shown in the current conversation first

Before saving, editing, committing, or executing task work, the following must be shown in the current conversation first:
- task standards
- execution reports
- completion reports
- next-task proposals
- next-task standards

This rule applies to:
- new task standards
- updated task standards
- implementation result summaries
- follow-up task proposals

Required sequence:
1. show the report or standard in the current conversation
2. obtain explicit approval when approval is required
3. only then save files, edit files, run the approved task, or commit task-scoped changes

## RULE-09: Detailed reporting is mandatory for every completed task step

After a task step is completed, the report in the current conversation must include:
- what changed
- which files changed
- why the change was made
- what was validated
- what remains on hold
- what the next task is

Short “done” responses are not sufficient for governed work.

## RULE-10: Repo governance changes also require approval

The following are governed changes and require a task standard plus approval:
- module manifest updates
- communication manifest updates
- zone manifest updates
- file classification gate changes
- manifest drift rules
- hook/precheck rule changes
- repo separation rules

## RULE-11: This rule overrides informal “just do it” execution

Even when the user asks to continue generally, implementation still requires:
- a task-specific standard
- explicit approval for that task

This rule is intended to keep execution auditable, bounded, and reviewable.

## RULE-12: Standard documents are part of the engineering control surface

Task standards are not informal notes.

They serve as:
- execution boundary
- review checklist
- audit basis
- pass/fail contract
- completion reporting baseline

Any work performed outside this structure should be treated as non-compliant process.

## RULE-13: Server verification is the final completion authority for Web Office work

For Web Office work, local verification is a required pre-deployment filter, but
it is not the final completion authority.

Required Web Office execution sequence:
1. implement or update locally
2. run local tests, local smoke checks, and local commit/push guards
3. transfer or deploy the verified change to the server
4. verify the server runtime, monitor, logs, and health endpoint
5. report completion only after the server passes

Current Web Office server baseline:
- server alias: `haehan-app`
- server path: `/home/ubuntu/apps/hwpx-web-office`
- health endpoint: `http://127.0.0.1:8767/api/web-office/health`
- runtime mode: `SANDBOX_ONLY`
- monitor: `scripts/ops/verify_web_office_server_monitor.py`
- auto-start: current user crontab `@reboot` entry marked `hwpx-web-office-monitor`

Completion rule:
- local pass + server not checked = incomplete
- local pass + server fail = incomplete
- local pass + server pass = complete

Server verification must include, at minimum:
- health verdict `HEALTHY` or an expected `RECOVERED` followed by `HEALTHY`
- backend response mode `SANDBOX_ONLY`
- `sourceMutationAllowed == false`
- monitor process or auto-start registration present
- relevant server logs checked for immediate errors

Any Web Office task that changes runtime behavior, scripts, API routes, frontend
serving, monitoring, recovery, or deployment must include the server verification
result in its completion report.

## RULE-14: Operational report artifacts are mandatory after governed work

Any governed task that changes tools, features, connections, runtime behavior,
server behavior, monitoring, recovery, deployment, backend structure, or Web
Office behavior must leave an operational report artifact before it is reported
complete.

The completion report must include, at minimum:
- standard document update status
- work result summary
- machine-readable log, audit payload, or verifier output location
- validation commands executed and their results
- local verification result
- server verification result when the task is Web Office related
- unresolved items, lock-required items, and hold items
- final status value

Approved final status values:
- `LOCAL_VERIFIED_SERVER_PENDING`
- `SERVER_VERIFIED_PASS`
- `SERVER_VERIFICATION_FAILED`
- `LOCAL_VERIFICATION_FAILED`
- `DOCUMENTATION_ONLY_RECORDED`

For Web Office work, the report artifact must be written under an audit or report
path before closeout, and the current conversation must summarize the same
result. A Web Office task cannot be called complete if the report artifact,
validation command record, or server verification result is missing.

Recommended machine-readable fields:
- `schemaVersion`
- `task`
- `baselineHead`
- `standardDocuments`
- `changedFiles`
- `validationCommands`
- `localVerification`
- `serverVerification`
- `reportArtifacts`
- `unresolvedItems`
- `holdItems`
- `finalStatus`
