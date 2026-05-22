# P9A: HwpxUploadHandler View 분리 보고서

**날짜**: 2026-05-15  
**기준 HEAD**: 9b0652e99be968976af13edb4a5be6d0b4812890  
**단계**: P9A  

---

## 1. 개요

P8I(OutputArtifactGate 연결) 완료 상태를 기준으로,  
3044라인 HwpxUploadHandler.java의 HTML/JS view 렌더링 책임을  
`HwpxUploadPageView.java`로 분리했다.  
기능 변경 없이 책임 분리만 수행.

---

## 2. 분리 전/후 handler line count

| 항목 | 분리 전 | 분리 후 |
|---|---|---|
| HwpxUploadHandler.java | 3044 라인 | 27 라인 |
| HwpxUploadPageView.java | 없음 | 3024 라인 |

---

## 3. 신규 파일

| 파일 | 설명 |
|---|---|
| `src/main/java/com/haehan/engine/http/HwpxUploadPageView.java` | HTML/JS 렌더링 전담 view 클래스 |
| `src/test/java/com/haehan/engine/http/HwpxUploadPageViewTest.java` | view 클래스 기본 테스트 6건 |

---

## 4. 이동한 책임 (→ HwpxUploadPageView)

- `PAGE_HTML_HEAD` (HTML 구조 + CSS)
- `PAGE_HTML_SCRIPT_1~4` (JavaScript 전체)
- `uploadGatePolicyScript()` (gate policy JS 생성)
- `gateResultJson()` / `jsString()` (유틸 메서드)
- `pageHtml()` (페이지 조립)
- 모든 gate 정적 필드 (FileTypeGate, UploadSecurityGate, ExecutionLocationGate, OutputArtifactGate)

---

## 5. 유지한 책임 (HwpxUploadHandler)

- HTTP GET endpoint 처리 (`handle()` 메서드)
- 405 method not allowed 응답 (`{"error":"method not allowed"}`)
- `HwpxUploadPageView.PAGE_HTML` 참조 후 응답 전송

---

## 6. Gate 유지 여부

| Gate | 위치 | 유지 여부 |
|---|---|---|
| FileTypeGate | HwpxUploadPageView (이동) | 유지 |
| UploadSecurityGate | HwpxUploadPageView (이동) | 유지 |
| ExecutionLocationGate | HwpxUploadPageView (이동) | 유지 |
| OutputArtifactGate | HwpxUploadPageView (이동) | 유지 |
| LOCAL_WORKER_REQUIRED | HwpxUploadPageView JS | 유지 |
| raw path guard | HwpxUploadPageView JS | 유지 |

---

## 7. endpoint / API 응답 key 유지 여부

- `/hwpx-editor`: 유지
- `/hwpx-upload`: 유지
- `{"error":"method not allowed"}`: 유지
- `/convert-hwp-to-hwpx`, `/api/hwpx/parse`, `/api/hwpx/editor`: 유지

---

## 8. 테스트 결과

| 테스트 | 결과 |
|---|---|
| `audit_hwpx_upload_handler_split_readiness.py` | WARN (tracked_dirty, raw_path_candidate_guarded) |
| `test_hwpx_upload_handler_split_readiness.py` | 7 PASS |
| `audit_handler_gate_runtime_connections.py` | WARN (convert preexisting, hwpx_upload dirty, inspection large) |
| `test_handler_gate_runtime_connections.py` | 5 PASS |
| `test_large_handler_gate_connections.py` | 2 PASS (same) |
| `test_api_upload_download_gate_audit.py` | PASS |
| 기타 P1~P8I audit tests | 8 PASS |
| `HwpxUploadPageViewTest` (Java) | 6 PASS (포함) |
| `gradlew tasks` | BUILD SUCCESSFUL |
| `gradlew test` | BUILD SUCCESSFUL |
| secret scan | 0건 (CLEAR) |

---

## 9. 남은 WARN/FAIL

| 항목 | 심각도 | 설명 |
|---|---|---|
| tracked_dirty_large_handler | WARN | 기존 dirty 상태 |
| raw_path_candidate_guarded | WARN | savedPath 후보 존재하나 guard 적용됨 |
| convert_handler_has_preexisting_gate_signals | WARN | ConvertHwpToHwpxHandler 기존 미정리 |
| inspection_large_handler_deferred | WARN | InspectionPageHandler 643 라인 |

---

## 10. P9B 권장안

**P9B: HwpxUploadPageView 추가 분리 또는 다음 도메인**

- view 파일이 여전히 3024 라인 → JS 모듈별 분리 가능
- 또는 다음 도메인 handler(InspectionPageHandler 등) gate 연결로 이동

---

## 11. 최종 판정

**PASS**

- view 분리: 완료 (3044 → 27 라인 handler)
- 신규 HwpxUploadPageView: 3024 라인
- gate 동작 유지: 확인
- endpoint/API key 유지: 확인
- 컴파일 성공: 확인
- gradlew test: BUILD SUCCESSFUL
- secret 노출: 없음
- push: 없음
