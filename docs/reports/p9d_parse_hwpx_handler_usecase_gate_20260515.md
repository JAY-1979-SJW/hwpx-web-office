# P9D: ParseHwpxHandler Usecase Gate 연결 보고서

**날짜**: 2026-05-15
**기준 HEAD**: ac85ddf481d3c9f1832598bbc6e8f3ac448bbf26
**단계**: P9D

---

## 1. 개요

P9C에서 추가한 `HwpxUploadParseUseCase`를 `ParseHwpxHandler`에 연결했다.
FileTypeGate / UploadSecurityGate 거부 결과를 기존 `{"error":"..."}` key를 유지하면서 HTTP 상태 코드로 매핑했다.

---

## 2. ParseHwpxHandler 변경 요약

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| 라인 수 | 99 | 103 |
| body 처리 | InputStream → FileOutputStream 스트리밍 | `readAllBytes()` → usecase 전달 |
| parser 호출 | `new HwpxParser().parse(tempFile, requestId)` | `HwpxUploadParseUseCase.execute(...)` |
| gate 검사 | 없음 | usecase 내부에서 FileTypeGate + UploadSecurityGate |
| Parser 주입 | 불가 | `package-private` 생성자로 주입 가능 |

---

## 3. Status Code 매핑

| 조건 | HTTP 상태 |
|---|---|
| `.hwpx` 정상 업로드 + parse 성공 | 200 |
| `.hwpx` 정상 업로드 + parse 실패 | 400 (기존 동작 유지) |
| 미지원 확장자 (`.bin`, `.pdf` 등) | **415** |
| `.hwp` (로컬 워커 필요) | **415** |
| 경로 순회 filename | **400** |
| 빈 body | **400** |
| 파일 크기 초과 (>80MB) | **413** |
| 파싱 중 예외 | 500 (기존 동작 유지) |
| GET 메서드 | 405 (기존 동작 유지) |

---

## 4. API 유지 여부

- endpoint path `/parse-hwpx`: 유지
- error key `{"error":"..."}`: 유지
- 성공 응답 구조 (`DocumentParseResponse`): 유지
- method not allowed: 유지

---

## 5. 테스트 결과

| 테스트 | 결과 |
|---|---|
| `ParseHwpxHandlerTest` 기존 12건 | **PASS (변경 없음)** |
| `ParseHwpxHandlerTest` 신규 4건 (P9D gate rejection) | **PASS** |
| `HwpxUploadParseUseCaseTest` | 8 PASS |
| `test_parse_hwpx_handler_usecase_gate.py` | **6 PASS** |
| `test_hwpx_upload_handler_split_readiness.py` | 9 PASS |
| `test_handler_gate_runtime_connections.py` | 5 PASS |
| 전체 Python | **29 PASS** (pre-existing 1 FAIL 제외) |
| `gradlew test` | **BUILD SUCCESSFUL** |
| secret scan | **0건 (CLEAR)** |

---

## 6. Audit 결과

```
parse_hwpx_handler_usecase_gate_status=PASS
finding_count=0
```

---

## 7. 남은 WARN

| 항목 | 설명 |
|---|---|
| `raw_path_candidate_guarded` | savedPath guard 적용됨 |
| `convert_handler_has_preexisting_gate_signals` | ConvertHwpToHwpxHandler 미정리 |
| `inspection_large_handler_deferred` | InspectionPageHandler 643라인 |

---

## 8. 최종 판정

**PASS**

- ParseHwpxHandler usecase 연결: 완료
- gate 거부 → 415/413/400 매핑: 완료
- layer boundary (http 미import): 확인
- 기존 API 응답 key 유지: 확인
- endpoint path 유지: 확인
- gradlew test: BUILD SUCCESSFUL
- secret 노출: 없음
- push: 없음

---

## 9. P9E 권장안

**P9E: download/export usecase 분리 또는 ConvertHwpToHwpxHandler gate 정규화**

- `HwpxEditorApiHandler`의 download/archive 흐름을 OutputArtifactGate와 연결
- 또는 `ConvertHwpToHwpxHandler`의 기존 gate signal 정규화
