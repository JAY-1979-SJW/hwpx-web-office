# P8F HwpxUploadHandler Dirty Baseline Decision

## 1. 기준

- 작업명: OFFICE-ANALYSIS-P8F-HWPX-UPLOAD-HANDLER-DIRTY-BASELINE-DECISION
- 기준 HEAD: `06463896e24376172ac800a4f08ccab9f1df00f5`
- branch: `main`
- 대상 파일: `src/main/java/com/haehan/engine/http/HwpxUploadHandler.java`
- 대상 상태: tracked dirty 대형 handler
- 변경 규모: 2776 insertions / 327 deletions
- 파일 규모: 2895 lines

## 2. Dirty 전체 감사 결과

| 항목 | 결과 |
| --- | --- |
| endpoint path 변경 | 없음으로 판단 |
| 기존 API 응답 key 변경 | 없음으로 판단 |
| HTML/UI 변경 | 있음 |
| upload flow 변경 | 있음 |
| `.hwpx` 처리 flow | 있음 |
| `.hwp` conversion UI flow | 있음 |
| `/convert-hwp-to-hwpx` 호출 flow | 있음 |
| file/path/temp 처리 후보 | 있음 |
| download/report/export flow | 있음 |
| raw path response 후보 | 있음 |
| HWP/Hancom 직접 실행 | 없음 |
| 외부 브라우저 실행 | 없음 |
| DB write | 없음 |
| known-prefix quoted secret literal | 0건 |
| 테스트/디버그 로그성 코드 | 대형 UI flow에 포함 가능, 별도 P8G 이후 정리 필요 |

## 3. Baseline 판정

- 판정: `BASELINE_WARN`
- 커밋 가능 여부: 가능
- 이유:
  - FAIL급 위험인 secret literal, server-side HWP/Hancom 직접 실행, 외부 브라우저 실행, DB write, endpoint/API key 변경 후보가 발견되지 않았다.
  - 다만 handler가 2895줄 대형 UI/handler로 남아 있고 gate 연결이 아직 직접 적용되지 않았으며 raw path 후보가 남아 있어 WARN 기준선으로만 볼 수 있다.

## 4. 남은 WARN

- `large_handler`: 대형 handler가 계속 분리 대상이다.
- `hwp_conversion_ui_flow`: HWP conversion UI flow는 후속 P8G/P8H에서 gate 연결이 필요하다.
- `file_type_gate_not_connected`: `FileTypeGate` 직접 연결이 아직 없다.
- `upload_security_gate_not_connected`: `UploadSecurityGate` 직접 연결이 아직 없다.
- `execution_location_gate_not_connected`: handler 내부 conversion UI flow와 runtime gate 연결은 후속 작업이다.
- `output_artifact_gate_not_connected`: download/report/export output 후보는 후속 작업이다.
- `raw_path_candidate`: saved path/report 후보는 output artifact 정책으로 감싸야 한다.

## 5. 테스트 결과

| 검증 | 결과 |
| --- | --- |
| `python scripts/audit_hwpx_upload_handler_split_readiness.py` | WARN / `BASELINE_WARN` |
| `python -m pytest tests/test_hwpx_upload_handler_split_readiness.py -q` | PASS |
| P1~P8E audit tests | PASS |
| `.\gradlew.bat tasks` | PASS |
| `.\gradlew.bat test` | PASS |
| known-prefix quoted literal scan | 0건 |

## 6. 커밋 판단

- `HwpxUploadHandler.java` 전체 dirty를 P8F 기준선으로 커밋 가능하다.
- 커밋 대상은 `HwpxUploadHandler.java`, P8F audit 보강 파일, P8F 보고서로 제한한다.
- Dockerfile, local-gui, HWPX engine 다른 대형 파일, untracked 산출물은 커밋하지 않는다.

## 7. 다음 단계 권장안

P8F 기준선 커밋 후 P8G에서 `FileTypeGate`와 `UploadSecurityGate`를 실제 handler 진입부에 최소 연결한다. 이후 별도 단계에서 `ExecutionLocationGate`, `OutputArtifactGate`, raw path artifact-id 전환, HTML/UI 분리를 순차 처리한다.

## 8. 최종 판정

최종 판정: `WARN`
