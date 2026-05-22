# HWPX Direct Writer P9 Document Composer CLI

## 목적

HWPX direct writer/editor의 개별 기능을 하나의 선언형 job JSON으로 묶어 실행하는 문서 합성 도구를 만든다.

이번 단계는 브라우저 뷰어나 한컴 실행 검증이 아니다. 한컴 COM/GUI 없이 HWPX ZIP/XML 패키지를 직접 수정해 아래 기능을 한 번의 CLI 흐름으로 실행하는 것이 목표다.

- placeholder 치환
- 문단 추가
- 표 생성
- PNG 그림 객체 삽입
- ZIP/XML validation
- Java HwpxParser roundtrip

## 구현

### 추가 파일

- `scripts/hwpx/hwpx_composer.py`

### 수정 파일

- `scripts/hwpx/hwpx_template_engine.py`

### CLI

```powershell
python scripts/hwpx/hwpx_template_engine.py compose `
  --job-json tmp\hwpx_modularization_check\compose_job.json `
  --output tmp\hwpx_modularization_check\composed_document_full.hwpx `
  --report-json tmp\hwpx_modularization_check\compose_report_full.json
```

## Job JSON 구조

```json
{
  "template": "template.hwpx",
  "output": "rendered.hwpx",
  "mapping": {},
  "paragraphs": [],
  "tables": [],
  "images": [],
  "expected_values": [],
  "validate": true
}
```

## 실행 순서

1. template HWPX package open
2. placeholder mapping 적용
3. 기존 표 치환 또는 table operations 적용
4. generated paragraph 추가
5. generated table 추가
6. generated PNG picture 삽입
7. package write
8. ZIP/XML validation
9. expected value validation

## 테스트

### 입력

- template: `tmp\hwpx_writer_poc\template_seed.hwpx`
- job: `tmp\hwpx_modularization_check\compose_job.json`
- output: `tmp\hwpx_modularization_check\composed_document_full.hwpx`
- report: `tmp\hwpx_modularization_check\compose_report_full.json`

### 적용 기능

- placeholder 4개 치환
- 문단 1개 추가
- 표 1개 생성
- PNG 그림 1개 삽입

### Validation 결과

- ZIP open: PASS
- XML parse: PASS
- section entry: PASS
- placeholder remaining: false
- missing expected values: []
- failed steps: []

### Step 결과

| step | result |
| --- | --- |
| replace_placeholders | PASS |
| paragraph_add | GENERATED_PARAGRAPH_APPEND_PASS |
| table_create | GENERATED_TABLE_APPEND_PASS |
| png_insert | GENERATED_PNG_PICTURE_INSERT_PASS |

## Java Parser Roundtrip

대상:

- `tmp\hwpx_modularization_check\composed_document_full.hwpx`

결과:

| item | result |
| --- | --- |
| parse_status | PASS |
| paragraph_count | 6 |
| table_count | 2 |
| semantic_sections_count | 3 |
| extracted_fields_count | 2 |
| diagnostics_exists | true |
| quality_score | 41 |
| warning_count | 0 |
| error_count | 0 |

## 판정

P9 composer CLI는 기능 합성 기준으로 PASS다.

다만 PNG 그림 객체는 직접 생성한 synthetic picture XML이므로 한컴 시각 확인은 아직 별도 단계로 남긴다. 따라서 제품 수준 판정은 다음과 같이 분리한다.

- HWPX package generation: PASS
- ZIP/XML validation: PASS
- Java parser roundtrip: PASS
- visual confirmation in Hancom: PENDING

최종 판정: WARN

## 현재 가능한 것

- 기존 HWPX template 기반 문서 생성
- placeholder 치환
- 문단 추가
- 표 생성
- 기존 표 조작
- PNG BinData 추가
- PNG 그림 객체 XML 생성
- Java parser roundtrip 검증

## 남은 작업

- synthetic picture XML의 한컴 시각 확인
- 스타일/글꼴/문단 모양 제어
- 이미지 배치/크기 정책 강화
- 그래프 PNG 생성 후 composer job에 연결
- composer job schema 안정화
- API layer 연결

## 다음 단계

1. P10: chart PNG generation and insertion
2. P11: style and layout control module
3. P12: generated HWPX visual validation policy
4. P13: document composer API
