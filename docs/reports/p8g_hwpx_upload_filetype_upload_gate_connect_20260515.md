# P8G HwpxUploadHandler FileType/Upload Gate Connect

## 1. 기준

- 작업명: OFFICE-ANALYSIS-P8G-HWPX-UPLOAD-FILETYPE-UPLOAD-GATE-CONNECT
- 기준 HEAD: `44431ce4077e338fe2184bead9859ab7f48b0a54`
- branch: `main`
- 대상 파일: `src/main/java/com/haehan/engine/http/HwpxUploadHandler.java`

## 2. Gate 연결 결과

| Gate | 결과 |
| --- | --- |
| `FileTypeGate` | `HwpxUploadHandler`가 Java gate 정책을 참조하고 HTML upload flow에 정책을 주입 |
| `UploadSecurityGate` | 기본 업로드 크기 제한과 pass result를 HTML upload flow에 주입 |
| `.hwpx` | `SERVER_ALLOWED` 정책으로 허용 |
| `.hwp` | `LOCAL_WORKER_REQUIRED` 정책으로 표시, 기존 conversion UI flow는 유지 |
| unknown extension | `UNKNOWN_EXTENSION_BLOCKED`로 차단 |
| path traversal | path separator 또는 `..` 포함 filename 차단 |
| empty filename | 차단 |
| unsafe control character | 차단 |
| size | `UploadSecurityGate.DEFAULT_MAX_UPLOAD_BYTES` 기준 초과 차단 |

## 3. Handler 영향

- endpoint path 변경: 없음
- 기존 API 응답 key 변경: 없음
- `/convert-hwp-to-hwpx` flow 변경: 없음
- `X-Conversion-Gate` 변경: 없음
- download/export flow 변경: 없음
- ExecutionLocationGate 연결: 이번 단계 제외
- OutputArtifactGate 연결: 이번 단계 제외
- HTML/UI 분리: 이번 단계 제외

## 4. 테스트 결과

| 검증 | 결과 |
| --- | --- |
| `python scripts/audit_hwpx_upload_handler_split_readiness.py` | WARN |
| `python -m pytest tests/test_hwpx_upload_handler_split_readiness.py -q` | PASS |
| `python scripts/audit_handler_gate_runtime_connections.py` | WARN |
| `python -m pytest tests/test_handler_gate_runtime_connections.py -q` | PASS |
| `python -m pytest tests/test_large_handler_gate_connections.py -q` | PASS |
| P1~P8F audit tests | PASS |
| `.\gradlew.bat tasks` | PASS |
| `.\gradlew.bat test` | PASS |
| known-prefix quoted literal scan | 0건 |

## 5. 남은 WARN

- `large_handler`: `HwpxUploadHandler`는 여전히 대형 handler다.
- `hwp_conversion_ui_flow`: ExecutionLocationGate 연결은 P8H에서 처리한다.
- `output_artifact_gate_not_connected`: download/report/export는 후속 단계에서 처리한다.
- `raw_path_candidate`: saved path 후보는 OutputArtifactGate 단계에서 처리한다.

## 6. 다음 단계

P8H에서 `HwpxUploadHandler`의 HWP conversion UI flow에 `ExecutionLocationGate`를 최소 연결한다. 이후 P8I/P9에서 output artifact gate와 HTML/UI 분리를 순차 진행한다.

## 7. 최종 판정

최종 판정: `WARN`
