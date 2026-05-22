# HWPX Direct Writer P46 Visible Picture Template Clone

## 목적

HWPX 이미지 삽입 경로를 기능별로 분리하고, 기존 합성 picture XML 경로와 별도로
한컴이 만든 visible picture 객체를 clone/rebind하는 경로를 first-class compose image mode로 추가했다.

이번 작업은 새 picture XML 구조를 더 추측하는 단계가 아니다. 기존 템플릿에 보이는 그림 객체가 있으면
그 객체를 복제하고 새 BinData 이미지로 연결하는 경로를 도구화하는 것이 목적이다.

## 구현

- `hwpx_job_schema.py`
  - `visible_png_insert`
  - `visible_chart_png`
  - `picture_index` 검증
- `hwpx_composer.py`
  - `visible_png_insert`는 기존 picture 객체 clone/rebind 경로 사용
  - `visible_chart_png`는 chart PNG 생성 후 기존 picture 객체 clone/rebind 경로 사용
  - 기존 `png_insert` / `chart_png`는 synthetic picture XML fallback으로 유지
  - 템플릿에 picture 객체가 없으면 `VISIBLE_PICTURE_TEMPLATE_NOT_FOUND` WARN 처리
- `hwpx_compose_schema_reference.py`
  - visible image modes 문서화
  - synthetic picture XML 한계 명시
- `hwpx_api_failure_smoke.py`
  - visible picture template missing case를 WARN으로 고정 검증

## 샘플 탐색

tracked/non-tmp HWPX 후보에서 기존 visible picture 객체를 탐색했다.

```text
picture_candidates = 0
```

따라서 이번 단계에서는 실제 clone 성공 샘플은 확보하지 못했다. 대신 picture 객체가 없는 템플릿에서
명확한 WARN으로 종료되는 경로를 검증했다.

## 검증

### Schema Reference

```text
schema-reference: PASS
supported_image_modes:
- chart_png
- png_insert
- visible_chart_png
- visible_png_insert
```

### Visible Chart Missing Template

입력:

```text
template: smoke-test.hwpx
mode: visible_chart_png
```

결과:

```text
compose status: WARN
step: visible_image_insert
step status: VISIBLE_PICTURE_TEMPLATE_NOT_FOUND
ZIP/XML validation: PASS
failed_steps: []
```

의미:

```text
템플릿에 기존 picture 객체가 없으면 HWPX를 손상시키지 않고 WARN으로 종료한다.
```

### Failure Smoke

```text
status: PASS
case_count: 8
pass_count: 8
compose_visible_picture_template_missing: WARN
```

### Regression

```text
strict regression: PASS
profile_count: 6
pass_count: 6
warn_count: 0
fail_count: 0
```

기존 `chart_png` synthetic fallback 경로도 회귀 없이 유지됐다.

### API Smoke

```text
API smoke: WARN
원인: 기존 chart_png / section_table_image_chart 경로가 synthetic picture XML warning을 유지
```

이는 기존 정책과 동일한 WARN이다. 이번 P46은 이 경고를 제거하지 않고,
경고를 피할 수 있는 clone-template 모드를 별도 제공하는 단계다.

## 판정

```text
P46 status: PASS_WITH_TEMPLATE_SAMPLE_GAP
```

완료:

```text
visible_png_insert mode 추가
visible_chart_png mode 추가
schema validation 추가
schema reference 반영
picture template missing WARN 경로 검증
failure smoke PASS
strict regression PASS
```

남은 gap:

```text
한컴이 실제 생성한 visible picture 객체 포함 HWPX 템플릿 없음
clone/rebind 성공 경로는 샘플 확보 후 검증 필요
기존 synthetic picture XML fallback은 여전히 EXPERIMENTAL_SYNTHETIC_PICTURE_XML WARN을 낸다
```

## 다음 단계

1. visible picture 객체가 포함된 HWPX 템플릿 확보
2. `visible_png_insert` 실제 clone/rebind PASS 검증
3. `visible_chart_png` 실제 clone/rebind PASS 검증
4. synthetic `png_insert` / `chart_png`를 fallback 전용으로 격하
5. P47: picture template fixture 기반 visible image regression 추가
