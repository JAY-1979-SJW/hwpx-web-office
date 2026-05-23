# HWPX Form Auto Fill Persistent Gates

- verdict: PASS_HWPX_FORM_AUTO_FILL_PERSISTENT_GATES_INSTALLED
- mode: SANDBOX_ONLY
- modules: 10
- zones: 6
- communications: 10
- security: pii=0 rawPath=0 rawFilename=0

## Commands
- python scripts/ops/audit_hwpx_form_auto_fill_modules.py
- python scripts/ops/gate_hwpx_form_auto_fill_zones.py
- python scripts/ops/install_hwpx_form_auto_fill_persistent_gates.py

## Checks
- PASS A01 module audit manifest exists
- PASS A02 zone gate manifest exists
- PASS A03 module communication manifest exists
- PASS A04 all audited modules have communication settings
- PASS A05 all zone modules exist in module audit manifest
- PASS A06 communication zones exist in zone manifest
- PASS A07 global mode is SANDBOX_ONLY
- PASS A08 global source mutation is disabled
- PASS A09 global raw payload is disabled
- PASS A10 global PII payload is disabled
- PASS A11 production and unsafe endpoints are globally forbidden
- PASS A12 module links reference known modules
- PASS A13 module communication remains sandbox and safe
- PASS A14 representative module audit runs
- PASS A15 representative zone gate runs
