# HWPX Direct Writer P18 Merged Cells

## 목적

HWPX direct writer의 생성 표 기능에 병합 셀 구조를 추가했다. 이번 단계는 한컴 실행 없이 `section.xml`의 표 셀 주소와 `cellSpan`을 직접 구성해, 기존 ZIP/XML 검증과 Java `HwpxParser` roundtrip까지 통과하는지 확인하는 작업이다.

## 구현

- `hwpx_table_merge_style.py`를 추가해 병합 셀 스타일을 별도 모듈로 분리했다.
- composer는 table style의 `merged_cells`를 `mergedCells` / `coveredCells` factory refs로 변환한다.
- element factory는 병합 anchor cell에 `hp:cellSpan`을 설정하고, 병합으로 덮인 cell은 생성하지 않는다.
- 병합 셀의 width/height는 span 범위의 column width / row height 합산값으로 설정한다.
- schema validation은 `merged_cells` 배열, `row`, `col`, `row_span`, `col_span` 값을 검증한다.

## 입력 예

```json
{
  "style": {
    "column_widths": [10000, 14000, 12000],
    "row_heights": [3000, 2400, 2400],
    "merged_cells": [
      {"row": 0, "col": 0, "row_span": 1, "col_span": 3},
      {"row": 1, "col": 0, "row_span": 2, "col_span": 1}
    ]
  }
}
```

## 테스트

- job validation: PASS
- compose: PASS
- ZIP/XML validation: PASS
- XML structure inspection: PASS
- Java `HwpxParser` roundtrip: PASS

## XML 검증 결과

| 항목 | 결과 |
| --- | --- |
| rowCnt | 3 |
| colCnt | 3 |
| generated cell count | 6 |
| covered cells omitted | `0,1`, `0,2`, `2,0` |
| header merge | `rowSpan=1`, `colSpan=3` |
| vertical merge | `rowSpan=2`, `colSpan=1` |
| header width | 36000 |
| vertical cell height | 4800 |

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

- 이번 단계는 생성 표의 병합 셀 구조 PoC다.
- 기존 문서에 있는 표를 병합하거나 병합 해제하는 기능은 아직 구현하지 않았다.
- 복잡한 병합 셀의 시각적 스타일 조정은 후속 단계로 둔다.
- 한컴 GUI 시각 확인은 수행하지 않았다.

## 결론

P18은 PASS다. HWPX direct writer는 생성 표에서 병합 셀 anchor/covered cell 구조를 만들고, ZIP/XML 및 Java parser roundtrip까지 통과했다.

## 다음 단계

1. P19: 기존 표 병합/병합 해제 table operation
2. P20: 표 정렬/셀 여백/vertical align 확장
3. P21: 섹션/페이지 레이아웃 생성 옵션
