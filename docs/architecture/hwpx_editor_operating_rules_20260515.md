# HWPX Editor Operating Rules

**버전:** F0 (P14B-1 기준 갱신)
**날짜:** 2026-05-15
**상태:** CONFIRMED — audit gate (`audit_hwpx_editor_architecture_gate.py`) + test로 강제됨
**Foundation 문서:** `docs/architecture/hwpx_editor_app_foundation_20260515.md`

---

## 레이어 아키텍처

```
UI Layer (HwpxUploadPageScripts.java JS 섹션)
    ↓
API Handler Layer (HwpxEditorApiHandler, ParseHwpxHandler, HwpxProxyHandler)
    ↓
UseCase Layer (HwpxEditorCommandUseCase, HwpxUploadParseUseCase)
    ↓
Validation/Gate Layer (HwpxEditorValidationGate, FileTypeGate, UploadSecurityGate)
    ↓
Domain/Command Model Layer (HwpxEditorCommand, HwpxEditorCommandResult, DocumentParseResponse)
    ↓
Engine Adapter Layer (ApplyEngine — P14 이후 연결, P14B-1 미연결)
    ↓
Infra/Storage Layer (ArtifactRegistry, PythonScriptBridge, HwpxParser)
```

**의존성 방향:** 위에서 아래로만. 아래 레이어가 위 레이어를 import 금지.
**순환 import 금지:** UseCase는 http.* import 금지. Gate는 usecase.* import 금지. Domain은 gateway.* import 금지.
**신규 코드 위치:** 새 command 처리 로직 → UseCase 또는 Gate에만 추가. Handler는 request/response 변환만.
**Audit/Test Layer:** `scripts/audit_hwpx_editor_architecture_gate.py`, `tests/test_hwpx_editor_architecture_gate.py`
**Documentation/Report Layer:** `docs/architecture/`, `docs/reports/`

---

## 규칙 목록

### RULE-01: UI는 command JSON만 생성한다
- 브라우저 JS는 `buildEditorCommand()`를 통해 command 객체를 생성하고 `/api/hwpx/editor`로만 전송한다
- 브라우저는 HWPX engine을 직접 호출하지 않는다
- **gate 검사:** `buildEditorCommand` 함수 존재 여부, XML/ZIP 접근 후보 없음

### RULE-02: 브라우저는 HWPX XML/ZIP을 직접 조작하지 않는다
- `BinData/`, `Contents/`, `.xml`, `.rels` 참조는 command dispatch 코드에 금지
- 기존 photo entry 코드는 예외 (upload_field 방식으로 서버가 처리)
- **gate 검사:** SCRIPT_5 영역에서 XML/ZIP 접근 후보 검사

### RULE-03: raw filesystem path는 UI/API 응답에 표시하지 않는다
- `rawPathGuard` 또는 `artifactId`만 외부 참조값으로 사용
- `C:\`, `/home/`, `/var/`, `~/` 등 OS 절대 경로 UI 표시 금지
- **gate 검사:** view/scripts에서 raw path 후보 검사

### RULE-04: artifactId만 외부 참조값으로 사용한다
- download 응답: `X-Hwpx-Editor-Saved-Path`는 artifactId 기반
- UI 표시: artifactId 앞 8자만
- 서버 절대 경로는 `guardedArtifactRef()`로 래핑
- **gate 검사:** `guardedArtifactRef` 또는 `guardedReportRef` 사용 여부

### RULE-05: Handler는 얇은 request/response adapter로 유지한다
- Handler는 multipart/JSON 파싱 + UseCase 호출 + 응답 직렬화만 담당
- business rule은 UseCase 또는 Gate에 위임
- engine 직접 조작은 EngineAdapter로 위임 (P14)
- **gate 검사:** handler가 `HwpxEditorCommandUseCase`를 통해 command 처리

### RULE-06: UseCase가 command 실행 흐름을 담당한다
- `HwpxEditorCommandUseCase.execute()` → validate → dryRun/apply
- UseCase는 `com.haehan.engine.http.*` import 금지
- UseCase는 `com.sun.net.httpserver.*` import 금지
- **gate 검사:** usecase 파일 import 검사

### RULE-07: ValidationGate가 command 허용 여부를 먼저 판단한다
- UseCase는 `HwpxEditorValidationGate.validate()` 호출 후 결과에 따라 분기
- GATE_REJECTED → apply 없이 반환
- **gate 검사:** gate 파일 side effect 없음 검사

### RULE-08: dryRun은 쓰기 작업을 하지 않는다
- `dryRun: true` → `applied: false` 항상
- HWPX 파일 write, DB write, 서버 archive 없음
- **gate 검사:** dryRun 기본값 true 정책 확인

### RULE-09: actual apply는 P14 이후 별도 adapter로만 연결한다
- P13 범위: `APPLY_DEFERRED` 반환
- `ApplyEngine` 실제 구현체는 P14에서만 추가
- P13 코드에 실제 HWPX 수정 로직 금지
- **gate 검사:** P13 코드 내 apply 코드 부재 확인

### RULE-10: endpoint path와 기존 API key는 변경하지 않는다
- `/api/hwpx/editor`, `/parse-hwpx`, `/hwpx-editor` 등 변경 금지
- 기존 응답 key `error`, `message`, `status`, `dry_run`, `report` 변경 금지
- additive meta만 허용 (`schemaVersion`, `engineVersion`, `requestId`)
- **gate 검사:** endpoint 등록 문자열 + 기존 key 존재 확인

### RULE-11: schemaVersion/engineVersion/requestId meta contract를 유지한다
- 모든 command 응답에 `schemaVersion`, `engineVersion` 포함
- `requestId`는 서버가 신규 생성
- 값 변경 시 모든 handler 일괄 갱신 필요 (`ApiResponseMeta` 상수 사용)
- **gate 검사:** API meta contract audit 재실행

### RULE-12: secret/token/password/session/cookie 출력 금지
- payload, 로그, UI, 응답에 노출 금지
- 금지 key 목록: RULE-07과 동일
- **gate 검사:** 금지 key 탐지 (ValidationGate 코드 확인)

### RULE-13: 서버 기동/배포/도메인 연결은 closeout 전까지 제외
- P13A/P13B/P14: local 코드 수정만
- nginx, firewall, compose, DNS, 인증서 작업 제외
- **gate 검사:** 해당 파일 변경 없음 확인

### RULE-14: 신규 기능은 반드시 audit gate와 test를 같이 추가한다
- 새 command type 추가 시 → `SUPPORTED_COMMANDS` 추가 + gate test 추가
- 새 layer 추가 시 → boundary rule 문서 갱신 + audit script 갱신
- **gate 검사:** P13A architecture gate 존재 여부

### RULE-15: 거대 파일/함수로 누적하지 않고 기능 단위로 분리한다
- HwpxUploadPageScripts가 3000줄 초과 시 분리 검토
- HwpxEditorApiHandler가 command/archive 책임 분리 검토 대상
- **gate 검사:** 파일 크기 WARN 기준 (3000줄)

### RULE-16: 운영규칙은 문서뿐 아니라 scripts/tests로 강제한다
- 이 문서의 규칙마다 gate 검사 항목이 존재해야 함
- gate가 없는 규칙은 WARN으로 보고
- **gate 검사:** `audit_hwpx_editor_architecture_gate.py` 포함 여부

### RULE-17: 단계 완료 보고서는 항상 대화창(Claude Code CLI)에 직접 출력한다
- 각 단계(P13A, P13B, P14A, … ) 완료 시 최종 보고를 `docs/reports/` 파일 저장과 별개로 **대화창에 한국어로 직접 출력**한다
- 보고서 내용: 작업 내용, 기준선, 수정 파일, 핵심 계약 변경, 보안 확인, Test/Audit/Gradle 결과, Git 커밋, 다음 단계, 최종 판정
- 파일만 쓰고 대화창 출력을 생략하는 것은 규칙 위반
- **gate 검사:** 해당 없음 (사람이 확인)

### RULE-18: validateDocument는 server artifactId를 반드시 포함해야 한다 (P14B-1)
- validateDocument도 server artifactId 없이 실행 불가
- artifactId 누락 → MISSING_ARTIFACT_ID (422)
- unknown artifactId → UNKNOWN_ARTIFACT_ID (422)
- sessionArtifactId만으로 validateDocument 실행 금지 (correlation 전용)
- clientSessionId는 correlation 목적으로만 사용; artifactId 대체 불가
- **gate 검사:** VALIDATE_DOCUMENT_REQUIRES_SERVER_ARTIFACT_ID

### RULE-19: 모든 command 응답에 artifactId를 echo한다 (P14B-1)
- validateDocument, replaceText, updateTableCell 등 모든 command 응답에 request의 artifactId 포함
- raw path, temp path, internal path는 응답에 포함 금지
- ArtifactMetadata internal reference(파일 경로 등) 응답 금지
- artifactId는 서버 발급값(UUID)만 사용; sessionArtifactId를 artifactId로 echo 금지
- **gate 검사:** COMMAND_RESPONSE_ECHOES_ARTIFACT_ID, COMMAND_RESPONSE_NO_RAW_PATH_LEAK

### RULE-20: /parse-hwpx 엔드포인트는 순수 파서 전용이며 ArtifactRegistry에 등록하지 않는다 (P14B-1)
- ParseHwpxHandler → HwpxUploadParseUseCase → HwpxParser 경로는 read-only
- ArtifactRegistry에 artifact 등록 없음
- DocumentParseResponse.artifactId 필드는 null (editor session과 다른 흐름)
- Browser editor session의 artifactId 발급은 HwpxProxyHandler → ArtifactRegistry.register 경로에서만
- 두 경로 응답 정책 분리: /api/hwpx/editor(multipart) = artifactId 발급, /parse-hwpx = artifactId 미발급
- **gate 검사:** PARSE_HWPX_ARTIFACT_POLICY_DOCUMENTED

### RULE-21: ArtifactRegistry는 in-memory이며 서버 재시작 시 초기화된다 (P14B-1)
- 현재 ArtifactRegistry는 `ConcurrentHashMap` 기반 in-memory
- 서버 프로세스 재시작 시 등록된 모든 artifact 소실
- production 배포 전 persistent artifact store 필요 (P14B-2 또는 P14C에서 구현)
- P14B-1에서 DB/파일 기반 영속성 구현 금지
- outputArtifact 생성 금지 (ApplyEngine 미연결 상태)
- **gate 검사:** IN_MEMORY_REGISTRY_LIMITATION_DOCUMENTED, PERSISTENT_REGISTRY_NOT_IMPLEMENTED_IN_P14B1

---

## audit gate 참조

- `scripts/audit_hwpx_editor_architecture_gate.py`
- `tests/test_hwpx_editor_architecture_gate.py`

규칙 변경 시 위 스크립트도 함께 갱신한다.

## 관련 문서

- `docs/architecture/hwpx_editor_app_foundation_20260515.md` — 앱 전체 foundation 아키텍처 (레이어, 권한, workflow, artifact, command, gate, API, audit, UI, test)
