# P9C: HWPX Upload/Parse Usecase 분리 보고서

**날짜**: 2026-05-15
**기준 HEAD**: 37bb0e1213c6fb4e25270b6b5c952f0805eadd61
**단계**: P9C

---

## 1. 개요

P9B 완료 상태(HwpxUploadPageView → 25라인)를 기준으로,
HWPX upload/parse 흐름의 Application Layer 경계를 설정했다.
기능 변경 없이 usecase skeleton + gate 연결 구조를 추가.
ParseHwpxHandler 연결은 P9D로 이월.

---

## 2. 신규 파일

| 파일 | 라인 | 역할 |
|---|---|---|
| `src/main/java/com/haehan/engine/usecase/HwpxUploadParseUseCase.java` | 57라인 | Application layer: FileTypeGate + UploadSecurityGate + HwpxParser 조율 |
| `src/main/java/com/haehan/engine/usecase/HwpxUploadParseResult.java` | 57라인 | Result DTO: Status(PASS/GATE_REJECTED/PARSE_ERROR) + gate result + parse response |

---

## 3. 책임 위치 조사 결과

| 컴포넌트 | 현재 위치 | 역할 |
|---|---|---|
| ParseHwpxHandler | http 패키지 | POST `/api/hwpx/parse` — raw binary 수신, 임시파일, HwpxParser 호출. Gate 미적용. |
| HwpxEditorApiHandler | http 패키지 | POST `/api/hwpx/editor` — multipart, Python bridge, archive. |
| HwpxUploadHandler | http 패키지 | GET `/hwpx-upload` — upload page HTML만 반환. |
| HwpxUploadParseUseCase | **usecase 패키지 (신규)** | FileTypeGate + UploadSecurityGate 검사 후 HwpxParser 위임. |

---

## 4. ParseHwpxHandler 연결 이월 이유

| 항목 | 현재 동작 | Gate 연결 후 동작 |
|---|---|---|
| 빈 파일명 | 허용 (UUID 대체) | UploadSecurityGate → FAIL |
| 파일 크기 무제한 | 허용 | UploadSecurityGate 80MB 제한 적용 |
| 확장자 미검사 | 허용 | FileTypeGate → 미지원 확장자 거부 |

→ 기능 동작 변경에 해당 → P9D에서 API key 유지 + 명시적 연결.

---

## 5. Layer Boundary 확인

- `HwpxUploadParseUseCase`는 `com.haehan.engine.http` import 없음
- `com.haehan.engine.usecase` 패키지에 위치
- gate, contract, parser 패키지만 의존

---

## 6. Gate 유지 여부

| Gate | 위치 | 유지 여부 |
|---|---|---|
| FileTypeGate | GatePolicy (JS) + UseCase (Java) | 유지 |
| UploadSecurityGate | GatePolicy (JS) + UseCase (Java) | 유지 |
| ExecutionLocationGate | GatePolicy (JS) | 유지 |
| OutputArtifactGate | GatePolicy (JS) | 유지 |

---

## 7. 테스트 결과

| 테스트 | 결과 |
|---|---|
| `HwpxUploadParseUseCaseTest` | **8 PASS** |
| `HwpxUploadParseResultTest` | **3 PASS** |
| `test_hwpx_upload_handler_split_readiness.py` | **9 PASS** |
| `test_handler_gate_runtime_connections.py` | **5 PASS** |
| `gradlew test` | **BUILD SUCCESSFUL** |
| secret scan | **0건 (CLEAR)** |

pre-existing FAIL 1건: `test_p8e_reports_hunk_split_decision` — P9A에서 `.hwpx` accept가 handler에서 styles로 이동한 이후 발생, P9C와 무관.

---

## 8. 남은 WARN

| 항목 | 설명 |
|---|---|
| `ParseHwpxHandler_gate_wiring_deferred_to_P9D` | usecase 연결 P9D로 이월 |
| `raw_path_candidate_guarded` | savedPath guard 적용됨 |
| `convert_handler_has_preexisting_gate_signals` | ConvertHwpToHwpxHandler 미정리 |
| `inspection_large_handler_deferred` | InspectionPageHandler 643라인 |

---

## 9. 최종 판정

**PASS**

- HwpxUploadParseUseCase skeleton: 완료
- layer boundary (http 미import): 확인
- gate 동작 유지: 확인
- endpoint/API key 유지: 확인
- gradlew test: BUILD SUCCESSFUL
- secret 노출: 없음
- push: 없음

---

## 10. P9D 권장안

**P9D: ParseHwpxHandler에 HwpxUploadParseUseCase 연결**

- `ParseHwpxHandler`에 usecase 호출 추가
- 기존 `{"error": ...}` 응답 key 유지
- FileTypeGate 거부 → 415 / UploadSecurityGate 거부 → 413 or 400
- gradlew test PASS 확인 후 커밋
