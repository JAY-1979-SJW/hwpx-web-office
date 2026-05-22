# HWPX Direct Writer P21 Cell Layout Operations

## 목적

P20에서 생성 표의 셀 레이아웃 style refs를 구현한 뒤, 이번 P21에서는 기존 HWPX 표의 특정 셀 레이아웃을 `table-op`으로 직접 변경하는 기능을 추가했다.

## 구현

- `hwpx_table_cell_layout_ops.py`를 추가해 기존 표 셀 레이아웃 mutation을 분리했다.
- `HwpxEditor` facade에 `set_cell_layout`을 추가했다.
- `table-op` 실행기가 `set_cell_layout` operation을 처리하도록 확장했다.
- schema validation이 `set_cell_layout`의 `row_index`, `col_index`, `layout`을 검증한다.

## Operation 예

```json
{
  "operations": [
    {
      "op": "set_cell_layout",
      "table_index": 0,
      "row_index": 1,
      "col_index": 1,
      "layout": {
        "cell_vertical_align": "BOTTOM",
        "cell_text_direction": "VERTICAL",
        "cell_line_wrap": "SQUEEZE",
        "cell_margin": {"left": 1300, "right": 1100, "top": 500, "bottom": 450}
      }
    }
  ]
}
```

## 테스트

| 항목 | 결과 |
| --- | --- |
| base table compose | PASS |
| set_cell_layout | PASS |
| ZIP/XML validation | PASS |
| XML attribute inspection | PASS |
| Java parser roundtrip | PASS |
| CELL_NOT_FOUND failure case | PASS |

## XML 검증 결과

대상 셀 `row=1`, `col=1`:

| 속성 | 결과 |
| --- | --- |
| `vertAlign` | `BOTTOM` |
| `textDirection` | `VERTICAL` |
| `lineWrap` | `SQUEEZE` |
| `cellMargin.left` | `1300` |
| `cellMargin.right` | `1100` |
| `cellMargin.top` | `500` |
| `cellMargin.bottom` | `450` |

## Java Parser Roundtrip

| 항목 | 결과 |
| --- | --- |
| parse_status | PASS |
| paragraph_count | 2 |
| table_count | 1 |
| diagnostics_exists | true |
| quality_score | 7 |
| warning_count | 0 |
| error_count | 0 |

## 제한

- 현재는 셀 단위 레이아웃 변경이다.
- 행/열 범위 단위 bulk layout operation은 아직 구현하지 않았다.
- 한컴 GUI 시각 확인은 수행하지 않았다.

## 결론

P21은 PASS다. HWPX direct writer는 기존 표의 특정 셀 레이아웃을 변경하고, ZIP/XML 및 Java parser roundtrip을 통과했다.

## 다음 단계

1. P22: 행/열/range bulk layout operation
2. P23: 페이지/섹션 레이아웃
3. P24: 목록/번호 매기기
