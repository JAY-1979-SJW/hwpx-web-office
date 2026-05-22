# P14A Report: HWPX Browser Editor — Server-Side Artifact ID

**작업명:** HWPX-BROWSER-EDITOR-P14A-SERVER-SIDE-ARTIFACT-ID  
**날짜:** 2026-05-15  
**기준선 HEAD:** 4e3737a (P13B 완료)  
**상태:** PASS

---

## 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/main/java/com/haehan/engine/artifact/ArtifactIdGenerator.java` | 신규 — UUID 기반 artifactId 생성 |
| `src/main/java/com/haehan/engine/artifact/ArtifactMetadata.java` | 신규 — artifact 세션 메타데이터 (raw path 미포함) |
| `src/main/java/com/haehan/engine/artifact/ArtifactRegistry.java` | 신규 — in-memory ConcurrentHashMap 레지스트리 |
| `src/main/java/com/haehan/engine/contract/DocumentParseResponse.java` | artifactId, artifactKind, artifactStatus 필드 추가 |
| `src/main/java/com/haehan/engine/http/HwpxProxyHandler.java` | parse 응답에 artifactId 주입 + 레지스트리 등록 |
| `src/main/java/com/haehan/engine/http/HwpxEditorApiHandler.java` | ArtifactRegistry 의존성 주입, 레지스트리 검증 추가 |
| `src/main/java/com/haehan/engine/http/HwpxUploadPageScripts.java` | state.artifactId 추가, buildEditorCommand에서 server artifactId 사용 |
| `src/test/java/com/haehan/engine/http/HwpxEditorApiHandlerCommandDispatchTest.java` | ArtifactRegistry 테스트 격리 (createForTest) |
| `scripts/audit_hwpx_editor_architecture_gate.py` | P14A 12개 gate 추가, phase → P14A |
| `tests/test_hwpx_browser_editor_p14a_server_artifact_id.py` | 신규 — 20개 P14A 테스트 |
| `tests/test_hwpx_browser_editor_p13b_command_ui.py` | P14A guard 업그레이드 반영 (artifact guard 유지) |
| `tests/test_hwpx_editor_architecture_gate.py` | phase 허용값에 P14A 추가 |

---

## ArtifactId 계약

| 항목 | 내용 |
|------|------|
| 생성 | `ArtifactIdGenerator.generate()` → `UUID.randomUUID().toString()` |
| 저장 | `ArtifactRegistry.INSTANCE` (in-memory, ConcurrentHashMap) |
| 외부 노출 | `artifactId` 문자열만 — raw path, temp path, internal path 미포함 |
| 예측 가능성 | UUID v4 — 순차 증가 값 금지 |
| 수명 | 서버 프로세스 생존 기간 (P14C에서 영속성 도입 예정) |

---

## Artifact Registry 구조

```
com.haehan.engine.artifact
  ├── ArtifactIdGenerator   — UUID.randomUUID() 생성
  ├── ArtifactMetadata      — artifactId, originalFileName, contentType, createdAt
  └── ArtifactRegistry      — ConcurrentHashMap, INSTANCE singleton
                              createForTest()로 테스트 격리
```

---

## Parse/Upload 응답 변경

`DocumentParseResponse`에 추가된 필드 (기존 필드 유지):

| 필드 | 값 |
|------|-----|
| `artifactId` | UUID (서버 발급) |
| `artifactKind` | `"HWPX_EDITOR_SESSION"` |
| `artifactStatus` | `"READY"` |

`HwpxProxyHandler`가 엔진 응답 JSON에 위 필드를 주입하고 레지스트리에 등록한다.

---

## Command Payload 변경

`buildEditorCommand`에서:
- **before:** `artifactId: state.sessionArtifactId || ''`
- **after:** `artifactId: state.artifactId || ''` (server artifactId)
- `clientSessionId: state.sessionArtifactId || ''` (correlation id로 유지)

---

## SessionArtifactId 처리

- `state.sessionArtifactId` — UI correlation id / 클라이언트 식별자로만 유지
- `clientSessionId` 필드로 payload에 포함 (선택적)
- 문서 lookup 기준은 `state.artifactId` (server-side UUID)
- `sessionArtifactId`만으로 `replaceText`/`updateTableCell` 실행 차단

---

## Raw Path Leak 차단

| 항목 | 결과 |
|------|------|
| HwpxProxyHandler 응답에 /tmp/ 등 포함 | 없음 |
| ArtifactMetadata에 파일 경로 저장 | 없음 (originalFileName만) |
| ArtifactRegistry → 외부 응답에 path 노출 | 없음 |
| UI에 raw path input field | 없음 |

---

## DryRun Only 유지 근거

- `buildEditorCommand` → `dryRun: opts.dryRun !== false` (기본 true)
- SCRIPT_5 전체 `dryRun: false` 리터럴 없음
- P14B에서 server-side 편집 검증, P14C에서 actual apply 도입

---

## ApplyEngine / PythonScriptBridge 미연결

- `HwpxEditorCommandUseCase`에 `ApplyEngine` 연결 없음 → `APPLY_DEFERRED` 반환
- `PythonScriptBridge`는 command dispatch에서 미호출
- P14C로 이월

---

## Architecture Gate 결과 (P14A 12개 + 기존 P13A/B 27개)

| Gate | 결과 |
|------|------|
| SERVER_ARTIFACT_ID_PARSE_RESPONSE_PRESENT | PASS |
| SERVER_ARTIFACT_ID_NON_EMPTY | PASS |
| SERVER_ARTIFACT_ID_NO_RAW_PATH_LEAK | PASS |
| COMMAND_PAYLOAD_USES_SERVER_ARTIFACT_ID | PASS |
| SESSION_ARTIFACT_ID_NOT_SOURCE_OF_TRUTH | PASS |
| COMMAND_BLOCKS_WITHOUT_ARTIFACT_ID | PASS |
| UNKNOWN_ARTIFACT_ID_REJECTED | PASS |
| DRY_RUN_ONLY_STILL_ENFORCED | PASS |
| NO_APPLY_ENGINE_CONNECTION_IN_P14A | PASS |
| NO_PYTHON_SCRIPT_BRIDGE_CONNECTION_IN_P14A | PASS |
| NO_XML_ZIP_BROWSER_MUTATION | PASS |
| EXISTING_RESPONSE_KEYS_PRESERVED | PASS |
| 기존 P13A/B 27개 | 27/27 PASS |
| **finding_count** | **0** |

---

## Test 결과

| 항목 | 결과 |
|------|------|
| test_hwpx_browser_editor_p14a_server_artifact_id (20) | 20/20 PASS |
| test_hwpx_browser_editor_p13b_command_ui (15) | 15/15 PASS |
| test_hwpx_editor_architecture_gate (17) | 17/17 PASS |
| test_hwpx_browser_editor_structure (27) | 27/27 PASS |
| test_ui_design_system (15) | 15/15 PASS |
| **Python 합계** | **94/94 PASS** |

---

## Gradle 결과

```
BUILD SUCCESSFUL
390 tests completed, 0 failed
```

---

## Secret scan

신규 secret 0건 — API key, password, token 모두 기존 env 참조(이전 단계와 동일).

---

## P14B로 넘길 항목

| 항목 | 내용 |
|------|------|
| ArtifactRegistry 영속성 | 현재 in-memory; 서버 재시작 시 초기화됨 |
| ParseHwpxHandler 연동 | `/parse-hwpx` 직접 엔드포인트도 artifactId 발급 필요 여부 검토 |
| validateDocument registry 검증 | 현재 validateDocument는 artifactId 없어도 통과; P14B에서 정책 결정 |
| command 응답에 artifactId echo | 클라이언트 확인용 응답 필드 추가 |

---

## 최종 판정: PASS — P14B 진행 가능

- P14A gate 12/12 PASS
- 전체 Python 테스트 94/94 PASS
- Gradle BUILD SUCCESSFUL (390 Java tests)
- finding 0건
- raw path leak 없음
- dryRun only 유지
