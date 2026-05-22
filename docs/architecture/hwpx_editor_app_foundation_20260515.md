# HWPX Editor App Foundation Architecture

**버전:** F0 (Foundation Lock)
**날짜:** 2026-05-15
**기준선 HEAD:** 9c081f2
**상태:** LOCKED — audit gate + operating rules로 강제됨

---

## 1. 앱 목적

HWPX Browser Editor는 서버에 업로드된 HWPX 문서를 브라우저에서 구조적으로 검수·편집·검증할 수 있게 하는 웹 애플리케이션이다.

**핵심 목적:**
- HWPX 문서의 텍스트/표 셀 내용을 브라우저에서 command 기반으로 수정
- 수정 전 dryRun 검증을 통해 안전한 변경 보장
- 편집 결과를 서버 artifact로 보존하고 다운로드 가능하게 제공
- 감리 서류·관공서 제출 서류의 구조적 무결성 검증

**범위 밖:**
- HWPX 신규 문서 생성 (기존 문서 편집만)
- 다중 사용자 동시 편집 (단일 세션 기반)
- 실시간 협업
- 문서 포맷 변환 (hwp→hwpx 변환은 별도 엔드포인트)

---

## 2. 앱 Boundary

| 경계 영역 | 범위 | 비고 |
|-----------|------|------|
| **UI** | 브라우저 JS (HwpxUploadPageScripts.java 내 SCRIPT_5) | 서버 렌더링, SPA 아님 |
| **API** | `/api/hwpx/editor`, `/api/hwpx/parse`, `/hwpx-editor`, `/hwpx-upload`, `/parse-hwpx` | HTTPS, JSON/multipart |
| **Command** | replaceText, updateTableCell, validateDocument | dryRun=true 전용 (F0) |
| **Artifact** | ArtifactRegistry (in-memory, UUID key) | 영속화 미구현 (F0) |
| **Storage** | 서버 로컬 파일시스템 (tmpdir 기반) | DB 연동 없음 (F0) |
| **Security** | FileTypeGate, UploadSecurityGate, HwpxEditorValidationGate | 인증/인가 미구현 (F0) |
| **Audit** | audit gate Python 스크립트 + Gradle 테스트 | production 이벤트 로그 미구현 (F0) |
| **Deployment** | 로컬 개발 서버 (localhost) | nginx/TLS/DNS 미연결 (F0) |

---

## 3. 레이어 구조

```
┌─────────────────────────────────────────────────────┐
│  UI Layer                                           │
│  HwpxUploadPageScripts (SCRIPT_5 — JS 섹션)         │
│  buildEditorCommand(), sendCommand(), renderResult() │
└───────────────────────┬─────────────────────────────┘
                        │ JSON POST /api/hwpx/editor
┌───────────────────────▼─────────────────────────────┐
│  API Handler Layer                                  │
│  HwpxEditorApiHandler (command dispatch)            │
│  HwpxProxyHandler     (multipart upload → artifact) │
│  ParseHwpxHandler     (read-only parse)             │
│  HwpxUploadHandler    (upload page render)          │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│  UseCase Layer                                      │
│  HwpxEditorCommandUseCase (validate → defer/apply)  │
│  HwpxUploadParseUseCase   (upload gate + parse)     │
│  HwpxDownloadExportUseCase (export/download)        │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│  Validation/Gate Layer                              │
│  HwpxEditorValidationGate  (command contract)       │
│  FileTypeGate              (HWPX MIME/ext)          │
│  UploadSecurityGate        (ZIP 구조 검사)           │
│  OutputArtifactGate        (output 정책)             │
│  ExecutionLocationGate     (실행 위치 제한)           │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│  Domain/Command Model Layer                         │
│  HwpxEditorCommand         (command contract)       │
│  HwpxEditorCommandResult   (result contract)        │
│  HwpxEditorValidationResult (gate 판정)             │
│  DocumentParseResponse     (parse 결과)             │
│  ApiResponseMeta           (schema/engine 버전)     │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│  Engine Adapter Layer                               │
│  ApplyEngine (interface — F0 미연결)                │
│  PythonScriptBridge (Python 호출 — F0 미연결)       │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│  Infra/Storage Layer                                │
│  ArtifactRegistry    (in-memory ConcurrentHashMap)  │
│  ArtifactMetadata    (artifactId, fileName, type)   │
│  ArtifactIdGenerator (UUID)                         │
│  HwpxParser          (read-only Java parser)        │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Auth/Permission Layer  (F0: 미구현)                │
│  향후: SessionManager, RoleGate, TokenValidator      │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Workflow Layer  (F0: UseCase 내 인라인)             │
│  향후: WorkflowEngine, StateTransitionGate           │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Audit/Event Layer  (F0: 미구현)                    │
│  향후: AuditEventLogger, EventStore                  │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Test/Gate Layer                                    │
│  scripts/audit_hwpx_editor_architecture_gate.py     │
│  src/test/java/.../*Test.java                        │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Documentation/Report Layer                         │
│  docs/architecture/   docs/reports/                 │
└─────────────────────────────────────────────────────┘
```

**의존성 방향:** 위 → 아래만. 하위 레이어는 상위 레이어 import 금지.
**순환 import 금지:** UseCase → http.* 금지. Gate → usecase.* 금지. Domain → gateway.* 금지.

---

## 4. 권한/역할 모델

### F0 상태 (미구현)

F0에서는 인증/인가 레이어가 없다. 모든 요청은 서버에 접근 가능한 클라이언트가 동등하게 처리된다.

### 목표 역할 모델 (F1 이후 구현 예정)

| 역할 | 허용 operation | 비고 |
|------|----------------|------|
| **viewer** | /parse-hwpx, /hwpx-editor (read-only 렌더) | 편집 불가 |
| **editor** | validateDocument, replaceText, updateTableCell (dryRun=true) | 실제 저장 불가 |
| **approver** | dryRun=false 허용, outputArtifact 생성 | ApplyEngine 연결 후 |
| **admin** | 모든 operation + artifact 삭제 + 레지스트리 조회 | 내부 전용 |

### F0 보안 게이트 (현재 적용 중)

- `FileTypeGate`: HWPX MIME/확장자 검사
- `UploadSecurityGate`: ZIP 구조, 경로 순회 방지, 최대 크기
- `HwpxEditorValidationGate`: commandType 허용 목록, artifactId 필수, FORBIDDEN_KEYS, raw path 금지
- `ExecutionLocationGate`: 실행 위치 제한

### 클라이언트 세션 정책 (F0)

- `clientSessionId`: 브라우저가 생성하는 correlation ID. artifactId 대체 불가.
- `artifactId`: 서버가 업로드 시 발급하는 UUID. 모든 command에 필수.
- 두 값은 서로 다른 목적. 혼용 금지. (RULE-18, RULE-21)

---

## 5. Workflow State Machine

### 문서 편집 세션 상태

```
[IDLE]
  │
  │ 사용자 파일 선택 + 업로드
  ▼
[UPLOADING]
  │ FileTypeGate, UploadSecurityGate 통과
  │
  ├─ FAIL → [UPLOAD_REJECTED] (422, 재시도 가능)
  │
  │ ArtifactRegistry.register(artifactId)
  ▼
[ARTIFACT_REGISTERED]
  │
  │ /parse-hwpx 호출
  ▼
[PARSING]
  │ HwpxParser 실행
  │
  ├─ FAIL → [PARSE_FAILED] (500, 재업로드 필요)
  │
  ▼
[PARSED] — DocumentParseResponse 반환됨
  │
  │ 브라우저 UI 렌더링 완료
  ▼
[READY_FOR_COMMAND]
  │
  │ buildEditorCommand() → POST /api/hwpx/editor
  ▼
[COMMAND_DISPATCHING]
  │ HwpxEditorValidationGate.validate()
  │
  ├─ GATE_REJECTED → [COMMAND_REJECTED] (422, READY_FOR_COMMAND으로 복귀)
  │
  │ dryRun=true (F0 기본값, 고정)
  ▼
[DRY_RUN_EVALUATED]
  │ HwpxEditorCommandUseCase → APPLY_DEFERRED
  │
  │ applied=false, result 반환
  ▼
[DRY_RUN_REPORTED] — 결과 UI 표시
  │
  │ 다음 command 또는 세션 종료
  ▼
[READY_FOR_COMMAND] (루프)

--- F0에서 진입 불가한 상태 (미래) ---

[APPLYING]        — dryRun=false, ApplyEngine 연결 후
[APPLY_SUCCEEDED] — outputArtifact 생성 후
[APPLY_FAILED]    — 엔진 오류 후
[DOWNLOADING]     — outputArtifact 다운로드 중
[DOWNLOADED]      — 세션 완료
[SESSION_EXPIRED] — ArtifactRegistry TTL 초과 (미구현)
```

### 상태 전이 규칙

| 전이 | 조건 | 담당 컴포넌트 |
|------|------|---------------|
| IDLE → UPLOADING | 파일 선택 | UI |
| UPLOADING → UPLOAD_REJECTED | gate fail | UploadSecurityGate, FileTypeGate |
| UPLOADING → ARTIFACT_REGISTERED | gate pass + register | HwpxProxyHandler |
| ARTIFACT_REGISTERED → PARSED | parse 성공 | ParseHwpxHandler |
| PARSED → READY_FOR_COMMAND | UI 렌더 완료 | UI |
| READY_FOR_COMMAND → COMMAND_REJECTED | gate reject | HwpxEditorValidationGate |
| READY_FOR_COMMAND → DRY_RUN_EVALUATED | gate pass, dryRun | HwpxEditorCommandUseCase |
| DRY_RUN_EVALUATED → DRY_RUN_REPORTED | 응답 수신 | UI |

---

## 6. Artifact Storage Policy

### F0 정책 (현재 적용 중)

| 항목 | 정책 |
|------|------|
| **저장소** | 서버 in-memory (ConcurrentHashMap) |
| **키** | UUID (ArtifactIdGenerator) |
| **메타데이터** | `{artifactId, originalFileName, contentType, createdAt}` |
| **파일 경로** | ArtifactMetadata에 저장 안 함 — 별도 파일시스템 관리 |
| **TTL** | 미구현 (서버 재시작 시 전체 소멸) |
| **다중 버전** | 미구현 |
| **outputArtifact** | 생성 금지 (ApplyEngine 미연결) |
| **영속화** | 미구현 — RULE-21 적용 |

### 발급 경로

```
HwpxProxyHandler → ArtifactRegistry.register(artifactId, metadata)
                → 응답: {"artifactId": "uuid-...", "sessionArtifactId": "..."}

ParseHwpxHandler → ArtifactRegistry 등록 없음 (RULE-20)
                → 응답: {"artifactId": null}
```

### 참조 정책

- UI: artifactId 앞 8자만 표시 (RULE-04)
- 서버 응답: raw path 절대 포함 금지 (RULE-03, RULE-19)
- command 응답: request의 artifactId를 그대로 echo (RULE-19)
- download: `X-Hwpx-Editor-Saved-Path` 헤더에 artifactId 기반 참조

### F1 이후 목표 정책

- 파일시스템 또는 DB 기반 영속 저장
- TTL + 자동 만료
- 다중 버전 (편집 이력)
- ArtifactMetadata에 파일 경로 필드 추가 (어댑터 레이어 경유)

---

## 7. Command Policy

### 허용 명령 (F0)

| commandType | 설명 | dryRun=false 허용 |
|-------------|------|-------------------|
| `replaceText` | 단락 텍스트 교체 | 금지 (F0) |
| `updateTableCell` | 표 셀 텍스트 교체 | 금지 (F0) |
| `validateDocument` | 문서 구조 검증 | 금지 (F0) |

### Command 계약 (P14B-1 확정)

```
Request:
{
  "commandType": "replaceText" | "updateTableCell" | "validateDocument",
  "artifactId": "<server-issued UUID>",        // 필수 (RULE-18)
  "clientSessionId": "<browser-generated>",    // correlation 전용 (RULE-18)
  "dryRun": true,                              // 항상 true (F0 고정)
  "commandId": "<idempotency key>",
  "requestId": "<request tracing>",
  "expectedVersion": "<optimistic lock>",
  "target": { "paragraphIndex": N }            // replaceText용
           | { "row": R, "col": C }            // updateTableCell용
           | {},                               // validateDocument용
  "payload": { "value": "새 텍스트" }          // replaceText, updateTableCell용
            | {}                               // validateDocument용
}

Response (200 — APPLY_DEFERRED):
{
  "status": "APPLY_DEFERRED",
  "artifactId": "<echoed from request>",      // RULE-19
  "applied": false,
  "dryRun": true,
  "requestId": "<server-generated>",
  "schemaVersion": "...",
  "engineVersion": "..."
}

Response (422 — GATE_REJECTED):
{
  "error": "MISSING_ARTIFACT_ID" | "UNKNOWN_ARTIFACT_ID" | "FORBIDDEN_COMMAND" | ...,
  "message": "...",
  "requestId": "..."
}
```

### Command 금지 정책

- dryRun=false 요청 → 영구 차단 (F0 기간 동안)
- FORBIDDEN_KEYS (secret/token/password/session/cookie) → 즉시 거부
- raw path in payload → GATE_REJECTED
- unknown commandType → GATE_REJECTED
- artifactId 미포함 → 422 MISSING_ARTIFACT_ID
- 미등록 artifactId → 422 UNKNOWN_ARTIFACT_ID

---

## 8. Gate 구조

### 현재 구현된 Gate (18개 검사 항목 포함)

| Gate | 위치 | 주요 검사 |
|------|------|-----------|
| `FileTypeGate` | upload path | HWPX MIME, .hwpx 확장자 |
| `UploadSecurityGate` | upload path | ZIP 구조, path traversal, 파일 크기 |
| `HwpxEditorValidationGate` | command path | commandType, artifactId, FORBIDDEN_KEYS, raw path, dryRun |
| `OutputArtifactGate` | download path | output artifact 정책 |
| `ExecutionLocationGate` | 서버 시작 시 | 실행 환경 제한 |

### Gate 판정 결과

| 판정 | 의미 | HTTP |
|------|------|------|
| `PASS` | 통과 | — (다음 단계 진행) |
| `GATE_REJECTED` | 규칙 위반 거부 | 422 |
| `WARN` | 통과하되 경고 기록 | — |

### Gate 불변 규칙

- Gate는 부작용(side effect) 없음. 판정만 반환.
- Gate는 usecase.* import 금지 (단방향 의존성)
- Gate 판정 후 UseCase가 분기 결정
- Gate 실패 시 UseCase execute 불실행

### Architecture Gate (감사 스크립트)

`scripts/audit_hwpx_editor_architecture_gate.py`

| 카테고리 | Gate 수 |
|----------|---------|
| P13 readiness | 14 |
| P14A readiness | 8 |
| P14B-1 readiness | 12 |
| **합계** | **34** |

---

## 9. API Route Boundary

### 등록된 엔드포인트

| 경로 | 핸들러 | 메서드 | 역할 |
|------|--------|--------|------|
| `/health` | HealthHandler | GET | 헬스체크 |
| `/parse-hwpx` | ParseHwpxHandler | POST | 순수 파싱 (ArtifactRegistry 미등록) |
| `/convert-hwp-to-hwpx` | ConvertHwpToHwpxHandler | POST | HWP→HWPX 변환 |
| `/parse-workbook` | WorkbookParseHandler | POST | 엑셀 파싱 |
| `/parse-workbook-raw` | WorkbookParseHandler | POST | 엑셀 raw 파싱 |
| `/parse-workbook-semantic` | WorkbookParseHandler | POST | 엑셀 semantic 파싱 |
| `/parse-workbook-aggregate` | WorkbookParseHandler | POST | 엑셀 집계 파싱 |
| `/inspection` | InspectionHandler | GET | 감리 조회 |
| `/inspection/settings` | InspectionHandler | GET/POST | 감리 설정 |
| `/inspection/generate` | InspectionHandler | POST | 감리 생성 |
| `/inspection/works` | InspectionHandler | GET | 감리 작업 목록 |
| `/api/hwpx/parse` | HwpxProxyHandler | POST | 편집 세션 업로드 + ArtifactRegistry 등록 |
| `/api/hwpx/editor` | HwpxEditorApiHandler | POST | command dispatch |
| `/hwpx-editor` | HwpxUploadHandler | GET | 편집기 UI 페이지 |
| `/hwpx-upload` | HwpxUploadHandler | GET | 업로드 UI 페이지 |
| `/internal/` | InternalHandler | * | 내부 전용 |

### 경로 변경 금지 (RULE-10)

위 경로 및 응답 key(`error`, `message`, `status`, `dry_run`, `report`)는 변경 금지.
additive meta(`schemaVersion`, `engineVersion`, `requestId`)만 추가 허용.

### /parse-hwpx vs /api/hwpx/parse 분리 정책

| 항목 | `/parse-hwpx` | `/api/hwpx/parse` (→ HwpxProxyHandler) |
|------|---------------|----------------------------------------|
| ArtifactRegistry 등록 | 없음 | 있음 |
| artifactId 발급 | 없음 (null) | 있음 (UUID) |
| 용도 | 순수 구조 파악 | 편집 세션 시작 |
| 후속 command | 불가 | 가능 |

---

## 10. Audit/Event Log Policy

### F0 상태 (현재)

| 항목 | 구현 여부 |
|------|-----------|
| Architecture audit gate | 구현됨 (scripts/audit_hwpx_editor_architecture_gate.py) |
| Gradle 단위 테스트 | 구현됨 (400+ tests) |
| Gate 통과/거부 로그 | 미구현 |
| Command 실행 이벤트 로그 | 미구현 |
| Artifact lifecycle 로그 | 미구현 |
| 사용자 행동 감사 로그 | 미구현 |

### F1 이후 목표

- 모든 command 실행 시 이벤트 기록: `{eventType, artifactId, commandType, result, timestamp, clientSessionId}`
- Gate 거부 이벤트 별도 기록
- Artifact 등록/조회/만료 이벤트
- 불변 append-only 이벤트 스토어 (DB 또는 파일)
- 감사 보고서 생성 API

### 현재 감사 대상 (Architecture Gate)

`audit_hwpx_editor_architecture_gate.py`가 검사하는 항목:
- 엔드포인트 등록 여부
- command 허용 목록
- dryRun 기본값
- Gate 부작용 없음
- UseCase HTTP import 금지
- FORBIDDEN_KEYS 존재
- artifactId echo
- raw path 미노출
- P14B-1 hardening 조건 12개

---

## 11. UI Navigation Skeleton

### 현재 구조 (F0)

```
브라우저 접속
    │
    ▼
/hwpx-editor 또는 /hwpx-upload
    │ HTML 렌더 (HwpxUploadPageScripts)
    ▼
[Upload Step]
    ├── 파일 선택 input
    ├── 업로드 버튼 → POST /api/hwpx/parse
    │   ├── 성공: artifactId 저장, Parse Step으로 전환
    │   └── 실패: 오류 메시지 표시
    │
    ▼
[Parse Step]
    ├── POST /parse-hwpx
    ├── 성공: 문서 구조 표시 (단락 목록, 표 구조)
    └── 실패: 오류 메시지 표시
    │
    ▼
[Command Step]
    ├── command 선택 (replaceText / updateTableCell / validateDocument)
    ├── target 입력 (단락 인덱스 / 행·열)
    ├── payload 입력 (새 텍스트)
    ├── buildEditorCommand() 호출
    ├── POST /api/hwpx/editor
    │   ├── 200 APPLY_DEFERRED: 결과 표시 → 다음 command 가능
    │   ├── 422 GATE_REJECTED: 오류 표시 → 재시도 가능
    │   └── 500: 오류 표시
    └── 루프 (Command Step 반복)
```

### UI 불변 규칙 (RULE-01, RULE-02, RULE-03)

- JS는 `buildEditorCommand()`를 통해서만 command 생성
- JS는 HWPX XML/ZIP 직접 접근 금지
- raw path를 UI에 표시 금지
- artifactId는 앞 8자만 표시

### F1 이후 목표

- 단락/표 인라인 편집 UI
- dryRun 결과 diff 뷰
- 편집 이력 조회
- 다운로드 버튼 (ApplyEngine 연결 후)

---

## 12. Test Plan

### 현재 테스트 커버리지 (F0 — 400+ tests PASS)

| 레이어 | 테스트 클래스 | 주요 시나리오 |
|--------|---------------|---------------|
| Gate | HwpxEditorValidationGateTest | commandType 허용/거부, artifactId 필수 (P14B-1), FORBIDDEN_KEYS |
| UseCase | HwpxEditorCommandUseCaseTest | dryRun, gate rejected, engine success/fail/exception, schema version |
| Handler | HwpxEditorApiHandlerCommandDispatchTest | 422/200, artifactId echo, raw path 미노출, session 분리 |
| Parser | HwpxParserTableCoordinatesTest | 표 좌표 파싱 |
| Architecture | audit_hwpx_editor_architecture_gate.py | 34개 gate PASS 확인 |

### 테스트 추가 기준 (RULE-14)

- 새 commandType → SUPPORTED_COMMANDS 추가 + gate test 추가
- 새 레이어 → boundary rule 문서 갱신 + audit script 갱신
- 새 gate 조건 → HwpxEditorValidationGateTest 추가
- P14B-1 이후 모든 신규 기능: 테스트 없으면 COMMIT 금지

### F1 이후 목표

- ApplyEngine 연결 통합 테스트
- Python 레이어 (hwpx_edit_tool.py, hwpx_server_ops.py) Java 라운드트립 연계 테스트
- Artifact 영속성 테스트
- UI E2E 테스트 (Playwright 또는 동등)

---

## 참조 문서

| 문서 | 내용 |
|------|------|
| `docs/architecture/hwpx_editor_operating_rules_20260515.md` | RULE-01~21 상세 |
| `docs/architecture/hwpx_editor_state_model_*.md` | 상태 모델 상세 |
| `docs/architecture/hwpx_editor_command_contract_*.md` | command 계약 상세 |
| `docs/architecture/hwpx_editor_ui_layout_*.md` | UI 레이아웃 상세 |
| `docs/reports/hwpx_browser_editor_p14b1_*.md` | P14B-1 작업 보고서 |
| `docs/reports/hwpx_browser_editor_p14b1a_*.md` | P14B-1A 기존 편집 기능 맵 |
| `scripts/audit_hwpx_editor_architecture_gate.py` | Architecture gate 스크립트 |
