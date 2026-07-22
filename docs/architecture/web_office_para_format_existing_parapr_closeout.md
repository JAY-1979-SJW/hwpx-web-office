# Web Office 문단서식(paraPr) 편집 — 준공 시방서

Task: WEB-OFFICE-PARA-FORMAT-01 (편집기 모듈 로드맵 M2)
Status: CLOSEOUT
Date: 2026-07-22

## 1. 목적

편집기에 **문단 정렬(align)** 편집을 추가한다. charPr(글자서식) 편집과 동일한
안전 원칙을 문단서식에 적용한다:

> **기존 paraPr 매칭만 허용 — 신규 paraPr 생성 및 header.xml mutation 없음.**

원하는 정렬을 가진 기존 paraPr 이 없으면 편집을 **거부**한다.

## 2. §4 안전선과의 관계

CLAUDE.md §4 의 다음 조항은 **그대로 유지**된다:

- 신규 charPr 생성 금지 → 본 공정도 신규 paraPr 생성하지 않음
- `header.xml` mutation 금지 → 본 공정은 header.xml 을 **읽기만** 함
- header/footer paragraph 편집 금지 → `_inlineScopeGuard` 로 차단
- 표 structure edit / image·shape / Excel 금지 → 본 공정 무관

본 공정은 §4 해제가 아니라, §4 원칙(기존 정의 매칭)을 문단서식으로 **확장 적용**한
것이다. 신규 paraPr 생성(= header mutation)은 **여전히 금지**이며, verify7 V5 가
이를 강제한다.

## 3. 구성

### 프론트엔드
- `frontend/web_office_viewer/weboffice/format_parpr_matcher.mjs` (신규)
  - `PARA_AXES` — align / lineSpacing / indentLeft
  - `matchParaAxisChange(curDef, defs, axis, value)` — 대상 축만 원하는 값이고
    나머지 축은 현재와 동일한 기존 paraPr id. 없으면 `null`(거부).
  - `extractParaAxisValues(defs, axis, curDef)` — 툴바 후보 목록
  - `_selfTest()` — 10 케이스
- `frontend/web_office_viewer/para_edit_command.mjs`
  - `CT_APPLY_PARA_FORMAT = "APPLY_PARA_FORMAT"`
  - `makeApplyParaFormatCommand()` — forward/inverse 포함, 텍스트 무변경
  - `applyCommandToParagraph()` 에 APPLY_PARA_FORMAT / _INVERSE 처리
- `frontend/web_office_viewer/para_edit_state.mjs`
  - `applyParaFormat(state, targetParaPrIDRef, paraPrDefs)`
  - 가드: NO_ACTIVE_PARAGRAPH / COMPOSITION_LOCKED / scope / inline(header·footer)
    / TARGET_PARAPR_REQUIRED / TARGET_PARAPR_NOT_IN_HEADER / NOOP_SAME_PARAPR
- `frontend/web_office_viewer/weboffice_edit.html`
  - 리본 "문단 정렬" 그룹 (LEFT/CENTER/RIGHT/JUSTIFY)
  - 매칭 paraPr 부재 시 버튼 비활성 + "신규 생성 금지" 안내

### 백엔드
- `scripts/hwpx/web_office/paragraph_writer_adapter.py`
  - `_SUPPORTED_COMMAND_TYPES` 에 `APPLY_PARA_FORMAT` 추가
  - `_read_header_para_pr_ids(package)` — header.xml 의 paraPr id 집합(읽기 전용)
  - 처리: 문단 요소의 `paraPrIDRef` 속성만 교체. 텍스트/run 무변경,
    header.xml 무수정. `expectedBefore`(문단 전체 텍스트) 불일치 시 거부.
  - 거부 사유: `TARGET_PARAPR_NOT_IN_HEADER`, `EXPECTED_BEFORE_MISMATCH`
- `scripts/hwpx/web_office/paragraph_save_verify7.py`
  - **V5_PARPR_PRESERVED 강화** — 기존 구현은 문단 존재/비어있음만 확인했고
    parPr 을 실제로 검증하지 않았다. 본 공정에서 실검증으로 교체:
    - `APPLY_PARA_FORMAT` 대상은 `afterParaPrIDRef == targetParaPrIDRef`
    - 그 id 는 **원본 header 의 paraPr id 집합에 존재**해야 함
    - 위반 시 `V5_PARAPR_TARGET_MISMATCH` / `V5_NEW_PARAPR_INTRODUCED`

## 4. 검증

| 계층 | 결과 |
|---|---|
| parPr 매처 단위 | 10/10 PASS (축 읽기·정렬 매칭·미존재 거부·타축 혼합 거부·후보목록) |
| 명령/상태 단위 | 12/12 PASS (적용·텍스트 불변·undo/redo 왕복·가드 4종) |
| 브라우저 | 정렬 버튼 현재값 표시, 매칭 부재 시 비활성 + 안내 |
| 백엔드 writer | 10/10 PASS (적용·산출물 반영·텍스트 불변·**header paraPr 집합 불변**·미존재 거부·expectedBefore 거부) |

핵심 확인: 저장된 HWPX 재로딩 시 문단 paraPr 이 의도값으로 바뀌고 텍스트는 동일,
header.xml 의 paraPr id 집합은 원본과 **완전 동일**(39개).

## 5. 알려진 제약 (KNOWN_HOLD)

- **정렬 변경 가능 비율은 문서에 의존**한다. 샘플 문서 기준 문단 76개 중 37개(49%)
  만 정렬 변경이 가능했다. "다른 축(줄간격·들여쓰기)이 완전히 동일한 paraPr" 이
  존재해야 매칭되기 때문이다. 이는 §4 준수의 대가이며 의도된 동작이다.
- 줄간격·들여쓰기 축은 매처에 구현되어 있으나 **UI 미노출**(정렬만 노출).
- 신규 paraPr 생성(header mutation)으로 100% 커버리지를 얻는 방안은 §4 핵심금지
  해제가 필요하므로 **본 공정 범위 밖**이며 별도 승인·검증 대상이다.
