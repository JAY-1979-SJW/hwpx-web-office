# Hancom HWP Converter Router Modular Connection Check

## Scope

HWP -> HWPX converter router modularization was checked at the source, unit, integration, and CLI preflight levels.

## Files

- `scripts/hwpx/hancom_hwp_converter_providers.py`
  - Owns provider status models, provider detection, provider selection, and the base `execute_one()` refusal contract.
- `scripts/hwpx/hancom_hwp_converter_router.py`
  - Owns CLI argument handling, one-file execution planning, JSON report output, and CSV provider status output.
- `scripts/hwpx/test_hancom_hwp_converter_providers.py`
  - Covers provider detection helpers, provider priority, unavailable COM detection, official converter evidence detection, and execution refusal.
- `scripts/hwpx/test_hancom_hwp_converter_router.py`
  - Covers planning, provider-to-router wiring, report generation, and convert-mode execution blocking.

## Connection Result

The router imports provider APIs from `hancom_hwp_converter_providers`:

- `PROVIDER_ORDER`
- `choose_provider`
- `detect_providers`
- `status_to_dict`

`router.run()` calls `detect_providers()`, passes the resulting `ProviderStatus` rows into `build_plan()`, serializes them into `router_report.json`, and writes `provider_status.csv`.

## Current Runtime Status

Latest preflight result:

- status: `NO_EXECUTABLE_PROVIDER`
- blocker: `No provider is both verified and execution_allowed`

Provider statuses:

- `official_converter`: `INTERNAL_CONVERTER_CANDIDATE_ONLY`
- `sdk`: `LICENSE_REQUIRED`
- `com`: `BLOCKED_SAVEAS_TIMEOUT`
- `local_gui`: `BLOCKED_SAVE_DIALOG_NOT_FOUND`
- `user_present`: `AVAILABLE_MANUAL_FALLBACK`

No provider is promoted to verified execution. This is intentional.

## Safety Policy

The safety policy remains unchanged:

- Batch conversion is not allowed.
- Only one input HWP file is planned at a time.
- `convert` mode requires `--allow-execute`.
- Even with `--allow-execute`, execution remains blocked until a provider is explicitly promoted to verified execution.

## Verification

Commands:

```powershell
python -m pytest scripts\hwpx\test_hancom_hwp_converter_router.py scripts\hwpx\test_hancom_hwp_converter_providers.py -q
python -m py_compile scripts\hwpx\hancom_hwp_converter_router.py scripts\hwpx\hancom_hwp_converter_providers.py scripts\hwpx\test_hancom_hwp_converter_router.py scripts\hwpx\test_hancom_hwp_converter_providers.py
python scripts\hwpx\hancom_hwp_converter_router.py --output-dir tmp\hancom_hwp_converter_router
```

Results:

- pytest: `12 passed`
- py_compile: pass
- CLI preflight: pass

Generated outputs:

- `tmp/hancom_hwp_converter_router/router_report.json`
- `tmp/hancom_hwp_converter_router/provider_status.csv`

## Next Development Step

The next bounded step is official converter contract discovery:

1. Inspect official converter shortcut/uninstall evidence.
2. Determine whether the candidate is CLI-capable or GUI-only.
3. Add a provider-specific detector field for the execution contract.
4. Keep `execute_one()` blocked until a one-file conversion is verified.
