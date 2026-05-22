# HWPX Direct Writer P47 Visible Picture Clone Regression

## 목적

P46에서 추가한 `visible_png_insert` / `visible_chart_png` 경로의 성공 케이스를 회귀 테스트에 편입했다.

P46에서는 tracked/non-tmp HWPX 샘플 중 기존 visible picture 객체가 없어 `VISIBLE_PICTURE_TEMPLATE_NOT_FOUND`
WARN 경로만 검증했다. P47에서는 별도 바이너리 fixture를 repo에 추가하지 않고, 회귀 실행 중 임시 HWPX를
만드는 2단계 방식으로 clone/rebind 성공 경로를 검증했다.

## 구현

수정 파일:

```text
scripts/hwpx/hwpx_compose_regression.py
```

추가 regression profile:

```text
visible_picture_clone
```

동작:

1. 기존 `image_chart` profile이 synthetic picture 객체가 포함된 임시 HWPX를 생성한다.
2. `visible_picture_clone` profile은 그 임시 HWPX를 template으로 사용한다.
3. `visible_chart_png`가 새 chart PNG를 생성한다.
4. 기존 picture 객체를 clone하고 새 BinData 이미지로 rebind한다.
5. package audit로 BinData/image reference/expected text를 검증한다.

## 검증 결과

실행:

```text
python scripts/hwpx/hwpx_compose_regression.py run --template smoke-test.hwpx --out-dir tmp/hwpx_p47_visible_clone_regression --strict --report-json tmp/hwpx_p47_visible_clone_regression/report.json
```

결과:

```text
status: PASS
profile_count: 7
pass_count: 7
warn_count: 0
fail_count: 0
```

신규 profile 결과:

```text
profile: visible_picture_clone
compose_status: PASS
audit_status: PASS
visible_clone_insert: PASS
bindata_image_count: 2
image_reference_count: 11
missing_expected_values: []
```

## 판정

```text
P47: PASS
```

완료:

```text
visible_chart_png clone/rebind 성공 경로 검증
VISIBLE_IMAGE_INSERT_PASS 확인
strict regression 7/7 PASS
repo에 HWPX/PNG fixture 추가 없음
```

제한:

```text
이번 fixture의 원본 picture 객체는 회귀 중 생성한 synthetic picture XML이다.
한컴이 직접 생성한 visible picture 객체 기반 검증은 아직 별도 샘플이 필요하다.
한컴 시각 확인은 미실행이다.
```

## 다음 단계

1. P48: image mode routing policy 정리
   - visible_* 모드를 우선 사용
   - picture template이 없을 때 synthetic fallback을 명시적으로 선택
2. P49: 한컴 생성 picture template 샘플 확보 후 clone/rebind 재검증
3. P50: chart/image API를 문서 작성 Builder에 더 명확히 노출
