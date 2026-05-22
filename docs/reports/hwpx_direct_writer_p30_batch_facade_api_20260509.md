# HWPX Direct Writer P30 Batch Facade API

## 목적

P29에서 추가한 Python facade API를 단건 compose 중심에서 batch compose까지 확장했다.

목표는 CLI를 거치지 않고 Python 코드에서 여러 HWPX compose job을 실행하고, 결과를 동일한 summary report 구조로 받을 수 있게 하는 것이다.

## 구현 파일

- `scripts/hwpx/hwpx_api.py`
- `scripts/hwpx/hwpx_api_smoke.py`

## 추가 API

| 함수 | 역할 |
| --- | --- |
| `batch_compose_documents` | dict job 리스트를 순차 compose하고 summary report 반환 |
| `batch_compose_documents_from_files` | job JSON 파일 리스트를 순차 compose하고 summary report 반환 |

## Batch Report 구조

```json
{
  "status": "PASS|WARN|FAIL",
  "operation": "batch_compose_documents_from_files",
  "job_count": 3,
  "pass_count": 2,
  "warn_count": 1,
  "fail_count": 0,
  "results": [],
  "output_dir": "...",
  "continue_on_error": true
}
```

## 구현 원칙

- 기존 compose 로직은 `hwpx_composer.py`에 유지했다.
- `hwpx_api.py`는 orchestration facade만 담당한다.
- batch 중 개별 job 실패는 result에 기록한다.
- `continue_on_error=false`일 때는 첫 FAIL에서 중단할 수 있게 했다.
- `output_dir`가 지정되면 각 job output 파일명만 유지해 해당 폴더 아래에 생성한다.

## Smoke 검증

실행:

```powershell
python scripts/hwpx/hwpx_api_smoke.py `
  --template "samples/[별표 8] 평가사 자격기준(제28조제2항 관련)(건설공사 품질관리 업무지침).hwpx" `
  --out-dir "tmp\hwpx_p30_batch_api_smoke" `
  --report-json "tmp\hwpx_p30_batch_api_smoke\smoke_report.json"
```

결과:

| 항목 | 결과 |
| --- | --- |
| schema reference | PASS |
| examples generation | PASS |
| single styled_table compose | PASS |
| single validate | PASS |
| batch compose | WARN |
| final smoke status | WARN |

batch compose가 WARN인 이유는 `page_layout_numbering` 예제가 기존 한계인 `HEADER_FOOTER_BODY_GENERATION_PENDING` warning을 포함하기 때문이다. batch 실패는 없었다.

Batch 결과:

| 항목 | 값 |
| --- | --- |
| job_count | 3 |
| pass_count | 2 |
| warn_count | 1 |
| fail_count | 0 |

## Java Parser Roundtrip

대상:

- `tmp/hwpx_p30_batch_api_smoke/batch_outputs/paragraph_list.hwpx`
- `tmp/hwpx_p30_batch_api_smoke/batch_outputs/styled_table.hwpx`
- `tmp/hwpx_p30_batch_api_smoke/batch_outputs/page_layout_numbering.hwpx`

결과:

| 파일 | parse_status | paragraph_count | table_count | semantic_sections | extracted_fields | diagnostics | quality_score |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |
| paragraph_list.hwpx | PASS | 7 | 1 | 2 | 1 | true | 28 |
| styled_table.hwpx | PASS | 5 | 2 | 2 | 2 | true | 25 |
| page_layout_numbering.hwpx | PASS | 5 | 1 | 2 | 1 | true | 28 |

Log4j rolling file appender 경고는 로컬 로그 경로 권한 문제이며, parser 결과의 warning/error count는 모두 0이었다.

## 판정

P30 batch facade API는 WARN으로 판정한다.

이유:

- batch compose 자체는 정상 동작했다.
- Java parser roundtrip도 3/3 PASS다.
- 다만 page layout/header/footer visible body 생성은 아직 pending이라 batch 전체 status는 WARN이다.

## 다음 단계

1. P31: Document object facade 초안
2. P32: API-level failure case smoke
3. P33: visible header/footer body generation
