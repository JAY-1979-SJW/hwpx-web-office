# OFFICE-ANALYSIS-P8A-CONVERT-HWP-HANDLER-BASELINE-AND-GATE-CONNECT

## 1. 기준선

- 기준 HEAD: `32c41460b8e1c1ff1cbacc6d832d582c07b8f4ac`
- branch: `main`
- hook 경로: `scripts/hooks`
- 기준 dirty: tracked 35건, staged 0건, untracked status entries 121건, deleted 0건
- push: 수행하지 않음
- history secret 위험: 사용자 처리 항목으로 유지
- working tree known-prefix quoted literal: 0건

## 2. Handler 정체 감사

대상: `src/main/java/com/haehan/engine/http/ConvertHwpToHwpxHandler.java`

- 판정: `BASELINE_CANDIDATE`
- package: `com.haehan.engine.http`
- handler type: `HttpHandler`
- endpoint path: `/convert-hwp-to-hwpx`
- registry 연결: working tree의 `EngineHttpServer.java`에 연결 후보 존재
- registry 커밋 여부: 보류
  - `EngineHttpServer.java`는 기존 tracked dirty와 섞여 있어 이번 P8A 커밋 대상에서 제외
- 의존 Java bridge:
  - `src/main/java/com/haehan/engine/hwp/HwpToHwpxCliBridge.java`
  - `src/main/java/com/haehan/engine/hwp/HwpToHwpxRouterBridge.java`
  - `src/main/java/com/haehan/engine/hwp/PythonScriptBridge.java`
- process execution 후보: bridge 계층에 존재
- P8A 조치: handler 진입부에서 `ExecutionLocationGate`를 먼저 적용하여 일반 서버 요청의 직접 변환 실행을 차단

## 3. Gate 연결

`ConvertHwpToHwpxHandler`에 `ExecutionLocationGate`를 최소 연결했다.

- HWP/Hancom 변환 operation: `LOCAL_WORKER_REQUIRED`
- 일반 서버 요청: `409` + 기존 `ErrorResponse(error, message, policy)` 구조 유지
- remote worker provider 요청: 기존 `forwardToRemoteWorker` 경로 유지
- local worker 표시 요청: `X-Remote-Worker-Request: true`일 때만 기존 conversion runner 진입 허용
- remote worker loop 후보: `REMOTE_WORKER_LOOP_BLOCKED`로 차단
- 추가 응답 header:
  - `X-Execution-Location-Gate`
  - `X-Required-Execution-Location`

기존 endpoint path와 기존 JSON 응답 key는 변경하지 않았다.

## 4. 보안 상태

| 항목 | 결과 |
|---|---|
| server-side HWP/Hancom direct conversion | 기본 차단 |
| local worker required 정책 | runtime 코드에 명시 |
| 실제 Hancom/HWP 실행 추가 | 없음 |
| 외부 브라우저 실행 | 없음 |
| DB write | 없음 |
| schema 변경 | 없음 |
| secret 값 출력 | 없음 |
| known-prefix quoted literal | 0건 |

## 5. 테스트/감사 결과

| 항목 | 결과 |
|---|---|
| `.\gradlew.bat test --tests "*ConvertHwpToHwpxHandlerTest"` | PASS |
| `python scripts/audit_handler_gate_runtime_connections.py` | WARN, 실행 PASS |
| `python scripts/audit_large_handler_gate_connections.py` | WARN, 실행 PASS |
| P1~P7 audit tests | PASS |
| `.\gradlew.bat tasks` | PASS |
| `.\gradlew.bat test` | PASS |
| working tree known-prefix quoted literal scan | 0건 |

## 6. 커밋 후보

P8A 커밋 후보:

- `src/main/java/com/haehan/engine/http/ConvertHwpToHwpxHandler.java`
- `src/main/java/com/haehan/engine/hwp/HwpToHwpxCliBridge.java`
- `src/main/java/com/haehan/engine/hwp/HwpToHwpxRouterBridge.java`
- `src/main/java/com/haehan/engine/hwp/PythonScriptBridge.java`
- `src/test/java/com/haehan/engine/http/ConvertHwpToHwpxHandlerTest.java`
- `src/test/java/com/haehan/engine/hwp/HwpToHwpxCliBridgeTest.java`
- `docs/reports/p8a_convert_hwp_handler_baseline_gate_20260515.md`
- `docs/reports/p8a_convert_hwp_handler_baseline_gate_20260515.json`

## 7. 커밋 보류/제외

- `EngineHttpServer.java`: endpoint registry 연결 후보가 있으나 기존 tracked dirty와 혼재되어 P8A 커밋 제외
- `HwpxUploadHandler.java`: 변경 금지
- `InspectionPageHandler.java`: 변경 금지
- Dockerfile 계열: 변경 금지
- HWPX engine 대형 변경: 커밋 금지
- local-gui 대형 변경: 커밋 금지

## 8. 남은 WARN

1. `EngineHttpServer.java`의 `/convert-hwp-to-hwpx` registry 연결은 기존 dirty와 섞여 있어 아직 커밋하지 않음
2. HWP bridge 계층은 process execution 기능을 포함하므로 반드시 `ExecutionLocationGate` 이후 경로에서만 사용해야 함
3. API meta contract 일관 적용은 후속 단계 필요
4. raw path/output artifact 정책은 후속 단계 필요
5. `HwpxUploadHandler` gate 직접 연결은 후속 단계 필요

## 9. 수행하지 않은 작업 확인

- 기존 dirty/untracked 삭제 없음
- git clean/reset/restore/checkout/stash 없음
- pull/push 없음
- remote/upstream 변경 없음
- DB write/schema 변경 없음
- 외부 브라우저 실행 없음
- secret 값 출력 없음
- endpoint path 변경 없음
- 기존 API 응답 key 변경 없음
- 실제 Hancom/HWP 실행 추가 없음
- `HwpxUploadHandler` 변경 없음
- `InspectionPageHandler` 변경 없음
- Dockerfile 변경 없음

## 10. 최종 판정

WARN

handler 기준선과 execution gate 연결은 완료했다. 다만 endpoint registry 파일이 기존 dirty와 섞여 있어 이번 커밋에서 제외되므로 WARN을 유지한다.
