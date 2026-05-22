# HWPX Editor UI State Policy

**버전:** P12B  
**날짜:** 2026-05-15  
**상태:** CONFIRMED

---

## 1. 상태 정의

| Phase | 설명 |
|-------|------|
| IDLE | 초기 상태. 파일 없음. |
| UPLOADING | 파일 전송 중 (`/parse-hwpx` 호출 전) |
| UPLOADED | 파일 전송 완료. gate 검사 진행 중. |
| PARSING | `/parse-hwpx` 응답 대기 중 |
| READY | 파싱 완료. 편집 준비. |
| EDITING | 사용자가 block/cell 편집 중 (pendingEdits ≥ 1) |
| VALIDATING | `validateDocument` command 전송 중 |
| DRY_RUN | dry-run 요청 중 |
| SAVING | `/api/hwpx/editor` apply 요청 중 |
| EXPORTED | 저장/다운로드 완료 |
| ERROR | 오류 발생 |

---

## 2. 상태별 상세

### IDLE

- 화면: UploadCard (active), 나머지 비활성
- 허용 버튼: 없음 (파일 업로드만)
- badge: 없음
- API 호출: 금지
- command dispatch: 금지

### UPLOADING

- 화면: UploadCard (loading spinner)
- 허용 버튼: 없음
- badge: 없음 (progress bar 표시 가능)
- API 호출: `/parse-hwpx` 호출 중
- command dispatch: 금지

### UPLOADED

- 화면: GateStatusPanel 표시
- 허용 버튼: 없음 (gate 결과 확인 중)
- badge: StatusBadge (gate code)
- 게이트 FAIL → ERROR로 전이
- 게이트 PASS → PARSING으로 전이

### PARSING

- 화면: DocumentTree (loading), Main Editor (loading)
- 허용 버튼: 없음
- badge: 없음

### READY

- 화면: DocumentTree, DocumentPreview, BlockInspector 활성
- 허용 버튼: Validate, Dry Run
- badge: PASS (from parse)
- API 호출: 가능 (validate, dry-run)
- command dispatch: 가능

### EDITING

- 화면: 모든 편집 영역 활성, pendingEdits 목록 표시
- 허용 버튼: Validate, Dry Run, Save
- badge: EDITING (blue)
- command dispatch: 가능
- pendingEdits: CommandEdit[] (브라우저 메모리)

### VALIDATING

- 화면: ValidationPanel (loading)
- 허용 버튼: 없음 (응답 대기)
- badge: VALIDATING (blue spinner)

### DRY_RUN

- 화면: ValidationPanel + CommandResultPanel (preview)
- 허용 버튼: Save (dry-run 결과 확인 후)
- badge: DRY_RUN (blue)
- applied: false

### SAVING

- 화면: EditorToolbar (loading), Bottom Status (progress)
- 허용 버튼: 없음 (저장 완료 대기)
- badge: SAVING (spinner)
- API 호출: `/api/hwpx/editor` 호출 중

### EXPORTED

- 화면: ArtifactInfoPanel + DownloadPanel 활성
- 허용 버튼: Download, (계속 편집 → EDITING)
- badge: SAVED (green)
- artifactId 표시 (앞 8자)

### ERROR

- 화면: ErrorBoundaryPanel
- 허용 버튼: 재시도, 초기화(→ IDLE)
- badge: ERROR (red)
- 금지: stack trace 직접 표시

---

## 3. 상태 전이 다이어그램

```
IDLE
  → [파일 선택] → UPLOADING

UPLOADING
  → [gate 통과] → PARSING
  → [gate FAIL] → ERROR

PARSING
  → [parse 성공] → READY
  → [parse 실패] → ERROR

READY
  → [block 클릭 + 편집] → EDITING
  → [validate 클릭] → VALIDATING
  → [dry-run 클릭] → DRY_RUN

EDITING
  → [save 클릭] → SAVING
  → [validate 클릭] → VALIDATING
  → [dry-run 클릭] → DRY_RUN
  → [reset 클릭] → READY

VALIDATING
  → [결과 수신] → EDITING (또는 READY)
  → [오류] → ERROR

DRY_RUN
  → [결과 수신] → EDITING
  → [오류] → ERROR

SAVING
  → [성공] → EXPORTED
  → [실패] → ERROR

EXPORTED
  → [계속 편집] → EDITING
  → [새 파일] → IDLE

ERROR
  → [재시도] → 이전 phase
  → [초기화] → IDLE
```

---

## 4. 원칙

| 원칙 | 내용 |
|------|------|
| UI state ≠ HWPX state | UI 상태는 브라우저 local, HWPX 상태는 서버가 소유 |
| source of truth | server-side parsed model + artifactId |
| 브라우저 저장 | pendingEdits: JS 메모리 또는 sessionStorage |
| 서버 stateless | 서버는 세션 DB 없음 |
| 새로고침 | IDLE 복귀, 파일 재업로드 필요 |
| artifactId | UUID, 브라우저에 앞 8자만 표시 |
| raw path | 브라우저에서 절대 표시 금지 |
| command | EDITING 또는 READY 이상에서만 dispatch |

---

## 5. 버튼 활성 조건 요약

| 버튼 | 활성 phase |
|------|-----------|
| Validate | READY, EDITING |
| Dry Run | READY, EDITING |
| Save | EDITING |
| Download | EXPORTED |
| Reset | READY, EDITING, ERROR |

---

## 6. API 호출 가능 조건

| API | 가능 phase |
|-----|-----------|
| POST /parse-hwpx | UPLOADING |
| POST /api/hwpx/editor (dry-run) | READY, EDITING, DRY_RUN |
| POST /api/hwpx/editor (apply) | SAVING |
| POST /api/hwpx/editor (validate) | VALIDATING |
