# HWPX Direct Writer P23 List Numbering Style

## 목적

한컴 실행 없이 HWPX 문단에 번호/목록 스타일을 적용하는 기능을 추가했다. 이번 단계는 paragraph 생성 로직에 직접 섞지 않고, `Contents/header.xml`의 numbering/paragraph property 정의를 만드는 list 전용 모듈로 분리했다.

## 구현

- `scripts/hwpx/hwpx_list_style_ops.py`
  - `apply_list_style_definitions`
  - `create_list_style`
  - `list_refs_from_names`
- `scripts/hwpx/hwpx_composer.py`
  - `style_definitions.list_styles` 적용
  - paragraph `style.list_style` / `style.list_level`을 `paraPrIDRef`로 연결
- `scripts/hwpx/hwpx_job_schema.py`
  - `list_styles` schema 그룹 허용
  - paragraph list style 참조와 `list_level` 검증
- `scripts/hwpx/hwpx_style_ops.py`
  - paragraph style warning에서 list 관련 필드 제외

## Job 예시

```json
{
  "style_definitions": {
    "list_styles": {
      "numbered_main": {
        "type": "number",
        "levels": [
          {"level": 1, "text": "^1.", "numFormat": "DIGIT"},
          {"level": 2, "text": "^2)", "numFormat": "DIGIT"}
        ]
      },
      "bullet_main": {
        "type": "bullet",
        "levels": [
          {"level": 1, "text": "-", "numFormat": "USER_CHAR"}
        ]
      }
    }
  }
}
```

## 테스트

대상 템플릿:

```text
samples/[별지 10] 레미콘(아스콘) 공장 정기점검  결과 보고(건설공사 품질관리 업무지침).hwpx
```

실행:

```text
python scripts/hwpx/hwpx_template_engine.py validate-job --job-json tmp/hwpx_p23_list_style/compose_list_job.json
python scripts/hwpx/hwpx_template_engine.py compose --job-json tmp/hwpx_p23_list_style/compose_list_job.json
```

결과:

```text
validate-job: PASS
compose: PASS
ZIP/XML validation: PASS
expected values: PASS
```

추가된 문단:

```text
P23 numbered list level 1 -> paraPrIDRef 21
P23 numbered list level 2 -> paraPrIDRef 22
P23 bullet list item -> paraPrIDRef 23
```

추가된 outline heading:

```text
paraPrIDRef 21 -> OUTLINE idRef 2 level 0
paraPrIDRef 22 -> OUTLINE idRef 2 level 1
paraPrIDRef 23 -> OUTLINE idRef 3 level 0
```

## Java Parser Roundtrip

대상:

```text
tmp/hwpx_p23_list_style/composed_list_style.hwpx
```

결과:

```text
parse_status: PASS
paragraph_count: 10
table_count: 2
semantic_sections_count: 2
extracted_fields_count: 1
diagnostics_exists: true
quality_score: 28
warning_count: 0
error_count: 0
```

Java 실행 중 기존 Log4j file appender 권한 경고가 출력됐지만, parser 결과 JSON은 정상 생성됐고 parse status는 PASS다.

## Failure Case

invalid job:

```json
{
  "style": {
    "list_style": "numbered_main",
    "list_level": 0
  }
}
```

결과:

```text
status: FAIL
LIST_LEVEL_INVALID
```

## 결론

```text
P23_LIST_NUMBERING_STYLE: PASS
```

번호/불릿 스타일은 전용 모듈로 분리됐고, composer의 선언형 job에서 문단에 적용 가능하다. ZIP/XML validation과 Java HwpxParser roundtrip 모두 통과했다.

## 제한

- 한컴 시각 확인은 수행하지 않았다.
- 기존 템플릿에 `Contents/header.xml`이 있어야 한다.
- 복잡한 다단계 outline preset과 자동 번호 restart 제어는 후속이다.

## 다음 단계

1. P24: 머리말/꼬리말/쪽 번호 구조 분석 및 최소 생성
2. P25: list restart / outline preset 고도화
3. P26: 문단 스타일 API 통합 정리
