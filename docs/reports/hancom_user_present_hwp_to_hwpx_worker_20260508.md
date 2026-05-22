# Hancom User-Present HWP to HWPX Worker

## 문제

- COM 직접 `Open()`은 `OPEN_START`에서 timeout된다.
- 같은 HWP 파일은 한컴 GUI에서 파일 경로를 올바르게 quoting해서 실행하면 열린다.
- 따라서 실패 지점은 파일 자체가 아니라 COM 자동 Open 경로다.

## 전환 방향

- 변환 provider를 `HANCOM_USER_PRESENT_GUI`로 분리한다.
- 사용자가 실제로 하는 방식과 동일하게 `Hwp.exe "input.hwp"`로 GUI를 실행한다.
- 보안, 복구, 확인 팝업은 자동 클릭하지 않고 사용자가 직접 처리한다.
- 문서 열림을 사용자가 확인한 뒤 열린 한컴 인스턴스에 대해 HWPX 저장만 시도한다.
- 자동 SaveAs가 막히면 사용자가 직접 HWPX로 저장하고 worker는 결과 검증만 수행한다.

## 구현 내용

- `scripts/hwp-worker/Convert-HwpToHwpx-UserPresent.ps1`
  - HWP 파일을 한컴 GUI로 실행한다.
  - 파일명 기반 창 제목으로 열림 상태를 감지한다.
  - 사용자가 Enter 또는 `N`으로 열림 여부를 확정한다.
  - `GetActiveObject("HwpFrame.HwpObject.2")`로 열린 한컴 COM 객체에 붙어 `SaveAs(..., "HWPX", "")`를 시도한다.
  - 자동 SaveAs 실패 시 사용자 직접 저장 후 검증으로 전환한다.
  - `OutputPath` 존재, ZIP header, 내부 XML 존재를 검증한다.
- `scripts/hwpx/hancom_hwp_to_hwpx_batch.py`
  - `--provider HANCOM_USER_PRESENT_GUI` 추가.
  - user-present worker 호출 추가.
  - `--provider HANCOM_USER_PRESENT_GUI --limit 1`만 허용하도록 대량 실행 차단.

## 테스트 결과

- GUI Open: 확인됨.
- 자동 SaveAs: 아직 사용자 상호작용 환경에서 실행 필요.
- HWPX 생성: 아직 미검증.
- ZIP 검증: 아직 미검증.

## 정책

- 팝업 자동 클릭 금지.
- 원본 HWP 삭제 금지.
- 산출물은 `tmp/` 하위만 사용.
- 한컴 외 provider 추가 없음.
- 1건 성공 전 batch 금지.

## 다음 단계

1. 로컬 PowerShell에서 `HANCOM_USER_PRESENT_GUI` 1건 실행.
2. 한컴 팝업을 직접 확인하고 Enter 입력.
3. 자동 SaveAs 실패 시 안내된 경로에 직접 HWPX 저장 후 Enter 입력.
4. ZIP 검증 성공 시 3건 preflight 허용 정책을 별도로 완화한다.
