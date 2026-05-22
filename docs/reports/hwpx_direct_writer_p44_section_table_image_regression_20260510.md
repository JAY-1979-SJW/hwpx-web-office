# HWPX Direct Writer P44 Section Table Image Regression

## 목적

P43에서 추가한 `DocumentBuilder` multi-section API를 복합 문서 생성 경로로 확장 검증했다. 이번 단계는 한컴 실행 없이 HWPX ZIP/XML을 직접 생성·수정하는 도구가 여러 section, section별 page layout/header/footer, 표, PNG chart 이미지를 한 문서 안에 함께 배치할 수 있는지 확인하는 회귀 단계다.

## 구현

수정 파일:

- `scripts/hwpx/hwpx_compose_regression.py`
- `scripts/hwpx/hwpx_api_smoke.py`

추가/보강 내용:

- `section_table_image_chart` golden regression profile 추가
- 3개 section 생성
- section별 page layout 및 visible header/footer 적용
- section 1에 표 생성
- section 2에 chart PNG 생성 및 visible picture XML 삽입
- regression profile check에 section count, BinData image count, image reference count, expected values 확인 추가
- API smoke에 `DocumentBuilder` 기반 복합 section/table/chart 문서 생성 경로 추가

## 검증

### Python/CLI

결과:

- `hwpx_compose_regression.py` AST: PASS
- `hwpx_api_smoke.py` AST: PASS
- `regression-suite --help`: PASS
- `hwpx_api_smoke.py --help`: PASS

### Regression Suite

명령:

```powershell
python scripts/hwpx/hwpx_template_engine.py regression-suite `
  --template smoke-test.hwpx `
  --out-dir tmp\hwpx_p44_section_table_image_regression `
  --strict `
  --report-json tmp\hwpx_p44_section_table_image_regression\report.json `
  --report-csv tmp\hwpx_p44_section_table_image_regression\report.csv
```

결과:

- status: PASS
- profile_count: 6
- pass_count: 6
- warn_count: 0
- fail_count: 0

신규 profile `section_table_image_chart`:

- compose_status: WARN
- compose_effective_status: PASS
- audit_status: PASS
- section_count: 3
- bindata_image_count: 1
- image_reference_count: 5
- missing_expected_values: []

`compose_status`가 WARN인 이유는 기존 정책과 동일하게 generated picture XML이 한컴에서 만든 picture sample을 clone하지 않고 직접 생성한 실험적 XML이기 때문이다. 해당 warning은 `EXPERIMENTAL_SYNTHETIC_PICTURE_XML`로 분리되어 있고, package audit과 parser roundtrip은 PASS다.

### API Smoke

명령:

```powershell
python scripts/hwpx/hwpx_api_smoke.py `
  --template smoke-test.hwpx `
  --out-dir tmp\hwpx_p44_api_smoke `
  --report-json tmp\hwpx_p44_api_smoke\report.json
```

전체 결과:

- status: WARN

원인:

- 기존 batch example 중 하나가 WARN을 유지한다.
- P44 신규 `builder_complex_compose`와 `builder_complex_validate`는 PASS다.

P44 builder complex 결과:

- output: `tmp\hwpx_p44_api_smoke\builder_complex_section_table_chart.hwpx`
- ZIP/XML validation: PASS
- section_entries: 3
- table: section 1에 1개
- image: section 2에 chart PNG 1개
- expected values missing: []

### Strict Package Audit

대상:

```text
tmp\hwpx_p44_api_smoke\builder_complex_section_table_chart.hwpx
```

결과:

- status: PASS
- section_entries: 3
- content.hpf: PASS
- META-INF/container.xml: PASS
- manifest/spine: PASS
- metadata: PASS
- preview text: PASS
- page_layouts: PASS / PASS / PASS
- page_numberings: PASS / PASS / PASS
- bindata_images: 1
- image_reference_count: 5
- missing_expected_values: []

### Java Parser Roundtrip

대상:

- `tmp/hwpx_p44_section_table_image_regression/section_table_image_chart.hwpx`
- `tmp/hwpx_p44_api_smoke/builder_complex_section_table_chart.hwpx`

결과:

- parse_status: PASS / PASS
- paragraph_count: 7 / 7
- table_count: 1 / 1
- diagnostics_exists: true / true
- quality_score: 7 / 7
- missing_expected_values: [] / []

Java parser 실행 중 기존 Log4j rolling file appender 권한 warning이 출력됐지만, parser 결과 자체는 PASS다.

## 판정

P44 최종 판정: PASS

확인된 기능:

- multi-section 문서 생성
- section별 page layout 적용
- section별 visible header/footer 적용
- section별 paragraph 배치
- section별 table 생성
- section별 generated chart PNG image 삽입
- manifest/spine repair
- preview text 생성
- strict package audit
- Java parser roundtrip

## 제한

- generated picture XML은 아직 한컴-authored picture sample 기반 clone이 아니라 직접 생성 방식이다.
- 한컴 GUI 시각 확인은 수행하지 않았다.
- Java parser의 semanticSections/extractedFields는 이번 복합 synthetic 문서에서 0으로 남아 있다. 이는 parser semantic extraction 범위 문제로 분리한다.

## 다음 단계

1. P45: DocumentBuilder/API 예제와 schema reference에 복합 section/table/image job 예시 추가
2. P46: picture XML 안정화, 한컴-authored picture sample clone 경로 확보
3. P47: HWPX chart PNG + image placement regression 확장
4. P48: HWPX document quality gate를 API/CI용 단일 smoke command로 묶기
