# Hancom HWP SaveAs HWPX Timeout Fix

## 문제

- Hancom Automation security module install is complete.
- `RegisterModule("FilePathCheckDLL", "FilePathCheckerModuleExample")` returns `true`.
- HWP `Open()` succeeds through the COM worker.
- Direct `$hwp.SaveAs($OutputPath, "HWPX", "")` timed out at `SAVEAS_START`.
- HAction `FileSaveAs_S` was added and tested, but it also timed out at `SAVEAS_HACTION_START`.

## 공식/기술 기준

- HWPX is a supported Hancom save format.
- When direct `SaveAs()` blocks, Hancom action execution can be tested through `HAction.GetDefault("FileSaveAs_S", HParameterSet.HFileOpenSave.HSet)` and `HAction.Execute(...)`.
- The test kept the existing Hancom COM provider and did not add another converter.

## 구현

- Added `-SaveStrategy` to `scripts/hwp-worker/Convert-HwpToHwpx-v2.ps1`.
- Supported strategies:
  - `direct`: existing `$hwp.SaveAs($OutputPath, "HWPX", "")`
  - `haction`: `HAction.Execute("FileSaveAs_S", HFileOpenSave.HSet)`
- Added stage logs:
  - `SAVEAS_DIRECT_START`
  - `SAVEAS_DIRECT_DONE`
  - `SAVEAS_HACTION_START`
  - `SAVEAS_HACTION_DONE`
  - `SAVEAS_OUTPUT_VALID`
- Added `--save-strategy` to `scripts/hwpx/hancom_hwp_to_hwpx_batch.py`.
- Supported runner strategies:
  - `direct`
  - `haction`
  - `auto`
- For `auto`, the runner can run strategies in separate PowerShell subprocesses so a direct SaveAs timeout does not block a second HAction attempt.

## 테스트

### RegisterModule

- Result: `true`
- Hancom version: `13, 0, 0, 3457`
- Module name: `FilePathCheckerModuleExample`

### 대상 파일

- Input: `C:\Users\skyjw\OneDrive\03. PYTHON\35. haehan-ai-orchestrator\tmp\g2b_user_present_downloads_20260508\0026_R26BK01418850_000_긴급입찰사유서.hwp`
- Size: `26112` bytes
- Reason: smallest ordinary HWP candidate from the local download set.

### Open-only

- Result: PASS
- Stage: `END`
- `RegisterModule`: `true`
- `Open`: `true`

### Direct SaveAs

- Strategy: `direct`
- Result: FAIL
- Last stage: `SAVEAS_START`
- Error: `HANCOM_SAVEAS_TIMEOUT`
- Output HWPX: not created

### HAction SaveAs

- Strategy: `haction`
- Result: FAIL
- Last stage: `SAVEAS_HACTION_START`
- Error: `HANCOM_SAVEAS_TIMEOUT`
- Owned Hwp PID: stopped by subprocess timeout cleanup
- Output HWPX: not created

### ZIP 검증

- HWPX file was not created.
- ZIP header validation was not possible.

### 3건 preflight

- Not run.
- Reason: one-file SaveAs did not succeed.

## 결론

- `RegisterModule=false` and HWP Open timeout are resolved.
- The remaining blocker is now the Hancom HWPX save operation.
- Both direct `SaveAs("HWPX")` and HAction `FileSaveAs_S` block in the current local COM automation path.
- Current automatic HWP to HWPX conversion status: FAIL.

## 다음 단계

- Diagnose whether Hancom shows a hidden save dialog or modal during HWPX save.
- Test additional `HFileOpenSave` parameter fields only within the existing Hancom worker.
- Keep file-level subprocess timeout and newly-created `Hwp.exe` cleanup.
- Do not run 3-file or 10-file preflight until one HWPX file is generated and ZIP validation succeeds.
