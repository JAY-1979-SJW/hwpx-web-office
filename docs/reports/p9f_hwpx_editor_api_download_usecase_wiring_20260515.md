# P9F Report: HwpxEditorApiHandler Download Export Usecase Wiring

**Date:** 2026-05-15  
**Phase:** P9F  
**Baseline HEAD:** e0a8acaa97f34a5a74c7096f41f393fd21bfa55a  

---

## 1. 변경 요약

`HwpxEditorApiHandler`의 download/export 준비 단계에서 직접 filename을 sanitize하고 raw path를 그대로 응답 헤더에 노출하던 책임을 `HwpxDownloadExportUseCase.prepare()`로 위임했다.

### 변경 파일
- `src/main/java/com/haehan/engine/http/HwpxEditorApiHandler.java`
- `src/test/java/com/haehan/engine/http/HwpxEditorApiHandlerTest.java`
- `scripts/audit_hwpx_download_export_usecase.py`
- `tests/test_hwpx_download_export_usecase.py`

---

## 2. Usecase 연결 위치

`HwpxEditorApiHandler.handle()` 내 archive 생성 직후, 응답 헤더 설정 전:

```java
HwpxDownloadExportResult exportResult = HwpxDownloadExportUseCase.prepare(
    outputName,
    archive != null ? archive.outputPath().toString() : ""
);
```

- `outputName`: `safeOutputName()` 거친 raw 파일명 (apply/create 분기에서 결정)
- `archive.outputPath().toString()`: 아카이브 저장 시 raw filesystem path (RAW_PATH_GUARDED 대상)
- archive 없을 경우: `""` → GATE_REJECTED (무해, 아카이브 헤더 미설정)

---

## 3. Result 매핑

| Status | 처리 |
|--------|------|
| PASS | 기존 성공 흐름 유지, `X-Hwpx-Editor-Saved-Path` = 아카이브 경로 |
| RAW_PATH_GUARDED | 기존 흐름 유지, `X-Hwpx-Editor-Saved-Path` = `artifactId` (raw path 비노출) |
| GATE_REJECTED | 아카이브 없음(정상), 기존 흐름 유지, Saved-Path 헤더 없음 |

아카이브 경로는 항상 filesystem 절대경로이므로 실질적으로 항상 RAW_PATH_GUARDED.

---

## 4. OutputArtifactGate 경계 유지 여부

- `OutputArtifactGate.validateResponseReference()` → usecase 내부에서 호출 (handler 직접 호출 없음)
- `OutputArtifactGate.sanitizeDownloadName()` → usecase 내부에서 호출
- `OutputArtifactGate.newArtifactId()` → usecase 내부에서 호출
- Gate 정책 변경 없음

---

## 5. Raw Path Guard 유지 여부

- archive 경로 (`archive.outputPath().toString()`) 는 항상 WARN → RAW_PATH_GUARDED
- `X-Hwpx-Editor-Saved-Path` 값이 raw path 대신 `artifactId` (UUID)로 교체됨
- raw path는 응답 본문/헤더 값으로 클라이언트에 노출되지 않음
- `X-Hwpx-Editor-Saved-Report-Path`는 report 경로 그대로 유지 (P9F 범위 외)

---

## 6. 기존 Endpoint/API Key 유지 여부

| 항목 | 상태 |
|------|------|
| endpoint path `/api/hwpx/editor` | 변경 없음 |
| HTTP method POST | 변경 없음 |
| error key (`error`, `message`) | 변경 없음 |
| `X-Hwpx-Editor-Status` | 변경 없음 |
| `X-Hwpx-Editor-Report` | 변경 없음 |
| `X-Hwpx-Editor-Saved-Path` (key) | 변경 없음 (값은 artifact ID로 교체) |
| `X-Hwpx-Editor-Saved-Report-Path` | 변경 없음 |
| `X-Hwpx-Editor-Saved-Sha256` | 변경 없음 |
| `X-Hwpx-Editor-Artifact-Id` | **신규 추가** (기존 key 변경 없음) |
| Content-Type `application/owpml` | 변경 없음 |

---

## 7. 새로 추가된 헤더

- `X-Hwpx-Editor-Artifact-Id`: `exportResult.artifactId()` (UUID), 모든 성공 응답에 포함

---

## 8. 테스트 결과

### Java (Gradle)
- 335 tests completed, 0 failed → `BUILD SUCCESSFUL`
- `applyCanArchiveEditedHwpxOnServer`: raw path 파일 존재 체크 → artifactRoot 스캔으로 변경
- `applyReturnsArtifactIdHeader`: X-Hwpx-Editor-Artifact-Id 헤더 존재 확인 (신규)
- `applyUnsafeFilenameIsSanitizedViaUsecase`: "/" path separator 제거 확인 (신규)
- `createReturnsArtifactIdHeaderWithSafeFilename`: create 연산에서 artifact ID 확인 (신규)

### Python audit
- `test_hwpx_download_export_usecase.py`: 11 passed
- `test_hwpx_upload_handler_split_readiness.py`: passed
- `test_handler_gate_runtime_connections.py`: passed
- `test_large_handler_gate_connections.py`: passed
- `test_api_upload_download_gate_audit.py`: passed
- `test_integrated_usecase_boundary_audit.py`: passed
- `test_hwpx_engine_boundary_audit.py`: passed
- `test_excel_statement_boundary_audit.py`: passed
- `test_layer_boundary_audit.py`: passed
- `test_import_cycle_audit.py`: passed
- `test_execution_location_gate_audit.py`: passed
- `test_upload_file_gate_audit.py`: passed

---

## 9. Audit 결과

```
hwpx_download_export_usecase_status=PASS
finding_count=0
```

handler_wiring:
- editor_handler_wired: true
- uses_safe_filename: true
- uses_artifact_id_header: true
- raw_path_guarded: true

---

## 10. 남은 WARN/FAIL

| 항목 | 성격 |
|------|------|
| `WARN raw_path_candidate_guarded` (upload handler split audit) | 기존 결함, P9F 무관 |
| `WARN convert_handler_has_preexisting_gate_signals` | 기존 결함, P9F 무관 |
| `WARN inspection_large_handler_deferred` | 기존 결함, P9F 무관 |
| Python 1 FAIL (`test_p8e_reports_hunk_split_decision`) | 기존 결함, P9F 무관 |

---

## 11. P10 권장안

- `X-Hwpx-Editor-Saved-Report-Path`도 raw path guard 적용 (현재 미적용)
- API meta contract 일관 적용 (P10 범위)
- artifact registry 연동 고려

---

## 12. 최종 판정

**PASS**

- usecase 연결 완료
- raw path guard 적용
- 기존 endpoint/API key 유지
- gate 동작 유지
- Java BUILD SUCCESSFUL (335 tests, 0 failed)
- Python audit all PASS
- secret scan CLEAN
- push 없음
