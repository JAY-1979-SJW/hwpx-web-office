# WEB-OFFICE PARA-EDIT ApplyFormat color Matching 부분 준공 등기

> 공정명: **WEB-OFFICE-PARA-EDIT-APPLYFORMAT-COLOR-MATCHING-CLOSEOUT-01**
> baseline commit : **09a29a3** (textColor matching + ColorPalette UI)
>
> textColor 변경 토글에 대한 existing charPr matching helper + Format
> Toolbar ColorPalette 본공사 (`WEB-OFFICE-PARA-EDIT-APPLYFORMAT-COLOR-
> MATCHING-EXISTING-CHARPR-01`) 의 준공 범위를 공식 부분 준공으로 동결.
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
[APPLYFORMAT MATCHING bold/underline/italic]     ████████ 100%  (3777e9d)
[APPLYFORMAT MATCHING CLOSEOUT 등기]             ████████ 100%  (8098944)
[APPLYFORMAT FONTSIZE MATCHING]                  ████████ 100%  (831cf61)
[APPLYFORMAT FONTSIZE MATCHING CLOSEOUT 등기]    ████████ 100%  (c3bc92b)
[APPLYFORMAT COLOR MATCHING]                     ████████ 100%  (09a29a3)
[APPLYFORMAT COLOR MATCHING CLOSEOUT 등기]       ████████ 100%  ← 본 공정
```

---

## 2. 공식 완료 범위 (IN_SCOPE)

### 2-1. matcher 확장

- `matchAxisChange(currentDef, defsDict, "textColor", newValue)` — color axis 분기
- `MATCH_AXIS_CHANGE_DIMENSIONS = ["fontSizePt", "textColor"]` 정적 잠금 (2개 정확, fontName 미포함)
- `extractAxisValues(defsDict, "textColor", currentDef)` — 문서 전체 color palette 후보 (중복 제거 + 정렬 + current/enabled 표시)

### 2-2. textColor matching 정책

| 비교 축 | 정합 |
|---------|------|
| `textColor` | `#RRGGBB` 문자열 정확 동등 (`===`) |
| `fontName` / `fontFace` / `fontSizePt` / `height` / `bold` / `italic` / `underline` | currentDef 와 정확 동등 |
| 자기 자신 | charPrId 동일 시 제외 |
| NOOP | `newValue === currentDef.textColor` → `null` |

### 2-3. fuzzy / color-distance 금지 원칙

- matcher 정적 grep — `fuzzy / approximate / similar / hsv / hsl / colorDistance / deltaE / Math.abs` **0건**
- 모든 비교는 `===` 정확 동등 — `#000000` 과 `#000001` 도 다른 색

### 2-4. ColorPalette UI 정책

- swatch grid 16×16 px, `<button>` element
- `background-color` inline style (`{color}`)
- 매칭 가능 swatch → `enabled=true`, 클릭 가능
- 매칭 불가 swatch → `disabled=true`, 회색조 (CSS class)
- 현재 색상 → `current=true, disabled=true`, 테두리 강조
- empty palette → `<small>현재 문단의 스타일에 대해 변경 가능한 색이 없습니다 — 후속 공정에서 신규 style 생성을 지원합니다</small>` 안내
- tooltip:
  - enabled: `color #RRGGBB → charPr #{id}`
  - current: `현재 선택된 색상`
  - disabled: `현재 문서에 같은 속성 조합의 기존 색상 스타일이 없습니다.`
- HTML `<input type="color">` / 외부 ColorPicker / `+ 색상 추가` / 신규 charPr 생성 trigger **미정의**

### 2-5. command 연결 방식

- ColorPalette swatch 클릭 → `onApplyCharPr(matchedCharPrId)` **콜백만**
- 직접 `makeApplyFormatCommand` / `applyFormatToSelection` / backend writer 호출 **0건** (정적 grep)
- 상위 호출자가 기존 `applyFormatToSelection(state, matchedId, charPrDefs)` 호출 → commandLog append-only 적재 (7795857 회로 그대로)

### 2-6. fontName 보류 사유

- 한글/영문 `fontFace` (id) vs `fontName` (역참조) 혼선 위험 (R-CFM-03)
- `MATCH_AXIS_CHANGE_DIMENSIONS` 에서 정적으로 제외
- matcher `axis="fontName"` → `null` (smoke `fontNameStillRejected` 회귀)
- toolbar `FontNameDropdown` / `extractAxisValues(_, "fontName", _)` 정적 grep 0
- 후속 공정: `APPLYFORMAT-FONTNAME-MATCHING-PREFLIGHT-01` → `APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01`

### 2-7. 운영 fixture 통계 회귀 잠금

| 지표 | 실측 | audit 게이트 |
|------|:----:|:----:|
| fixture-level color matching | **93.3%** (28/30) | `≥ 80%` |
| per-charPr 평균 매칭 가능 색 | **0.29** | `≥ 0.15` |

### 2-8. 안전 게이트 (정적 grep 잠금)

- matcher: fuzzy/HSV/거리 계산 0건
- matcher: axis enum 정확히 `{"fontSizePt", "textColor"}`, fontName 미포함
- toolbar: HTML color input / 외부 ColorPicker / 신규 charPr trigger 0건
- toolbar: `makeApplyFormatCommand\( / applyFormatToSelection\( / save_paragraph_edits\( / apply_paragraph_edits_plan\( / create_hwpx_document\( / write_package\( / .write_xml(` 0건
- backend (paragraph_writer_adapter 외 9개) `git diff 09a29a3` 0 행

---

## 3. 공식 차단 범위 (OUT_OF_SCOPE)

| 항목 | 차단 방식 | 후속 공정 후보 |
|------|-----------|----------------|
| **fontName matching** | matcher `axis="fontName"` → null + toolbar FontNameDropdown 0 | APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01 |
| **fuzzy / approximate / similar matching** | matcher 정적 grep 0 | (영구 금지) |
| **HSV / RGB 거리 기반 유사색 matching** | matcher 정적 grep 0 | (영구 금지) |
| **신규 charPr 생성** | `def create_char_pr` grep 0 | APPLYFORMAT-NEW-CHARPR-01 |
| **header.xml charPr 추가/복제/삭제** | `package.entries[...header.xml] = ...` 0 | APPLYFORMAT-NEW-CHARPR-01 |
| **HTML `<input type="color">`** | toolbar 정적 grep 0 | (영구 금지) |
| **외부 ColorPicker 라이브러리** | toolbar 정적 grep 0 (`ColorPicker / react-color`) | (영구 금지) |
| **`+ 색상 추가` 버튼** | toolbar 정적 grep 0 | APPLYFORMAT-NEW-CHARPR-01 |
| **color 값을 조합해 새 style 생성** | model 미발급 | APPLYFORMAT-NEW-CHARPR-01 |
| **backend writer 직접 호출** | frontend 5 파일 grep 0 | — (영구 금지) |
| **save pipeline 재설계** | `paragraph_save_pipeline.py` 무수정 | — |
| **paragraph_writer_adapter.py 수정** | `git diff 09a29a3` 0 행 | — |
| **para_edit_command.mjs factory 재정의** | `git diff 09a29a3` 0 행 | — |
| **paragraph add/delete** | `UNSUPPORTED_COMMAND_TYPE` | PARA-EDIT-STRUCTURE-PREFLIGHT-01 |
| **table structure edit** | 모듈 외 | TABLE-STRUCTURE-EDIT-01 |
| **image/stamp/signature edit** | 모듈 외 | MEDIA-EDIT-01 |
| **AI 자동 입력** | CLAUDE.md §10 | AUTO-FILL-MASTER |
| **원본 HWPX 직접 수정** | `OUTPUT_EQUALS_SOURCE` + sha/mtime 검증 | — (영구 금지) |

---

## 4. 핵심 시공 자재 (09a29a3 기준)

| 파일 | 역할 |
|------|------|
| `frontend/web_office_viewer/format_charpr_matcher.mjs` | matchAxisChange (fontSize + color) + matchToggle (bold/underline/italic) |
| `frontend/web_office_viewer/components/WebOfficeFormatToolbar.tsx` | bold/underline/italic 토글 + FontSizeDropdown + ColorPalette |
| `frontend/web_office_viewer/format_charpr_matcher_smoke.mjs` | node smoke 50 checks |

---

## 5. 핵심 회귀 자재 (테스트/스모크 파일 목록)

본 closeout 의 보호 대상:

- `tests/test_web_office_para_edit_applyformat_color_matching_existing_charpr.py` (본 공정 핵심 19건)
- `tests/test_web_office_para_edit_applyformat_fontsize_matching_closeout.py`
- `tests/test_web_office_para_edit_applyformat_fontsize_matching_existing_charpr.py`
- `tests/test_web_office_para_edit_applyformat_matching_existing_charpr_closeout.py`
- `tests/test_web_office_para_edit_applyformat_matching_existing_charpr.py`
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

## 6. 운영 fixture matching 통계 (실측 09a29a3)

| 축 | fixture-level 매칭 | per-charPr 평균 | audit 게이트 |
|----|:--:|:--:|:--:|
| **textColor** (본 공정) | **93.3%** (28/30) | **0.29** | `≥ 80%` / `≥ 0.15` |
| fontSizePt (831cf61) | 100.0% | (palette 8 size) | `≥ 90%` |
| bold (3777e9d) | 53.3% | — | `≥ 20%` |
| underline (3777e9d) | 30.0% | — | (모니터링) |
| italic (3777e9d) | 0.0% | — | `≤ 30%` 강제 |

---

## 7. 다음 후보 공정

| 공정 | 활성화 조건 | 우선 |
|------|-------------|------|
| `APPLYFORMAT-FONTNAME-MATCHING-PREFLIGHT-01` | fontName matching 한/영 fontFace 정합 사전 정찰 | 1 |
| `APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01` | fontName dropdown 본공사 | 2 |
| `APPLYFORMAT-NEW-CHARPR-PREFLIGHT-01` | 매칭 없을 때 신규 style 생성 사전 정찰 | 3 |
| `APPLYFORMAT-NEW-CHARPR-01` | 본공사 (header.xml mutation) | 4 |
| `APPLYFORMAT-UI-POLISH-01` | toolbar 아이콘/단축키/접근성 폴리시 | 5 |
| `PARA-EDIT-STRUCTURE-PREFLIGHT-01` | paragraph add/delete + Enter capture 사전 정찰 | 6 |

---

## 8. RISK-LEDGER 상태

| ID | 항목 | 상태 |
|----|------|------|
| R-COLOR-01 | color 후보 다수 UX 복잡 | MITIGATED (palette 평균 3.4개, swatch 16×16) |
| R-COLOR-02 | per-charPr 매칭 0.29 → disabled 빈도 | MITIGATED (disabled tooltip 안내) |
| R-COLOR-03 | `#RRGGBB` 정규화 | MITIGATED (header 양식 일관, `===` 비교) |
| R-COLOR-04 | 특수색 UI | MITIGATED (swatch 그대로 표시) |
| R-COLOR-05 | multi-charPr selection 기준 | MITIGATED (currentCharPrId 단일) |
| R-COLOR-06 | 문서 vs paragraph palette 차이 | MITIGATED (문서 전체 palette 채택) |
| R-COLOR-07 | matching 실패 빈도 → 신뢰도 저하 | MITIGATED (현재/disabled 명시 + footer 안내) |
| R-COLOR-08 | 신규 charPr 생성 요구 증가 | PLANNED (NEW-CHARPR 공정) |
| R-COLOR-09 | c3bc92b closeout 잠금 위반 | MITIGATED (LOCKED 14 자재 무수정) |
| R-CFM-03 | fontName 한/영 fontFace 혼동 | PLANNED (FONTNAME-MATCHING-PREFLIGHT) |

---

## 9. 본 공정 산출물

- `docs/architecture/web_office_para_edit_applyformat_color_matching_closeout.md` — 본 시방서 (신설)
- `scripts/ops/audit_web_office_para_edit_applyformat_color_matching_closeout.py` — closeout 준공검사 (신설)
- `tests/test_web_office_para_edit_applyformat_color_matching_closeout.py` — closeout 감리 (신설)

기존 matcher / toolbar / smoke / state / command / preview / writer / adapter / model / plan / verify7 / readback / inventory / render_payload — **모두 무수정**.

---

*생성: WEB-OFFICE-PARA-EDIT-APPLYFORMAT-COLOR-MATCHING-CLOSEOUT-01 (2026-05-21)*
*baseline : 09a29a3*


---

> **baseline 갱신**: 1f442ec

> **baseline 갱신**: 98d64ed (SCOPE-BOUNDARY-REJECT-01 준공, 2026-05-21) — header/footer/non-body scope reject guard 추가. para_edit_state.mjs / para_edit_model.py 정당 변경 확인 후 베이스라인 갱신. (STRUCTURE-PARA-INSERT-01 준공, 2026-05-21) — 잠금 파일 정당 변경 확인 후 베이스라인 갱신.

> **저장소 분리 기준**: e04d325 (hwpx-web-office 신규 저장소 초기 커밋, 2026-05-22)

> **baseline 갱신**: 685e8c9 (WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01 준공, 2026-05-22) — charPr guard 추가로 잠금 파일 정당 변경 확인 후 베이스라인 갱신.
