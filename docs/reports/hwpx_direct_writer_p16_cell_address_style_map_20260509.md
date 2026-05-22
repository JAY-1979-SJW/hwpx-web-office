# HWPX Direct Writer P16 Cell Address Style Map

## 목적

P15의 header/body row 단위 셀 스타일에서 한 단계 더 확장해, 생성 표의 특정 셀 좌표별로 `borderFillIDRef`를 지정할 수 있게 했다.

이번 단계도 한컴 실행 없이 HWPX ZIP/XML을 직접 생성하고 Java parser로 roundtrip 검증했다.

## 구현

- `scripts/hwpx/hwpx_table_cell_address_style.py` 추가
  - `cell_border_fill_map` 처리
  - 지원 주소 형식:
    - `row,col`
    - `row:col`
    - `r{row}c{col}`
  - style name을 생성된 `borderFillIDRef`로 변환
- `scripts/hwpx/hwpx_element_factory.py`
  - cell 생성 시 특정 좌표 style map을 최우선 적용
  - 우선순위:
    1. `cellBorderFillIDRefMap[row,col]`
    2. header row `headerBorderFillIDRef`
    3. body row `bodyBorderFillIDRef`
    4. table/default `borderFillIDRef`
- `scripts/hwpx/hwpx_composer.py`
  - cell address style map을 compose flow에 연결
- `scripts/hwpx/hwpx_job_schema.py`
  - invalid cell address warning
  - unresolved cell style warning
- `scripts/hwpx/hwpx_style_ops.py`
  - `cell_border_fill_map`을 지원 키로 분리

## 테스트

입력 job:

```text
header_blue_fill -> header row
body_yellow_fill -> body row
alert_red_fill   -> cell 1,1
ok_green_fill    -> cell r2c1
```

실행 결과:

```text
validate-job: PASS
compose: PASS
ZIP/XML validation: PASS
Java HwpxParser roundtrip: PASS
```

## XML 검증 결과

생성된 borderFill:

```text
6: #DDEBFF
7: #FFF7D6
8: #FFE1E1
9: #E5F8E8
```

생성 table cell refs:

```text
0,0 -> 6
0,1 -> 6
1,0 -> 7
1,1 -> 8
2,0 -> 7
2,1 -> 9
```

검증:

```text
header default refs: PASS
body default refs: PASS
cell address override: PASS
```

Java parser:

```text
parse_status: PASS
paragraph_count: 9
table_count: 3
semantic_sections_count: 5
diagnostics_exists: true
quality_score: 40
error_count: 0
```

## 제한

- 주소는 zero-based row/column 기준이다.
- 기존 표 조작(`table-op`)의 기존 표 셀에는 아직 적용하지 않는다.
- 병합 셀의 spanning address 해석은 후속이다.
- 한컴 GUI 시각 확인은 하지 않았다.

## 결론

P16 판정: PASS

생성 표에서 헤더/본문 기본 스타일 위에 특정 셀 좌표별 스타일 override를 적용할 수 있게 됐다. 이제 HWPX direct writer는 표 전체, 행 역할, 개별 셀 단위까지 `borderFill` 스타일을 제어할 수 있다.

## 다음 단계

1. P17: column width / row height 세부 제어
2. P18: merged cell structure PoC
3. P19: paragraph/table style presets
4. P20: composer API layer 정리
