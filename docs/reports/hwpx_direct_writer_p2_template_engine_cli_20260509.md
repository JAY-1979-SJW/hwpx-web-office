# HWPX Direct Writer P2 Template Engine CLI

## 목적

HWPX direct writer/editor P0/P1 결과를 실제 CLI 도구로 확장했다.

이번 작업은 HWPX 템플릿 기반 문서 생성 도구화 단계이며, 한컴 실행, 한컴 COM, 한컴 GUI, HWP 변환, 서버 배포, Docker 작업을 수행하지 않았다.

## 기준

```text
HEAD = 1b9205f5e3e0312a94adc3d498fc58ffffbb3955
P0 = HWPX direct writer/editor PoC PASS
P1 = Java parser roundtrip PASS
```

## 구현

추가 파일:

```text
scripts/hwpx/hwpx_template_engine.py
```

지원 명령:

```text
render
validate
batch-render
```

기존 재사용 모듈:

```text
scripts/hwpx/hwpx_writer_adapter.py
scripts/hwpx/hwpx_package_inspector.py
```

## CLI

### render

```text
python scripts/hwpx/hwpx_template_engine.py render \
  --template <template.hwpx> \
  --output <rendered.hwpx> \
  --mapping-json <mapping.json> \
  --table-json <table_data.json> \
  --validate \
  --report-json <render_report.json>
```

역할:

- placeholder 치환
- 첫 번째 표 셀 데이터 치환
- HWPX ZIP/XML validation
- render report JSON 생성

### validate

```text
python scripts/hwpx/hwpx_template_engine.py validate \
  --input <rendered.hwpx> \
  --expected-json <expected_values.json> \
  --report-json <validate_report.json>
```

역할:

- ZIP open 검증
- XML parse 검증
- section entry 확인
- placeholder 잔존 여부 확인
- expected values 확인

### batch-render

```text
python scripts/hwpx/hwpx_template_engine.py batch-render \
  --job-json <batch_jobs.json> \
  --output-dir <output_dir> \
  --report-json <batch_report.json>
```

역할:

- 복수 job JSON 기반 렌더링
- 각 job별 render/validate report 생성
- batch summary 생성

## Mapping JSON

입력 예:

```json
{
  "PROJECT_NAME": "테스트 소방공사 P2",
  "BID_DEADLINE": "2026-05-20",
  "AWARD_METHOD": "종합평가낙찰제",
  "CLIENT_NAME": "테스트 발주처 P2"
}
```

치환 규칙:

```text
{{PROJECT_NAME}} -> 테스트 소방공사 P2
{{BID_DEADLINE}} -> 2026-05-20
{{AWARD_METHOD}} -> 종합평가낙찰제
{{CLIENT_NAME}} -> 테스트 발주처 P2
```

report 기록:

```text
mapping_key
placeholder
replacement_length
found_count
replaced_count
```

## Table JSON

입력 예:

```json
{
  "tables": [
    {
      "table_id": "main_summary",
      "mode": "replace_first_table_cells",
      "headers": ["항목", "값"],
      "rows": [
        ["공사명", "테스트 소방공사 P2"],
        ["입찰마감일", "2026-05-20"],
        ["낙찰방법", "종합평가낙찰제"]
      ]
    }
  ]
}
```

P2 지원 mode:

```text
replace_first_table_cells
```

동작:

- 기존 템플릿의 첫 번째 table 구조 유지
- 기존 cell text node를 `headers + rows` 순서로 치환
- 복잡한 표 생성, 병합 셀 생성, 스타일 신규 생성은 후순위

## 테스트 산출물

tmp 하위에만 생성했다.

```text
tmp/hwpx_template_engine_poc/mapping.json
tmp/hwpx_template_engine_poc/table_data.json
tmp/hwpx_template_engine_poc/expected_values.json
tmp/hwpx_template_engine_poc/rendered.hwpx
tmp/hwpx_template_engine_poc/render_report.json
tmp/hwpx_template_engine_poc/validate_report.json
tmp/hwpx_template_engine_poc/batch_jobs.json
tmp/hwpx_template_engine_poc/batch_001.hwpx
tmp/hwpx_template_engine_poc/batch_002.hwpx
tmp/hwpx_template_engine_poc/batch_report.json
```

## Single Render 결과

입력:

```text
template = tmp/hwpx_writer_poc/template_seed.hwpx
mapping = tmp/hwpx_template_engine_poc/mapping.json
table = tmp/hwpx_template_engine_poc/table_data.json
output = tmp/hwpx_template_engine_poc/rendered.hwpx
```

결과:

| 항목 | 결과 |
| --- | --- |
| render status | PASS |
| mapping keys | 4/4 replaced |
| placeholder remaining | false |
| table updated | 1 |
| updated cells | 8 |
| zip_ok | true |
| xml_ok | true |
| missing expected values | 0 |

확인된 expected values:

```text
항목
값
공사명
테스트 소방공사 P2
입찰마감일
2026-05-20
낙찰방법
종합평가낙찰제
```

## Validate 결과

`validate` 명령으로 `rendered.hwpx`를 재검증했다.

결과:

```text
status = PASS
zip_ok = true
xml_ok = true
placeholder_remaining = false
missing_expected_values = []
```

## Batch Render 결과

2건 batch-render를 수행했다.

결과:

| 항목 | 값 |
| --- | ---: |
| job_count | 2 |
| pass_count | 2 |
| warn_count | 0 |
| fail_count | 0 |

출력:

```text
tmp/hwpx_template_engine_poc/batch_001.hwpx
tmp/hwpx_template_engine_poc/batch_002.hwpx
```

두 출력 모두:

```text
zip_ok = true
xml_ok = true
placeholder_remaining = false
missing_expected_values = []
```

## Java Parser Roundtrip

P2 CLI에는 `--roundtrip` 옵션을 추가했지만, 이번 단계에서 안정적인 Java parser CLI 통합은 수행하지 않았다.

현재 상태:

```text
P1에서 tmp runner 기반 Java parser roundtrip PASS 확인 완료
P2에서는 roundtrip 옵션 구조만 마련
stable Java parser CLI/API 연결은 후속 단계
```

따라서 P2 최종 판정은 기능 자체는 PASS이나, Java parser roundtrip 자동 연결은 후속 과제로 남긴다.

## 구현상 주의

P2 샘플 템플릿은 P0에서 만든 `template_seed.hwpx`를 사용한다. 이 템플릿은 일부 placeholder가 첫 번째 표 내부 text node에 존재한다.

따라서 처리 순서는 다음과 같다.

```text
1. mapping placeholder 치환
2. table JSON으로 첫 번째 표 셀 치환
```

이 경우 table 치환이 일부 mapping 치환 결과를 의도적으로 덮어쓸 수 있다. 그래서 최종 output expected-value 검증은 table JSON의 최종 값 기준으로 수행하고, mapping 치환 성공 여부는 `found_count/replaced_count` report로 별도 검증한다.

## 제한

- 이미지 삽입은 P3
- 그래프 PNG 삽입은 P4
- 신규 HWPX 생성은 후순위
- 복잡한 표 생성/병합 셀/스타일 신규 생성은 후순위
- Java parser roundtrip 자동 연결은 다음 단계에서 안정화 필요

## 결론

HWPX direct writer/editor는 P2에서 템플릿 기반 문서 생성 CLI로 확장됐다.

가능해진 것:

```text
template.hwpx + mapping.json + table_data.json
-> rendered.hwpx
-> ZIP/XML validation
-> render/validate/batch report JSON
```

이번 단계 결과:

```text
single render PASS
validate PASS
batch-render 2/2 PASS
```

## 다음 단계

1. P2.1: Java parser roundtrip을 template engine 품질 게이트로 통합
2. P3: 이미지 포함 템플릿 `BinData` 교체
3. P4: 그래프 PNG 생성 후 이미지 교체 엔진 재사용
4. P5: HWPX 문서 작성 API화
