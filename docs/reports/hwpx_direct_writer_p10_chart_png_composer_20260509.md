# HWPX Direct Writer P10 Chart PNG Composer

## 목적

한컴 실행 없이 그래프 이미지를 생성하고, HWPX composer job에서 PNG 그림으로 삽입하는 도구 단계를 구현한다.

이번 단계는 한컴 native chart 객체 생성이 아니다. HWPX 내부에 표시 가능한 PNG 그림 객체를 넣는 기존 파이프라인을 재사용해, 차트/그래프를 이미지 기반으로 문서에 포함하는 방식이다.

## 구현

### 추가 파일

- `scripts/hwpx/hwpx_chart_png.py`

### 수정 파일

- `scripts/hwpx/hwpx_composer.py`
- `scripts/hwpx/hwpx_template_engine.py`

## 기능

### chart-png CLI

```powershell
python scripts/hwpx/hwpx_template_engine.py chart-png `
  --data-json tmp\hwpx_modularization_check\chart_data.json `
  --output tmp\hwpx_modularization_check\chart_generated_standalone.png `
  --report-json tmp\hwpx_modularization_check\chart_png_report.json
```

결과:

- status: PASS
- width: 640
- height: 360
- series_count: 3
- max_value: 40
- output size: 3009 bytes

### composer chart_png image mode

Composer job의 `images` 항목에서 `mode: chart_png`를 지원한다.

```json
{
  "mode": "chart_png",
  "chart_json": "chart_data.json",
  "chart_output": "chart_generated.png",
  "image_entry": "BinData/composer_chart001.png",
  "width": 16000,
  "height": 9000
}
```

동작:

1. chart JSON 로드
2. dependency-free PNG bar chart 생성
3. generated PNG picture insertion 실행
4. HWPX package write
5. ZIP/XML validation

## 테스트

### 단독 PNG 생성

입력:

- `tmp\hwpx_modularization_check\chart_data.json`

출력:

- `tmp\hwpx_modularization_check\chart_generated_standalone.png`

결과:

- PNG 생성: PASS
- series_count: 3
- file size: 3009 bytes

### HWPX compose

입력:

- template: `tmp\hwpx_writer_poc\template_seed.hwpx`
- job: `tmp\hwpx_modularization_check\compose_chart_job.json`

출력:

- `tmp\hwpx_modularization_check\composed_chart_document.hwpx`
- `tmp\hwpx_modularization_check\compose_chart_report.json`

결과:

| item | result |
| --- | --- |
| replace_placeholders | PASS |
| paragraph_add | GENERATED_PARAGRAPH_APPEND_PASS |
| table_create | GENERATED_TABLE_APPEND_PASS |
| chart PNG generation | PASS |
| generated picture insert | GENERATED_PNG_PICTURE_INSERT_PASS |
| ZIP validation | PASS |
| XML validation | PASS |
| placeholder remaining | false |
| missing expected values | [] |

최종 compose status는 WARN이다. 이유는 기존 P8/P9와 동일하게 picture XML을 한컴이 생성한 템플릿에서 clone한 것이 아니라 direct writer가 synthetic XML로 만든 상태이기 때문이다.

## Java Parser Roundtrip

대상:

- `tmp\hwpx_modularization_check\composed_chart_document.hwpx`

결과:

| item | result |
| --- | --- |
| parse_status | PASS |
| paragraph_count | 6 |
| table_count | 2 |
| semantic_sections_count | 3 |
| extracted_fields_count | 1 |
| diagnostics_exists | true |
| quality_score | 28 |
| warning_count | 0 |
| error_count | 0 |

## 판정

- chart PNG generation: PASS
- chart PNG insertion through composer: PASS
- ZIP/XML validation: PASS
- Java parser roundtrip: PASS
- Hancom visual confirmation: PENDING

최종 판정: WARN

## 제한

- 한컴 native chart 객체 생성은 아직 지원하지 않는다.
- PNG 안의 축/레이블 텍스트 렌더링은 최소화되어 있다.
- 시각 확인은 한컴 실행 없이 수행하지 않았다.

## 다음 단계

1. P11: style and layout control module
2. P12: composer job schema validation
3. P13: document composer API
4. P14: optional visual validation with Hancom or external renderer
