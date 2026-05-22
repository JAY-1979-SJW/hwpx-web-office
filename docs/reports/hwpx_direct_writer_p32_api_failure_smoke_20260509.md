# HWPX Direct Writer P32 API Failure Smoke

## 목적

P29~P31에서 정상 경로 facade, batch facade, DocumentBuilder facade가 추가됐다.

P32는 실패 경로가 Python exception으로 새지 않고 표준 `FAIL/WARN/PASS` report로 닫히는지 검증하는 단계다.

## 구현 파일

- `scripts/hwpx/hwpx_api_failure_smoke.py`

## 검증 범위

| 케이스 | 목적 | 기대 |
| --- | --- | --- |
| `compose_missing_template` | 없는 template으로 compose | FAIL report |
| `compose_invalid_page_layout` | 잘못된 page layout schema | FAIL report |
| `compose_missing_image_file` | 없는 이미지 파일 참조 | FAIL report |
| `validate_missing_output` | 없는 HWPX validate | FAIL report |
| `compose_missing_job_file` | 없는 job JSON 파일 | FAIL report |
| `batch_continue_on_error` | batch 중 일부 실패 후 계속 진행 | FAIL summary, job_count 2 |
| `batch_stop_on_error` | 첫 실패에서 batch 중단 | FAIL summary, job_count 1 |

## 실행

```powershell
python scripts/hwpx/hwpx_api_failure_smoke.py `
  --template "samples/[별표 8] 평가사 자격기준(제28조제2항 관련)(건설공사 품질관리 업무지침).hwpx" `
  --out-dir "tmp\hwpx_p32_api_failure_smoke" `
  --report-json "tmp\hwpx_p32_api_failure_smoke\failure_smoke_report.json"
```

## 결과

| 항목 | 값 |
| --- | ---: |
| case_count | 7 |
| pass_count | 7 |
| fail_count | 0 |
| final status | PASS |

## 주요 확인

### 없는 템플릿

`TEMPLATE_NOT_FOUND`가 schema error로 기록되고 compose result는 `FAIL`로 반환됐다.

### 잘못된 page layout

`PAGE_ORIENTATION_INVALID`, `PAGE_DIMENSION_INVALID`가 schema error로 기록됐다.

### 없는 이미지 파일

`EXTERNAL_FILE_NOT_FOUND`가 schema error로 기록됐다.

### 없는 validate 대상

`zip_ok=false`, `xml_ok=false`, `exists=false`와 함께 `FAIL`로 반환됐다.

### 없는 job JSON

`compose_document_from_file`에서 `FileNotFoundError`가 `errors[]`에 기록되고 `FAIL`로 반환됐다.

### batch continue

첫 job은 PASS, 둘째 job은 FAIL로 기록됐고 전체 summary는 FAIL이다.

```text
job_count=2
pass_count=1
fail_count=1
```

### batch stop

첫 job 실패 후 중단됐다.

```text
job_count=1
pass_count=0
fail_count=1
```

## 모듈화 판단

실패 경로 검증은 별도 `hwpx_api_failure_smoke.py`로 분리했다.

기존 구조:

- 정상 facade smoke: `hwpx_api_smoke.py`
- 실패 facade smoke: `hwpx_api_failure_smoke.py`
- API 표면: `hwpx_api.py`
- 객체형 builder: `hwpx_document_builder.py`
- 실행 엔진: `hwpx_composer.py`

## 결론

P32 API failure smoke는 PASS다.

현재 API facade는 주요 실패 경로에서 프로세스를 비정상 종료하지 않고 machine-readable report를 반환한다.

## 다음 단계

1. P33: visible header/footer body generation
2. P34: public document object model 정리
3. P35: server/API endpoint 연결 검토
