# HWPX Direct Writer P29 Python Facade API

## 목적

HWPX direct writer/editor가 CLI 중심에서만 동작하지 않도록, 다른 Python 코드가 안정적으로 호출할 수 있는 얇은 facade API를 추가했다.

이번 단계는 새 HWPX 기능을 추가하는 것이 아니라, 이미 구현된 render, compose, validate, examples, schema reference 기능을 모듈형 API 표면으로 묶는 작업이다.

## 구현 파일

- `scripts/hwpx/hwpx_api.py`
- `scripts/hwpx/hwpx_api_smoke.py`

## Facade 함수

| 함수 | 역할 | 하위 모듈 |
| --- | --- | --- |
| `render_document` | template + mapping/table 입력으로 HWPX 렌더링 | `hwpx_template_render` |
| `compose_document` | dict 기반 compose job 실행 | `hwpx_composer` |
| `compose_document_from_file` | JSON job 파일 기반 compose 실행 | `hwpx_composer` |
| `validate_document` | HWPX ZIP/XML 및 expected text 검증 | `hwpx_validation` |
| `generate_examples` | compose job 예제 생성 | `hwpx_compose_examples` |
| `generate_schema_reference` | compose schema reference 생성 | `hwpx_compose_schema_reference` |

## 오류 처리

Facade 함수는 예외를 호출자에게 그대로 전파하지 않고 아래 구조의 dict로 반환한다.

```json
{
  "status": "FAIL",
  "operation": "...",
  "warnings": [],
  "errors": [
    {
      "type": "ExceptionType",
      "message": "..."
    }
  ]
}
```

정상 결과는 하위 모듈의 report를 `result` 필드에 보존한다.

## Smoke 검증

실행:

```powershell
python scripts/hwpx/hwpx_api_smoke.py `
  --template "samples/[별표 8] 평가사 자격기준(제28조제2항 관련)(건설공사 품질관리 업무지침).hwpx" `
  --out-dir "tmp\hwpx_p29_api_smoke" `
  --report-json "tmp\hwpx_p29_api_smoke\smoke_report.json"
```

결과:

| 항목 | 결과 |
| --- | --- |
| schema reference 생성 | PASS |
| examples 생성 | PASS |
| styled table compose | PASS |
| validate | PASS |
| 최종 smoke status | PASS |

## Java Parser Roundtrip

대상:

```text
tmp/hwpx_p29_api_smoke/examples/styled_table.hwpx
```

결과:

| 항목 | 값 |
| --- | --- |
| parse_status | PASS |
| paragraph_count | 5 |
| table_count | 2 |
| semantic_sections_count | 2 |
| extracted_fields_count | 2 |
| diagnostics_exists | true |
| quality_score | 25 |
| warning_count | 0 |
| error_count | 0 |

로컬 Log4j appender 경로 권한 경고는 있었지만 Java parser 결과에는 warning/error가 없었다.

## 모듈화 판단

이번 단계에서 `hwpx_template_engine.py`에 기능을 더 쌓지 않고 `hwpx_api.py`를 별도 facade로 분리했다.

현재 구조:

- 저수준 ZIP/XML 조작: `hwpx_writer_adapter.py`, `hwpx_*_ops.py`
- compose orchestration: `hwpx_composer.py`
- CLI: `hwpx_template_engine.py`
- 외부 Python 호출 표면: `hwpx_api.py`
- facade smoke: `hwpx_api_smoke.py`

## 제한

- 아직 서버 HTTP API는 아니다.
- async/job queue는 미구현이다.
- batch facade는 후속 단계에서 별도 설계가 필요하다.
- 한컴 시각 확인은 수행하지 않았다.
- visible header/footer와 일부 고급 문서 객체는 후속 단계로 남아 있다.

## 결론

P29 Python facade API는 PASS다.

HWPX direct writer를 CLI뿐 아니라 Python 모듈로 호출할 수 있는 최소 안정 표면이 생겼고, facade smoke 및 Java parser roundtrip까지 통과했다.

## 다음 단계

1. P30: batch compose facade 및 대량 job report 표준화
2. P31: HWPX document API 객체 모델 초안
3. P32: 서버 API 연결 여부 판단
