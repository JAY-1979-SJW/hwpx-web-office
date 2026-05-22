# HWPX Direct Writer P2.5 Table Operations PoC

## 목적

HWPX direct writer/editor의 표 기능을 기존 표 셀 치환에서 행 추가/삭제와 표 조작으로 확장했다.

이 작업은 HWPX ZIP/XML을 직접 수정하는 PoC이며, 한컴 프로그램, COM, GUI, HWP 변환은 사용하지 않았다.

## 현재까지의 기준

```text
HWPX ZIP/XML 읽기 = PASS
placeholder 치환 = PASS
기존 표 셀 텍스트 수정 = PASS
HWPX 재저장 = PASS
Java HwpxParser roundtrip = PASS
```

## 구현

수정 파일:

```text
scripts/hwpx/hwpx_writer_adapter.py
scripts/hwpx/hwpx_template_engine.py
```

추가한 adapter 기능:

```text
find_tables()
get_table_cells(table_index)
update_table_cells(table_index, values)
append_table_row(table_index, row_values)
delete_table_row(table_index, row_index)
clone_table(table_index)
```

추가한 CLI:

```text
python scripts/hwpx/hwpx_template_engine.py table-op
```

CLI 예:

```powershell
python scripts/hwpx/hwpx_template_engine.py table-op `
  --template "tmp\hwpx_writer_poc\table_updated.hwpx" `
  --output "tmp\hwpx_table_ops_poc\table_ops_result_unicode.hwpx" `
  --ops-json "tmp\hwpx_table_ops_poc\table_ops_unicode.json" `
  --validate `
  --report-json "tmp\hwpx_table_ops_poc\table_ops_report_unicode.json"
```

## 테스트 입력

최종 성공 테스트는 아래 작업 순서로 수행했다.

```json
{
  "operations": [
    {
      "op": "update_cells",
      "table_index": 0,
      "values": ["수정항목", "수정값"],
      "clear_remaining_cells": false
    },
    {
      "op": "append_row",
      "table_index": 0,
      "values": ["추가항목", "추가값"],
      "clear_remaining_cells": true
    },
    {
      "op": "delete_row",
      "table_index": 0,
      "row_index": 1
    }
  ]
}
```

설명:

```text
1. 첫 번째 표의 앞쪽 셀 2개를 수정
2. 마지막 행을 clone해서 새 행 1개 추가
3. 기존 데이터 행 row_index=1 삭제
4. header row 삭제는 기본 차단
```

## Table-op 결과

출력:

```text
tmp/hwpx_table_ops_poc/table_ops_result_unicode.hwpx
tmp/hwpx_table_ops_poc/table_ops_report_unicode.json
```

결과 요약:

```text
status = PASS
initial table_count = 1
initial row_count = 2
update_cells = PASS
append_row = APPEND_ROW_PASS
delete_row = DELETE_ROW_PASS
final table_count = 1
final row_count = 2
final text_node_count = 4
ZIP/XML validation = PASS
placeholder_remaining = false
missing_expected_values = []
```

검증된 최종 값:

```text
수정항목
수정값
추가항목
추가값
```

삭제된 기존 데이터 행:

```text
공사명
테스트 소방공사
입찰마감일
2026-05-15
낙찰방법
제한최저가
```

`delete_row` 결과의 `removed_text`에 위 값들이 기록됐다.

## Java Parser Roundtrip

대상:

```text
tmp/hwpx_table_ops_poc/table_ops_result_unicode.hwpx
```

임시 runner:

```text
tmp/hwpx_table_ops_poc/JavaTableOpsRoundtrip.java
```

결과:

```text
tmp/hwpx_table_ops_poc/java_roundtrip_result.json
tmp/hwpx_table_ops_poc/java_roundtrip_result.csv
```

검증 결과:

| 항목 | 결과 |
| --- | --- |
| parse_status | PASS |
| paragraph_count | 5 |
| table_count | 1 |
| semantic_sections_count | 1 |
| extracted_fields_count | 1 |
| diagnostics_exists | true |
| quality_score | 20 |
| missing_expected_values | [] |
| deleted_table_values_absent | true |

판정:

```text
Java parser roundtrip = PASS
추가/수정 값 확인 = PASS
삭제된 표 데이터 미존재 확인 = PASS
```

주의:

Java console 출력에는 기존 P1/P2와 동일하게 일부 mojibake와 Log4j RollingFileAppender 권한 경고가 발생했다. 결과 JSON 기준으로 parse와 expected-value 검증은 PASS다.

## Failure Cases

### Case A: 없는 table_index

입력:

```json
{
  "operations": [
    {
      "op": "update_cells",
      "table_index": 999,
      "values": ["X"]
    }
  ]
}
```

결과:

```text
status = FAIL
operation status = TABLE_NOT_FOUND
ZIP/XML validation = PASS
report JSON 생성 = PASS
```

### Case B: header row 삭제 요청

입력:

```json
{
  "operations": [
    {
      "op": "delete_row",
      "table_index": 0,
      "row_index": 0
    }
  ]
}
```

결과:

```text
status = WARN
operation status = HEADER_ROW_DELETE_BLOCKED
ZIP/XML validation = PASS
report JSON 생성 = PASS
```

## 제한

이번 P2.5는 기존 표 XML 구조를 clone/수정하는 방식이다.

아직 하지 않은 것:

```text
병합 셀 신규 생성
복잡한 테두리/배경 스타일 생성
표 너비/높이 재계산
한컴 native table style 생성
완전 신규 표 생성
```

또한 append row는 기존 마지막 행을 clone하므로, 원본 표 구조가 복잡하면 스타일/셀 구조도 그대로 복제된다. 이는 의도된 template-first 전략이다.

## 결론

P2.5 판정은 PASS다.

```text
기존 표 구조 읽기 = PASS
기존 표 셀 수정 = PASS
행 추가 = PASS
행 삭제 = PASS
ZIP/XML validation = PASS
Java parser roundtrip = PASS
failure case report = PASS
```

이제 HWPX direct writer는 기존 표에 대해 읽기, 셀 수정, 행 추가, 행 삭제까지 가능한 상태다.

## 다음 단계

1. P3: 이미지 포함 템플릿 BinData 교체
2. P4: 그래프 PNG 생성 후 이미지 삽입
3. P5: HWPX 문서 작성 API화
