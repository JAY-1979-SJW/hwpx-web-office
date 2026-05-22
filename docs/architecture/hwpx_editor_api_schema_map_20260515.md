# HWPX Editor API Schema Map

**버전:** P13A  
**날짜:** 2026-05-15  
**상태:** CONFIRMED

---

## 1. Endpoint 목록 (변경 금지)

| Endpoint | Method | 역할 |
|----------|--------|------|
| `/hwpx-editor` | GET | 편집기 UI 페이지 |
| `/parse-hwpx` | POST | HWPX 파일 parse (octet-stream) |
| `/api/hwpx/editor` | POST | command dispatch + upload/archive/download |
| `/convert-hwp-to-hwpx` | POST | HWP → HWPX 변환 |
| `/api/hwpx/parse` | POST | HWPX parse (browser 직접 호출) |

---

## 2. `/api/hwpx/editor` 요청 유형

### 유형 A: Command Dispatch (P13~)
- Content-Type: `application/json`
- Body: `HwpxEditorCommand` JSON
- 판정 기준: `Content-Type.startsWith("application/json")`
- 처리: `HwpxEditorApiHandler.handleCommandDispatch()` → `HwpxEditorCommandUseCase.execute()`

### 유형 B: Upload / Archive / Download (기존)
- Content-Type: `multipart/form-data; boundary=...`
- Body: `plan` + `file` + `operation` + `dry_run` 등
- 처리: 기존 multipart 흐름 유지

---

## 3. Command Request Schema (유형 A)

```json
{
  "commandId": "uuid-string",
  "commandType": "validateDocument | replaceText | updateTableCell | ...",
  "artifactId": "uuid-string (validateDocument 제외 필수)",
  "target": { ... },
  "payload": { ... },
  "dryRun": true,
  "expectedVersion": null,
  "requestId": null
}
```

**금지 키 (target/payload):**
`secret`, `token`, `password`, `cookie`, `session`, `auth`, `credential`,  
`apikey`, `api_key`, `access_token`, `private_key`, `signing_key`

**금지 값 패턴 (target/payload):**
- Unix raw path: `/home/`, `/var/`, `/tmp/`, `~/`
- Windows raw path: `C:\`, `D:\`
- 상위 경로: `../`, `..\`
- ZIP/XML entry: `BinData/`, `Contents/`, `.xml`, `.rels`

---

## 4. Command Type별 Schema

### validateDocument
```json
{ "commandType": "validateDocument", "target": {}, "payload": {}, "dryRun": true }
```
- artifactId: 불필요
- target: 없음
- payload: 없음

### replaceText (dryRun only in P13)
```json
{
  "commandType": "replaceText",
  "artifactId": "uuid",
  "target": { "paragraphIndex": 0 },
  "payload": { "oldText": "...", "replacement": "..." },
  "dryRun": true
}
```

### updateTableCell (dryRun only in P13)
```json
{
  "commandType": "updateTableCell",
  "artifactId": "uuid",
  "target": { "tableIndex": 0, "row": 0, "col": 0 },
  "payload": { "value": "..." },
  "dryRun": true
}
```

### replacePlaceholder (P14 이후)
```json
{
  "commandType": "replacePlaceholder",
  "artifactId": "uuid",
  "target": {},
  "payload": { "key": "...", "value": "..." },
  "dryRun": true
}
```

### updateParagraph / addTableRow / deleteTableRow
P14 이월. schema는 `hwpx_editor_command_contract_20260515.json` 참조.

---

## 5. Command Response Schema

### 성공 (200)
```json
{
  "status": "PASS | WARN | DRY_RUN_ONLY | APPLY_DEFERRED",
  "commandId": "uuid",
  "commandType": "validateDocument",
  "requestId": "server-generated-uuid",
  "artifactId": "uuid",
  "dryRun": true,
  "applied": false,
  "validationResult": { "allowed": true, "code": "COMMAND_VALID", "message": "...", "violations": [] },
  "warnings": [],
  "errors": [],
  "schemaVersion": "1.0",
  "engineVersion": "0.6.2"
}
```

### 실패 - gate 거부 (422)
```json
{
  "status": "GATE_REJECTED",
  "commandId": "...",
  "validationResult": { "allowed": false, "code": "RAW_PATH_IN_COMMAND", "message": "..." },
  "applied": false,
  "schemaVersion": "1.0",
  "engineVersion": "0.6.2"
}
```

### 실패 - 잘못된 요청 (400)
```json
{ "error": "INVALID_COMMAND", "message": "commandType is required" }
```

---

## 6. 기존 응답 key (변경 금지)

| 기존 key | 유형 | 변경 여부 |
|---------|------|---------|
| `error` | error response | 금지 |
| `message` | error response | 금지 |
| `status` | command response | 금지 |
| `dry_run` | old multipart response | 금지 |
| `report` | old multipart response | 금지 |
| `exitCode` | old error response | 금지 |

---

## 7. artifactId 정책

| 항목 | 내용 |
|------|------|
| P13 | 브라우저가 `crypto.randomUUID()` 생성 (sessionArtifactId) |
| P14 | server-side parse 시 UUID 생성 → 브라우저에 반환 |
| 표시 | 앞 8자만 UI 표시 (e.g. `c684e55d…`) |
| 금지 | raw filesystem path 대신 artifactId만 참조 |

---

## 8. dryRun 정책

| 항목 | 내용 |
|------|------|
| P13 기본값 | `dryRun: true` 항상 |
| P13 apply | APPLY_DEFERRED 반환 (실제 수정 없음) |
| P14 apply | ApplyEngine 실제 연결 후 `applied: true` 가능 |
| applied=false | dryRun 또는 APPLY_DEFERRED 상태에서 항상 false |

---

## 9. meta contract (변경 금지)

| key | 값 |
|-----|----|
| `schemaVersion` | `"1.0"` |
| `engineVersion` | `"0.6.2"` |
| `requestId` | `UUID.randomUUID().toString()` |

---

## 10. P13 범위 / P14 이월

| 항목 | P13 | P14 |
|------|-----|-----|
| validateDocument dispatch | ✅ | |
| replaceText dryRun | ✅ | |
| updateTableCell dryRun | ✅ | |
| actual apply | ❌ | ✅ |
| server-side artifactId | ❌ | ✅ |
| replacePlaceholder | ❌ | ✅ |
| updateParagraph | ❌ | ✅ |
| addTableRow / deleteTableRow | ❌ | ✅ |
