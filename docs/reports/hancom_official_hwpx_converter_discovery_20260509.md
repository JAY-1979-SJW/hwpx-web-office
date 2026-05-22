# Hancom Official HWPX Converter Discovery

## 목적

한컴 본프로그램의 COM/GUI SaveAs 자동화 대신, 한컴이 별도로 제공하는 HWPX 변환기 또는 Add-in이 로컬 PC에 설치되어 있는지 확인했다. 이번 작업은 탐색 전용이며 HWP 원본 변환, HWPX 저장, batch 실행은 수행하지 않았다.

## 기준 상태

- 기준 HEAD: `5b111df86c3c43e4941a4460b0f2e9847b3ad7e3`
- staged 파일: 없음
- 탐색 산출물: `tmp/hancom_official_hwpx_converter_discovery/`

## 탐색 범위

다음 위치에서 `HWPX`, `변환`, `Convert`, `Converter`, `Add-in`, `Hwp` 관련 파일을 탐색했다.

- `C:\Program Files (x86)\HNC`
- `C:\Program Files\HNC`
- `%LOCALAPPDATA%`
- `%APPDATA%`
- `%ProgramData%\Microsoft\Windows\Start Menu\Programs`
- `%USERPROFILE%\Desktop`
- `%USERPROFILE%\Downloads`

설치 프로그램 목록은 HKCU/HKLM uninstall registry 기준으로 확인했다. 시작 메뉴 바로가기는 `.lnk` target과 arguments를 확인했다.

## 발견된 후보

한컴오피스 설치 폴더에서 다음 converter 이름의 실행 파일이 확인됐다.

| 파일 | 설명 | 버전 | 판정 |
| --- | --- | --- | --- |
| `C:\Program Files (x86)\HNC\Office 2024\HOffice130\Bin\HwpConverter.exe` | `HwpConverter` | `13, 0, 0, 3457` | 내부 converter 후보, 공식 HWPX Add-in 여부 미확정 |
| `C:\Program Files (x86)\HNC\Office 2024\HOffice130\Bin\HpdfHwpConverter.exe` | `HpdfHwpConverter` | `13, 0, 0, 3457` | PDF/HWP 관련 내부 후보 |
| `C:\Program Files (x86)\HNC\Office 2024\HOffice130\Bin\HncPUAConverter.exe` | `Hancom PUAConverter` | `13, 0, 0, 3457` | 문자/PUA 변환 후보 |
| `C:\Program Files (x86)\HNC\Office 2024\HOffice130\Bin\OdfConverter.exe` | `OpenXML/ODF Translator Command Line Tool` | `1.0.0.0` | ODF 변환 도구, HWPX 변환기 아님 |

## 설치 프로그램/바로가기 확인

HKCU/HKLM uninstall registry에서 `HWPX`, `한컴`, `Hancom`, `변환`, `Converter` 조건으로 별도 HWPX 변환기/Add-in 설치 항목은 확인되지 않았다.

시작 메뉴에서 확인된 한컴 관련 바로가기는 아래 2개뿐이었다.

| 바로가기 | Target |
| --- | --- |
| 한컴 기본 설정 2024 | `HConfig.exe` |
| 한컴 자동 업데이트 2024 | `HncUpdater.exe` |

`HWPX 변환기`, `HWPX Converter`, `Add-in` 성격의 별도 바로가기는 확인되지 않았다.

## Help/CLI probe

후보 실행 파일에 대해 변환 실행 없이 help/version 성격의 인자만 짧은 timeout으로 확인했다.

| 파일 | 인자 | 결과 |
| --- | --- | --- |
| `HwpConverter.exe` | `/?`, `--help`, `-help` | timeout, stdout/stderr 없음 |
| `HpdfHwpConverter.exe` | `/?`, `--help`, `-help` | timeout, stdout/stderr 없음 |
| `HncPUAConverter.exe` | `/?`, `--help`, `-help` | timeout, stdout/stderr 없음 |
| `OdfConverter.exe` | `/?`, `--help`, `-help` | 종료됐으나 HWPX 변환 CLI 근거 없음 |

help probe 중 생성된 빈 `Hwp.exe` 프로세스는 이번 작업에서 새로 생긴 PID만 지정해 정리했다.

## 판정

| 항목 | 판정 |
| --- | --- |
| 공식 HWPX 변환기/Add-in 설치 여부 | `OFFICIAL_CONVERTER_NOT_INSTALLED` |
| 내부 converter 후보 | `INTERNAL_CONVERTER_CANDIDATE_FOUND` |
| CLI 변환 가능 여부 | `UNKNOWN` |
| GUI 전용 여부 | `UNKNOWN` |
| 30개 단위 변환 가능성 | 공식 Add-in 설치 후 확인 필요 |

현재 로컬에서 확인된 `HwpConverter.exe`는 한컴오피스 본체 설치 폴더의 내부 구성 파일로 보인다. 별도 Add-in 설치 항목, 시작 메뉴 바로가기, help 출력이 없어 한컴 FAQ의 공식 HWPX 변환기와 동일한 도구로 단정하지 않는다.

## 다음 단계

1. 한컴 공식 다운로드 센터에서 추가 기능(Add-in) `HWPX 변환기` 설치 여부를 대표님 PC에서 확인한다.
2. 설치 후 시작 메뉴/설치 프로그램/실행 파일/바로가기를 재탐색한다.
3. CLI 인자가 확인되면 1건 HWP를 `tmp/hancom_official_hwpx_converter_test/` 하위로 변환 테스트한다.
4. CLI가 없고 GUI 전용이면 공식 변환기 GUI를 대상으로 별도 UI 자동화 가능성을 검토한다.
5. 1건 성공 후에만 3건, 이후 30건 단위 preflight로 확장한다.

## 결론

한컴 본프로그램 SaveAs 자동화보다 공식 HWPX 변환기/Add-in 경로가 우선 검토 대상인 것은 맞다. 다만 현재 PC에서는 별도 공식 HWPX 변환기/Add-in 설치 흔적이 확인되지 않았다. 한컴오피스 내부 `HwpConverter.exe`는 후보로 기록하되, 공식 Add-in 또는 자동 변환 CLI로 판정하려면 추가 근거가 필요하다.
