# Hancom HWP to HWPX Timeout Root Cause

## 현재 상태

- Provider: `HANCOM_COM_32BIT_ONLY`
- 32-bit PowerShell: `C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe`
- COM ProgID: `HwpFrame.HwpObject.2`
- Hancom version: `13.0.0.3457` (previous environment check)
- SetMessageBoxMode: `0`
- RegisterModule: `false`
- Existing manual diagnostic: stopped after `open_begin`, classified as `OPEN_START 이후 멈춤`
- Current `Hwp.exe`: no remaining process after diagnostics

## 진단 결과

Open-only diagnostics were run serially against three HWP files. Each run created one new `Hwp.exe`, timed out at `OPEN_START`, and the batch wrapper stopped only that newly detected PID.

| Target | Mode | Result | Last stage | New PID | Stopped PID |
| --- | --- | --- | --- | --- | --- |
| `0026_R26BK01418850_000_긴급입찰사유서.hwp` | open-only | `HANCOM_OPEN_TIMEOUT` | `OPEN_START` | `34808` | `34808` |
| `0013_R26BK01442118_005_1. 물품제조 구매 규격서_일주지앤에스_저작도구.hwp` | open-only | `HANCOM_OPEN_TIMEOUT` | `OPEN_START` | `104276` | `104276` |
| `0099_R26BK01418150_000_★과업지시서(스마트 재난안전관리 실증실험 인프라 고도화 연구).hwp` | open-only | `HANCOM_OPEN_TIMEOUT` | `OPEN_START` | `23788` | `23788` |

SaveAs diagnostics were not run because Open-only did not complete for any of the three files.

## 원인 판정

- `OPEN_TIMEOUT`: confirmed on 3/3 files.
- `SAVEAS_TIMEOUT`: not reached.
- `POPUP_WAIT`: likely, because COM creation, SetMessageBoxMode, and RegisterModule all returned before `Open()` blocked.
- `REGISTER_MODULE_LIMIT`: possible contributor. `RegisterModule("FilePathCheckDLL", "SecurityModule")` returned `false` in all three runs.
- `FILE_SPECIFIC`: less likely, because three different HWP files all blocked at the same Open stage.
- `UNKNOWN`: remains for the exact hidden dialog/security cause until a user-present Hancom window check is performed.

## 적용한 수정

- Added staged JSONL diagnostics in `scripts/hwp-worker/Convert-HwpToHwpx-v2.ps1`.
- Added `-Mode open-only|saveas|convert`.
- Added required stages from `START` through `END`/`ERROR`.
- Added stage records containing timestamp, input/output path, elapsed milliseconds, return value, error message, and before/after HWP PIDs.
- Added Python timeout classification based on last diagnostic stage:
  - `HANCOM_OPEN_TIMEOUT`
  - `HANCOM_SAVEAS_TIMEOUT`
  - `COM_CREATE_TIMEOUT`
  - `QUIT_TIMEOUT`
  - fallback `HANCOM_CONVERSION_TIMEOUT`
- Preserved 32-bit PowerShell and Hancom-only provider policy.
- Preserved one-file-per-process execution.
- Preserved cleanup scope to only newly detected `Hwp.exe` PIDs.
- Added stdout/stderr capture under `tmp/hancom_hwp_to_hwpx_diag/`.

## 남은 문제

- User-present Hancom check is needed to confirm the exact Open-stage prompt or security dialog.
- 3-file preflight conversion is blocked until at least one Open-only run succeeds.
- Batch conversion of 104 HWP files should not proceed yet.

## 다음 단계

- With Hancom visible/user-present, retry one Open-only diagnostic and observe any prompt.
- If one Open-only run succeeds, run one SaveAs diagnostic.
- If SaveAs succeeds and ZIP validation passes, run a 10-file preflight before considering the 104-file batch.
