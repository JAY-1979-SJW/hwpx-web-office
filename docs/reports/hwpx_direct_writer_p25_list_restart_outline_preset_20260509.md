# HWPX Direct Writer P25 List Restart Outline Preset

## 목적

HWPX direct writer의 목록/개요 기능을 강화했다. P23에서 기본 list style을 생성한 뒤, 이번 P25에서는 재시작/이어가기 번호와 사전 정의 outline preset을 job schema와 composer 경로에서 검증했다.

## 구현

- `scripts/hwpx/hwpx_list_style_ops.py`
  - `OUTLINE_PRESETS` 추가
  - `decimal`, `korean`, `mixed_legal`, `bullet_dash` preset 정의
  - `restart=true`이면 numbering `start=0`
  - `restart=false`이면 `continue_from` 값을 numbering `start`로 반영
  - level별 `paraHead` 생성과 `start_number` 반영
- `scripts/hwpx/hwpx_job_schema.py`
  - list style preset 검증
  - `start_number`, `continue_from`, `levels[].level`, `levels[].start` 범위 검증
  - unsupported preset을 schema error로 차단

## 테스트 입력

템플릿:

```text
samples/[별표 8] 평가사 자격기준(제28조제2항 관련)(건설공사 품질관리 업무지침).hwpx
```

성공 job:

```text
tmp/hwpx_p25_list_restart/compose_outline_preset_job.json
```

실패 job:

```text
tmp/hwpx_p25_list_restart/invalid_list_preset_job.json
```

## 검증 결과

### schema validation

성공 job:

```text
status: PASS
paragraphs: 3
warnings: []
errors: []
```

실패 job:

```text
status: FAIL
errors:
- LIST_PRESET_UNSUPPORTED
- LIST_START_INVALID
- LIST_LEVEL_INVALID
- LIST_START_INVALID
```

### compose

출력:

```text
tmp/hwpx_p25_list_restart/composed_outline_preset.hwpx
```

결과:

```text
status: PASS
ZIP/XML validation: PASS
missing_expected_values: []
```

추가 문단:

```text
P25 legal outline level 1
P25 legal outline level 2
P25 decimal continued level 1
```

### numbering/paraHead 검사

`Contents/header.xml`에 새 numbering이 추가됐다.

```text
legal_outline:
- numbering start: 0
- paraHead start: 3
- level 1: DIGIT / ^1.
- level 2: HANGUL_SYLLABLE / ^2.
- level 3: DIGIT / ^3)
- level 4: HANGUL_SYLLABLE / ^4)

continued_decimal:
- numbering start: 5
- paraHead start: 6
- level 1: DIGIT / ^1.
- level 2: DIGIT / ^2)
- level 3: DIGIT / (^3)
```

`Contents/section0.xml`의 추가 문단은 생성된 `paraPrIDRef`를 참조했다.

```text
P25 legal outline level 1 -> paraPrIDRef 17
P25 legal outline level 2 -> paraPrIDRef 18
P25 decimal continued level 1 -> paraPrIDRef 21
```

### Java parser roundtrip

대상:

```text
tmp/hwpx_p25_list_restart/composed_outline_preset.hwpx
```

결과:

```text
parse_status: PASS
paragraph_count: 7
table_count: 1
semantic_sections_count: 2
extracted_fields_count: 1
diagnostics_exists: true
quality_score: 28
warning_count: 0
error_count: 0
```

Log4j file appender 권한 경고는 기존 roundtrip 검증에서도 발생하던 로컬 로그 경로 문제이며, parser 결과는 PASS다.

## 판정

```text
P25_LIST_RESTART_OUTLINE_PRESET: PASS
```

## 제한

- 한컴 GUI 시각 확인은 수행하지 않았다.
- 실제 화면에서 번호가 어떻게 렌더링되는지는 한컴 시각 검증이 필요하다.
- 이어가기 번호는 HWPX numbering `start` metadata를 기준으로 반영한다.
- 복잡한 다단계 목록 간 상호 참조나 문서 중간 재시작 시나리오는 후속 검증이 필요하다.

## 다음 단계

1. P26: paragraph style API consolidation
2. P27: visible header/footer fixture 확보 후 본문 표시 header/footer 생성
3. P28: 문서 생성 job schema 문서화 및 sample job 정리
