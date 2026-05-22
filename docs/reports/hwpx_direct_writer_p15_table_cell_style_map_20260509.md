# HWPX Direct Writer P15 Table Cell Style Map

## 목적

P14에서 생성한 `borderFill` 정의를 표 전체에 적용하는 수준에서 확장해, 생성 표의 헤더 행과 본문 행 셀에 서로 다른 `borderFillIDRef`를 적용했다.

이번 단계도 한컴 실행 없이 HWPX ZIP/XML을 직접 생성/수정하는 방식으로 수행했다.

## 구현

- `scripts/hwpx/hwpx_table_cell_style.py` 추가
  - `header_border_fill_style`
  - `body_border_fill_style`
  - `cell_border_fill_style`
  - 위 이름을 `style_definitions.border_fills`에서 생성된 ID로 매핑
- `scripts/hwpx/hwpx_element_factory.py`
  - generated table cell 생성 시 row index 기준으로 셀 `borderFillIDRef` 선택
  - header row는 `headerBorderFillIDRef`
  - body row는 `bodyBorderFillIDRef`
  - fallback은 기존 `borderFillIDRef`
  - repeat header가 켜진 첫 행 cell에는 `header="1"` 설정
- `scripts/hwpx/hwpx_composer.py`
  - table style name mapping을 compose flow에 연결
- `scripts/hwpx/hwpx_job_schema.py`
  - unresolved `header_border_fill_style`, `body_border_fill_style`, `cell_border_fill_style` warning 추가
- `scripts/hwpx/hwpx_style_ops.py`
  - cell-level style key를 지원 키로 분리

## 테스트

입력 job은 세 개의 borderFill을 정의했다.

```text
table_outline_blue -> table borderFillIDRef
header_blue_fill   -> header row cell borderFillIDRef
body_yellow_fill   -> body row cell borderFillIDRef
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
table_outline_blue: id 6, fill #FFFFFF
header_blue_fill:   id 7, fill #DDEBFF
body_yellow_fill:   id 8, fill #FFF7D6
```

생성 table/cell 참조:

```text
table borderFillIDRef: 6
header row cell refs: 7, 7
body row cell refs: 8, 8, 8, 8
header cell flags: 1, 1
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
- 개별 셀 주소별 스타일 지정은 아직 없다.
- 열 단위/행 단위 style map은 아직 없다.
- 병합 셀과 복합 테두리 스타일은 후속 단계다.

## 결론

P15 판정: PASS

생성 표에서 table-level, header-row cell-level, body-row cell-level `borderFillIDRef`를 분리 적용할 수 있게 됐다. HWPX 문서 작성 엔진에서 표 헤더와 본문을 시각적으로 구분할 수 있는 기반이 마련됐다.

## 다음 단계

1. P16: cell address 기반 style map
2. P17: column width / row height 세부 제어
3. P18: merged cell 구조 PoC
4. P19: composer API layer 정리
