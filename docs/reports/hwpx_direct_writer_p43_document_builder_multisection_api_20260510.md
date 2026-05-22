# HWPX Direct Writer P43 DocumentBuilder Multi-Section API

## 목적

P41/P42에서 composer job으로 가능해진 multi-section, section-specific page layout, visible header/footer 기능을 상위 Python `DocumentBuilder` API에서도 직접 사용할 수 있게 정리했다.

이번 단계는 저수준 XML 기능 추가가 아니라, 이미 모듈화된 composer 기능을 사용자가 안정적인 fluent API로 호출할 수 있게 하는 API 계층 강화다.

## 구현

### DocumentBuilder

추가된 메서드:

```text
sections(count, clear_body=True)
section_page_layout(section_index, **layout)
section_page_numbering(section_index, **numbering)
section_visible_header(section_index, text, align="CENTER", start_page=None)
section_visible_footer(section_index, text="Page {page}", align="CENTER", start_page=None)
```

기존 메서드는 유지했다.

```text
page_layout(...)
page_numbering(...)
visible_header(...)
visible_footer(...)
```

### Schema Reference

compose schema reference에 아래 필드를 추가했다.

```text
page_layouts
page_numberings
section_index in page_layout_fields
section_index in page_numbering_fields
```

### API Smoke

`hwpx_api_smoke.py`에 builder 기반 multi-section compose를 추가했다.

검증 내용:

```text
3 sections
section별 page layout
section별 visible header/footer
section별 start page
section별 paragraph
validate_document expected values
```

## 검증 결과

### Python AST

```text
PY_AST_OK scripts/hwpx/hwpx_document_builder.py
PY_AST_OK scripts/hwpx/hwpx_compose_schema_reference.py
PY_AST_OK scripts/hwpx/hwpx_api_smoke.py
```

### API Smoke

대상:

```text
tmp/hwpx_p43_builder_api/report.json
tmp/hwpx_p43_builder_api/builder_multisection.hwpx
```

결과:

```text
overall api smoke: WARN
builder_compose: PASS
builder_validate: PASS
```

overall WARN 사유:

```text
기존 batch example 중 1건이 WARN을 유지한다.
이번 P43 builder multi-section 경로는 PASS다.
```

### Strict Audit

대상:

```text
tmp/hwpx_p43_builder_api/builder_multisection.hwpx
```

결과:

```text
status: PASS
section_entries: 3
manifest_spine: PASS
metadata: PASS
preview_text: PASS
sections_inspect: PASS
page_layouts: PASS, PASS, PASS
page_numberings: PASS, PASS, PASS
missing expected values: []
```

### Regression Suite

명령:

```text
python scripts/hwpx/hwpx_template_engine.py regression-suite --template smoke-test.hwpx --out-dir tmp/hwpx_p43_builder_api_regression --strict
```

결과:

```text
status: PASS
profile_count: 5
pass_count: 5
warn_count: 0
fail_count: 0
```

### Java Parser Roundtrip

대상:

```text
tmp/hwpx_p43_builder_api/builder_multisection.hwpx
```

결과:

| File | Parse | Paragraphs | Tables | Diagnostics | Quality | Missing Expected |
| --- | --- | ---: | ---: | --- | ---: | --- |
| builder_multisection.hwpx | PASS | 6 | 0 | true | 7 | 0 |

Java 실행 중 기존과 동일하게 Log4j rolling file appender 권한 경고가 출력됐지만, `HwpxParser.parse()` 결과는 PASS였다.

## 결론

P43 판정:

```text
PASS
```

이제 상위 Python API에서 아래 흐름을 직접 구성할 수 있다.

```python
document(template, output)
  .sections(3)
  .section_page_layout(0, orientation="portrait")
  .section_page_layout(1, orientation="landscape")
  .section_page_numbering(0, start_page=1, visible_header=True, header_text="...")
  .section_page_numbering(1, start_page=10, visible_footer=True, footer_text="...")
  .paragraph("...", section_index=1)
  .compose()
```

## 제한

- API smoke overall WARN은 기존 batch example의 WARN에서 온다.
- native dynamic page field는 아직 guard 상태다.
- 한컴 GUI 시각 확인은 별도 단계다.

## 다음 단계

1. P44: section-aware image/table placement regression
2. P45: compose API failure/hardening 추가
3. P46: style/theme preset catalog 확장
