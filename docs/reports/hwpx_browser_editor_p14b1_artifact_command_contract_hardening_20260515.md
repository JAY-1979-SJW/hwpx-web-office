# HWPX Browser Editor P14B-1 Artifact Command Contract Hardening

**작업명:** HWPX-BROWSER-EDITOR-P14B-1-ARTIFACT-COMMAND-CONTRACT-HARDENING
**날짜:** 2026-05-15
**기준선 HEAD:** cf6e22268caa9cb613698c029b81c8b992c390f9
**최종 판정:** PASS

---

## 수정 파일

| 파일 | 변경 내용 |
|------|-----------|
| `src/main/java/com/haehan/engine/gate/HwpxEditorValidationGate.java` | validateDocument artifactId 예외 제거 |
| `src/main/java/com/haehan/engine/http/HwpxEditorApiHandler.java` | validateDocument 예외 제거, artifactId echo 추가 |
| `src/test/java/com/haehan/engine/gate/HwpxEditorValidationGateTest.java` | validate_document_requires_artifact_id_p14b1 신규 |
| `src/test/java/com/haehan/engine/http/HwpxEditorApiHandlerCommandDispatchTest.java` | P14B-1 테스트 9개 추가, 기존 2개 수정 |
| `src/test/java/com/haehan/engine/usecase/HwpxEditorCommandUseCaseTest.java` | validate_document_without_artifactId 신규 |
| `scripts/audit_hwpx_editor_architecture_gate.py` | P14B-1 gate 12개 추가 |
| `docs/architecture/hwpx_editor_operating_rules_20260515.md` | 레이어 아키텍처, RULE-18/19/20/21 추가 |

---

## 운영규칙 완전성 확인 결과

초기 확인 시 레이어 명칭, 의존성 방향, 순환 import 금지, outputArtifact 키워드 미포함으로 WARN 판정.
P14B-1에서 레이어 아키텍처 다이어그램 및 RULE-18/19/20/21 추가하여 완전성 보강.

추가된 항목:
- UI Layer / API Handler Layer / UseCase Layer / Validation/Gate Layer / Domain/Command Model Layer / Engine Adapter Layer / Infra/Storage Layer / Audit/Test Layer / Documentation/Report Layer 레이어 정의
- 의존성 방향 규칙 (위→아래만)
- 순환 import 금지 명시
- 신규 코드 위치 규칙
- RULE-18: validateDocument server artifactId 필수 (P14B-1)
- RULE-19: 모든 command 응답 artifactId echo (P14B-1)
- RULE-20: /parse-hwpx 순수 파서, ArtifactRegistry 미등록 (P14B-1)
- RULE-21: ArtifactRegistry in-memory 한계 명시 (P14B-1)

---

## validateDocument artifactId 정책

**변경 전 (P14A):**
- `HwpxEditorValidationGate`: validateDocument는 artifactId 없어도 통과
- `HwpxEditorApiHandler`: `requiresArtifact = !"validateDocument"` — validateDocument 예외 처리

**변경 후 (P14B-1):**
- `HwpxEditorValidationGate`: 모든 command 동일하게 artifactId 필수
- `HwpxEditorApiHandler`: `requiresArtifact` 분기 제거, validateDocument 포함 전체 통일
- artifactId 누락 → `MISSING_ARTIFACT_ID` (422)
- unknown artifactId → `UNKNOWN_ARTIFACT_ID` (422)
- sessionArtifactId만으로 실행 금지 (레지스트리 미등록이므로 자동 차단)
- clientSessionId는 correlation 전용

---

## Command Response artifactId Echo

**변경 내용:**
```java
// P14B-1: always echo artifactId from request in response
resp.addProperty("artifactId", command.artifactId);
```

- `handleCommandDispatch`에서 UseCase 결과 직렬화 후 request의 `command.artifactId`를 명시 echo
- validateDocument, replaceText, updateTableCell 모두 적용
- raw path / temp path / internal path 응답 없음 확인
- `HwpxEditorCommandResult.gateRejected()`는 변경 없음 (핸들러 레벨에서 echo 처리)

---

## /parse-hwpx 직접 엔드포인트 정책

**정책 확정:**
- `ParseHwpxHandler` → `HwpxUploadParseUseCase` → `HwpxParser` 경로는 순수 read-only 파서
- `ArtifactRegistry`에 artifact 등록 없음
- `DocumentParseResponse.artifactId`는 null (이 경로에서 발급 안 함)
- Browser editor session의 artifactId는 `HwpxProxyHandler` → `ArtifactRegistry.register()` 경로에서만 발급
- `/parse-hwpx` 응답과 `/api/hwpx/editor` 응답 정책이 명확히 분리됨
- RULE-20으로 운영규칙에 고정

---

## ArtifactRegistry In-Memory 한계

- 현재 `ArtifactRegistry`는 `ConcurrentHashMap` 기반 in-memory
- 서버 프로세스 재시작 시 모든 등록 artifact 소실
- Production 배포 전 persistent artifact store 필요 (P14B-2 또는 P14C)
- P14B-1에서 DB/파일 기반 영속성 구현 없음
- RULE-21로 운영규칙에 명시, architecture gate `IN_MEMORY_REGISTRY_LIMITATION_DOCUMENTED`로 강제

---

## 이번 단계에서 하지 않은 작업

- ApplyEngine 연결 없음 (P14 이후 별도 단계)
- PythonScriptBridge 연결 없음 (command dispatch path)
- dryRun=false 허용 없음
- outputArtifact 생성 없음
- DB/schema 변경 없음
- 서버 배포/재시작 없음
- ArtifactRegistry 파일/DB 기반 영속화 없음
- push 없음

---

## Architecture Gate 결과

```
hwpx_editor_architecture_gate_status=PASS
p13_readiness=True
p14a_readiness=True
p14b1_readiness=True
finding_count=0
```

추가된 P14B-1 gate 12개:
- VALIDATE_DOCUMENT_REQUIRES_SERVER_ARTIFACT_ID ✅
- VALIDATE_DOCUMENT_REJECTS_UNKNOWN_ARTIFACT_ID ✅
- SESSION_ARTIFACT_ID_NOT_ACCEPTED_AS_ARTIFACT_ID ✅
- COMMAND_RESPONSE_ECHOES_ARTIFACT_ID ✅
- COMMAND_RESPONSE_NO_RAW_PATH_LEAK ✅
- PARSE_HWPX_ARTIFACT_POLICY_DOCUMENTED ✅
- IN_MEMORY_REGISTRY_LIMITATION_DOCUMENTED ✅
- PERSISTENT_REGISTRY_NOT_IMPLEMENTED_IN_P14B1 ✅
- DRY_RUN_ONLY_STILL_ENFORCED ✅
- NO_APPLY_ENGINE_CONNECTION_IN_P14B1 ✅
- NO_PYTHON_SCRIPT_BRIDGE_CONNECTION_IN_P14B1 ✅
- EXISTING_P14A_GATES_STILL_PASS ✅

---

## Test 결과

**Gradle:** BUILD SUCCESSFUL (400+ tests 전체 PASS)

추가된 테스트:
1. `validate_document_requires_artifact_id_p14b1` — artifactId 없으면 GATE_REJECTED
2. `validate_document_with_artifact_id_passes_p14b1` — 유효 artifactId면 PASS
3. `validate_document_command_deferred` — 유효 artifactId로 APPLY_DEFERRED 확인 (기존 수정)
4. `validate_document_without_artifactId_is_gate_rejected_p14b1` — UseCase 레벨 확인
5. `validateDocumentCommand_withArtifactId_returnsJson` — 200 응답 확인 (기존 수정)
6. `validateDocument_dryRun_applied_false` — applied=false 확인 (기존 수정)
7. `validateDocument_withoutArtifactId_returns422` — 422 + MISSING_ARTIFACT_ID
8. `validateDocument_withUnknownArtifactId_returns422` — 422 + UNKNOWN_ARTIFACT_ID
9. `validateDocument_sessionArtifactIdNotInRegistry_returns422` — 미등록 ID 차단
10. `validateDocument_response_echoes_artifactId` — echo 검증
11. `replaceText_response_echoes_artifactId` — echo 검증
12. `updateTableCell_response_echoes_artifactId` — echo 검증
13. `commandResponse_artifactId_matches_request` — 요청/응답 일치
14. `commandResponse_noRawPathLeak` — raw path 없음
15. `clientSessionId_isDifferentFrom_artifactId` — correlation 분리 확인

---

## Secret Scan

- 수정 파일 내 credential/secret/token/password 노출 없음
- FORBIDDEN_KEYS 목록 내 문자열만 존재 (검증 로직)

---

## Git

- 기준선: cf6e222
- push 미수행
- 서버 배포/재시작 미수행

---

## 남은 Dirty 파일과 충돌 여부

- `Dockerfile`, `Dockerfile.hwpx-engine`, `scripts/hwpx/*`, `scripts/local-gui/*`, `scripts/extract_hwp_body_fields.py` — P14B-1 무관, 미수정, staged 없음
- `Application.java`, `HwpxParser.java`, `HwpxParserTableCoordinatesTest.java` — P14B-1 무관, 미수정, staged 없음
- EngineHttpServer.java, HttpServerTest.java — clean 유지 확인

---

## P14B-2 / P14C로 넘길 항목

- ArtifactRegistry 파일/DB 기반 영속화 (P14B-2 또는 P14C)
- ApplyEngine 실제 연결 (P14 이후)
- outputArtifact 생성 및 다운로드 연결
- dryRun=false 허용 정책 결정
- /parse-hwpx와 editor upload 경로 통합 여부 검토
