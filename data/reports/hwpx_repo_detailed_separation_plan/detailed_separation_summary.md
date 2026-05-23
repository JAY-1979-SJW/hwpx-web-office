# HWPX Repo Detailed Separation Plan

- verdict: PASS_HWPX_REPO_DETAILED_SEPARATION_PLAN
- baseline: fbfb29f
- scope: tracked_files_only_classification_no_move
- total files: 955
- modules linked: 10
- release zones gated: 6
- hold zones: 5
- security: pii=0 rawPath=0 rawFilename=0

## Areas
- runtime_autofill_line: files=18 action=protect_with_module_audit_and_zone_gate move=no_move_until_gate_green
- hwpx_core_library: files=184 action=keep_as_shared_core_with_import_review move=no_move_until_import_impact_review
- frontend_viewer_shell: files=28 action=protect_browser_contracts move=no_move_until_route_contract_review
- audit_gate_layer: files=120 action=keep_as_release_gate_layer move=no_move_until_gate_bootstrap_review
- test_support_layer: files=169 action=keep_with_target_module_mapping move=no_move_until_test_owner_review
- docs_reports_layer: files=284 action=keep_pii_safe_artifacts move=no_move_until_report_retention_review
- legacy_experiment_quarantine: files=149 action=quarantine_before_any_archive_or_split move=no_move_no_delete_without_owner_approval
- config_root_layer: files=2 action=keep_as_root_configuration move=no_move_without_build_review
- manual_review_hold: files=1 action=hold_until_classified move=no_move_no_delete_without_owner_approval

## Zone Gates
- batch_api_browser: files=9 gate=True readiness=GATED
- browser_ui: files=28 gate=False readiness=HOLD_FOR_REVIEW
- closeout_security: files=148 gate=True readiness=GATED
- docs_reports: files=284 gate=False readiness=HOLD_FOR_REVIEW
- download_export: files=4 gate=True readiness=GATED
- hwpx_core: files=207 gate=False readiness=HOLD_FOR_REVIEW
- input_parse: files=12 gate=True readiness=GATED
- review_approval: files=4 gate=True readiness=GATED
- test_support: files=30 gate=False readiness=HOLD_FOR_REVIEW
- unassigned: files=225 gate=False readiness=HOLD_FOR_REVIEW
- writer_readback: files=4 gate=True readiness=GATED

## Next Work
- no file move/delete before owner review
- wire detailed modules only after zone gate remains green
- keep legacy and unknown files in hold until classified
