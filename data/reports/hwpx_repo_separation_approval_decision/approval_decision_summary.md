# HWPX Repo Separation Approval Decision Gate

- verdict: PASS_HWPX_REPO_SEPARATION_APPROVAL_DECISION_GATE
- baseline: 23bae47
- mode: REVIEW_DECISION_ONLY
- decisions: 9
- pending: 9
- reviewApproved: 0
- blocked: 0
- executionAllowed: 0
- security: pii=0 rawPath=0 rawFilename=0

## Guardrails
- review-only decisions do not approve move/delete/archive
- HOLD packages cannot be review-approved in this gate
- execution approval needs a separate future plan
