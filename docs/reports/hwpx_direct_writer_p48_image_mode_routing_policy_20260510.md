# HWPX Direct Writer P48 Image Mode Routing Policy

## 목적

P46/P47에서 visible picture clone 경로를 추가하고 검증했으므로, 이미지 삽입 정책을 모듈화했다.

목표는 아래처럼 명확하다.

```text
기본 권장 경로: visible_png_insert / visible_chart_png
명시적 fallback: png_insert / chart_png
```

visible 모드는 템플릿에 기존 picture 객체가 있을 때 clone/rebind로 이미지를 삽입한다.
synthetic 모드는 템플릿 picture 객체가 없을 때 직접 picture XML을 생성하는 fallback이며,
`EXPERIMENTAL_SYNTHETIC_PICTURE_XML` 경고를 유지한다.

## 구현

### 정책 모듈

추가:

```text
scripts/hwpx/hwpx_image_policy.py
```

역할:

```text
SUPPORTED_IMAGE_MODES
VISIBLE_IMAGE_MODES
SYNTHETIC_IMAGE_MODES
normalize_image_mode
image_step_name
visible_template_missing_warning
```

### Schema / Composer

변경:

```text
scripts/hwpx/hwpx_job_schema.py
scripts/hwpx/hwpx_composer.py
scripts/hwpx/hwpx_compose_schema_reference.py
```

효과:

```text
image mode 정의를 정책 모듈로 통합
visible mode와 synthetic mode의 step 이름/경고 정책 통합
schema reference에 visible 우선, synthetic fallback 정책 명시
```

### Builder API

변경:

```text
scripts/hwpx/hwpx_document_builder.py
```

추가:

```text
visible_image_png()
synthetic_image_png()
visible_chart_png()
synthetic_chart_png()
```

기존 `image_png()` / `chart_png()`는 호환성을 위해 synthetic 기본값을 유지한다.
대신 `prefer_visible=True` 또는 전용 visible 메서드를 통해 clone/rebind 경로를 사용한다.

### Picture Rebind Guard

변경:

```text
scripts/hwpx/hwpx_picture_ops.py
```

수정:

```text
이미지 참조 속성만 rebind하도록 제한
textFlow="BOTH_SIDES" 같은 비이미지 속성을 잘못 변경하지 않도록 보강
```

## 검증

### AST

```text
hwpx_image_policy.py: PASS
hwpx_job_schema.py: PASS
hwpx_composer.py: PASS
hwpx_document_builder.py: PASS
hwpx_compose_schema_reference.py: PASS
hwpx_api_smoke.py: PASS
hwpx_picture_ops.py: PASS
```

### Schema Reference

```text
schema-reference: PASS
supported_image_modes:
- chart_png
- png_insert
- visible_chart_png
- visible_png_insert
```

### Regression

```text
strict regression: PASS
profile_count: 7
pass_count: 7
warn_count: 0
fail_count: 0
visible_picture_clone: PASS
```

### API Smoke

```text
API smoke: WARN
visible_builder_compose: PASS
visible_builder_validate: PASS
```

API smoke가 WARN인 이유:

```text
기존 examples/batch에 synthetic chart fallback profile이 남아 있어 EXPERIMENTAL_SYNTHETIC_PICTURE_XML 경고가 유지됨
```

이번 작업에서 새로 추가한 Builder visible chart 경로는 PASS다.

### Rebind Guard 확인

`visible_builder_compose`의 clone result:

```text
changed:
- tag: img
  attribute: binaryItemIDRef
  old: p44_builder_chart
  new: p48_builder_visible_chart
```

이전처럼 `textFlow` 같은 비이미지 속성을 변경하지 않는다.

## 판정

```text
P48: PASS_WITH_SYNTHETIC_FALLBACK_WARN
```

완료:

```text
이미지 정책 모듈화
visible/synthetic mode 분리
Builder visible image/chart API 추가
schema reference 반영
visible builder smoke PASS
strict regression PASS
비이미지 속성 rebind 버그 수정
```

남은 항목:

```text
기존 example profile의 synthetic chart 경고 제거는 별도 P49에서 처리
한컴이 직접 만든 picture template 샘플 기반 시각 검증은 별도 필요
```

## 다음 단계

1. P49: compose examples의 image profile을 visible-template-aware 구조로 재정리
2. P50: image placeholder template acquisition 또는 generated fixture promotion 정책 결정
3. P51: chart/image Builder examples를 visible 우선 API로 정리
