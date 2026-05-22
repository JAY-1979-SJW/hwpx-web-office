# HWPX Direct Writer P31 Document Builder Facade

## 목적

P29/P30에서 Python 함수형 facade를 추가했지만, 실제 도구 사용 관점에서는 매번 compose job dict를 직접 조립해야 했다.

P31은 문단, 표, 스타일, 이미지, 차트, 페이지 설정을 객체형 API로 쌓아 올리고 기존 `hwpx_composer`로 실행하는 `DocumentBuilder` facade를 추가한 단계다.

## 지시문 완성도 검토

P31 지시문은 아래 항목을 포함해야 완전하다.

| 항목 | 필요 여부 | 반영 |
| --- | --- | --- |
| 객체형 builder API | 필수 | 반영 |
| 기존 compose job과 호환 | 필수 | 반영 |
| 저수준 XML 조작 중복 금지 | 필수 | 반영 |
| 문단/표/스타일 API | 필수 | 반영 |
| 이미지/차트 API 표면 | 필수 | 반영 |
| job export | 필수 | 반영 |
| compose 실행 | 필수 | 반영 |
| ZIP/XML validation | 필수 | 반영 |
| Java parser roundtrip | 필수 | 반영 |
| 한컴 실행 없이 검증 | 필수 | 반영 |

## 구현 파일

- `scripts/hwpx/hwpx_document_builder.py`
- `scripts/hwpx/hwpx_api.py`

## 추가 API

### `DocumentBuilder`

Fluent API로 compose job을 만든다.

주요 메서드:

- `template(path)`
- `output(path)`
- `validate(enabled)`
- `mapping(values)`
- `expect(*values)`
- `style_definitions(definitions)`
- `char_style(name, **style)`
- `paragraph_style(name, **style)`
- `border_fill(name, **style)`
- `list_style(name, **style)`
- `page_layout(**layout)`
- `page_numbering(**numbering)`
- `paragraph(text, style=None, section_index=0)`
- `table(rows, style=None, section_index=0)`
- `table_operation(operation)`
- `image_png(path, ...)`
- `chart_png(chart, ...)`
- `to_job()`
- `write_job(path)`
- `compose(output=None, report_json=None)`

### `document(template=None, output=None)`

새 builder를 반환하는 helper다.

## 모듈화 판단

`DocumentBuilder`는 직접 XML을 수정하지 않는다.

역할 분리:

- `hwpx_document_builder.py`: 사용자 친화적 객체형 job 작성
- `hwpx_composer.py`: compose job 실행 순서와 orchestration
- `hwpx_*_ops.py`: 기능별 XML 조작
- `hwpx_api.py`: 외부 Python 호출 표면
- `hwpx_template_engine.py`: CLI 표면

따라서 P31은 기존 모듈화 원칙을 유지한다.

## Smoke 검증

실행 내용:

```python
from hwpx_api import document

b = document(template, output)
b.char_style("blue_bold", height=1200, text_color="#1F4E79", bold=True)
b.paragraph_style("centered", align="CENTER", line_spacing=160)
b.border_fill("header_fill", fill_color="#D9EAF7")
b.paragraph("P31 DocumentBuilder paragraph", {"char_style": "blue_bold", "para_style": "centered"})
b.table([["Item", "Value"], ["Builder", "PASS"]], {"header_border_fill_style": "header_fill", "width": 32000})
b.write_job(job_path)
b.compose(report_json=report_path)
```

결과:

| 항목 | 결과 |
| --- | --- |
| compose status | PASS |
| schema status | PASS |
| paragraph_add | GENERATED_PARAGRAPH_APPEND_PASS |
| table_create | GENERATED_TABLE_APPEND_PASS |
| ZIP validation | PASS |
| XML validation | PASS |
| missing expected values | 없음 |
| warnings | 없음 |

## Java Parser Roundtrip

대상:

```text
tmp/hwpx_p31_document_builder/builder_ascii_output.hwpx
```

결과:

| 항목 | 값 |
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

Log4j rolling file appender 경고는 로컬 로그 경로 권한 문제이며 parser 결과에는 warning/error가 없었다.

## 제한

- builder는 아직 async/job queue를 제공하지 않는다.
- server HTTP endpoint는 아직 연결하지 않았다.
- visible header/footer body 생성은 별도 pending이다.
- 이미지/차트 메서드는 composer의 기존 `images` job 구조로 위임한다.

## 결론

P31 DocumentBuilder facade는 PASS다.

이제 HWPX direct writer는 다음 3개 인터페이스를 갖는다.

1. CLI: `hwpx_template_engine.py`
2. 함수형 Python API: `hwpx_api.py`
3. 객체형 Python API: `DocumentBuilder`

## 다음 단계

1. P32: API-level failure case smoke
2. P33: visible header/footer body generation
3. P34: public document object model 정리
