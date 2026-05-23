# HWPX Form Auto Fill Upload Gate

- verdict: PASS_HWPX_FORM_AUTO_FILL_UPLOAD_GATE
- accepted: 1
- blocked: 4
- security: pii=0 rawPath=0 rawFilename=0

## Scenarios
- sanitizedSynthetic: UPLOAD_ACCEPTED_SANITIZED ACCEPTED
- realUserFile: BLOCKED BLOCKED_REAL_USER_FILE
- piiRisk: BLOCKED BLOCKED_PII_RISK
- rawFilenameRisk: BLOCKED BLOCKED_RAW_FILENAME_RISK
- nonSandbox: BLOCKED BLOCKED_NON_SANDBOX_MODE
