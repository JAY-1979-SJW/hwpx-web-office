# P13 Report: HWPX Browser Editor Command Dispatch

**날짜:** 2026-05-15  
**단계:** P13  
**기준 HEAD:** 462645a (P12B 완료 시점)  
**상태:** PASS

---

## 결과 요약

| 항목 | 결과 |
|------|------|
| audit_hwpx_browser_editor_structure | PASS (finding 0) |
| test_hwpx_browser_editor_structure (27 tests) | 27/27 PASS |
| audit_ui_design_system | PASS |
| test_ui_design_system (15 tests) | 15/15 PASS |
| audit_api_meta_contract | PASS |
| test_new_code_structure_rules | PASS |
| ./gradlew test | BUILD SUCCESSFUL (11 new dispatch tests) |
| secret scan | 0건 |

---

## 구현 내용

### 1. Browser Command Dispatch (HwpxUploadPageScripts.java — SCRIPT_5)

| 함수 | 설명 |
|------|------|
| `initSessionArtifactId()` | 문서 로드 시 UUID 기반 세션 참조 ID 생성 |
| `buildEditorCommand(type, target, payload, opts)` | command JSON 생성 (dryRun=true 기본) |
| `dispatchEditorCommand(command)` | `/api/hwpx/editor` JSON POST 전송 |
| `renderEditorCommandResult(result)` | commandResultPanel 결과 렌더링 |
| `validateEditorDocument()` | validateDocument command dispatch |
| `dryRunReplaceText(paragraphIndex, oldText, newText)` | replaceText dryRun dispatch |
| `dryRunUpdateTableCell(tableIndex, row, col, value)` | updateTableCell dryRun dispatch |

### 2. UI 패널 추가 (HwpxUploadPageStyles.java)

| 추가 항목 | 설명 |
|----------|------|
| `.cmd-result-panel` | Command 결과 표시 패널 CSS |
| `.cmd-dispatch-section` | 명령 dispatch 버튼 영역 CSS |
| `.badge-dry-run` / `.badge-pass` / `.badge-reject` | Status badge CSS |
| `commandResultPanel` HTML | Command 결과 표시 div |
| `cmdDispatchSection` HTML | validateDocument 버튼 포함 dispatch 섹션 |

### 3. API Handler Wiring (HwpxEditorApiHandler.java)

| 변경 | 내용 |
|------|------|
| JSON 분기 추가 | `Content-Type: application/json` → `handleCommandDispatch()` |
| `handleCommandDispatch()` | `HwpxEditorCommandUseCase.execute()` 호출 → JSON 응답 |
| 기존 multipart flow | 변경 없음 (boundary 없으면 400) |
| 응답 meta | schemaVersion, engineVersion 포함 |

---

## 지원 Command (dryRun only)

| commandType | target 필수 키 | payload 필수 키 | 비고 |
|-------------|---------------|----------------|------|
| validateDocument | 없음 | 없음 | artifactId 불필요 |
| replaceText | paragraphIndex | oldText, replacement | artifactId 필요 |
| updateTableCell | tableIndex, row, col | value | artifactId 필요 |
| (미구현) replacePlaceholder | — | — | P14 이월 |
| (미구현) updateParagraph | — | — | P14 이월 |
| (미구현) addTableRow | — | — | P14 이월 |
| (미구현) deleteTableRow | — | — | P14 이월 |

---

## 보안 차단 결과

| 항목 | 결과 |
|------|------|
| raw path in payload (`/etc/passwd`) | GATE_REJECTED 422 |
| secret key in payload (`password`) | GATE_REJECTED 422 |
| unknown commandType | GATE_REJECTED 422 |
| XML/ZIP 직접 조작 | JS command dispatch에 없음 |
| 실제 apply (HWPX 수정) | 전부 APPLY_DEFERRED — 실제 변경 없음 |
| raw path 표시 | commandResultPanel에 미표시 |
| stack trace 표시 | 금지 — message만 표시 |

---

## dryRun 처리

- 모든 command dispatch는 `dryRun: true` 기본
- `HwpxEditorCommandUseCase.execute()` → `APPLY_DEFERRED` 반환
- `applied: false` 유지
- 실제 HWPX 파일 수정 없음

---

## sessionArtifactId 처리

- 브라우저가 `crypto.randomUUID()`로 생성
- 문서 파싱 후 첫 command dispatch 시 초기화
- artifactId = server-side 없음 (P14에서 실제 parse artifact와 연결)
- raw path 아님 — UUID만 전달

---

## UI 표준 준수

- Top Accent Line 유지
- 기존 element id 변경 없음
- 기존 upload/download flow 변경 없음
- commandResultPanel: navy/neutral 기반, orange 강조 minimal
- raw path 표시 없음

---

## 기존 API 불변 확인

- `/api/hwpx/editor` endpoint path 변경 없음
- multipart flow (plan/file form) 변경 없음
- 기존 응답 key 변경 없음 (additive meta만 추가)
- gate 동작 변경 없음

---

## 남은 WARN

없음 (finding 0건)

---

## P14 권장안

- `HwpxEditorCommandUseCase.execute()` ApplyEngine 실제 연결
- parse 시 server-side artifactId 반환 → browser에 저장
- sessionArtifactId → server-side artifactId로 교체
- validateDocument: 실제 HWPX 파싱 결과 검증
- replaceText / updateTableCell apply 실행

---

## 최종 판정: PASS

- browser command dispatch 구조 완성
- server usecase wiring 완성
- 보안 차단 동작 확인
- 기존 flow 변경 없음
- push 없음
