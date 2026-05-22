# HWPX Editor Command Schema Contract

**버전:** P13A  
**날짜:** 2026-05-15  
**상태:** CONFIRMED — HwpxEditorValidationGate로 강제됨

---

## 1. Supported Commands (MVP)

| commandType | target 필수 키 | payload 필수 키 | P13 구현 |
|-------------|---------------|----------------|---------|
| validateDocument | 없음 | 없음 | ✅ |
| replaceText | paragraphIndex (int≥0) | 없음 (비어도 통과) | ✅ dryRun |
| updateTableCell | tableIndex, row, col (int≥0) | value | ✅ dryRun |
| replacePlaceholder | 없음 | — | ❌ P14 |
| updateParagraph | paragraphIndex (int≥0) | — | ❌ P14 |
| addTableRow | tableIndex (int≥0) | — | ❌ P14 |
| deleteTableRow | tableIndex (int≥0) | — | ❌ P14 |

## 2. Post-MVP Commands (WARN 반환, apply 없음)

| commandType | 비고 |
|-------------|------|
| replaceImage | P15 이후 |
| insertChart | P15 이후 |
| updateCellStyle | P15 이후 |
| saveDocument | 내부 처리 |
| exportHwpx | 별도 export flow |

---

## 3. HwpxEditorCommand 필드

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| commandId | String (UUID) | 권장 | 브라우저가 생성, 서버는 그대로 반환 |
| commandType | String | 필수 | supported 목록에 있어야 함 |
| artifactId | String (UUID) | validateDocument 제외 필수 | sessionArtifactId (P13) |
| target | Map<String,Object> | commandType별 | 대상 지정 |
| payload | Map<String,Object> | commandType별 | 변경 내용 |
| dryRun | boolean | 권장 | true=검증만, false=실제 수정 (P14) |
| expectedVersion | String | 선택 | 낙관적 잠금 (P14) |
| requestId | String | 선택 | null 허용, 서버가 신규 생성 |

---

## 4. HwpxEditorValidationResult 코드

| code | severity | 의미 |
|------|----------|------|
| COMMAND_VALID | PASS | 검증 통과 |
| COMMAND_WARN | WARN | Post-MVP command |
| POST_MVP_COMMAND | WARN | Post-MVP command |
| NULL_COMMAND | FAIL | command 객체 null |
| MISSING_COMMAND_TYPE | FAIL | commandType 없음 |
| UNKNOWN_COMMAND_TYPE | FAIL | 지원하지 않는 commandType |
| MISSING_ARTIFACT_ID | FAIL | artifactId 없음 (validateDocument 제외) |
| MISSING_TARGET | FAIL | target 필요한데 없음 |
| MISSING_PAYLOAD | FAIL | payload 필요한데 없음 |
| FORBIDDEN_KEY_IN_COMMAND | FAIL | secret/token/password 등 |
| RAW_PATH_IN_COMMAND | FAIL | filesystem path / ZIP/XML entry |
| COMMAND_INVALID | FAIL | 기타 검증 실패 |

---

## 5. HwpxEditorCommandResult 상태

| status | 의미 | applied |
|--------|------|---------|
| PASS | 검증 통과 + apply 완료 (P14) | true |
| WARN | 검증 WARN + apply 완료 (P14) | true |
| GATE_REJECTED | 게이트 거부 | false |
| DRY_RUN_ONLY | dryRun=true → 수정 없음 | false |
| APPLY_DEFERRED | ApplyEngine 미연결 (P13) | false |
| INTERNAL_ERROR | 내부 오류 | false |

---

## 6. target 유효성 상세

### updateTableCell
```
target.tableIndex : int ≥ 0
target.row        : int ≥ 0
target.col        : int ≥ 0
```

### replaceText / updateParagraph
```
target.paragraphIndex : int ≥ 0  (또는 paragraph_index)
```

### addTableRow / deleteTableRow
```
target.tableIndex : int ≥ 0  (또는 table_index)
```

---

## 7. 보안 금지 기준

### 금지 키 (target, payload)
`secret`, `token`, `password`, `cookie`, `session`, `auth`, `credential`,
`apikey`, `api_key`, `access_token`, `private_key`, `signing_key`

### 금지 값 패턴 (모든 String 값)
- raw Unix path: `/`, `~/`, `../`
- raw Windows path: `C:\`
- ZIP/XML entry: `BinData/`, `Contents/`, `.xml`, `.rels`

---

## 8. 코드 참조

- 게이트 구현: `gate/HwpxEditorValidationGate.java`
- 결과 모델: `usecase/HwpxEditorCommandResult.java`
- 검증 결과 모델: `gate/HwpxEditorValidationResult.java`
- 요청 모델: `contract/HwpxEditorCommand.java`
- 실행 흐름: `usecase/HwpxEditorCommandUseCase.java`
