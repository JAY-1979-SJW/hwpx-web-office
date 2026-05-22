# HWPX Direct Writer P5 Generated Table Builder

## 목적

P2.5에서는 기존 표를 수정하거나 기존 행을 clone해 행을 추가/삭제했다.

이번 P5 목표는 기존 표를 clone하지 않고, 최소 HWPX 표 XML을 직접 생성해 section에 삽입하는 것이다.

## 구현

### 확장 모듈

```text
scripts/hwpx/hwpx_element_factory.py
```

추가 함수:

```text
create_cell_paragraph
create_table_cell
create_generated_table
create_table_paragraph
append_generated_table
```

### 연결 모듈

```text
scripts/hwpx/hwpx_table_ops.py
scripts/hwpx/hwpx_writer_adapter.py
scripts/hwpx/hwpx_template_engine.py
```

추가 CLI:

```text
python scripts/hwpx/hwpx_template_engine.py table-create
```

## 생성 구조

P5 generated table은 아래 최소 구조를 직접 생성한다.

```text
p
└─ run
   └─ tbl
      ├─ sz
      ├─ pos
      ├─ outMargin
      ├─ inMargin
      └─ tr
         └─ tc
            ├─ subList
            │  └─ p
            │     └─ run
            │        └─ t
            ├─ cellAddr
            ├─ cellSpan
            ├─ cellSz
            └─ cellMargin
└─ linesegarray
```

이번 단계에서는 병합 셀, 복잡한 border/fill 스타일, 행/열 크기 정밀 계산은 제외한다.

## 테스트

입력:

```text
tmp/hwpx_modularization_check/generated_table_rows.json
```

내용:

```text
항목 | 값 | 비고
공사명 | P5 생성 표 공사 | 직접 생성
입찰마감일 | 2026-05-15 | 검증
```

실행:

```text
python scripts/hwpx/hwpx_template_engine.py table-create \
  --template tmp\hwpx_writer_poc\template_seed.hwpx \
  --output tmp\hwpx_modularization_check\generated_table.hwpx \
  --rows-json tmp\hwpx_modularization_check\generated_table_rows.json \
  --validate \
  --report-json tmp\hwpx_modularization_check\generated_table_report.json
```

결과:

```text
status: PASS
add_result.status: GENERATED_TABLE_APPEND_PASS
entry: Contents/section0.xml
paragraph_id: 2147483649
row_count: 3
col_count: 3
zip_ok: true
xml_ok: true
missing_expected_values: []
```

추가 validate:

```text
python scripts/hwpx/hwpx_template_engine.py validate \
  --input tmp\hwpx_modularization_check\generated_table.hwpx \
  --report-json tmp\hwpx_modularization_check\generated_table_validate_report.json
```

결과:

```text
status: PASS
zip_ok: true
xml_ok: true
```

## 판정

P5 generated table builder 판정: `PASS`

의미:

```text
기존 표 clone 없이 rows x cols 표 XML을 직접 생성할 수 있다.
```

## 제한

아직 후속:

```text
병합 셀
표 스타일/테두리/배경 세부 제어
행 높이/열 너비 자동 계산
한컴 시각 확인
Java parser table_count roundtrip
```

## 다음 단계

1. P6: Java parser roundtrip for generated paragraph/table
2. P7: style resolver for paragraph/table defaults
3. P8: visible picture template 확보 후 clone/rebind 성공 케이스
4. P9: DocumentBuilder API layer
