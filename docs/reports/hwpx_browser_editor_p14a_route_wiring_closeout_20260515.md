# HWPX-BROWSER-EDITOR-P14A Route Wiring Closeout

작업명: HWPX-BROWSER-EDITOR-P14A-ROUTE-WIRING-CLOSEOUT-COMMIT
날짜: 2026-05-15
작성자: Claude Sonnet 4.6

---

## 기준선

- HEAD (커밋 전): `a0c5d995d376330a795884d12b6be95312da92d8`
- Branch: `main`

---

## 묶음 1 파일 목록

| 파일 | 상태 | 사유 |
|---|---|---|
| `src/main/java/com/haehan/engine/http/EngineHttpServer.java` | M | P14A 누락 route wiring 핵심 |
| `src/test/java/com/haehan/engine/http/HttpServerTest.java` | M | route 응답 검증 테스트 |
| `logs/change_history.jsonl` | M | devlog hook 자동 (P14A/RULE-17 기록) |
| `docs/reports/hwpx_browser_editor_p14b0_dirty_worktree_triage_20260515.md` | A | P14B-0 triage 보고서 |
| `docs/reports/hwpx_browser_editor_p14a_route_wiring_closeout_20260515.md` | A | 이 보고서 |

**제외 파일:**
- `src/main/java/com/haehan/engine/Application.java` — AuditWatchLifecycle + HwpToHwpxCliBridge 혼합 변경으로 별도 처리
- 나머지 dirty 28개 — 묶음 2~4, P14B-1 무관

---

## Route Wiring 누락 원인

P14A 커밋(e0f5652)에서 `HwpxEditorApiHandler.java`는 신규 생성됐으나 `EngineHttpServer.java`가 커밋에 포함되지 않았음. 결과적으로 핸들러가 존재하지만 서버 context에 등록되지 않아 `/api/hwpx/editor` 엔드포인트로 HTTP 요청이 도달하지 못했음.

---

## 수정 내용

### EngineHttpServer.java

1. `/api/hwpx/editor` → `HwpxEditorApiHandler()` 등록 (P14A 누락 wiring)
2. `/hwpx-editor` → `HwpxUploadHandler()` 등록
3. `AuditWatchLifecycle` 생성자 오버로드 추가 (기존 단인자 생성자 유지)
4. `auditWatch.close()` shutdown hook 및 stop()에 추가

변경 확인:
- raw path 노출 없음 ✅
- secret 없음 ✅
- ApplyEngine 연결 없음 ✅
- PythonScriptBridge 연결 없음 ✅
- dryRun=false 경로 없음 ✅
- outputArtifact 생성 없음 ✅

### HttpServerTest.java

- `hwpxEditorPage_returnsBrowserEditor()` 테스트 추가
- `/hwpx-editor` GET 200, body에 "HWPX" 및 "/api/hwpx/editor" 포함 검증

---

## 테스트 결과

| 항목 | 결과 |
|---|---|
| Gradle BUILD | SUCCESSFUL (2m 3s) |
| P14A Python 테스트 (20개) | 20 PASSED |
| P13B Python 테스트 (15개) | 15 PASSED |
| architecture gate | PASS, finding=0 |

---

## Secret / Raw Path 확인

- staged 파일에 raw path / temp path / internal path 없음
- secret / token / password 없음

---

## 남은 Dirty (커밋 후 예상)

| 그룹 | 파일 수 | 설명 |
|---|---|---|
| B | 1 | `Application.java` (혼합 변경) |
| C | 2 | `HwpxParser.java`, `HwpxParserTableCoordinatesTest.java` |
| D | 2 | `Dockerfile`, `Dockerfile.hwpx-engine` |
| E | 21 | `scripts/hwpx/*` standalone/converter |
| F | 4 | `scripts/local-gui/*` |
| 기타 | 1 | `scripts/extract_hwp_body_fields.py` |

---

## P14B-1 진행 가능 여부

| 조건 | 상태 |
|---|---|
| EngineHttpServer.java clean | ✅ (이 커밋 후) |
| HttpServerTest.java clean | ✅ (이 커밋 후) |
| P14A 테스트 PASS | ✅ |
| architecture gate PASS | ✅ |
| Application.java dirty | ⚠️ 별도 판단 필요 |

Application.java가 dirty로 남으나, P14B-1 작업 범위(validateDocument 정책, command response, ParseHwpxHandler 정책)와 직접 충돌하지 않으므로 P14B-1 진행 가능으로 판단.

---

## 최종 판정

**PASS**

P14A 누락 route wiring 확인 및 커밋 완료. 남은 dirty는 P14B-1과 비충돌.

---

*작성: Claude Sonnet 4.6 / HWPX-BROWSER-EDITOR-P14A-ROUTE-WIRING-CLOSEOUT*
