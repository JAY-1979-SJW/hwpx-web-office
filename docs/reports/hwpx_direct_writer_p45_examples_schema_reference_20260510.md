# HWPX Direct Writer P45 Examples and Schema Reference

## 목적

P44에서 검증한 section/table/image/chart 복합 문서 생성 기능을 실제 사용자가 찾고 재사용할 수 있도록 예제와 schema reference에 노출했다. 이번 단계는 새 HWPX 기능 자체보다 도구 사용성, 문서화, CLI 진입점 보강이 목적이다.

## 구현

수정 파일:

- `scripts/hwpx/hwpx_compose_examples.py`
- `scripts/hwpx/hwpx_compose_schema_reference.py`
- `scripts/hwpx/hwpx_template_engine.py`
- `scripts/hwpx/hwpx_api_smoke.py`

변경 내용:

- `complex_section_table_chart` 예제 job 추가
- schema reference에 `image_fields`, `section_aware_fields`, `example_profiles` 추가
- `hwpx_template_engine.py schema-reference` CLI 추가
- API smoke batch 대상에 `complex_section_table_chart` 포함

## 예제

신규 예제:

```text
complex_section_table_chart
```

포함 기능:

- `sections.count = 3`
- section별 `page_layouts`
- section별 `page_numberings`
- section별 문단 배치
- section 1 표 생성
- section 2 chart PNG 생성 및 image 삽입
- metadata / preview / package manifest 생성

## 검증

### AST

결과:

- `hwpx_compose_examples.py`: PASS
- `hwpx_compose_schema_reference.py`: PASS
- `hwpx_template_engine.py`: PASS
- `hwpx_api_smoke.py`: PASS

### Examples CLI

명령:

```powershell
python scripts/hwpx/hwpx_template_engine.py examples `
  --template smoke-test.hwpx `
  --out-dir tmp\hwpx_p45_examples `
  --report-json tmp\hwpx_p45_examples\report.json
```

결과:

- status: PASS
- count: 4
- generated profiles:
  - `paragraph_list`
  - `styled_table`
  - `page_layout_numbering`
  - `complex_section_table_chart`

### Schema Reference CLI

명령:

```powershell
python scripts/hwpx/hwpx_template_engine.py schema-reference `
  --out-json tmp\hwpx_p45_schema\schema_reference.json `
  --out-md tmp\hwpx_p45_schema\schema_reference.md
```

결과:

- status: PASS
- JSON 생성: PASS
- Markdown 생성: PASS
- image fields 노출: PASS
- section-aware fields 노출: PASS
- complex example profile 노출: PASS

### API Smoke

명령:

```powershell
python scripts/hwpx/hwpx_api_smoke.py `
  --template smoke-test.hwpx `
  --out-dir tmp\hwpx_p45_api_smoke `
  --report-json tmp\hwpx_p45_api_smoke\report.json
```

결과:

- status: WARN
- 원인: 기존 batch example WARN 유지 및 generated picture XML warning
- examples: PASS, count 4
- `complex_section_table_chart` compose: WARN, effective PASS
- builder complex compose/validate: PASS

### Regression Suite

명령:

```powershell
python scripts/hwpx/hwpx_template_engine.py regression-suite `
  --template smoke-test.hwpx `
  --out-dir tmp\hwpx_p45_regression `
  --strict `
  --report-json tmp\hwpx_p45_regression\report.json `
  --report-csv tmp\hwpx_p45_regression\report.csv
```

결과:

- status: PASS
- profile_count: 6
- pass_count: 6
- warn_count: 0
- fail_count: 0

## 판정

P45 최종 판정: PASS

사용성 기준으로 아래가 충족됐다.

- 복합 section/table/image/chart job 예제 제공
- schema reference에서 section-aware/image 필드 확인 가능
- CLI에서 schema reference 생성 가능
- API smoke와 regression suite가 변경을 흡수함

## 제한

- API smoke 전체는 기존 batch WARN을 유지한다.
- chart/image 삽입은 여전히 `EXPERIMENTAL_SYNTHETIC_PICTURE_XML` warning이 붙는다.
- 한컴 GUI 시각 확인은 수행하지 않았다.

## 다음 단계

1. P46: generated picture XML 안정화 및 한컴-authored picture sample clone 경로 확보
2. P47: `DocumentBuilder` example cookbook 추가
3. P48: 단일 quality gate CLI로 examples/regression/audit/API smoke 묶기
