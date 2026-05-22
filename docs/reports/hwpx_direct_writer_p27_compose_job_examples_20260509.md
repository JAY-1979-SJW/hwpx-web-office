# HWPX Direct Writer P27 Compose Job Examples

## 목적

HWPX direct writer 기능이 늘어나면서 compose job을 직접 작성하기 어려워졌다. 이번 P27에서는 기능별 예시 job을 코드에서 생성하는 명령을 추가하고, 실제 sample 템플릿으로 validate/compose/parser roundtrip을 검증했다.

## 구현

### 신규 모듈

```text
scripts/hwpx/hwpx_compose_examples.py
```

역할:

```text
example_jobs(template, output_dir)
write_example_jobs(out_dir, template)
```

### CLI 추가

```text
python scripts/hwpx/hwpx_template_engine.py examples \
  --out-dir tmp/hwpx_p27_compose_examples_sample \
  --template "samples/[별표 8] 평가사 자격기준(제28조제2항 관련)(건설공사 품질관리 업무지침).hwpx"
```

생성 파일:

```text
paragraph_list.json
styled_table.json
page_layout_numbering.json
index.json
```

## 예시 범위

### paragraph_list

포함 기능:

```text
char_styles
para_styles
list_styles
paragraphs
expected_values
```

검증 결과:

```text
validate-job: PASS
compose: PASS
ZIP/XML validation: PASS
missing_expected_values: []
```

### styled_table

포함 기능:

```text
border_fills
tables
column_widths
row_heights
header/body border fill refs
cell vertical align
cell line wrap
cell margin
```

검증 결과:

```text
validate-job: PASS
compose: PASS
ZIP/XML validation: PASS
missing_expected_values: []
Java parser roundtrip: PASS
```

Java parser 결과:

```text
parse_status: PASS
paragraph_count: 5
table_count: 2
semantic_sections_count: 2
extracted_fields_count: 2
diagnostics_exists: true
quality_score: 25
warning_count: 0
error_count: 0
```

### page_layout_numbering

포함 기능:

```text
page_layout
page_numbering
paragraphs
```

검증 결과:

```text
validate-job: PASS
compose: WARN
ZIP/XML validation: PASS
missing_expected_values: []
```

WARN 사유:

```text
HEADER_FOOTER_BODY_GENERATION_PENDING
```

이는 page numbering metadata는 반영되지만, 실제 보이는 header/footer body 생성은 별도 fixture 확보 후 진행해야 하기 때문이다.

## smoke-test 템플릿 주의

`smoke-test.hwpx`는 최소 fixture라 `Contents/header.xml`이 없어 header style/list style/page numbering 일부가 WARN으로 떨어진다. 예시를 전체 PASS에 가깝게 검증하려면 header가 있는 실제 HWPX 템플릿을 사용해야 한다.

## 판정

```text
P27_COMPOSE_JOB_EXAMPLES: PASS
```

## 제한

- 예시 job JSON은 tmp에 생성하며 commit하지 않는다.
- 생성 HWPX도 commit하지 않는다.
- page numbering visible header/footer body는 아직 pending이다.
- 브라우저 뷰어/한컴 GUI 확인은 수행하지 않았다.

## 다음 단계

1. P28: compose job schema reference 문서화
2. P29: API wrapper 또는 Python library facade 설계
3. P30: visible header/footer fixture 확보 후 본문 표시 header/footer 생성
