# WEB-OFFICE PARA-EDIT ApplyFormat fontName Matching 부분 준공 등기

> 공정명: **APPLYFORMAT-FONTNAME-MATCHING-CLOSEOUT-01**
> baseline commit : **95b69ab** (fontName matching + FontNameDropdown UI)
>
> fontName 변경 토글에 대한 existing charPr matching helper + Format
> Toolbar FontNameDropdown 본공사 (`WEB-OFFICE-PARA-EDIT-APPLYFORMAT-
> FONTNAME-MATCHING-EXISTING-CHARPR-01`) 의 준공 범위를 공식 부분 준공
> 으로 동결한다. 신규 시공 없음 — 시방서 + audit + 테스트만 신축.

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
[APPLYFORMAT COLOR MATCHING CLOSEOUT 등기]       ████████ 100%  (86c030d)
[APPLYFORMAT FONTNAME MATCHING]                  ████████ 100%  (95b69ab)
[APPLYFORMAT FONTNAME MATCHING CLOSEOUT 등기]    ████████ 100%  ← 본 공정
```

---

## 2. 공식 완료 범위 (IN_SCOPE)

### 2-1. matcher 확장

- `matchAxisChange(currentDef, defsDict, "fontName", newValue)` — fontName axis 분기
- `MATCH_AXIS_CHANGE_DIMENSIONS = ["fontSizePt", "textColor", "fontName"]` 정적 잠금 (정확히 3개)
- `extractAxisValues(defsDict, "fontName", currentDef)` — 문서 전체 fontName palette 후보

### 2-2. fontName matching 정책

| 비교 축 | 정합 |
|---------|------|
| `fontName` | 문자열 정확 동등 (`===`) |
| `fontSizePt` / `height` / `textColor` / `bold` / `italic` / `underline` | currentDef 와 정확 동등 |
| **`fontFace`** | **비교 제외** (corpus 실측 fontFace ↔ fontName 다대다 — HWPX 내부 슬롯 인덱스) |
| 자기 자신 | charPrId 동일 시 제외 |
| NOOP | `newValue === currentDef.fontName` → `null` |

### 2-3. fontFace 비교 제외 정책

- 정찰 결과 `fontFace=4` → ["HY헤드라인M", "바탕", "바탕체", "한양견고딕", "한양신명조", "한컴바탕", "함초롬바탕", "휴먼명조"] 등 1:n 다대다
- fontFace 는 HWPX 내부 언어별 슬롯 인덱스 (hangul/latin/hanja/japanese), 폰트 정체성 아님
- matcher 의 fontName 분기 `otherKeys` 리스트에서 fontFace 명시적 제외
- audit `FONTFACE_IN_FONTNAME_IDENTITY` 게이트로 정적 잠금

### 2-4. fuzzy / alias / 거리 계산 금지 원칙

- matcher 정적 grep — `fuzzy / approximate / similar / alias / levenshtein / hsv / hsl / colorDistance / deltaE / Math.abs` **0건**
- 모든 비교는 `===` 정확 동등 — `돋움` 과 `Dotum` 도 자동 매칭 안 됨

### 2-5. FontNameDropdown UI 정책

- `WebOfficeFormatToolbar.tsx` 내부 컴포넌트
- `<label>FontName</label>` + `<select>` + `<option disabled={!c.enabled}>`
- 후보 0건 → select 자체 disabled + `(후보 없음)` + footer note
- tooltip:
  - enabled: `fontName {name} → charPr #{id}`
  - current: `{name} (현재 선택)`
  - disabled: `현재 문서에 같은 속성 조합의 기존 폰트 스타일이 없습니다.`
- 선택 시 `onApplyCharPr(matchedCharPrId)` 콜백 위임
- 외부 font picker / 시스템 fontList / `+ 폰트 추가` / alias 추천 UI / 신규 charPr 생성 trigger **미정의**

### 2-6. command 연결 방식

- FontNameDropdown 콜백 위임: `onApplyCharPr(matchedCharPrId)` 만
- 직접 `makeApplyFormatCommand` / `applyFormatToSelection` / backend writer 호출 **0건** (정적 grep)
- 상위 호출자가 기존 `applyFormatToSelection(state, matchedId, charPrDefs)` 호출 → commandLog append-only 적재 (7795857 회로 그대로)

### 2-7. 운영 fixture 통계 회귀 잠금

| 지표 | 실측 | audit 게이트 |
|------|:----:|:----:|
| fontName fixture-level matching | **100.0%** (30/30) | `≥ 90%` |
| per-charPr 평균 매칭 fontName | **1.25** | `≥ 0.5` |

### 2-8. 안전 게이트 (정적 grep 잠금)

- matcher: fuzzy/alias/HSV/거리 계산 0건
- matcher: axis enum 정확히 `{"fontSizePt", "textColor", "fontName"}` 3개
- matcher: fontName 분기 비교 키에 fontFace 미포함
- toolbar: `makeApplyFormatCommand\( / applyFormatToSelection\( / save_paragraph_edits\( / apply_paragraph_edits_plan\( / create_hwpx_document\( / write_package\( / .write_xml(` 0건
- toolbar: 외부 font picker (`FontPicker / systemFonts / fontList`) 0건
- toolbar: `<input type="color">` / 외부 ColorPicker 0건
- toolbar: `+ 폰트 추가` (`createFont / aliasRecommend`) 0건
- backend (paragraph_writer_adapter 외 9개) `git diff 95b69ab` 0 행

---

## 3. 공식 차단 범위 (OUT_OF_SCOPE)

| 항목 | 차단 방식 | 후속 공정 후보 |
|------|-----------|----------------|
| **font alias matching** (돋움 ↔ 돋움체 자동 추천) | matcher 정적 grep 0 (`alias`) | APPLYFORMAT-FONT-ALIAS-PREFLIGHT-01 |
| **영문 alias matching** (Dotum 등) | matcher `===` 비교만 | APPLYFORMAT-FONT-ALIAS-MATCHING-01 |
| **fuzzy / approximate / levenshtein matching** | matcher 정적 grep 0 | (영구 금지) |
| **fontFace exact matching** | fontName 분기에서 fontFace 명시적 제외 | (영구 — 정체성 아님) |
| **fontName + fontFace 동시 exact** | fontFace 비교 제외 정책 | (영구) |
| **신규 charPr 생성** | `def create_char_pr` grep 0 | APPLYFORMAT-NEW-CHARPR-01 |
| **header.xml charPr 추가/복제/삭제** | `package.entries[...header.xml] = ...` 0 | APPLYFORMAT-NEW-CHARPR-01 |
| **외부 font picker** | toolbar grep 0 | (영구 금지) |
| **시스템 font list 호출** | toolbar grep 0 | (영구 금지) |
| **`+ 폰트 추가` 버튼** | toolbar grep 0 | APPLYFORMAT-NEW-CHARPR-01 |
| **fontName 값을 조합해 새 style 생성** | model 미발급 | APPLYFORMAT-NEW-CHARPR-01 |
| **backend writer 직접 호출** | frontend 5 파일 grep 0 | — (영구 금지) |
| **save pipeline 재설계** | `paragraph_save_pipeline.py` 무수정 | — |
| **paragraph_writer_adapter.py 수정** | `git diff 95b69ab` 0 행 | — |
| **para_edit_command.mjs factory 재정의** | `git diff 95b69ab` 0 행 | — |
| **paragraph add/delete** | `UNSUPPORTED_COMMAND_TYPE` | PARA-EDIT-STRUCTURE-PREFLIGHT-01 |
| **table structure edit** | 모듈 외 | TABLE-STRUCTURE-EDIT-PREFLIGHT-01 |
| **image/stamp/signature edit** | 모듈 외 | MEDIA-EDIT-PREFLIGHT-01 |
| **AI 자동 입력** | CLAUDE.md §10 | AUTO-FILL-MASTER |
| **원본 HWPX 직접 수정** | `OUTPUT_EQUALS_SOURCE` + sha/mtime 검증 | — (영구 금지) |

---

## 4. 핵심 시공 자재 (95b69ab 기준)

| 파일 | 역할 |
|------|------|
| `frontend/web_office_viewer/format_charpr_matcher.mjs` | matchAxisChange (fontSize + color + fontName) + matchToggle (bold/underline/italic) |
| `frontend/web_office_viewer/components/WebOfficeFormatToolbar.tsx` | bold/underline/italic 토글 + FontSizeDropdown + ColorPalette + **FontNameDropdown** |
| `frontend/web_office_viewer/format_charpr_matcher_smoke.mjs` | node smoke **64 checks** |

---

## 5. 핵심 회귀 자재 (테스트/스모크 파일 목록)

본 closeout 의 보호 대상:

- `tests/test_web_office_para_edit_applyformat_fontname_matching_existing_charpr.py` (본 공정 핵심 21건)
- `tests/test_web_office_para_edit_applyformat_color_matching_closeout.py`
- `tests/test_web_office_para_edit_applyformat_color_matching_existing_charpr.py`
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

## 6. 운영 fixture matching 통계 (실측 95b69ab)

| 축 | fixture-level 매칭 | per-charPr 평균 | audit 게이트 |
|----|:--:|:--:|:--:|
| **fontName** (본 공정) | **100.0%** (30/30) | **1.25** | `≥ 90%` / `≥ 0.5` |
| fontSizePt (831cf61) | 100.0% | (palette 8 size) | `≥ 90%` |
| textColor (09a29a3) | 93.3% | 0.29 | `≥ 80%` / `≥ 0.15` |
| bold (3777e9d) | 53.3% | — | `≥ 20%` |
| underline (3777e9d) | 30.0% | — | (모니터링) |
| italic (3777e9d) | 0.0% | — | `≤ 30%` 강제 |

fontName 매칭이 **모든 matching 축 중 가장 풍부** — 운영 가치 최대, disabled 빈도 최소.

---

## 7. 다음 후보 공정

| 공정 | 활성화 조건 | 우선 |
|------|-------------|------|
| `APPLYFORMAT-FONT-ALIAS-PREFLIGHT-01` | 돋움/돋움체 등 alias 정책 사전 정찰 | 1 |
| `APPLYFORMAT-FONT-ALIAS-MATCHING-01` | alias 본공사 (matcher alias 룰 추가) | 2 |
| `APPLYFORMAT-NEW-CHARPR-PREFLIGHT-01` | 매칭 없을 때 신규 style 생성 사전 정찰 (header.xml mutation 위험 분석) | 3 |
| `APPLYFORMAT-NEW-CHARPR-01` | 본공사 (header.xml mutation) | 4 |
| `APPLYFORMAT-UI-POLISH-01` | toolbar 아이콘/단축키/접근성 폴리시 | 5 |
| `PARA-EDIT-STRUCTURE-PREFLIGHT-01` | paragraph add/delete + Enter capture 사전 정찰 | 6 |
| `TABLE-STRUCTURE-EDIT-PREFLIGHT-01` | 표 행/열 add/delete/merge 사전 정찰 | 7 |
| `MEDIA-EDIT-PREFLIGHT-01` | image/stamp/signature 편집 사전 정찰 | 8 |

---

## 8. RISK-LEDGER 상태

| ID | 항목 | 상태 |
|----|------|------|
| R-FONT-01 | fontName ↔ fontFace 1:1 아님 | **MITIGATED** (fontFace 비교 제외, audit 정적 게이트) |
| R-FONT-02 | 같은 fontName 다른 fontFace over-restrict | MITIGATED (fontFace 비교 제외) |
| R-FONT-03 | 한글/영문 alias (돋움 ↔ Dotum) | PLANNED (FONT-ALIAS-PREFLIGHT) |
| R-FONT-04 | 사용자 기대 폰트가 문서 header 에 없음 | MITIGATED (운영 100% / per-charPr 1.25) |
| R-FONT-05 | matching 실패 빈도 → UI 신뢰도 | MITIGATED (per-charPr 1.25 — disabled 적음) |
| R-FONT-06 | multi-charPr selection 기준 | MITIGATED (currentCharPrId 단일) |
| R-FONT-07 | 문서 vs paragraph palette 차이 | MITIGATED (문서 전체 채택) |
| R-FONT-08 | 신규 charPr 생성 요구 | PLANNED (NEW-CHARPR 공정) |
| R-FONT-09 | 86c030d closeout 잠금 위반 | MITIGATED (LOCKED 14 자재 무수정) |
| R-FONT-10 | fontName 표기 변종 | MITIGATED (`===` exact — 사용자 명시 선택 한정) |

---

## 9. 본 공정 산출물

- `docs/architecture/web_office_para_edit_applyformat_fontname_matching_closeout.md` — 본 시방서 (신설)
- `scripts/ops/audit_web_office_para_edit_applyformat_fontname_matching_closeout.py` — closeout 준공검사 (신설)
- `tests/test_web_office_para_edit_applyformat_fontname_matching_closeout.py` — closeout 감리 (신설)

기존 matcher / toolbar / smoke / state / command / preview / writer / adapter / model / plan / verify7 / readback / inventory / render_payload — **모두 무수정**.

---

*생성: APPLYFORMAT-FONTNAME-MATCHING-CLOSEOUT-01 (2026-05-21)*
*baseline : 95b69ab*


---

> **baseline 갱신**: 1f442ec

> **baseline 갱신**: 98d64ed (SCOPE-BOUNDARY-REJECT-01 준공, 2026-05-21) — header/footer/non-body scope reject guard 추가. para_edit_state.mjs / para_edit_model.py 정당 변경 확인 후 베이스라인 갱신. (STRUCTURE-PARA-INSERT-01 준공, 2026-05-21) — 잠금 파일 정당 변경 확인 후 베이스라인 갱신.

> **저장소 분리 기준**: e04d325 (hwpx-web-office 신규 저장소 초기 커밋, 2026-05-22)

> **baseline 갱신**: b411164 (WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01 준공, 2026-05-22) — charPr guard 추가로 잠금 파일 정당 변경 확인 후 베이스라인 갱신.
