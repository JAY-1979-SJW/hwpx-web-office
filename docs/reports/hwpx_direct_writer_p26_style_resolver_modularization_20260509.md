# HWPX Direct Writer P26 Style Resolver Modularization

## 목적

HWPX direct writer가 커지면서 composer 내부에 문단/표/이미지 스타일 연결 로직이 누적되고 있었다. 이번 P26에서는 기능별 모듈화 원칙에 맞춰 스타일 참조 해석을 전용 모듈로 분리했다.

목표는 새 표현 기능을 추가하기 전에 composer를 orchestration 계층으로 유지하고, 스타일별 세부 처리는 별도 resolver가 담당하도록 정리하는 것이다.

## 구현

### 신규 모듈

```text
scripts/hwpx/hwpx_style_resolver.py
```

역할:

```text
resolve_paragraph_style()
resolve_table_style()
resolve_image_layout()
```

### composer 정리

수정 파일:

```text
scripts/hwpx/hwpx_composer.py
```

변경 전:

```text
composer가 paragraph style normalize
composer가 char/para named style resolve
composer가 list style resolve
composer가 table border/cell/dimension/merge/layout refs resolve
composer가 image layout normalize
```

변경 후:

```text
composer는 resolve_* 호출만 수행
style_resolver가 하위 스타일 모듈을 조합
```

## 모듈 경계

```text
hwpx_composer.py
- job 실행 순서 orchestration
- expected values/validation/report 조립

hwpx_style_resolver.py
- paragraph/table/image style block 해석
- named style map과 direct refs 병합
- style warning 수집

개별 style modules
- header style 생성
- list style 생성
- table border/cell/dimension/merge/layout refs 생성
```

## 회귀 검증

### P25 list restart regression

명령:

```text
python scripts/hwpx/hwpx_template_engine.py compose --job-json tmp/hwpx_p25_list_restart/compose_outline_preset_job.json
```

결과:

```text
status: PASS
ZIP/XML validation: PASS
missing_expected_values: []
```

### P20 table cell layout regression

명령:

```text
python scripts/hwpx/hwpx_template_engine.py compose --job-json tmp/hwpx_p20_cell_layout/compose_cell_layout_job.json
```

결과:

```text
status: PASS
table_create: GENERATED_TABLE_APPEND_PASS
ZIP/XML validation: PASS
missing_expected_values: []
```

### P18 merged cells regression

명령:

```text
python scripts/hwpx/hwpx_template_engine.py compose --job-json tmp/hwpx_p18_merged_cells/compose_merged_cells_job.json
```

결과:

```text
status: PASS
table_create: GENERATED_TABLE_APPEND_PASS
ZIP/XML validation: PASS
missing_expected_values: []
```

### Java parser roundtrip

대상:

```text
tmp/hwpx_p20_cell_layout/composed_cell_layout.hwpx
```

결과:

```text
parse_status: PASS
paragraph_count: 2
table_count: 1
diagnostics_exists: true
warning_count: 0
error_count: 0
```

Log4j file appender 권한 경고는 기존 로컬 roundtrip 검증과 동일한 로그 경로 문제이며, parser 결과는 PASS다.

## 수정 중 발견한 문제

초기 분리 후 `cell_address_refs_from_names()` 호출에 `style_maps` 인자가 누락되어 표 스타일 회귀 검증이 실패했다.

수정:

```text
cell_address_refs_from_names(style, style_maps)
```

이후 P20/P18/P25 compose가 모두 PASS했다.

## 판정

```text
P26_STYLE_RESOLVER_MODULARIZATION: PASS
```

## 남은 제한

- 새 스타일 기능이 아니라 composer 내부 구조 정리 단계다.
- 한컴 GUI 시각 확인은 수행하지 않았다.
- 문단/표/이미지 외 page/header/footer style resolver는 아직 별도 계층으로 묶지 않았다.

## 다음 단계

1. P27: composer job schema/examples 문서화
2. P28: visible header/footer fixture 확보 시 본문 표시 header/footer 생성
3. P29: style resolver에 page/header/footer resolver 계층 추가
