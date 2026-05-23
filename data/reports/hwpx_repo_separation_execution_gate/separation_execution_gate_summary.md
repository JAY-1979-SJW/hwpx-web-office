# HWPX Repo Separation Execution Gate

- verdict: PASS_HWPX_REPO_SEPARATION_EXECUTION_GATE
- baseline: f63e141
- mode: DRY_RUN_ONLY
- executionAllowed: False
- packages: 9
- dryRunPackages: 9
- holdPackages: 2
- security: pii=0 rawPath=0 rawFilename=0

## Packages
- pkg_runtime_autofill_line: phase=P1_GATE_PROTECTED_REFACTOR_PLAN operation=REVIEW_AND_GATE_ONLY files=18 dryRun=True
- pkg_hwpx_core_library: phase=P2_DEPENDENCY_IMPACT_REVIEW operation=REVIEW_AND_IMPORT_IMPACT_ONLY files=184 dryRun=True
- pkg_frontend_viewer_shell: phase=P2_DEPENDENCY_IMPACT_REVIEW operation=REVIEW_AND_IMPORT_IMPACT_ONLY files=28 dryRun=True
- pkg_audit_gate_layer: phase=P1_GATE_PROTECTED_REFACTOR_PLAN operation=REVIEW_AND_GATE_ONLY files=121 dryRun=True
- pkg_test_support_layer: phase=P2_DEPENDENCY_IMPACT_REVIEW operation=REVIEW_AND_IMPORT_IMPACT_ONLY files=170 dryRun=True
- pkg_docs_reports_layer: phase=P3_RETENTION_REVIEW operation=RETENTION_REVIEW_ONLY files=287 dryRun=True
- pkg_legacy_experiment_quarantine: phase=P0_HOLD operation=HOLD_ONLY files=149 dryRun=True
- pkg_config_root_layer: phase=P4_CONFIG_REVIEW operation=CONFIG_REVIEW_ONLY files=2 dryRun=True
- pkg_manual_review_hold: phase=P0_HOLD operation=HOLD_ONLY files=1 dryRun=True

## Guardrails
- no file move/delete/archive is performed by this gate
- owner approval is required before any future execution script
- legacy and unknown packages remain HOLD_ONLY
