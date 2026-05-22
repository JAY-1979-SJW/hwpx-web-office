# HWPX Direct Writer P49 Examples Visible Policy

## 목적

HWPX direct writer의 기본 예제/API smoke에서 synthetic picture fallback 경고가 기본 경로에 섞이지 않도록 예제 정책을 분리했다.

P48에서 이미지 mode 라우팅 정책은 정리됐지만, 기본 예제와 API smoke에는 여전히 `complex_section_table_chart` synthetic chart 예제가 포함되어 있었다. 이 때문에 실사용 기본 smoke가 기능적으로는 통과해도 `EXPERIMENTAL_SYNTHETIC_PICTURE_XML` 경고로 WARN이 됐다.

## 변경

- `hwpx_compose_examples.py`
  - stable example profiles와 experimental example profiles를 분리했다.
  - 기본 `examples` 생성은 stable 3건만 생성한다.
  - `complex_section_table_chart`는 explicit experimental synthetic fallback 예제로 분리했다.
  - `paragraph_list` 기본 예제에서 header/style 의존성을 제거해 smoke-test 템플릿에서도 PASS가 되게 했다.

- `hwpx_template_engine.py`
  - `examples --include-experimental` 옵션을 추가했다.
  - 기본 `examples`는 stable profile만 생성한다.

- `hwpx_api.py`
  - `generate_examples(..., include_experimental=False)` 옵션을 추가했다.

- `hwpx_compose_schema_reference.py`
  - stable example profiles와 experimental example profiles를 분리해서 문서화했다.
  - synthetic `chart_png`는 명시적 fallback으로만 사용하도록 제한을 명확히 했다.

- `hwpx_api_smoke.py`
  - visible picture clone을 만들기 위한 synthetic bootstrap 결과는 별도 반환하되, 기본 smoke 판정에는 포함하지 않게 했다.
  - 최종 visible chart compose/validate 결과가 smoke 판정 대상이다.

## 검증

### 기본 examples

```text
command: python scripts/hwpx/hwpx_template_engine.py examples --template smoke-test.hwpx --out-dir tmp\hwpx_p49_examples --report-json tmp\hwpx_p49_examples_report.json
status: PASS
count: 3
stable_profiles:
- paragraph_list
- styled_table
- page_layout_numbering
excluded_experimental_profiles:
- complex_section_table_chart
```

### experimental examples

```text
command: python scripts/hwpx/hwpx_template_engine.py examples --template smoke-test.hwpx --out-dir tmp\hwpx_p49_examples_experimental --include-experimental --report-json tmp\hwpx_p49_examples_experimental_report.json
status: PASS
count: 4
include_experimental: true
```

### schema reference

```text
command: python scripts/hwpx/hwpx_template_engine.py schema-reference --out-json tmp\hwpx_p49_schema.json --out-md tmp\hwpx_p49_schema.md
status: PASS
```

### API smoke

```text
command: python scripts/hwpx/hwpx_api_smoke.py --template smoke-test.hwpx --out-dir tmp\hwpx_p49_api_smoke2 --report-json tmp\hwpx_p49_api_smoke2_report.json
status: PASS
examples: PASS
batch: PASS
visible_builder_compose: PASS
visible_builder_validate: PASS
```

### regression

```text
command: python scripts/hwpx/hwpx_template_engine.py regression-suite --template smoke-test.hwpx --out-dir tmp\hwpx_p49_regression2 --strict --report-json tmp\hwpx_p49_regression2_report.json
status: PASS
profile_count: 7
pass_count: 7
warn_count: 0
fail_count: 0
```

## 결론

P49 PASS.

기본 예제와 API smoke는 이제 synthetic fallback 경고 없이 PASS가 된다. synthetic picture XML 경로는 삭제하지 않고 experimental example 및 regression fallback으로 유지했다. HWPX 완전 구현 목표에서 기본 사용 경로는 visible picture clone 정책을 우선하고, synthetic fallback은 명시적으로 선택할 때만 노출한다.

## 다음 단계

1. P50: stable examples/API smoke에 Java parser roundtrip 요약 연결
2. P51: visible picture template fixture 획득 시 synthetic bootstrap 제거
3. P52: 표/이미지/섹션 조합의 공개 CLI smoke 묶음 정리
