# P8I: HwpxUploadHandler OutputArtifactGate 연결 보고서

**날짜**: 2026-05-15  
**기준 HEAD**: 52da821c9de73ebf90cd452e1523541cf51d8cb1  
**단계**: P8I  

---

## 1. 개요

P8H(ExecutionLocationGate 연결) 완료 상태를 기준으로,  
HwpxUploadHandler의 download/export flow에 OutputArtifactGate를 최소 연결했다.  
raw filesystem path 직접 노출 차단 및 download filename sanitize 정책을 명확히 고정함.

---

## 2. OutputArtifactGate 연결 위치

| 항목 | 내용 |
|---|---|
| Java import | `com.haehan.engine.gate.OutputArtifactGate` 추가 |
| 정적 필드 | `HWPX_DOWNLOAD_ARTIFACT_GATE = OutputArtifactGate.validateResponseReference("hwpx.artifact")` |
| JS 정책 주입 | `uploadGatePolicy.outputArtifact.downloadGate` (서버 gate 결과를 JS에 주입) |
| 파일 | `src/main/java/com/haehan/engine/http/HwpxUploadHandler.java` |

---

## 3. downloadBlob / downloadRawBlob / downloadDraftJson 처리

| 함수 | 처리 내용 |
|---|---|
| `downloadBlob` | 기존 `.hwpx` 강제 extension 유지 (이미 안전) |
| `downloadRawBlob` | `outputArtifactSanitizeName()` 적용 추가 |
| `downloadDraftJson` | 하드코딩 안전 이름 유지 (변경 없음) |
| `outputArtifactSanitizeName()` | 새 helper: unsafe 문자 `_` 치환, `..` 치환 |

---

## 4. report/draft export flow 영향 여부

- inspection report 다운로드 (`hwpx-inspection-report.md`): `downloadRawBlob` → sanitize 통과
- dry run report 다운로드 (`hwpx-dry-run-report.md`): `downloadRawBlob` → sanitize 통과
- editor report 다운로드 (`hwpx-editor-report.md`): `downloadRawBlob` → sanitize 통과
- draft JSON 다운로드 (`hwpx-editor-draft.json`): `downloadRawBlob` → sanitize 통과
- 모든 다운로드 동작: **변경 없음** (이름이 이미 안전하고 sanitize 통과)

---

## 5. raw path response 처리

| 항목 | 처리 내용 |
|---|---|
| `X-Hwpx-Editor-Saved-Path` 헤더 | `outputArtifactRawPathGuard()` 적용 |
| raw path 감지 시 | `[artifact: raw-path-guarded]` 표시, `warn` 레벨 |
| artifact ref 감지 시 | `[artifact]` 표시, `ok` 레벨 |
| raw path 직접 로깅 | **차단** (이전: raw path 직접 `reportEvent`에 노출) |

---

## 6. artifact-id policy 적용 여부

- `OutputArtifactGate.newArtifactId()` Java 테스트로 검증됨
- `uploadGatePolicy.outputArtifact.downloadGate` JS 주입 완료
- `rawPathResponsePolicy: 'WARN'` 정책 명시

---

## 7. filename sanitize 적용 여부

- `outputArtifactSanitizeName(name, fallback)` JS helper 추가
- `[\/:*?"<>|]` → `_` 치환
- `..` → `_` 치환
- `downloadRawBlob()` 호출 시 모든 이름이 sanitize 통과

---

## 8. endpoint / API 응답 key 유지 여부

- `/hwpx-editor`: 유지
- `/hwpx-upload`: 유지
- `/convert-hwp-to-hwpx`: 유지
- `/api/hwpx/parse`: 유지
- `/api/hwpx/editor`: 유지
- `{"error": ...}` method-not-allowed 응답 key: 유지

---

## 9. 테스트 결과

| 테스트 | 결과 |
|---|---|
| `audit_hwpx_upload_handler_split_readiness.py` | WARN (tracked_dirty_large_handler, large_handler, raw_path_candidate_guarded) |
| `test_hwpx_upload_handler_split_readiness.py` | 6 PASS |
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

## 10. 남은 WARN/FAIL

| 항목 | 심각도 | 설명 |
|---|---|---|
| tracked_dirty_large_handler | WARN | HwpxUploadHandler 전체 dirty; 범위 외 |
| large_handler | WARN | 3045 라인; 분리는 별도 단계 |
| raw_path_candidate_guarded | WARN | savedPath 후보는 있으나 outputArtifactRawPathGuard 로 관리됨 |

---

## 11. P8J 권장안

**P9 / P8J: HwpxUploadHandler 1차 분리 또는 HTML/JS 분리**

- 3000+ 라인 handler를 별도 페이지 리소스 파일 또는 서브핸들러로 분리
- 또는 gate 연결 완료 선언 후 다음 도메인으로 이동

---

## 12. 최종 판정

**PASS (WARN 잔여)**

- OutputArtifactGate Java-side gate 연결: 완료
- raw path guard: 완료 (`outputArtifactRawPathGuard`)
- filename sanitize: 완료 (`outputArtifactSanitizeName`)
- 기존 download 동작 유지: 확인
- endpoint/API key 유지: 확인
- 직접 HWP/Hancom 실행 추가: 없음
- secret 노출: 없음
- push: 없음
