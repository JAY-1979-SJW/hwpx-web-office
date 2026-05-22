# HWPX Direct Writer P11 Style and Layout Control

## 목적

HWPX composer job에서 문단, 표, 이미지의 기본 스타일/레이아웃 힌트를 받을 수 있게 한다.

이번 단계는 새 한컴 스타일 정의를 header에 생성하는 작업이 아니다. 기존 문서가 가진 style/paragraph/character/border reference를 재사용하고, direct writer가 안정적으로 적용할 수 있는 치수와 참조값만 우선 지원한다.

## 구현

### 추가 파일

- `scripts/hwpx/hwpx_style_ops.py`

### 수정 파일

- `scripts/hwpx/hwpx_element_factory.py`
- `scripts/hwpx/hwpx_text_ops.py`
- `scripts/hwpx/hwpx_table_ops.py`
- `scripts/hwpx/hwpx_writer_adapter.py`
- `scripts/hwpx/hwpx_composer.py`

## 지원 범위

### Paragraph

Composer paragraph job에서 아래 style reference를 지원한다.

```json
{
  "text": "Styled composer paragraph",
  "style": {
    "para_pr_id": 0,
    "char_pr_id": 0,
    "style_id": 0
  }
}
```

적용 결과:

- `paraPrIDRef`
- `styleIDRef`
- `charPrIDRef`

### Table

Composer table job에서 아래 layout/style hint를 지원한다.

```json
{
  "style": {
    "width": 36000,
    "row_height": 2200,
    "border_fill_id": 2,
    "repeat_header": true
  }
}
```

적용 결과:

- `tableWidth`
- `rowHeight`
- `borderFillIDRef`
- `repeatHeader`

### Image

기존 composer image job의 `width`, `height`, `section_index`를 `hwpx_style_ops.normalize_image_layout()`에서 검증/정규화하도록 분리했다.

## 테스트

### 입력

- job: `tmp\hwpx_modularization_check\compose_style_job.json`
- template: `tmp\hwpx_writer_poc\template_seed.hwpx`
- output: `tmp\hwpx_modularization_check\composed_style_document.hwpx`

### 실행

```powershell
python scripts/hwpx/hwpx_template_engine.py compose `
  --job-json tmp\hwpx_modularization_check\compose_style_job.json `
  --output tmp\hwpx_modularization_check\composed_style_document.hwpx `
  --report-json tmp\hwpx_modularization_check\compose_style_report.json
```

### 결과

| item | result |
| --- | --- |
| replace_placeholders | PASS |
| paragraph_add | GENERATED_PARAGRAPH_APPEND_PASS |
| paragraph style refs | paraPrIDRef/styleIDRef/charPrIDRef applied |
| table_create | GENERATED_TABLE_APPEND_PASS |
| table style refs | borderFillIDRef/tableWidth/rowHeight/repeatHeader applied |
| chart PNG insert | GENERATED_PNG_PICTURE_INSERT_PASS |
| ZIP validation | PASS |
| XML validation | PASS |
| placeholder remaining | false |
| missing expected values | [] |

Compose status는 WARN이다. 이유는 P8 이후 동일하게 generated picture XML이 한컴에서 생성된 객체가 아니라 direct writer synthetic XML이기 때문이다.

## Java Parser Roundtrip

대상:

- `tmp\hwpx_modularization_check\composed_style_document.hwpx`

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

- style/layout normalization: PASS
- paragraph style refs: PASS
- table layout/style refs: PASS
- image layout normalization: PASS
- ZIP/XML validation: PASS
- Java parser roundtrip: PASS
- full style definition creation: PENDING
- Hancom visual confirmation: PENDING

최종 판정: WARN

## 제한

- 글꼴명, 글자 크기, 색상, 정렬 등은 현재 새 header style definition 생성이 필요하므로 pending 처리한다.
- 복잡한 표 배경색/테두리/셀별 스타일은 후속 단계에서 header/borderFill definition 생성 모듈로 분리해야 한다.
- 한컴 시각 확인은 아직 수행하지 않았다.

## 다음 단계

1. P12: composer job schema validation
2. P13: header style definition builder
3. P14: cell-level table style and border fill generation
4. P15: document composer API layer
