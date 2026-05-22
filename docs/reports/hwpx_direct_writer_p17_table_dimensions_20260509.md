# HWPX Direct Writer P17 Table Dimensions

## 목적

생성 표에서 열별 너비와 행별 높이를 직접 제어할 수 있도록 했다.

P14~P16에서 표 색상/테두리/셀별 스타일을 다뤘고, P17은 표 레이아웃의 기본 치수 제어를 모듈화한 단계다.

## 구현

- `scripts/hwpx/hwpx_table_dimension_style.py` 추가
  - `column_widths` 정규화
  - `row_heights` 정규화
  - `tableWidth` 자동 합산
  - 잘못된 값에 대한 warning 생성
- `scripts/hwpx/hwpx_element_factory.py`
  - generated table 생성 시 열별 `cellSz.width` 적용
  - 행별 `cellSz.height` 적용
  - table `sz.width`는 열 너비 합계
  - table `sz.height`는 행 높이 합계
- `scripts/hwpx/hwpx_composer.py`
  - dimension style refs를 compose flow에 연결
- `scripts/hwpx/hwpx_job_schema.py`
  - `column_widths`, `row_heights` list validation 추가
- `scripts/hwpx/hwpx_style_ops.py`
  - table style 지원 키에 `column_widths`, `row_heights` 추가

## 테스트

입력:

```text
column_widths: [12000, 18000, 9000]
row_heights: [3200, 2400, 3600]
```

실행:

```text
validate-job: PASS
compose: PASS
ZIP/XML validation: PASS
Java HwpxParser roundtrip: PASS
```

## XML 검증 결과

생성 table:

```text
table width: 39000
table height: 9200
```

셀 크기:

```text
row 0 widths: 12000, 18000, 9000
row 1 widths: 12000, 18000, 9000
row 2 widths: 12000, 18000, 9000

row 0 heights: 3200, 3200, 3200
row 1 heights: 2400, 2400, 2400
row 2 heights: 3600, 3600, 3600
```

Java parser:

```text
parse_status: PASS
paragraph_count: 9
table_count: 3
semantic_sections_count: 4
diagnostics_exists: true
quality_score: 39
error_count: 0
```

## 제한

- 한컴 GUI 시각 확인은 하지 않았다.
- 기존 표 수정 경로(`table-op`)에는 아직 dimension 변경을 적용하지 않는다.
- 열 너비 합계가 페이지 폭을 넘는지에 대한 layout guard는 아직 없다.
- 병합 셀에서의 width/height 계산은 후속이다.

## 결론

P17 판정: PASS

HWPX direct writer는 이제 generated table에 대해 열별 width와 행별 height를 직접 제어할 수 있다. 표 스타일, 셀 스타일, 좌표별 override, 치수 제어가 모두 모듈화된 상태다.

## 다음 단계

1. P18: merged cell structure PoC
2. P19: table style preset catalog
3. P20: composer API layer 정리
4. P21: generated document smoke set
