# WEB-OFFICE PARA-EDIT ApplyFormat Toolbar Command 부분 준공 등기

> 공정명: **WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-CLOSEOUT-01**
> baseline commit : **7795857** (ApplyFormat toolbar command 활성화)
>
> ApplyFormat toolbar UI → commandLog 연결 본공사 (`WEB-OFFICE-PARA-EDIT
> -APPLYFORMAT-TOOLBAR-COMMAND-01`) 의 준공 범위를 공식 부분 준공으로
> 동결한다. 신규 시공 없음 — 시방서 + audit + 테스트만 신축.

---

## 1. 단지 진척도

```
[CONTENT EDITING TYPE/REPLACE/DELETE CLOSEOUT]     ████████ 100%  (d61f10f)
[CHARPR INVENTORY (read-only)]                     ████████ 100%  (5459cd6)
[APPLYFORMAT EXISTING CHARPR (writer)]             ████████ 100%  (97c4095)
[APPLYFORMAT EXISTING CHARPR CLOSEOUT 등기]        ████████ 100%  (dc9e6ad)
[APPLYFORMAT TOOLBAR PREVIEW (read-only UI)]       ████████ 100%  (abebab6)
[APPLYFORMAT TOOLBAR COMMAND (UI→commandLog)]      ████████ 100%  (7795857)
[APPLYFORMAT TOOLBAR COMMAND CLOSEOUT 등기]        ████████ 100%  ← 본 공정
```

---

## 2. 공식 완료 범위 (IN_SCOPE)

### 2-1. helper 활성화

- `applyFormatToSelection(state, targetCharPrIDRef, charPrDefs)` JS helper
- 입력 검증 7중: `NO_ACTIVE_PARAGRAPH` / `COMPOSITION_LOCKED` / `NO_TEXT_RANGE` / `EMPTY_RANGE` / `REQUIRES_REVIEW_NO_CONTAINER_SCOPE` / `TARGET_CHARPR_REQUIRED` / `TARGET_CHARPR_NOT_IN_HEADER`
- 통과 시 기존 `makeApplyFormatCommand` factory 재사용 (재정의 0)

### 2-2. preview command mode opt-in

- `WebOfficeFormatPreview.tsx` 신규 props: `enableApplyCommand` (기본 `false`), `onApplyCharPr` callback
- **기본값 false → abebab6 read-only mode 보존** (`readOnlyMode = !enableApplyCommand`)
- `enableApplyCommand=true` 시에만 후보 항목이 `<button>` 으로 렌더 + 클릭 핸들러 활성
- 컴포넌트가 직접 `makeApplyFormatCommand` 호출하지 않음 — 상위 콜백으로 위임

### 2-3. commandLog 정합 (commandLog append-only)

- `_appendCommand(state, cmd, nextPara)` 재사용 — commandLog append-only 보장
- `undoStack` 에 추가, `redoStack` 비움, `dirty=true`
- `undo` → `_applyFormatInverse` (`inverse.restoreSegments` 복원) 호출
- `redo` → `_applyFormat` 재적용
- `commandLog append-only` + `inverse.restoreSegments` 직렬화는 node smoke 25 checks 로 회귀 잠금

### 2-4. paragraph.text 무변경 원칙

- `_applyFormat` (JS in-memory) 가 run split 후 charPr 만 교체 — text node 의 `.text` 합은 원본과 동일
- node smoke `paragraphTextUnchanged` 검증

### 2-5. save dry-run payload 포함

- `buildSaveDryRunPayload(state)` 가 commandLog 의 APPLY_FORMAT command 를 그대로 직렬화
- 신규 save API 추가 없음 — 기존 경로 그대로

### 2-6. backend / writer 분리

- preview / state / command 어디서도 `save_paragraph_edits` / `apply_paragraph_edits_plan` / `create_hwpx_document` / `write_package` 호출 0건
- 신규 charPr 생성 함수 (`create_char_pr`) 정의 0건
- `header.xml` write 경로 (`package.entries[...header.xml] = ...`) 0건

### 2-7. 검증 게이트

- node smoke `para_edit_apply_format_smoke.mjs` — 25 checks all PASS
- abebab6 read-only preview 회귀 (10 tests) PASS
- dc9e6ad ApplyFormat existing-charPr closeout 회귀 PASS
- 97c4095 ApplyFormat writer 회귀 (V1~V7 PASS) PASS
- d61f10f content closeout (TYPE/REPLACE/DELETE) 회귀 PASS

---

## 3. 공식 차단 범위 (OUT_OF_SCOPE)

| 항목 | 차단 방식 | 후속 공정 후보 |
|------|-----------|----------------|
| **신규 charPr 생성** | `def create_char_pr` 정적 grep 0건 | APPLYFORMAT-NEW-CHARPR-01 |
| **header.xml charPr 추가/복제/삭제** | `package.entries[...header.xml] = ...` 0건 | APPLYFORMAT-NEW-CHARPR-01 |
| **bold/italic/color/fontSize 직접 버튼** | preview 컴포넌트에 미정의 | APPLYFORMAT-FAUX-BOLD-TOOLBAR-01 |
| **matching charPr 알고리즘** | 존재 안 함 | APPLYFORMAT-MATCHING-PREFLIGHT-01 / APPLYFORMAT-MATCHING-EXISTING-CHARPR-01 |
| **backend writer 직접 호출** | frontend 4 파일 정적 grep 0건 | — (영구 금지) |
| **save pipeline 재설계** | `paragraph_save_pipeline.py` 무수정 | — |
| **paragraph add/delete** | `UNSUPPORTED_COMMAND_TYPE` | PARA-EDIT-STRUCTURE-01 |
| **table structure edit** | 모듈 외 | TABLE-STRUCTURE-EDIT-01 |
| **image/stamp/signature edit** | 모듈 외 | MEDIA-EDIT-01 |
| **AI 자동 입력** | CLAUDE.md §10 | AUTO-FILL-MASTER |
| **원본 HWPX 직접 수정** | `OUTPUT_EQUALS_SOURCE` reject + sha/mtime 검증 | — (영구 금지) |
| **multi-paragraph selection ApplyFormat** | state 가 단일 paragraph activeId 만 추적 | APPLYFORMAT-MULTI-PARA-01 |

---

## 4. 핵심 시공 자재 (7795857 기준)

| 파일 | 역할 |
|------|------|
| `frontend/web_office_viewer/para_edit_state.mjs` | `applyFormatToSelection` helper |
| `frontend/web_office_viewer/para_edit_command.mjs` | APPLY_FORMAT(_INVERSE) dispatch + `_applyFormat`/`_applyFormatInverse` |
| `frontend/web_office_viewer/components/WebOfficeFormatPreview.tsx` | preview + opt-in command mode |
| `frontend/web_office_viewer/para_edit_apply_format_smoke.mjs` | node smoke 25 checks |

---

## 5. 핵심 회귀 자재 (테스트/스모크 파일)

본 closeout 의 보호 대상:

- `tests/test_web_office_para_edit_applyformat_toolbar_command.py` (본 공정 핵심 16건)
- `tests/test_web_office_para_edit_applyformat_toolbar_preview.py` (abebab6 read-only)
- `tests/test_web_office_para_edit_applyformat_existing_charpr.py` (97c4095 writer)
- `tests/test_web_office_para_edit_applyformat_existing_charpr_closeout.py` (dc9e6ad)
- `tests/test_web_office_para_edit_format_charpr_inventory.py` (5459cd6)
- `tests/test_web_office_para_edit_content_closeout.py` (d61f10f)
- `tests/test_web_office_para_edit_e2e_full_closeout.py`
- `tests/test_web_office_para_edit_e2e_integration.py`
- `tests/test_web_office_para_edit_ime_live.py`
- `tests/test_web_office_para_edit_multi_run.py`
- `tests/test_web_office_para_edit_type_multi_run.py`
- `frontend/web_office_viewer/para_edit_apply_format_smoke.mjs` (JS smoke)
- `frontend/web_office_viewer/para_edit_browser_self_test.mjs`
- `frontend/web_office_viewer/para_edit_ime_live_smoke.mjs`

---

## 6. 다음 후보 공정

| 공정 | 활성화 조건 | 우선 |
|------|-------------|------|
| `APPLYFORMAT-MATCHING-PREFLIGHT-01` | bold/italic/color/fontSize 토글 → existing charPr 매칭 알고리즘 사전 정찰 | 1 |
| `APPLYFORMAT-MATCHING-EXISTING-CHARPR-01` | 매칭 알고리즘 본공사 + matching 없을 때 disabled 정책 | 2 |
| `APPLYFORMAT-FAUX-BOLD-TOOLBAR-01` | 표준 워드프로세서식 bold/italic/color/fontSize 버튼 UI | 3 |
| `APPLYFORMAT-NEW-CHARPR-PREFLIGHT-01` | header.xml 에 신규 charPr 추가 시 무결성 사전 정찰 | 4 |
| `APPLYFORMAT-NEW-CHARPR-01` | 신규 style 생성 본공사 (header.xml mutation) | 5 |
| `PARA-EDIT-STRUCTURE-PREFLIGHT-01` | paragraph add/delete + Enter capture 사전 정찰 | 6 |

---

## 7. RISK-LEDGER 상태

| ID | 항목 | 상태 |
|----|------|------|
| R-TB-01 | matching charPr 없을 때 사용자 혼란 | PLANNED (MATCHING 공정에서 활성) |
| R-TB-02 | paragraph 단위 후보만 vs 문서 전체 후보 표시 정책 | MITIGATED (현재 paragraph 단위만 + showDocumentScope 옵션) |
| R-TB-03 | multi-paragraph selection | MITIGATED (`NO_TEXT_RANGE` 또는 activeParagraphId 단일 강제) |
| R-TB-04 | selection 과 paragraph offset 변환 정합 | MITIGATED (setRange + makeApplyFormatCommand 재사용) |
| R-TB-05 | IME composition 중 toolbar 클릭 차단 | MITIGATED (`COMPOSITION_LOCKED` reject) |
| R-TB-06 | commandLog / undo / redo 정합 | MITIGATED (`_appendCommand` 재사용 + APPLY_FORMAT_INVERSE 핸들러) |
| R-TB-07 | payload schema 변경으로 viewer 회귀 | MITIGATED (additive only, 116/188 회귀 PASS) |
| R-TB-08 | TYPE/REPLACE/DELETE UI 회귀 침해 | MITIGATED (기존 state/command 함수 무수정) |
| R-TB-09 | 사용자가 신규 style 원할 때 UX 막다른 길 | PLANNED (NEW-CHARPR 공정 트리거) |
| R-TB-10 | dc9e6ad/abebab6 closeout 잠금 위반 | MITIGATED (LOCKED 자재 갱신 명시) |

---

## 8. 본 공정 산출물

- `docs/architecture/web_office_para_edit_applyformat_toolbar_command_closeout.md` — 본 시방서 (신설)
- `scripts/ops/audit_web_office_para_edit_applyformat_toolbar_command_closeout.py` — closeout 준공검사 (신설)
- `tests/test_web_office_para_edit_applyformat_toolbar_command_closeout.py` — closeout 감리 (신설)

기존 state / command / preview / smoke / writer / adapter / model / plan / verify7 / readback / inventory / render_payload — **모두 무수정**.

---

*생성: WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-CLOSEOUT-01 (2026-05-21)*
*baseline : 7795857*


---

> **baseline 갱신**: 1f442ec

> **baseline 갱신**: 98d64ed (SCOPE-BOUNDARY-REJECT-01 준공, 2026-05-21) — header/footer/non-body scope reject guard 추가. para_edit_state.mjs / para_edit_model.py 정당 변경 확인 후 베이스라인 갱신. (STRUCTURE-PARA-INSERT-01 준공, 2026-05-21) — 잠금 파일 정당 변경 확인 후 베이스라인 갱신.

> **저장소 분리 기준**: e04d325 (hwpx-web-office 신규 저장소 초기 커밋, 2026-05-22)

> **baseline 갱신**: 334d665 (WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01 준공, 2026-05-22) — charPr guard 추가로 잠금 파일 정당 변경 확인 후 베이스라인 갱신.
