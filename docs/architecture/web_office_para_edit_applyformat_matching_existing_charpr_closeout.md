# WEB-OFFICE PARA-EDIT ApplyFormat Matching (existing charPr) 부분 준공 등기

> 공정명: **WEB-OFFICE-PARA-EDIT-APPLYFORMAT-MATCHING-EXISTING-CHARPR-CLOSEOUT-01**
> baseline commit : **3777e9d** (matchToggle + FormatToolbar 활성화)
>
> bold/underline/italic 토글에 대한 existing charPr matching helper +
> Format Toolbar 본공사 (`WEB-OFFICE-PARA-EDIT-APPLYFORMAT-MATCHING-
> EXISTING-CHARPR-01`) 의 준공 범위를 공식 부분 준공으로 동결한다.
> 신규 시공 없음 — 시방서 + audit + 테스트만 신축.

---

## 1. 단지 진척도

```
[CONTENT EDITING TYPE/REPLACE/DELETE CLOSEOUT]   ████████ 100%  (d61f10f)
[CHARPR INVENTORY (read-only)]                   ████████ 100%  (5459cd6)
[APPLYFORMAT EXISTING CHARPR (writer)]           ████████ 100%  (97c4095)
[APPLYFORMAT EXISTING CHARPR CLOSEOUT 등기]      ████████ 100%  (dc9e6ad)
[APPLYFORMAT TOOLBAR PREVIEW]                    ████████ 100%  (abebab6)
[APPLYFORMAT TOOLBAR COMMAND]                    ████████ 100%  (7795857)
[APPLYFORMAT TOOLBAR COMMAND CLOSEOUT 등기]      ████████ 100%  (af1dcf3)
[APPLYFORMAT MATCHING EXISTING CHARPR]           ████████ 100%  (3777e9d)
[APPLYFORMAT MATCHING CLOSEOUT 등기]             ████████ 100%  ← 본 공정
```

---

## 2. 공식 완료 범위 (IN_SCOPE)

### 2-1. matcher 모듈

- `frontend/web_office_viewer/format_charpr_matcher.mjs` 신축
- `matchToggle(currentDef, defsDict, dimension)` — `dimension ∈ {"bold","underline","italic"}` 외 → `null`
- `matchAllToggles(currentDef, defsDict)` — 3 토글 일괄 결과
- `MATCH_DIMENSIONS` enum 정적 잠금 (3개 외 추가 금지)
- `_attrsEqual` 7축 (fontName, fontFace, fontSizePt, height, textColor, 토글 외 두 가지) 정확 동등(===) 비교
- 자기 자신 (charPrId) 제외

### 2-2. matching 정책

| 토글 | 비교 축 | 운영 가용성 |
|------|---------|------------|
| **bold** | (fontName, fontFace, fontSizePt, height, textColor, italic, underline) | **53.3%** |
| **underline** | (fontName, fontFace, fontSizePt, height, textColor, bold, italic) | **30.0%** |
| **italic** | (fontName, fontFace, fontSizePt, height, textColor, bold, underline) | **0.0%** (운영 fixture 한계) |

### 2-3. Format Toolbar UI

- `frontend/web_office_viewer/components/WebOfficeFormatToolbar.tsx`
- `enableApplyCommand` 기본 `false` → 컴포넌트 자체 렌더 미노출
- `enableApplyCommand=true` 시 bold/underline/italic 3 버튼 표시
- matching 결과로 `disabled={!mId || !currentDef || !onApplyCharPr}`
- disabled tooltip: **"현재 문서에 매칭되는 기존 스타일이 없습니다."**
- 클릭 시 `onApplyCharPr(matchedId)` 콜백 위임
- 컴포넌트가 직접 `makeApplyFormatCommand` / `applyFormatToSelection` / backend writer **호출 0건** (정적 grep)
- 신규 charPr 생성 버튼 / color picker / fontSize input **미정의**

### 2-4. command 연결

- 상위 호출자가 `applyFormatToSelection(state, matchedId, charPrDefs)` 호출 → commandLog append-only 적재
- `_appendCommand` / undo / redo / dirty / save dry-run payload 정합 7795857 회로 그대로 재사용
- `makeApplyFormatCommand` factory 재정의 0 (1개 정의 정적 잠금)

### 2-5. 운영 fixture 통계 회귀 잠금

- audit 의 `_run_fixture_stats` 가 30 fixture 측정
- **boldPct ≥ 20%** 강제 (실측 53.3%)
- **italicPct ≤ 30%** 강제 (실측 0.0%) — 운영 한계 회귀 잠금
- underlinePct 모니터링 (실측 30.0%)

### 2-6. 안전 게이트 (정적 grep 잠금)

- matcher: `fuzzy / approximate / similar / Math.abs / prompt() / showColorPicker` 0건
- toolbar: `makeApplyFormatCommand\( / applyFormatToSelection\( / save_paragraph_edits\( / apply_paragraph_edits_plan\( / create_hwpx_document\( / write_package\( / .write_xml(` 0건
- toolbar: `<input type="color"> / <input type="number"> / 신규 charPr / createCharPr` 0건
- backend (`paragraph_writer_adapter.py` 외 9개) `git diff af1dcf3` 0 행

---

## 3. 공식 차단 범위 (OUT_OF_SCOPE)

| 항목 | 차단 방식 | 후속 공정 후보 |
|------|-----------|----------------|
| **신규 charPr 생성** | `def create_char_pr` grep 0 | APPLYFORMAT-NEW-CHARPR-01 |
| **header.xml charPr 추가/복제/삭제** | `package.entries[...header.xml] = ...` 0 | APPLYFORMAT-NEW-CHARPR-01 |
| **fuzzy / approximate / similar matching** | matcher 정적 grep 0 | (영구 금지 — 잘못된 스타일 위험) |
| **color 직접 입력 UI** | `<input type="color">` 0 | APPLYFORMAT-COLOR-FONTSIZE-MATCHING-PREFLIGHT-01 |
| **fontSize 직접 입력 UI** | `<input type="number">` 0 | APPLYFORMAT-COLOR-FONTSIZE-MATCHING-PREFLIGHT-01 |
| **fontName 직접 변경 UI** | font 선택 UI 미정의 | APPLYFORMAT-FAUX-BOLD-TOOLBAR-01 |
| **bold/italic/color/fontSize 조합 → 새 style 생성** | model 미발급 | APPLYFORMAT-NEW-CHARPR-01 |
| **backend writer 직접 호출** | frontend 5 파일 grep 0 | — (영구 금지) |
| **save pipeline 재설계** | `paragraph_save_pipeline.py` 무수정 | — |
| **paragraph_writer_adapter.py 수정** | `git diff af1dcf3` 0 행 | — |
| **para_edit_command.mjs factory 재정의** | 1개 정의 정적 잠금 | — |
| **paragraph add/delete** | `UNSUPPORTED_COMMAND_TYPE` | PARA-EDIT-STRUCTURE-PREFLIGHT-01 |
| **table structure edit** | 모듈 외 | TABLE-STRUCTURE-EDIT-01 |
| **image/stamp/signature edit** | 모듈 외 | MEDIA-EDIT-01 |
| **AI 자동 입력** | CLAUDE.md §10 | AUTO-FILL-MASTER |
| **원본 HWPX 직접 수정** | `OUTPUT_EQUALS_SOURCE` + sha/mtime 검증 | — (영구 금지) |

---

## 4. 핵심 시공 자재 (3777e9d 기준)

| 파일 | 역할 |
|------|------|
| `frontend/web_office_viewer/format_charpr_matcher.mjs` | matcher (matchToggle / matchAllToggles) |
| `frontend/web_office_viewer/components/WebOfficeFormatToolbar.tsx` | bold/underline/italic 토글 버튼 |
| `frontend/web_office_viewer/format_charpr_matcher_smoke.mjs` | node smoke 16 checks |

---

## 5. 핵심 회귀 자재 (테스트/스모크 파일 목록)

본 closeout 의 보호 대상:

- `tests/test_web_office_para_edit_applyformat_matching_existing_charpr.py` (본 공정 핵심 21건)
- `tests/test_web_office_para_edit_applyformat_toolbar_command_closeout.py`
- `tests/test_web_office_para_edit_applyformat_toolbar_command.py`
- `tests/test_web_office_para_edit_applyformat_toolbar_preview.py`
- `tests/test_web_office_para_edit_applyformat_existing_charpr.py`
- `tests/test_web_office_para_edit_applyformat_existing_charpr_closeout.py`
- `tests/test_web_office_para_edit_format_charpr_inventory.py`
- `tests/test_web_office_para_edit_content_closeout.py`
- `frontend/web_office_viewer/format_charpr_matcher_smoke.mjs`
- `frontend/web_office_viewer/para_edit_apply_format_smoke.mjs`
- `frontend/web_office_viewer/para_edit_browser_self_test.mjs`
- `frontend/web_office_viewer/para_edit_ime_live_smoke.mjs`

---

## 6. 운영 fixture matching 통계 (실측 3777e9d)

| 토글 | 매칭 가능 fixture 비율 | audit 회귀 게이트 |
|------|:-----:|:-----:|
| **bold** | **53.3%** (16/30) | `≥ 20%` 강제 |
| **underline** | **30.0%** (9/30) | (모니터링) |
| **italic** | **0.0%** (0/30) | `≤ 30%` 강제 |

한국 공공/행정 양식 HWPX 의 charPr table 작성 관행 — italic 변형이 사전 정의되지 않음. bold 와 underline 만 실용적.

---

## 7. 다음 후보 공정

| 공정 | 활성화 조건 | 우선 |
|------|-------------|------|
| `APPLYFORMAT-FAUX-BOLD-TOOLBAR-01` | 표준 워드프로세서식 toolbar UI 폴리시 (아이콘/단축키) | 1 |
| `APPLYFORMAT-COLOR-FONTSIZE-MATCHING-PREFLIGHT-01` | 사용자 입력 → 정확 일치 charPr 검색 사전 정찰 | 2 |
| `APPLYFORMAT-COLOR-FONTSIZE-MATCHING-01` | 본공사 | 3 |
| `APPLYFORMAT-NEW-CHARPR-PREFLIGHT-01` | header.xml 에 신규 charPr 추가 시 무결성 사전 정찰 | 4 |
| `APPLYFORMAT-NEW-CHARPR-01` | 본공사 (header.xml mutation) | 5 |
| `PARA-EDIT-STRUCTURE-PREFLIGHT-01` | paragraph add/delete + Enter capture 사전 정찰 | 6 |

---

## 8. RISK-LEDGER 상태

| ID | 항목 | 상태 |
|----|------|------|
| R-MATCH-01 | italic 매칭 후보 0% (운영 한계) | MITIGATED (audit `italicPct ≤ 30%` 회귀 잠금 + UI disabled) |
| R-MATCH-02 | 완전 일치 보수성 — 매칭 자주 없음 | MITIGATED (disabled tooltip 안내) |
| R-MATCH-03 | fuzzy matching 잘못된 스타일 선택 | MITIGATED (정적 grep 0) |
| R-MATCH-04 | color/fontSize 후보 폭발 | MITIGATED (1차 미포함, 정적 grep 0) |
| R-MATCH-05 | paragraph vs 문서 전체 후보 정책 | MITIGATED (문서 전체 charPrDefs 검색) |
| R-MATCH-06 | multi-charPr selection 기준 선택 | MITIGATED (currentCharPrId 단일 기준) |
| R-MATCH-07 | multi-paragraph selection 차단 | MITIGATED (applyFormatToSelection `NO_TEXT_RANGE` reject) |
| R-MATCH-08 | IME composition 잠금 | MITIGATED (`COMPOSITION_LOCKED` reject) |
| R-MATCH-09 | undo/redo 정합 | MITIGATED (`_appendCommand` 재사용) |
| R-MATCH-10 | af1dcf3 closeout 잠금 위반 | MITIGATED (LOCKED 14 자재 무수정) |

---

## 9. 본 공정 산출물

- `docs/architecture/web_office_para_edit_applyformat_matching_existing_charpr_closeout.md` — 본 시방서 (신설)
- `scripts/ops/audit_web_office_para_edit_applyformat_matching_existing_charpr_closeout.py` — closeout 준공검사 (신설)
- `tests/test_web_office_para_edit_applyformat_matching_existing_charpr_closeout.py` — closeout 감리 (신설)

기존 matcher / toolbar / smoke / state / command / preview / writer / adapter / model / plan / verify7 / readback / inventory / render_payload — **모두 무수정**.

---

*생성: WEB-OFFICE-PARA-EDIT-APPLYFORMAT-MATCHING-EXISTING-CHARPR-CLOSEOUT-01 (2026-05-21)*
*baseline : 3777e9d*


---

> **baseline 갱신**: 1f442ec

> **baseline 갱신**: 98d64ed (SCOPE-BOUNDARY-REJECT-01 준공, 2026-05-21) — header/footer/non-body scope reject guard 추가. para_edit_state.mjs / para_edit_model.py 정당 변경 확인 후 베이스라인 갱신. (STRUCTURE-PARA-INSERT-01 준공, 2026-05-21) — 잠금 파일 정당 변경 확인 후 베이스라인 갱신.

> **저장소 분리 기준**: e04d325 (hwpx-web-office 신규 저장소 초기 커밋, 2026-05-22)

> **baseline 갱신**: 334d665 (WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01 준공, 2026-05-22) — charPr guard 추가로 잠금 파일 정당 변경 확인 후 베이스라인 갱신.

> **baseline 갱신**: 2f7db75 (텍스트 편집 시 lineseg 완전 제거 → 한컴 재조판 유도 준공, 2026-07-23) — paragraph_writer_adapter.py 에 _strip_lineseg() 추가(TYPE_TEXT/REPLACE_TEXT_RANGE/DELETE_TEXT_RANGE 저장 직전 호출). 실제 Hancom Office COM으로 줄바꿈 재조판 확인 후 정당 변경으로 베이스라인 갱신.

> **baseline 갱신**: e9517fc (머리말/꼬리말 텍스트 편집 준공, 2026-07-24) — paragraph_writer_adapter.py 에
> _resolve_header_footer_paragraph 추가(CLAUDE.md §4.2), hwpx_edit_tool.py 의 containerScope.kind
> 허용 집합에 header/footer 추가. 실제 Hancom Office COM 으로 머리말 텍스트 편집 확인 후
> 정당 변경으로 베이스라인 갱신.
