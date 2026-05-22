# Hancom HWP Converter Router Scaffold

## 목적

HWP -> HWPX 변환을 특정 구현 하나에 고정하지 않고, 현재 PC에서 사용할 수 있는 한컴 변환 경로를 provider 단위로 판정하는 router scaffold를 만들었다.

이번 작업은 변환 성공 구현이 아니라 안전한 변환 도구의 기준선이다. 기본 동작은 `preflight`이며, 1건 성공 전 batch 변환은 허용하지 않는다.

## 구현 파일

- `scripts/hwpx/hancom_hwp_converter_router.py`

## Provider 우선순위

1. `official_converter`
2. `sdk`
3. `com`
4. `local_gui`
5. `user_present`

## Provider 판정

| provider | 현재 상태 | blocker | 다음 조치 |
| --- | --- | --- | --- |
| `official_converter` | `NOT_INSTALLED` 또는 내부 후보만 존재 | `OFFICIAL_ADDIN_NOT_INSTALLED` | 공식 HWPX Converter Add-in 설치 후 재탐색 |
| `sdk` | `LICENSE_REQUIRED` | `SDK_NOT_INSTALLED_OR_LICENSE_NOT_CONFIRMED` | Hwp SDK 라이선스/설치/API 샘플 확인 |
| `com` | `BLOCKED_SAVEAS_TIMEOUT` | `COM_SAVEAS_HWPX_TIMEOUT` | Open/preflight 용도로만 유지 |
| `local_gui` | `BLOCKED_SAVE_DIALOG_NOT_FOUND` | `SAVE_DIALOG_NOT_FOUND` | 저장창 탐지 해결 전 저장 금지 |
| `user_present` | `AVAILABLE_MANUAL_FALLBACK` | `REQUIRES_USER_PRESENT_SAVEAS` | 정책 승인 시 최후 fallback |

## 실행 정책

- 기본 모드: `preflight`
- 입력: HWP 1건만 허용하는 설계
- batch 변환: 거부
- 실제 변환 실행: `--allow-execute` 및 verified provider가 생기기 전까지 거부
- 출력/리포트: `tmp/hancom_hwp_converter_router/` 하위

## CLI 예시

Provider 판정만 실행:

```powershell
python scripts/hwpx/hancom_hwp_converter_router.py `
  --output-dir tmp/hancom_hwp_converter_router
```

HWP 1건 기준 라우팅 계획:

```powershell
python scripts/hwpx/hancom_hwp_converter_router.py `
  --input "C:\path\sample.hwp" `
  --output-dir tmp/hancom_hwp_converter_router `
  --mode preflight
```

현재 `convert` 모드는 provider가 verified로 승격되기 전까지 실행하지 않는다.

## 결과 산출물

- `router_report.json`
- `provider_status.csv`

## 현재 결론

현재 자동 실행 가능한 verified provider는 없다.

HWP 변환의 다음 순서는 다음과 같다.

1. 공식 HWPX Converter Add-in 설치/탐색
2. Add-in이 CLI면 router의 `official_converter` provider 구현
3. Add-in이 GUI면 공식 변환기 GUI provider 구현
4. SDK 도입 시 `sdk` provider 구현
5. COM/Local GUI는 fallback으로 유지

## 다음 개발 후보

- `official_converter` post-install discovery 결과를 router detector에 연결
- provider별 `execute_one()` 인터페이스 정의
- HWPX output ZIP/XML 검증 공통 모듈 분리
- 1건 성공 후 3건, 이후 30건 단위 preflight
