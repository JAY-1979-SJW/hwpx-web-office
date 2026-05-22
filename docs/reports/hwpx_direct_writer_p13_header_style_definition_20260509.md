# HWPX Direct Writer P13 Header Style Definition Builder

## 목적

P11에서는 기존 style reference만 재사용했다. P13에서는 HWPX `Contents/header.xml`에 새 `charPr` / `paraPr` 정의를 생성하고, 생성 문단이 그 새 정의를 참조하도록 연결한다.

이번 단계도 한컴 실행 없이 HWPX ZIP/XML을 직접 수정한다.

## 구현

### 추가 파일

- `scripts/hwpx/hwpx_header_style.py`

### 수정 파일

- `scripts/hwpx/hwpx_composer.py`
- `scripts/hwpx/hwpx_job_schema.py`
- `scripts/hwpx/hwpx_style_ops.py`

## 모듈화

### `hwpx_header_style.py`

역할:

- `Contents/header.xml` 로드
- `charProperties`의 기존 `charPr` clone
- 새 `charPr` ID 생성
- 글자 크기, 색상, bold 적용
- `paraProperties`의 기존 `paraPr` clone
- 새 `paraPr` ID 생성
- 정렬, 줄간격 적용
- header item count 갱신
- style name → ID map 반환

### `hwpx_composer.py`

역할:

- job의 `style_definitions`를 먼저 header에 적용
- paragraph style의 `char_style` / `para_style` 이름을 새 ID reference로 변환
- 생성 문단에 `charPrIDRef` / `paraPrIDRef` 적용

### `hwpx_job_schema.py`

역할:

- `style_definitions.char_styles`
- `style_definitions.para_styles`
- paragraph style name reference 검증

## Job 예시

```json
{
  "style_definitions": {
    "char_styles": {
      "emphasis_blue": {
        "height": 1400,
        "text_color": "#1F5FBF",
        "bold": true
      }
    },
    "para_styles": {
      "center_130": {
        "align": "CENTER",
        "line_spacing": 130
      }
    }
  },
  "paragraphs": [
    {
      "text": "Header style generated paragraph",
      "style": {
        "char_style": "emphasis_blue",
        "para_style": "center_130"
      }
    }
  ]
}
```

## 테스트

### 입력

- job: `tmp\hwpx_modularization_check\compose_header_style_job.json`
- template: `tmp\hwpx_writer_poc\template_seed.hwpx`
- output: `tmp\hwpx_modularization_check\composed_header_style_document.hwpx`

### 실행

```powershell
python scripts/hwpx/hwpx_template_engine.py compose `
  --job-json tmp\hwpx_modularization_check\compose_header_style_job.json `
  --output tmp\hwpx_modularization_check\composed_header_style_document.hwpx `
  --report-json tmp\hwpx_modularization_check\compose_header_style_report.json
```

## 결과

### Schema

- status: PASS
- errors: []
- warnings: []

### Header style definitions

| item | result |
| --- | --- |
| char style `emphasis_blue` | charPrIDRef `14` |
| para style `center_130` | paraPrIDRef `17` |
| header write | PASS |

### Section references

| item | result |
| --- | --- |
| generated paragraph `charPrIDRef` | `14` |
| generated paragraph `paraPrIDRef` | `17` |
| run refs found | 1 |
| paragraph refs found | 1 |

### Validation

| item | result |
| --- | --- |
| compose status | PASS |
| ZIP validation | PASS |
| XML validation | PASS |
| placeholder remaining | false |
| missing expected values | [] |

## Java Parser Roundtrip

대상:

- `tmp\hwpx_modularization_check\composed_header_style_document.hwpx`

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

- header charPr definition: PASS
- header paraPr definition: PASS
- generated paragraph references: PASS
- ZIP/XML validation: PASS
- Java parser roundtrip: PASS

최종 판정: PASS

## 제한

- font face 신규 등록은 아직 미구현이다.
- 완전한 named style(`hh:style`) 생성은 아직 미구현이다.
- 셀 배경색/테두리 색상은 P14 borderFill builder에서 처리한다.
- 한컴 시각 확인은 아직 수행하지 않았다.

## 다음 단계

1. P14: borderFill and cell-level table style generation
2. P15: named style creation
3. P16: composer API layer
