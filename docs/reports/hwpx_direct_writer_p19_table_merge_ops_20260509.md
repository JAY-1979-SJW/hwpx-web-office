# HWPX Direct Writer P19 Table Merge Operations

## 목적

P18에서 생성 표의 병합 셀 구조를 지원한 뒤, 이번 P19에서는 기존 HWPX 표를 직접 조작하는 `table-op` 경로에 병합/병합 해제 기능을 추가했다.

## 구현

- `hwpx_table_merge_ops.py`를 추가해 기존 표 병합/병합 해제 로직을 분리했다.
- `HwpxEditor` facade에 `merge_table_cells`, `unmerge_table_cell`을 추가했다.
- `table-op` 실행기가 `merge_cells`, `unmerge_cell` operation을 처리하도록 확장했다.
- compose job schema가 병합 operation의 `row_index`, `col_index`, `row_span`, `col_span`을 검증한다.

## Operation 예

```json
{
  "operations": [
    {
      "op": "merge_cells",
      "table_index": 0,
      "row_index": 1,
      "col_index": 0,
      "row_span": 2,
      "col_span": 2
    }
  ]
}
```

```json
{
  "operations": [
    {
      "op": "unmerge_cell",
      "table_index": 0,
      "row_index": 1,
      "col_index": 0
    }
  ]
}
```

## 테스트

| 항목 | 결과 |
| --- | --- |
| base table compose | PASS |
| merge_cells | PASS |
| unmerge_cell | PASS |
| ZIP/XML validation | PASS |
| Java parser roundtrip merged | PASS |
| Java parser roundtrip unmerged | PASS |
| ROW_NOT_FOUND failure case | PASS |
| UNMERGE_NOOP warning case | PASS |

## XML 구조 검증

### 병합 결과

- `rowCnt=3`
- `colCnt=3`
- generated cell count: 6
- anchor: `row=1`, `col=0`
- span: `rowSpan=2`, `colSpan=2`
- covered cells removed: `1,1`, `2,0`, `2,1`

### 병합 해제 결과

- `rowCnt=3`
- `colCnt=3`
- generated cell count: 9
- anchor span restored to `1x1`
- generated cells: `1,1`, `2,0`, `2,1`
- generated covered cells are empty by default
- row-local cell order is sorted by `colAddr`

## Java Parser Roundtrip

| 파일 | parse_status | table_count | diagnostics | quality_score |
| --- | --- | ---: | --- | ---: |
| merged_table.hwpx | PASS | 1 | true | 7 |
| unmerged_table.hwpx | PASS | 1 | true | 7 |

## 제한

- 병합 시 covered cell의 텍스트는 anchor로 자동 합치지 않는다.
- 병합 해제 시 복원된 covered cell 텍스트는 빈 값으로 생성한다.
- 복잡한 병합 패턴의 시각적 검증은 아직 한컴 GUI에서 수행하지 않았다.

## 결론

P19는 PASS다. HWPX direct writer는 생성 표뿐 아니라 기존 표 XML에 대해서도 병합/병합 해제 operation을 수행하고, ZIP/XML 및 Java parser roundtrip을 통과했다.

## 다음 단계

1. P20: 셀 정렬/여백/vertical align 확장
2. P21: 페이지/섹션 레이아웃
3. P22: 목록/번호 매기기
