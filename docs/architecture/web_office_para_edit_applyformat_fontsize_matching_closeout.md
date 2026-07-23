# WEB-OFFICE PARA-EDIT ApplyFormat fontSize Matching 부분 준공 등기

> 공정명: **WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTSIZE-MATCHING-CLOSEOUT-01**
> baseline commit : **831cf61** (matchAxisChange + FontSizeDropdown 활성화)
>
> fontSize 변경 토글에 대한 existing charPr matching helper + Format
> Toolbar fontSize dropdown 본공사 (`WEB-OFFICE-PARA-EDIT-APPLYFORMAT-
> FONTSIZE-MATCHING-EXISTING-CHARPR-01`) 의 준공 범위를 공식 부분 준공
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
[APPLYFORMAT FONTSIZE MATCHING CLOSEOUT 등기]    ████████ 100%  ← 본 공정
```

---

## 2. 공식 완료 범위 (IN_SCOPE)

### 2-1. matcher 확장

- `frontend/web_office_viewer/format_charpr_matcher.mjs`:
  - `matchAxisChange(currentDef, defsDict, axis, newValue)` — 1차 axis enum `["fontSizePt"]` 한정
  - `extractAxisValues(defsDict, axis, currentDef)` — dropdown 후보 추출
  - `MATCH_AXIS_CHANGE_DIMENSIONS` enum 정적 잠금 (1차 fontSizePt 만)
  - `_heightFromFontSizePt(pt)` 헬퍼 — `Math.round(pt × 100)`
  - 기존 `matchToggle` bold/underline/italic 회로 **무변경**

### 2-2. fontSize matching 정책

| 비교 축 | 정합 |
|---------|------|
| `fontSizePt` | 사용자 newValue 와 정확 동등 (`===`) |
| `height` (정의된 경우만) | `Math.round(newValue × 100)` 와 정확 동등 |
| `fontName` | currentDef 와 정확 동등 |
| `fontFace` | currentDef 와 정확 동등 |
| `textColor` | currentDef 와 정확 동등 |
| `bold` / `italic` / `underline` | currentDef 와 정확 동등 |
| **자기 자신** | charPrId 동일 시 제외 |
| **NOOP** | `newValue === currentDef.fontSizePt` → `null` |

### 2-3. height/fontSizePt 정합 정책

- header.xml 의 charPr `height` 는 일반적으로 `pt × 100` (정수)
- `_heightFromFontSizePt(pt) = Math.round(pt × 100)`
- def 의 `height` 가 `null/undefined` 인 경우 정합 검증 면제
- def 의 `height` 가 잘못 적혀 있으면 (예: pt=12 인데 height=999) 매칭 제외 — smoke `heightMismatchExcluded` 회귀 잠금

### 2-4. dropdown 후보 추출 정책

`extractAxisValues(defsDict, "fontSizePt", currentDef)` → `[{value, matchedCharPrId, enabled, current}]`:
- 문서 전체 `defsDict` 에서 fontSizePt 후보 set 추출
- 중복 제거 + 숫자 오름차순 정렬
- `current === true` 시 enabled=false (현재 값)
- `matchedCharPrId !== null` 시 enabled=true (다른 후보)

### 2-5. FontSizeDropdown UI 정책

- `WebOfficeFormatToolbar.tsx` 내부 컴포넌트
- `<select>` + `<option disabled={!c.enabled}>` 패턴
- 후보 0건 → select 자체 disabled + `(후보 없음)` 옵션
- 각 옵션 `title` (tooltip):
  - enabled: `"{N}pt → charPr #{id}"`
  - current: `"{N}pt (현재 선택)"`
  - disabled+미현재: `"현재 문서에 같은 속성 조합의 기존 스타일이 없습니다."`
- 선택 시 `onApplyCharPr(matchedCharPrId)` 콜백 위임
- color picker / fontName dropdown / 신규 charPr 생성 버튼 **미정의**
- 상위 toolbar 의 `enableApplyCommand` opt-in 기본 false 유지 — 비활성 시 자체 disabled

### 2-6. command 연결 방식

- `FontSizeDropdown` 은 **콜백만** — `makeApplyFormatCommand` / `applyFormatToSelection` / backend writer 호출 0건 (정적 grep)
- 상위 호출자가 기존 `applyFormatToSelection(state, matchedId, charPrDefs)` 호출 → commandLog append-only 적재 (7795857 회로 그대로)
- `_appendCommand` / undo / redo / dirty / save dry-run 정합 — 변경 없음

### 2-7. 운영 fixture 통계 회귀 잠금

- audit `_run_fixture_stats` 가 30 fixture 측정
- **fontSize matching 100.0%** (audit 게이트 `fontSizePct ≥ 0.9` 강제)
- 운영 paragraph 어디서나 fontSize dropdown 활성 가능

### 2-8. 안전 게이트 (정적 grep 잠금)

- matcher: `fuzzy / approximate / similar / Math.abs` 0건 (`Math.round` 만 허용)
- matcher: `MATCH_AXIS_CHANGE_DIMENSIONS` enum 정확히 `["fontSizePt"]` (1차 정적 잠금)
- toolbar: `makeApplyFormatCommand\( / applyFormatToSelection\( / save_paragraph_edits\( / apply_paragraph_edits_plan\( / create_hwpx_document\( / write_package\( / .write_xml(` 0건
- toolbar: `<input type="color"> / ColorPicker / FontNameDropdown / extractAxisValues(_, "textColor", _) / extractAxisValues(_, "fontName", _)` 0건
- backend (paragraph_writer_adapter 외 9개) `git diff 831cf61` 0 행

---

## 3. 공식 차단 범위 (OUT_OF_SCOPE)

| 항목 | 차단 방식 | 후속 공정 후보 |
|------|-----------|----------------|
| **textColor / color matching** | matcher `axis="textColor"` → null + toolbar `<input type="color">` 0 | APPLYFORMAT-COLOR-MATCHING-EXISTING-CHARPR-01 |
| **fontName matching** | matcher `axis="fontName"` → null + toolbar `FontNameDropdown` 0 | APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01 |
| **fuzzy / approximate / similar matching** | matcher 정적 grep 0 | (영구 금지) |
| **신규 charPr 생성** | `def create_char_pr` grep 0 | APPLYFORMAT-NEW-CHARPR-01 |
| **header.xml charPr 추가/복제/삭제** | `package.entries[...header.xml] = ...` 0 | APPLYFORMAT-NEW-CHARPR-01 |
| **color picker UI** | toolbar 정적 grep 0 | APPLYFORMAT-COLOR-MATCHING-EXISTING-CHARPR-01 |
| **fontName dropdown UI** | toolbar 정적 grep 0 | APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01 |
| **fontSize 값을 조합해 새 style 생성** | model 미발급 | APPLYFORMAT-NEW-CHARPR-01 |
| **backend writer 직접 호출** | frontend 5 파일 grep 0 | — (영구 금지) |
| **save pipeline 재설계** | `paragraph_save_pipeline.py` 무수정 | — |
| **paragraph_writer_adapter.py 수정** | `git diff 831cf61` 0 행 | — |
| **para_edit_command.mjs factory 재정의** | `git diff 831cf61` 0 행 | — |
| **paragraph add/delete** | `UNSUPPORTED_COMMAND_TYPE` | PARA-EDIT-STRUCTURE-PREFLIGHT-01 |
| **table structure edit** | 모듈 외 | TABLE-STRUCTURE-EDIT-01 |
| **image/stamp/signature edit** | 모듈 외 | MEDIA-EDIT-01 |
| **AI 자동 입력** | CLAUDE.md §10 | AUTO-FILL-MASTER |
| **원본 HWPX 직접 수정** | `OUTPUT_EQUALS_SOURCE` + sha/mtime 검증 | — (영구 금지) |

---

## 4. color/fontName 보류 사유

| 축 | 보류 사유 | 후속 공정 |
|----|-----------|----------|
| **color** | color picker UX 복잡도 (palette 디자인) + 운영 색 분포 (`#000000` 압도적). 1차 fontSize 만 정착 후 분리. | APPLYFORMAT-COLOR-MATCHING-EXISTING-CHARPR-01 |
| **fontName** | 한글/영문 `fontFace` (id) vs `fontName` (역참조) 혼선 위험 (R-CFM-03). 정찰 후 별도 시공. | APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01 |

운영 통계 (3777e9d 정찰 대비): color 93.3% / fontSize 100% / fontName 100% — color 와 fontName 도 매칭 가능률 높으나 UX 복잡도로 1차 미포함.

---

## 5. 핵심 시공 자재 (831cf61 기준)

| 파일 | 역할 |
|------|------|
| `frontend/web_office_viewer/format_charpr_matcher.mjs` | matchAxisChange + extractAxisValues + matchToggle (기존) |
| `frontend/web_office_viewer/components/WebOfficeFormatToolbar.tsx` | bold/underline/italic 토글 + FontSizeDropdown |
| `frontend/web_office_viewer/format_charpr_matcher_smoke.mjs` | node smoke 35 checks |

---

## 6. 핵심 회귀 자재 (테스트/스모크 파일 목록)

본 closeout 의 보호 대상:

- `tests/test_web_office_para_edit_applyformat_fontsize_matching_existing_charpr.py` (본 공정 핵심 22건)
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

## 7. 운영 fixture matching 통계 (실측 831cf61)

| 축 | 운영 매칭 가능률 | 게이트 |
|----|:----:|:----:|
| **fontSizePt** (본 공정) | **100.0%** (30/30) | `≥ 90%` 강제 |
| bold (3777e9d) | 53.3% | `≥ 20%` |
| underline (3777e9d) | 30.0% | (모니터링) |
| italic (3777e9d) | 0.0% | `≤ 30%` 강제 |

fontSize 매칭은 운영 paragraph 모두 적용 가능 — 1차 공정 운영 가치 최대.

---

## 8. 다음 후보 공정

| 공정 | 활성화 조건 | 우선 |
|------|-------------|------|
| `APPLYFORMAT-COLOR-MATCHING-PREFLIGHT-01` | color picker UX + matching axis 추가 사전 정찰 | 1 |
| `APPLYFORMAT-COLOR-MATCHING-EXISTING-CHARPR-01` | color picker 본공사 (axis enum 에 `textColor` 추가) | 2 |
| `APPLYFORMAT-FONTNAME-MATCHING-PREFLIGHT-01` | fontName matching 한/영 fontFace 정합 사전 정찰 | 3 |
| `APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01` | fontName dropdown 본공사 | 4 |
| `APPLYFORMAT-NEW-CHARPR-PREFLIGHT-01` | 매칭 없을 때 신규 style 생성 사전 정찰 | 5 |
| `APPLYFORMAT-NEW-CHARPR-01` | 본공사 (header.xml mutation) | 6 |
| `PARA-EDIT-STRUCTURE-PREFLIGHT-01` | paragraph add/delete + Enter capture 사전 정찰 | 7 |

---

## 9. RISK-LEDGER 상태

| ID | 항목 | 상태 |
|----|------|------|
| R-CFM-01 | color 후보 다수 UX 복잡 | PLANNED (COLOR-MATCHING 공정에서) |
| R-CFM-02 | fontSize 사용자 기대 미충족 | MITIGATED (운영 100%, palette 한정적) |
| R-CFM-03 | fontName 한/영 fontFace 혼동 | PLANNED (FONTNAME-MATCHING-PREFLIGHT) |
| R-CFM-04 | fontSizePt/height 정규화 오차 | MITIGATED (`_heightFromFontSizePt` 검증) |
| R-CFM-05 | textColor 표기 정규화 | PLANNED (COLOR-MATCHING 공정) |
| R-CFM-06 | multi-charPr selection 기준 charPr | MITIGATED (currentCharPrId 단일) |
| R-CFM-07 | matching 실패 빈도 UX 신뢰도 | MITIGATED (fontSize 100% 적용) |
| R-CFM-08 | 신규 charPr 생성 요구 증가 | PLANNED (NEW-CHARPR 공정) |
| R-CFM-09 | dropdown 후보 폭발 | MITIGATED (운영 palette 8 size 한정) |
| R-CFM-10 | 8098944 closeout 잠금 위반 | MITIGATED (LOCKED 14 자재 무수정) |

---

## 10. 본 공정 산출물

- `docs/architecture/web_office_para_edit_applyformat_fontsize_matching_closeout.md` — 본 시방서 (신설)
- `scripts/ops/audit_web_office_para_edit_applyformat_fontsize_matching_closeout.py` — closeout 준공검사 (신설)
- `tests/test_web_office_para_edit_applyformat_fontsize_matching_closeout.py` — closeout 감리 (신설)

기존 matcher / toolbar / smoke / state / command / preview / writer / adapter / model / plan / verify7 / readback / inventory / render_payload — **모두 무수정**.

---

*생성: WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTSIZE-MATCHING-CLOSEOUT-01 (2026-05-21)*
*baseline : 831cf61*


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

> **baseline 갱신**: 517849c (빈 입력칸 기입 준공, 2026-07-24) — 서식의 빈 입력칸은 run 은 있는데 `<hp:t>` 텍스트 노드가 없어 writer 가 `RUN_TEXT_NODE_MISSING` 으로 거부했다. **자동채움이 노리는 칸은 정의상 전부 빈 칸이므로 채울 수 있는 칸이 하나도 없었다.** 삽입에 한해 빈 run 에 `<hp:t>` 를 생성하도록 교정(교체·삭제이거나 `hp:ctrl` 등 다른 자식이 있는 run 은 종전대로 거부). `charPrIDRef` 는 run 의 것을 그대로 쓰므로 신규 charPr 을 만들지 않는다. 전기사용신청서 HTTP 종단 시험 3/3 제자리·옆칸 유출 0. 잠금 파일 정당 변경 확인 후 베이스라인 갱신.

## 재고정 이력 (append-only)

- 2026-07-24: baseline → `6111a9e` (문단 텍스트 편집 시 lineseg 보존 로직 준공 — _strip_lineseg 전체삭제 대신 _fix_lineseg_on_text_edit 로 교체, 한컴 COM 실측 재검증 완료)
