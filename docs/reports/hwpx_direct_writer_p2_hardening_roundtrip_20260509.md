# HWPX Direct Writer P2 Hardening and Roundtrip

## 목적

P2 template engine CLI를 PoC 수준에서 실사용 도구 기준선으로 강화했다.

기존 P2는 `render`, `validate`, `batch-render`가 동작했지만 다음 검증이 부족했다.

```text
Java parser roundtrip이 P2에서 직접 실행되지 않음
clean output directory 재현성 검증 부족
self-test 명령 없음
mapping/table 충돌 warning 부족
실패 케이스 report 검증 부족
```

이번 작업은 P3 이미지 삽입이 아니다. HWPX template engine P2를 닫기 위한 hardening 작업이다.

## 기준

```text
기준 HEAD = 53ad79d58dfa00bef953315d2baf84d6205ac9f3
P2 기능 commit = 6851d26 feat(hwpx): add template engine CLI
P2 devlog commit = 53ad79d docs: devlog 6851d26
```

## 보강 내용

### self-test 명령

`scripts/hwpx/hwpx_template_engine.py`에 `self-test` 명령을 추가했다.

```powershell
python scripts/hwpx/hwpx_template_engine.py self-test `
  --template "tmp\hwpx_writer_poc\template_seed.hwpx" `
  --out-dir "tmp\hwpx_template_engine_hardening" `
  --report-json "tmp\hwpx_template_engine_hardening\selftest_report_002.json"
```

역할:

```text
mapping.json 자동 생성
table_data.json 자동 생성
batch_job.json 자동 생성
render 실행
validate 실행
batch-render 2건 실행
selftest_report 생성
```

기존 파일 삭제 없이 `unique_path()`로 출력 파일명을 회피한다.

### 실패 report 보존

`render`와 `batch-render`에서 입력 JSON 오류, 누락 파일, invalid table JSON을 만나도 report JSON을 남기도록 보강했다.

예:

```json
{
  "status": "FAIL",
  "error_type": "FileNotFoundError",
  "error_message": "..."
}
```

### mapping/table override warning

P2 템플릿에서는 일부 placeholder가 첫 번째 표 내부에 있을 수 있다. 이 경우 처리 순서는 아래와 같다.

```text
1. mapping placeholder 치환
2. table JSON 기반 첫 번째 표 셀 치환
```

따라서 표 셀 내부의 mapping 결과가 table JSON으로 덮어써질 수 있다.

이번 보강에서 `ordering` 필드를 추가했다.

```json
{
  "mapping_applied_before_table": true,
  "table_update_may_override_mapping": true,
  "overwritten_mapping_values": ["제한최저가", "테스트 발주처"]
}
```

이 warning은 결과 HWPX 검증 실패가 아니라 처리 순서와 템플릿 설계상의 주의 신호다. 최종 expected-value 검증은 table JSON 기준으로 수행한다.

## Clean 재현성 검증

새 출력 폴더:

```text
tmp/hwpx_template_engine_hardening/
```

사용 템플릿:

```text
tmp/hwpx_writer_poc/template_seed.hwpx
```

산출물:

```text
rendered_001.hwpx
validate_report_001.json
batch_001_001.hwpx
batch_002_001.hwpx
batch_report_001.json
selftest_report_002.json
```

### Self-test 결과

```text
self-test status = PASS
render status = PASS
validate status = PASS
batch status = PASS
batch pass_count = 2
batch warn_count = 0
batch fail_count = 0
```

### Render 검증

```text
mapping replaced = 4/4
table updated = 1 table
updated cells = 8
zip_ok = true
xml_ok = true
placeholder_remaining = false
missing_expected_values = []
```

### Batch 검증

| 파일 | status | mapping | table | validation |
| --- | --- | --- | --- | --- |
| `batch_001_001.hwpx` | PASS | 4/4 | 8 cells | ZIP/XML PASS |
| `batch_002_001.hwpx` | PASS | 4/4 | 8 cells | ZIP/XML PASS |

## Java Parser Roundtrip

P2 산출물 3개를 기존 Java `HwpxParser`로 직접 읽었다.

대상:

```text
tmp/hwpx_template_engine_hardening/rendered_001.hwpx
tmp/hwpx_template_engine_hardening/batch_001_001.hwpx
tmp/hwpx_template_engine_hardening/batch_002_001.hwpx
```

임시 runner:

```text
tmp/hwpx_template_engine_hardening/JavaRoundtripCheckP2.java
```

결과:

```text
tmp/hwpx_template_engine_hardening/java_roundtrip_results.json
tmp/hwpx_template_engine_hardening/java_roundtrip_results.csv
```

| 파일 | parse | paragraphs | tables | semanticSections | extractedFields | diagnostics | qualityScore | missing expected |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| `rendered_001.hwpx` | PASS | 4 | 1 | 2 | 1 | true | 28 | 0 |
| `batch_001_001.hwpx` | PASS | 4 | 1 | 2 | 1 | true | 28 | 0 |
| `batch_002_001.hwpx` | PASS | 4 | 1 | 2 | 1 | true | 28 | 0 |

판정:

```text
Java parser roundtrip = PASS
parse_success = 3/3
missing_expected_values = 0/3
diagnostics_exists = 3/3
```

주의:

Java console 출력에는 기존 P1과 동일하게 일부 mojibake와 Log4j RollingFileAppender 권한 경고가 발생했다. 그러나 `HwpxParser.parse()` 결과는 3개 모두 `PASS`였고, 결과 JSON 기준으로 missing expected values는 없다.

## 실패 케이스 검증

### Case A: 없는 mapping 파일

명령:

```powershell
python scripts/hwpx/hwpx_template_engine.py render `
  --template "tmp\hwpx_writer_poc\template_seed.hwpx" `
  --output "tmp\hwpx_template_engine_hardening\fail_missing_mapping.hwpx" `
  --mapping-json "tmp\hwpx_template_engine_hardening\not_exists.json" `
  --report-json "tmp\hwpx_template_engine_hardening\fail_missing_mapping_report.json"
```

결과:

```text
status = FAIL
error_type = FileNotFoundError
report_json = 생성됨
```

### Case B: invalid table JSON

명령:

```powershell
python scripts/hwpx/hwpx_template_engine.py render `
  --template "tmp\hwpx_writer_poc\template_seed.hwpx" `
  --output "tmp\hwpx_template_engine_hardening\fail_invalid_table_no_bom.hwpx" `
  --table-json "tmp\hwpx_template_engine_hardening\invalid_table_no_bom.json" `
  --report-json "tmp\hwpx_template_engine_hardening\fail_invalid_table_no_bom_report.json"
```

결과:

```text
status = FAIL
error_type = ValueError
error_message = tables must be a list
report_json = 생성됨
```

## 결론

P2 hardening 판정은 PASS다.

```text
self-test 명령 추가 = PASS
clean output directory 재현 = PASS
render/validate/batch-render = PASS
Java parser roundtrip = PASS
mapping/table override warning = PASS
failure case report = PASS
```

이제 P2는 단순 PoC가 아니라 반복 실행, 자동 검증, 실패 report, Java parser roundtrip까지 갖춘 HWPX template engine CLI 기준선으로 볼 수 있다.

## 남은 한계

```text
이미지 삽입은 P3로 분리
그래프 PNG 삽입은 P4로 분리
신규 HWPX 생성은 P5 이후로 분리
복잡한 표 생성/병합은 후속 템플릿 설계 필요
mapping/table 처리 순서는 table JSON 우선 결과로 검증해야 함
```

## 다음 단계

1. P3: 이미지 포함 템플릿 BinData 교체
2. P4: 그래프 PNG 생성 후 이미지 삽입
3. P5: HWPX 문서 작성 API화
