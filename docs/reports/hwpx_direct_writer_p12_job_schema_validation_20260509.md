# HWPX Direct Writer P12 Job Schema Validation

## 목적

HWPX composer가 지원하는 기능이 늘어나면서 job JSON 입력을 실행 전에 엄격히 검증하는 schema validation 계층이 필요해졌다.

이번 단계는 기능 실행 로직을 CLI에 직접 추가하지 않고, 전용 모듈 `hwpx_job_schema.py`로 분리해 composer와 CLI가 동일한 검증 결과를 사용하도록 만든다.

## 구현

### 추가 파일

- `scripts/hwpx/hwpx_job_schema.py`

### 수정 파일

- `scripts/hwpx/hwpx_composer.py`
- `scripts/hwpx/hwpx_template_engine.py`

## 모듈화

### `hwpx_job_schema.py`

역할:

- compose job JSON 구조 검증
- template/output/mapping/expected_values 검증
- paragraphs/tables/table_operations/images 검증
- style/layout warning 수집
- 외부 파일 존재 확인 옵션 지원
- machine-readable schema report 생성

### `hwpx_composer.py`

역할:

- 실행 전 schema validation 호출
- schema FAIL이면 package mutation 없이 FAIL report 반환
- schema report를 compose report에 포함

### `hwpx_template_engine.py`

역할:

- `validate-job` CLI 추가
- composer와 같은 schema validator 호출

## CLI

```powershell
python scripts/hwpx/hwpx_template_engine.py validate-job `
  --job-json tmp\hwpx_modularization_check\compose_style_job.json `
  --require-template-exists `
  --require-external-files `
  --report-json tmp\hwpx_modularization_check\validate_style_job_report.json
```

## 검증 범위

### 지원 이미지 mode

- `png_insert`
- `chart_png`

### 지원 table operation

- `inspect`
- `update_cells`
- `append_row`
- `delete_row`
- `clone_table`

### 검증 항목

- job root object 여부
- template 필수 여부
- mapping object 여부
- paragraphs list 여부
- paragraph text 필수 여부
- tables rows list 여부
- table_operations op 지원 여부
- images mode 지원 여부
- png_insert path 필수 여부
- chart_png chart/chart_json 필수 여부
- external file 존재 여부

## 테스트

### Valid job

대상:

- `tmp\hwpx_modularization_check\compose_style_job.json`

결과:

| item | result |
| --- | --- |
| schema status | PASS |
| errors | [] |
| warnings | [] |
| paragraphs | 1 |
| tables | 1 |
| table_operations | 0 |
| images | 1 |

### Invalid job

대상:

- `tmp\hwpx_modularization_check\invalid_compose_job.json`

결과:

| error | result |
| --- | --- |
| TEMPLATE_REQUIRED | PASS |
| PARAGRAPHS_NOT_LIST | PASS |
| TABLE_ROWS_INVALID | PASS |
| IMAGE_MODE_UNSUPPORTED | PASS |

### Compose integration

대상:

- `tmp\hwpx_modularization_check\compose_style_job.json`
- output: `tmp\hwpx_modularization_check\composed_style_schema_document.hwpx`

결과:

- schema: PASS
- compose: WARN
- ZIP/XML validation: PASS
- placeholder remaining: false
- missing expected values: []

Compose status가 WARN인 이유는 기존과 동일하게 synthetic picture XML의 한컴 시각 확인이 아직 pending이기 때문이다.

## Java Parser Roundtrip

대상:

- `tmp\hwpx_modularization_check\composed_style_schema_document.hwpx`

결과:

| item | result |
| --- | --- |
| parse_status | PASS |
| paragraph_count | 6 |
| table_count | 2 |
| semantic_sections_count | 2 |
| extracted_fields_count | 1 |
| diagnostics_exists | true |
| quality_score | 28 |
| warning_count | 0 |
| error_count | 0 |

## 판정

- job schema module: PASS
- validate-job CLI: PASS
- invalid case reporting: PASS
- compose integration: PASS
- Java parser roundtrip: PASS

최종 판정: PASS

## 다음 단계

1. P13: header style definition builder
2. P14: cell-level table style and border fill generation
3. P15: document composer API layer
