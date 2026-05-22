# HWPX-BROWSER-EDITOR-P14B-0 Dirty Worktree Triage

작업명: HWPX-BROWSER-EDITOR-P14B-0-DIRTY-WORKTREE-TRIAGE
날짜: 2026-05-15
작성자: Claude Sonnet 4.6

---

## 기준선

- HEAD: `a0c5d995d376330a795884d12b6be95312da92d8`
- Branch: `main`
- Upstream: 없음 (push 미실행)
- tracked dirty: 33개
- 판정 기준: e0f5652, a0c5d99 커밋 확인 ✅

---

## Dirty 파일 전체 목록 및 그룹 분류

### 그룹 A — P14A/Editor HTTP wiring 관련 (P14B-1 직접 관련)

| 파일 | 변경 규모 | P14B-1 관련성 | P14A 누락 가능성 |
|---|---|---|---|
| `src/main/java/com/haehan/engine/http/EngineHttpServer.java` | +11줄 | **HIGH** | **HIGH — P14A 누락** |
| `src/test/java/com/haehan/engine/http/HttpServerTest.java` | +12줄 | **HIGH** | **HIGH — P14A 누락** |

**EngineHttpServer.java 변경 내용:**
- `/api/hwpx/editor` → `HwpxEditorApiHandler` route 등록 ← P14A에서 HwpxEditorApiHandler를 만들었으나 서버에 **등록이 누락**됨
- `/hwpx-editor` → `HwpxUploadHandler` route 추가
- `AuditWatchLifecycle` 도입 (생성자 오버로드)
- `auditWatch.close()` shutdown/stop에 추가

**HttpServerTest.java 변경 내용:**
- `hwpxEditorPage_returnsBrowserEditor()` 테스트 추가 (`/hwpx-editor` 200 응답 검증)

**판정:** P14A 커밋(e0f5652)에 `EngineHttpServer.java`가 **포함되지 않았음**. HwpxEditorApiHandler가 만들어졌지만 서버에 라우트로 등록되지 않은 상태로 P14A가 커밋됨. P14B-1 진행 전 반드시 먼저 커밋 처리해야 한다.

---

### 그룹 B — AuditWatchLifecycle + HwpToHwpxCliBridge (Application 레벨, 혼합 변경)

| 파일 | 변경 규모 | P14B-1 관련성 | 판단 |
|---|---|---|---|
| `src/main/java/com/haehan/engine/Application.java` | +46줄 | MEDIUM | 혼합 변경 — hunk 분리 필요 없으나 묶음 고려 필요 |

**Application.java 변경 내용 (두 종류 혼합):**

종류 1 — AuditWatchLifecycle 도입:
- `AuditWatchLifecycle.startDefault()` 호출 후 `EngineHttpServer(port, auditWatch)` 생성
- `ensureDefaultLogDirectory()` 추가
- → EngineHttpServer.java 변경과 직접 연결됨

종류 2 — HwpToHwpxCliBridge CLI:
- `convert-hwp-to-hwpx` CLI 명령 추가
- `runConvertHwpToHwpx()` 메서드 추가
- → P14A/P14B와 무관한 별도 CLI 확장 작업

**판단:** 한 파일 안에 두 성격이 섞였지만, hunk가 명확히 분리되어 있고 Git 기능상 분리 커밋이 가능하다. 그러나 이번 단계에서 직접 분리하지 않고 사용자 승인 후 처리한다.

---

### 그룹 C — HwpxParser 기능 개선 (순수 parser, P14B-1과 무관)

| 파일 | 변경 규모 | P14B-1 관련성 | 판단 |
|---|---|---|---|
| `src/main/java/com/haehan/engine/parser/HwpxParser.java` | +78줄 | LOW | 별도 커밋 가능 |
| `src/test/java/com/haehan/engine/parser/HwpxParserTableCoordinatesTest.java` | +33줄 | LOW | HwpxParser와 묶음 |

**HwpxParser.java 변경 내용:**
- MIME 타입에 `owpml` 추가 (`application/owpml` 지원)
- `processedTables` Set으로 중복 테이블 처리 방지
- `buildVisualTableGrid()` 신규 메서드 — 셀 covered 처리
- 테이블 좌표 계산 수정 (rowCnt/rowCount 속성 우선 활용)
- `findAndProcessTablesRecursive()` 시그니처 변경

**HwpxParserTableCoordinatesTest.java 변경 내용:**
- 테이블 좌표 기대값 수정 (buildVisualTableGrid에 맞춰 조정)
- `directSectionTablesAreNotAddedTwice()` 테스트 신규 추가
- mimetype을 `application/owpml`로 변경

**판단:** P14B-1 artifact/command 계약과 무관한 순수 parser 개선. 별도 커밋으로 처리 가능.

---

### 그룹 D — Dockerfile / Python 의존성 (Application CLI와 연관)

| 파일 | 변경 규모 | P14B-1 관련성 | 판단 |
|---|---|---|---|
| `Dockerfile` | +3줄 | LOW | Application CLI 지원 |
| `Dockerfile.hwpx-engine` | +6줄 | LOW | Application CLI 지원 |

**Dockerfile 변경:** Python3, pip, olefile 설치 추가 → HwpToHwpxCliBridge 런타임 지원

**판단:** Application.java의 HwpToHwpxCliBridge 추가와 묶어 커밋 가능.

---

### 그룹 E — standalone/converter/tooling Python 확장

| 파일 | 변경 규모 | P14B-1 관련성 | 판단 |
|---|---|---|---|
| `scripts/hwpx/hwp_to_hwpx_standalone.py` | +612줄 | LOW | 대규모 별도 작업 |
| `scripts/hwpx/hwpx_package.py` | +236줄 | LOW | 별도 작업 |
| `scripts/hwpx/hancom_hwp_converter_providers.py` | +95줄 | LOW | 별도 작업 |
| `scripts/hwpx/hancom_hwp_converter_router.py` | +104줄 | LOW | 별도 작업 |
| `scripts/hwpx/hwpx_api.py` | +127줄 | LOW | 별도 작업 |
| `scripts/hwpx/hwp_to_hwpx_sdk.py` | +5줄 | LOW | 별도 작업 |
| `scripts/hwpx/hwpx_capability_coverage.py` | ±4줄 | LOW | 소규모 |
| `scripts/hwpx/hwpx_compose_schema_reference.py` | ±4줄 | LOW | 소규모 |
| `scripts/hwpx/hwpx_element_factory.py` | +19/-11줄 | LOW | 소규모 |
| `scripts/hwpx/hwpx_image_policy.py` | +1/-4줄 | LOW | 소규모 |
| `scripts/hwpx/hwpx_job_schema.py` | +8/-4줄 | LOW | 소규모 |
| `scripts/hwpx/hwpx_list_style_ops.py` | +1/-23줄 | LOW | 소규모 |
| `scripts/hwpx/hwpx_style_ops.py` | +1/-119줄 | LOW | 대규모 리팩토링 |
| `scripts/hwpx/hwpx_table_cell_address_style.py` | +1/-23줄 | LOW | 소규모 |
| `scripts/hwpx/HWP_TO_HWPX_STANDALONE.md` | +30줄 | LOW | 문서 |
| `scripts/hwpx/diagnostics/06_roundtrip_text_probe.py` | +16/-2줄 | LOW | diagnostics |
| `scripts/hwpx/test_hancom_hwp_converter_providers.py` | +45줄 | LOW | E 그룹 테스트 |
| `scripts/hwpx/test_hancom_hwp_converter_router.py` | +105줄 | LOW | E 그룹 테스트 |
| `scripts/hwpx/test_hwp_to_hwpx_sdk.py` | +5줄 | LOW | E 그룹 테스트 |
| `scripts/hwpx/test_hwp_to_hwpx_standalone.py` | +263줄 | LOW | E 그룹 테스트 |
| `scripts/extract_hwp_body_fields.py` | +91줄 | LOW | HWP 레코드 태그 확장 |

**판단:** standalone converter 대규모 확장 작업 잔재. P14B-1과 충돌하지 않으나 P14B-1 전에 별도 커밋하는 것이 안전.

---

### 그룹 F — local-gui 개선

| 파일 | 변경 규모 | P14B-1 관련성 | 판단 |
|---|---|---|---|
| `scripts/local-gui/app_controller.py` | +21줄 | LOW | 별도 작업 |
| `scripts/local-gui/dialog_detector.py` | +56줄 | LOW | 별도 작업 |
| `scripts/local-gui/hancom_hwp_to_hwpx_local_gui.py` | +4줄 | LOW | 별도 작업 |
| `scripts/local-gui/hancom_window_inventory.py` | +2줄 | LOW | 별도 작업 |

**판단:** Windows GUI 창 활성화 안정성 개선. P14B-1 무관.

---

### 그룹 G — Devlog (자동 생성)

| 파일 | 변경 규모 | 판단 |
|---|---|---|
| `logs/change_history.jsonl` | +36줄 | devlog hook 자동 추가 |

**logs/change_history.jsonl 변경 내용:**
- `a0c5d99` (RULE-17 추가), `e0f5652` (P14A) 커밋 이후 작업들의 history 자동 누적
- 내용 확인: P14A 작업, RULE-17 추가 기록 포함

**판단:** 각 커밋 묶음과 함께 포함 가능. 로그 파일만 단독 커밋하지 않는다.

---

## 줄바꿈 노이즈 판단

- `git diff --ignore-space-at-eol --stat` 결과와 일반 diff 결과 **동일**
- `git diff --ignore-all-space --stat`도 실질 변경 그대로 유지
- **판정: 줄바꿈 노이즈가 아님. 모든 33개 파일의 변경은 실질 내용 변경.**
- LF→CRLF 경고는 Git 자동 변환 예고이며, 실제 파일 내용 변경과 무관한 OS 차이에서 발생.

---

## P14A 누락 가능성 분석

P14A 커밋(e0f5652) 포함 파일:
- `HwpxEditorApiHandler.java` ← 신규 핸들러 작성됨
- `EngineHttpServer.java` ← **포함 안 됨** ← 핸들러를 서버에 등록하는 파일

**결론: P14A 누락 확인.**

`EngineHttpServer.java`에서 `/api/hwpx/editor` route 등록이 빠진 채 P14A가 커밋됨. 이 상태에서는 `HwpxEditorApiHandler`가 존재해도 HTTP 요청을 받지 못한다. P14B-1 진행 전 반드시 처리해야 한다.

---

## 권장 커밋 전략

### 커밋 묶음 1 — P14A 누락 wiring 및 AuditWatchLifecycle (우선순위 최고)

**조건:** P14B-1 진행 전 필수 처리

포함 파일:
- `src/main/java/com/haehan/engine/http/EngineHttpServer.java`
- `src/main/java/com/haehan/engine/Application.java`
- `src/test/java/com/haehan/engine/http/HttpServerTest.java`
- `logs/change_history.jsonl` (devlog 포함)

권장 커밋 메시지:
```
fix(hwpx): wire editor endpoint and audit lifecycle
```

주의: Application.java 안에 HwpToHwpxCliBridge 관련 변경도 포함되어 있음. 이를 분리하려면 hunk 단위 `git add -p` 필요. 분리하지 않고 함께 커밋해도 P14B-1 진행에는 문제없음 (P14B-1과 충돌하지 않는 별도 기능 추가이므로).

---

### 커밋 묶음 2 — HwpxParser 테이블 좌표 개선

포함 파일:
- `src/main/java/com/haehan/engine/parser/HwpxParser.java`
- `src/test/java/com/haehan/engine/parser/HwpxParserTableCoordinatesTest.java`

권장 커밋 메시지:
```
fix(hwpx): improve table grid extraction and owpml mime support
```

---

### 커밋 묶음 3 — standalone/converter Python 확장

포함 파일:
- `Dockerfile`, `Dockerfile.hwpx-engine`
- `scripts/hwpx/hwp_to_hwpx_standalone.py`
- `scripts/hwpx/hwpx_package.py`
- `scripts/hwpx/hancom_hwp_converter_providers.py`
- `scripts/hwpx/hancom_hwp_converter_router.py`
- `scripts/hwpx/hwpx_api.py`
- `scripts/hwpx/hwp_to_hwpx_sdk.py`
- `scripts/hwpx/hwpx_*.py` (소규모 수정들)
- `scripts/hwpx/HWP_TO_HWPX_STANDALONE.md`
- `scripts/hwpx/diagnostics/06_roundtrip_text_probe.py`
- `scripts/hwpx/test_*.py`
- `scripts/extract_hwp_body_fields.py`

권장 커밋 메시지:
```
feat(hwpx): extend standalone converter and server ops api
```

---

### 커밋 묶음 4 — local-gui 안정성 개선

포함 파일:
- `scripts/local-gui/*.py`

권장 커밋 메시지:
```
fix(local-gui): improve window activation reliability
```

---

## P14B-1 진행 가능 여부

| 조건 | 상태 |
|---|---|
| P14A 누락분(EngineHttpServer route wiring) 커밋 전 | ⚠️ WARN — 먼저 처리 필요 |
| P14B-1 작업 파일과 dirty 파일 충돌 가능성 | MEDIUM — EngineHttpServer 커밋 후 해소 |
| dirty 파일이 P14B-1 테스트/gate 대상과 겹치는 파일 | `EngineHttpServer.java`, `Application.java` |
| 그룹 C/E/F dirty 상태에서 P14B-1 진행 가능성 | 가능 (비충돌) |

**권장 처리 순서:**
1. 묶음 1 커밋 (사용자 승인 후)
2. 묶음 2 커밋 (사용자 승인 후)
3. 묶음 3/4 커밋 (사용자 승인 후)
4. worktree clean 확인 후 P14B-1 진행

묶음 1 커밋만 완료되어도 P14B-1 시작 가능 (EngineHttpServer/Application이 정리된 후).

---

## STEP 8 검증

git diff --check 실행 결과 참조 예정 (보고서 작성 후 STEP 8 별도 실행).

---

## 최종 판정

**WARN**

이유:
- tracked dirty 33개 파일 중 P14A 누락분(EngineHttpServer.java route wiring)이 포함되어 있음
- 사용자 승인 없이는 어떤 파일도 커밋하지 않음
- 구현 변경 없음, 보고서만 작성
- P14B-1 진행 전 묶음 1 커밋 처리가 선행되어야 함

---

*작성: Claude Sonnet 4.6 / HWPX-BROWSER-EDITOR-P14B-0-DIRTY-WORKTREE-TRIAGE*
