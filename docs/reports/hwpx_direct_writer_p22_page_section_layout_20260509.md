# HWPX Direct Writer P22 Page Section Layout

## 목적

한컴 실행 없이 HWPX `section.xml`의 페이지/섹션 레이아웃을 직접 설정하는 기능을 추가했다. 이번 단계는 본문 작성/표/이미지 모듈과 분리된 페이지 레이아웃 전용 모듈을 만드는 작업이다.

## 구현

- `scripts/hwpx/hwpx_page_layout_ops.py`
  - `normalize_page_layout`
  - `inspect_page_layout`
  - `set_page_layout`
- `scripts/hwpx/hwpx_composer.py`
  - compose job의 `page_layout` 단계 연결
- `scripts/hwpx/hwpx_job_schema.py`
  - `page_layout` schema 검증 추가

## 지원 범위

- section index 지정
- portrait / landscape
- width / height
- left / right / top / bottom margin
- header / footer / gutter margin
- 기존 `pagePr` 수정
- `pagePr`이 없는 최소 HWPX에는 `secPr/pagePr/margin` 생성

## 테스트

대상 템플릿:

```text
smoke-test.hwpx
```

실행:

```text
python scripts/hwpx/hwpx_template_engine.py validate-job --job-json tmp/hwpx_p22_page_layout/compose_page_layout_job.json
python scripts/hwpx/hwpx_template_engine.py compose --job-json tmp/hwpx_p22_page_layout/compose_page_layout_job.json
```

결과:

```text
compose status: PASS
ZIP validation: PASS
XML validation: PASS
expected values: PASS
```

생성된 `pagePr`:

```json
{
  "landscape": "WIDELY",
  "width": "84189",
  "height": "59528",
  "gutterType": "LEFT_ONLY"
}
```

생성된 `margin`:

```json
{
  "left": "3000",
  "right": "3000",
  "top": "2500",
  "bottom": "2500",
  "header": "1000",
  "footer": "1000",
  "gutter": "0"
}
```

## Java Parser Roundtrip

대상:

```text
tmp/hwpx_p22_page_layout/composed_page_layout.hwpx
```

결과:

```text
parse_status: PASS
paragraph_count: 2
table_count: 0
diagnostics_exists: true
quality_score: 7
warning_count: 0
error_count: 0
```

Java 실행 중 기존 Log4j file appender 권한 경고가 출력됐지만, parser 결과 JSON은 정상 생성됐고 parse status는 PASS다.

## Failure Case

invalid job:

```json
{
  "orientation": "diagonal",
  "margins": {
    "left": -1
  }
}
```

결과:

```text
status: FAIL
PAGE_ORIENTATION_INVALID
PAGE_MARGIN_INVALID
```

## 결론

```text
P22_PAGE_SECTION_LAYOUT: PASS
```

페이지/섹션 레이아웃 기능은 별도 모듈로 분리됐고, composer job schema와 compose 단계에 연결됐다. HWPX ZIP/XML validation과 Java HwpxParser roundtrip 모두 통과했다.

## 제한

- 한컴 시각 확인은 수행하지 않았다.
- 복수 section 문서의 모든 section 동시 변경은 아직 구현하지 않았다.
- paper preset(A4/B4 등) 이름 기반 설정은 후속 단계다.

## 다음 단계

1. P23: 문단 번호/불릿/list style 모듈
2. P24: 머리말/꼬리말/쪽 번호 구조 분석
3. P25: section별 page layout batch 적용
