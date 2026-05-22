# P8H: HwpxUploadHandler HWP Conversion ExecutionLocationGate 연결 보고서

**날짜**: 2026-05-15  
**기준 HEAD**: bde45ed027d53859ea984c5b2516be20ab812572  
**단계**: P8H  

---

## 1. 개요

P8G(FileTypeGate/UploadSecurityGate 연결) 완료 상태를 기준으로,  
HwpxUploadHandler의 HWP conversion UI flow에 ExecutionLocationGate를 최소 연결했다.  
`.hwp` / Hancom 변환은 `LOCAL_WORKER_REQUIRED` 정책으로 명확히 고정됨.

---

## 2. ExecutionLocationGate 연결 위치

| 항목 | 내용 |
|---|---|
| Java import | `com.haehan.engine.gate.ExecutionLocationGate` 추가 |
| 정적 필드 | `HWP_CONVERSION_EXECUTION_GATE = ExecutionLocationGate.classifyOperation("hwp.conversion")` |
| JS 정책 주입 | `uploadGatePolicy.hwpConversionExecution` (서버 gate 결과를 JS에 주입) |
| 파일 | `src/main/java/com/haehan/engine/http/HwpxUploadHandler.java` |

---

## 3. .hwp conversion UI flow 처리

| 위치 | 변경 내용 |
|---|---|
| `selectFile()` | HWP 파일 선택 시 `LOCAL_WORKER_REQUIRED` 안내 + `renderVerification` 표시 |
| `validateUploadFile()` | `LOCAL_WORKER_REQUIRED` 경로에서 `ExecutionLocationGate` 코드도 함께 `reportEvent` |
| `renderHwpConversionNotice()` | 변환 완료 notice에 `실행 위치: LOCAL_WORKER_REQUIRED` 항목 추가 |

---

## 4. /convert-hwp-to-hwpx flow 영향 여부

- `/convert-hwp-to-hwpx` endpoint path: **변경 없음**
- `convertHwpToHwpx()` 함수 구조: **변경 없음**
- `X-Conversion-Gate` 헤더 읽기: **변경 없음**
- 실제 HWP/Hancom 실행: **추가 없음**

---

## 5. X-Conversion-Gate 처리

- `X-Conversion-Gate` 헤더는 서버(ConvertHwpToHwpxHandler)가 반환하는 헤더이며 P8H에서 변경 없음.
- ExecutionLocationGate 정책(`LOCAL_WORKER_REQUIRED`)은 `uploadGatePolicy.hwpConversionExecution`으로 별도 제공됨.
- `renderHwpConversionNotice`에서 두 값을 함께 표시함.

---

## 6. LOCAL_WORKER_REQUIRED 적용 여부

| 정책 | 적용 여부 |
|---|---|
| `.hwp` → LOCAL_WORKER_REQUIRED | PASS (FileTypeGate + ExecutionLocationGate 양쪽에서 표시) |
| HWP/Hancom conversion → LOCAL_WORKER_REQUIRED | PASS (hwpConversionExecution gate 주입) |
| `.hwpx` → SERVER_ALLOWED | PASS (기존 유지) |
| password/otp/sign → USER_PRESENT_REQUIRED | 범위 외 (P8H 제외) |

---

## 7. endpoint / API 응답 key 유지 여부

- `/hwpx-editor`: 유지
- `/hwpx-upload`: 유지
- `/convert-hwp-to-hwpx`: 유지
- `/api/hwpx/parse`: 유지
- `/api/hwpx/editor`: 유지
- `{"error": ...}` method-not-allowed 응답 key: 유지

---

## 8. 테스트 결과

| 테스트 | 결과 |
|---|---|
| `audit_hwpx_upload_handler_split_readiness.py` | WARN (tracked_dirty_large_handler, large_handler, output_artifact_gate_not_connected, raw_path_candidate) |
| `test_hwpx_upload_handler_split_readiness.py` | 5 PASS |
| `audit_handler_gate_runtime_connections.py` | WARN (convert preexisting, hwpx_upload dirty, inspection large) |
| `test_handler_gate_runtime_connections.py` | 3 PASS |
| `test_large_handler_gate_connections.py` | 2 PASS |
| `test_api_upload_download_gate_audit.py` | PASS |
| `test_integrated_usecase_boundary_audit.py` | PASS |
| `test_hwpx_engine_boundary_audit.py` | PASS |
| `test_excel_statement_boundary_audit.py` | PASS |
| `test_layer_boundary_audit.py` | PASS |
| `test_import_cycle_audit.py` | PASS |
| `test_execution_location_gate_audit.py` | PASS |
| `test_upload_file_gate_audit.py` | PASS |
| `gradlew tasks` | BUILD SUCCESSFUL |
| `gradlew test` | BUILD SUCCESSFUL |
| secret scan | 0건 (CLEAR) |

---

## 9. 남은 WARN/FAIL

| 항목 | 심각도 | 설명 |
|---|---|---|
| tracked_dirty_large_handler | WARN | HwpxUploadHandler 전체가 dirty; 범위 외 |
| large_handler | WARN | 3000+ 라인; 분리는 별도 단계 |
| output_artifact_gate_not_connected | WARN | OutputArtifactGate 연결은 P8I 범위 |
| raw_path_candidate | WARN | savedPath 등 후보; OutputArtifactGate 연결 시 처리 예정 |

---

## 10. P8I 권장안

**P8I: HwpxUploadHandler OutputArtifactGate 연결**

- `downloadBlob`, `downloadRawBlob`, `downloadDraftJson` 등 download flow에 OutputArtifactGate 최소 연결
- `X-Hwpx-Editor-Saved-Path` raw path 후보 처리

---

## 11. 최종 판정

**PASS (WARN 잔여)**

- ExecutionLocationGate Java-side gate 연결: 완료
- LOCAL_WORKER_REQUIRED UI 안내: 완료
- 기존 conversion UI flow 유지: 확인
- endpoint/API key 유지: 확인
- 직접 HWP/Hancom 실행 추가: 없음
- secret 노출: 없음
- push: 없음
