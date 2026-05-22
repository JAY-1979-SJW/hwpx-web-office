# HWPX Direct Writer P50 Full Scenario Runner

## 목적

HWPX direct writer의 대표 흐름을 단일 명령으로 실행하는 전체 시나리오 runner를 추가했다.

기존에는 schema reference, examples, API smoke, regression suite를 각각 실행해야 했다. P50에서는 이 흐름을 `full-scenario` CLI와 `hwpx_full_scenario.py` 모듈로 묶어, HWPX 직접 작성 도구의 현재 안정 경로를 한 번에 검증할 수 있게 했다.

## 구현

### 신규 모듈

```text
scripts/hwpx/hwpx_full_scenario.py
```

역할:

- schema reference 생성
- stable examples 생성
- examples batch compose
- API smoke 실행
- compose regression suite 실행
- 단계별 status 취합
- artifact 경로와 next action 요약

### CLI

```text
python scripts/hwpx/hwpx_template_engine.py full-scenario \
  --template smoke-test.hwpx \
  --out-dir tmp\hwpx_p50_full_scenario \
  --strict-regression \
  --report-json tmp\hwpx_p50_full_scenario_report.json
```

옵션:

```text
--include-experimental
--strict-regression
--report-json
```

### Python facade

```python
from hwpx_api import run_scenario

report = run_scenario(
    "smoke-test.hwpx",
    "tmp/hwpx_p50_full_scenario",
    include_experimental=False,
    strict_regression=True,
)
```

## Stable Scenario 결과

```text
command: python scripts/hwpx/hwpx_template_engine.py full-scenario --template smoke-test.hwpx --out-dir tmp\hwpx_p50_full_scenario --strict-regression --report-json tmp\hwpx_p50_full_scenario_report.json
status: PASS
phase_count: 5
pass_count: 5
warn_count: 0
fail_count: 0
example_job_count: 3
regression_profile_count: 7
```

단계별 결과:

```text
schema_reference: PASS
examples: PASS
examples_batch: PASS
api_smoke: PASS
regression: PASS
```

## Experimental Scenario 결과

```text
command: python scripts/hwpx/hwpx_template_engine.py full-scenario --template smoke-test.hwpx --out-dir tmp\hwpx_p50_full_scenario_experimental --include-experimental --strict-regression --report-json tmp\hwpx_p50_full_scenario_experimental_report.json
status: WARN
phase_count: 5
pass_count: 4
warn_count: 1
fail_count: 0
example_job_count: 4
regression_profile_count: 7
```

WARN 사유:

```text
examples_batch: WARN
reason: complex_section_table_chart uses explicit experimental synthetic picture XML fallback
warning: EXPERIMENTAL_SYNTHETIC_PICTURE_XML
```

이는 P49 정책과 일치한다. 기본 stable path는 visible picture 우선 정책을 따르고, synthetic path는 명시적 experimental 모드에서만 노출된다.

## 모듈화 판단

P50은 새 문서 변형 로직을 추가하지 않았다.

기능 경계:

```text
hwpx_full_scenario.py: orchestration only
hwpx_api.py: public facade
hwpx_api_smoke.py: facade smoke
hwpx_compose_regression.py: regression profiles
hwpx_template_engine.py: CLI entrypoint
```

따라서 전체 시나리오 구현은 기존 기능 모듈을 재사용하는 얇은 orchestration 계층으로 유지됐다.

## 결론

P50 PASS.

HWPX direct writer는 이제 아래 전체 시나리오를 단일 명령으로 검증할 수 있다.

```text
schema reference
→ stable examples
→ examples batch compose
→ API smoke
→ regression suite
→ unified scenario report
```

## 남은 과제

1. Java parser roundtrip을 안정적인 callable gate로 연결
2. committed visible-picture fixture 확보 후 synthetic bootstrap 제거
3. full-scenario 결과를 CI/릴리스 게이트로 연결
4. HWPX 기능 확장 시 full-scenario에 새 phase를 추가
