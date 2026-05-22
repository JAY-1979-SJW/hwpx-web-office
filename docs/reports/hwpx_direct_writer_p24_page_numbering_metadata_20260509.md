# HWPX Direct Writer P24 Page Numbering Metadata

## 목적

한컴 실행 없이 HWPX의 쪽 번호 시작값과 첫 페이지 표시 정책을 직접 제어하는 기능을 추가했다. 실제 보이는 머리말/꼬리말 본문 객체 구조는 샘플에서 발견되지 않아, 이번 단계에서는 검증 가능한 페이지 번호 메타데이터만 구현했다.

## 구현

- `scripts/hwpx/hwpx_header_footer_ops.py`
  - `normalize_page_numbering`
  - `inspect_page_numbering`
  - `apply_page_numbering`
- `scripts/hwpx/hwpx_composer.py`
  - compose job의 `page_numbering` 단계 연결
- `scripts/hwpx/hwpx_job_schema.py`
  - `page_numbering` schema 검증 추가

## 지원 범위

- `Contents/header.xml`의 `hh:beginNum page` 수정
- `Contents/section*.xml`의 `hp:startNum pageStartsOn/page` 수정
- `hp:visibility hideFirstPageNum` 수정
- first header/footer 숨김 플래그 수정

## 테스트

대상 템플릿:

```text
samples/[별지 10] 레미콘(아스콘) 공장 정기점검  결과 보고(건설공사 품질관리 업무지침).hwpx
```

실행:

```text
python scripts/hwpx/hwpx_template_engine.py validate-job --job-json tmp/hwpx_p24_page_numbering/compose_page_numbering_job.json
python scripts/hwpx/hwpx_template_engine.py compose --job-json tmp/hwpx_p24_page_numbering/compose_page_numbering_job.json
```

결과:

```text
validate-job: PASS
compose: WARN
ZIP/XML validation: PASS
expected values: PASS
```

`compose`가 WARN인 이유는 실제 머리말/꼬리말 본문 객체 생성이 아직 pending으로 기록되기 때문이다. 메타데이터 변경 자체는 PASS다.

## 변경된 값

`beginNum`:

```json
{
  "page": "5",
  "footnote": "1",
  "endnote": "1",
  "pic": "1",
  "tbl": "1",
  "equation": "1"
}
```

`startNum`:

```json
{
  "pageStartsOn": "BOTH",
  "page": "4",
  "pic": "0",
  "tbl": "0",
  "equation": "0"
}
```

`visibility`:

```json
{
  "hideFirstHeader": "0",
  "hideFirstFooter": "0",
  "hideFirstMasterPage": "0",
  "border": "SHOW_ALL",
  "fill": "SHOW_ALL",
  "hideFirstPageNum": "1",
  "hideFirstEmptyLine": "0",
  "showLineNumber": "0"
}
```

## Java Parser Roundtrip

대상:

```text
tmp/hwpx_p24_page_numbering/composed_page_numbering.hwpx
```

결과:

```text
parse_status: PASS
paragraph_count: 8
table_count: 2
semantic_sections_count: 2
extracted_fields_count: 1
diagnostics_exists: true
quality_score: 28
warning_count: 0
error_count: 0
```

Java 실행 중 기존 Log4j file appender 권한 경고가 출력됐지만, parser 결과 JSON은 정상 생성됐고 parse status는 PASS다.

## Failure Case

invalid job:

```json
{
  "start_page": 0,
  "page_starts_on": "MIDDLE"
}
```

결과:

```text
status: FAIL
PAGE_START_INVALID
PAGE_STARTS_ON_INVALID
```

## 결론

```text
P24_PAGE_NUMBERING_METADATA: WARN
```

쪽 번호 메타데이터 제어는 성공했다. 다만 실제 머리말/꼬리말 본문 객체 생성은 로컬 샘플에서 구조를 찾지 못해 후속 단계로 분리한다.

## 다음 단계

1. P24-2: 실제 header/footer body 샘플 확보 및 구조 분석
2. P24-3: master page/header/footer object 생성
3. P25: list restart / outline preset 고도화
