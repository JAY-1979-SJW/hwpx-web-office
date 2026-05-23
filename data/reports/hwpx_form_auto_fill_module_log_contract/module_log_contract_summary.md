# HWPX Form Auto Fill Module Log Contract

- verdict: PASS_HWPX_FORM_AUTO_FILL_MODULE_LOG_CONTRACT
- expectedModules: 10
- loggedModules: 10
- missingModuleLogs: 0
- entriesPassed: 10
- entriesFailed: 0
- security: pii=0 rawPath=0 rawFilename=0

## Contract
- module audit history entries require moduleId, zone, verdict, runId, timestampUtc, checks, and security
- module logs must not contain raw path, raw filename, or PII patterns
- missing module logs fail the gate
