# HWPX Editor API Contract

`/api/hwpx/editor` (multipart) → Python `hwpx_edit_tool.apply_edit_plan` 경로의 셀 입력 plan 키와 후처리 옵션 계약.

## 셀 입력 plan 키

| plan key | 좌표 기준 | 위치 식별 |
|---|---|---|
| `set_cells` | physical (`row`, `col`) | 직접 지정 |
| `set_cells_by_text` | physical | 셀 텍스트 검색 (`exact` / `contains` / `regex` / `text`) |
| `set_cells_by_label` | physical | 라벨 셀 검색 + `row_offset` / `col_offset` |
| `set_visual_cells` | visual (`visual_row`, `visual_col`) | 직접 지정 (병합 고려) |

각 plan key는 `value`(필수), `table`(또는 `table_index`), `clear_remaining`(기본 true) 외에 **공통 후처리 옵션**을 받는다.

## 공통 후처리 옵션 (HWPX-EDITOR-SHRINK-TO-FIT-OPTION-PROPAGATION-01 + HWPX-CELL-STYLE-POSTPROCESS-01)

옵션은 선택이며, **지정하지 않으면 기존 동작과 동일**하다.

| 옵션 | 타입 | 동작 |
|---|---|---|
| `shrink_to_fit` | bool | true이면 입력 직후 `shrink_table_visual_cell_text_to_fit`을 호출하여 셀 너비/마진/원본 폰트 높이를 분석한 후 들어맞는 목표 높이로 `charPr`을 **복제**(원본 보존)하고 해당 셀의 모든 `<hp:run>`에 새 `charPrIDRef`를 적용한다. 본문이 셀에 이미 들어가면 `FONT_SHRINK_NOT_NEEDED`로 no-op. |
| `vertical_align` | str | `"CENTER"` 등 한컴 vertAlign 값. `set_table_visual_cell_vertical_align` 호출. |
| `solid_fill` | `{"color": "D9EAF7"}` 또는 str | 셀 배경색 solid fill 적용. `ensure_solid_border_fill`로 동일 색상 borderFill 재사용 또는 신규 생성 후 셀 `borderFillIDRef` 변경. 원본 borderFill 정의 보존. |
| `fill_color` | str | `solid_fill`과 동일 (단축형). `"D9EAF7"` 또는 `"#D9EAF7"` 형식 모두 지원. |
| `preserve_border` | bool | solid_fill 적용 시 기존 테두리 속성 유지 (기본 동작 — 소스 borderFill을 복제하므로 항상 보존). |

### 공통 처리 규칙

1. 옵션은 plan item 단위로 지정. plan 전역 기본값은 없음.
2. 옵션을 지정하면 `apply_edit_plan` 결과 `operations` 배열에 후처리 op (`vertical_alignment`, `font_adjustment`) report가 추가됨.
3. `set_cells`는 physical 좌표를 visual 좌표로 변환한 뒤 후처리 호출 (내부 `_resolve_visual_coords`).
4. `set_cells_by_text` / `set_cells_by_label`는 매칭된 셀의 visual 좌표를 그대로 사용. label은 `row_offset` / `col_offset` 적용 후 변환.
5. 후처리는 입력 셀에만 적용되며 라벨 셀이나 다른 셀은 훼손하지 않는다.

### 예시

`set_cells` + 폰트 자동 조정:
```json
{
  "set_cells": [
    {"table": 1, "row": 0, "col": 1, "value": "매우 긴 공사명 텍스트",
     "shrink_to_fit": true, "vertical_align": "CENTER"}
  ]
}
```

`set_cells_by_label` + 폰트 자동 조정:
```json
{
  "set_cells_by_label": [
    {"table": 1, "contains": "공 사 명", "value": "긴 공사명",
     "row_offset": 0, "col_offset": 1, "shrink_to_fit": true}
  ]
}
```

`set_cells_by_text` + 폰트 자동 조정:
```json
{
  "set_cells_by_text": [
    {"table": 2, "contains": "기존문구", "value": "교체 문구",
     "shrink_to_fit": true}
  ]
}
```

`set_visual_cells` (기존부터 지원):
```json
{
  "set_visual_cells": [
    {"table": 3, "visual_row": 1, "visual_col": 7, "value": "긴 시공자명",
     "shrink_to_fit": true, "vertical_align": "CENTER"}
  ]
}
```

## 호환성

- 기존 plan(옵션 미지정)에는 영향 없음 — `_apply_cell_post_edit_options`는 옵션이 없으면 빈 리스트를 반환하고 helper 호출 자체가 발생하지 않는다.
- `shrink_to_fit` 호출은 새 `<hh:charPr>` 정의를 header.xml에 추가하지만 원본 `charPr` 정의는 그대로 보존되므로 다른 셀의 폰트는 변하지 않는다.
- mimetype ZIP_STORED 보존, `repair_for_server` 미경유, dangling 참조 없음 (header에 새 ID 등록 후 cell run에 적용).

## 독립 스타일 plan 키 (HWPX-CELL-STYLE-POSTPROCESS-01)

### `set_cell_styles`

값 입력 없이 스타일만 적용한다. 단일 셀 또는 범위 지정 가능.

```json
{
  "set_cell_styles": [
    {
      "table": 1,
      "visual_row": 2, "visual_col": 3,
      "solid_fill": {"color": "D9EAF7"},
      "vertical_align": "CENTER"
    },
    {
      "table": 1,
      "visual_row_start": 3, "visual_row_end": 3,
      "visual_col_start": 5, "visual_col_end": 10,
      "solid_fill": {"color": "92D050"}
    }
  ]
}
```

### `fill_schedule_bars`

공정표 막대 채우기용 헬퍼. 날짜축 자동 인식 없이 row / col 직접 지정.

```json
{
  "fill_schedule_bars": [
    {
      "table": 1,
      "task_row": 3,
      "start_col": 5, "end_col": 10,
      "color": "92D050",
      "text": "배관 설치",
      "text_at": "center",
      "shrink_to_fit": true
    }
  ]
}
```

- `text_at`: `"start"` / `"center"` / `"end"` (기본 `"center"`)
- 연속 셀 solid fill 후 지정 위치 셀에 텍스트 입력 (선택)

## 관련 함수

| 함수 | 위치 |
|---|---|
| `shrink_table_visual_cell_text_to_fit` | `scripts/hwpx/hwpx_table_ops.py` |
| `estimate_text_fit` | `scripts/hwpx/hwpx_table_ops.py` |
| `clone_char_pr_with_height` | `scripts/hwpx/hwpx_table_ops.py` |
| `set_table_visual_cell_vertical_align` | `scripts/hwpx/hwpx_table_ops.py` |
| `set_table_visual_cell_solid_fill` | `scripts/hwpx/hwpx_table_ops.py` |
| `ensure_solid_border_fill` | `scripts/hwpx/hwpx_table_ops.py` |
| `_apply_cell_post_edit_options` | `scripts/hwpx/hwpx_edit_tool.py` |
| `_resolve_visual_coords` | `scripts/hwpx/hwpx_edit_tool.py` |
| `style_postprocess_verifier` | `scripts/hwpx/pipeline/style_postprocess_verifier.py` |

## 회귀 테스트

`tests/test_hwpx_shrink_to_fit_plan_options.py` — 4개 plan 키 + 옵션 누락 시 기존 동작 + charPr 원본 보존 + mimetype ZIP_STORED + dangling 없음 등 8개 케이스.

## 감사 스크립트

`scripts/ops/audit_hwpx_shrink_to_fit_plan_options.py` — 정적 감사로 4개 plan 키가 모두 helper를 호출하는지, 테스트가 존재하는지, 계약 문서가 갱신됐는지 검사.
