# HWPX Direct Writer P4 Structure Builder Foundation

## 목적

기존 HWPX writer는 문단 추가 시 기존 문단 XML을 clone해서 텍스트만 바꾸는 방식이었다.

완전한 HWPX 작성 엔진으로 가려면 clone 기반 수정기를 넘어, 최소 XML 구조를 직접 생성하는 builder 계층이 필요하다.

이번 P4 목표:

```text
1. HWPX XML namespace/element factory 추가
2. p/run/t 문단 XML 직접 생성
3. 기존 section XML에 새 문단 삽입
4. ZIP/XML validation
5. CLI 연결
```

## 구현

### 신규 모듈

```text
scripts/hwpx/hwpx_element_factory.py
```

주요 함수:

```text
hp(tag)
next_paragraph_id(root)
infer_paragraph_defaults(root)
create_text_paragraph(text, paragraph_id, defaults)
append_generated_paragraph(package, text, section_index)
```

### 기존 모듈 연결

```text
scripts/hwpx/hwpx_text_ops.py
scripts/hwpx/hwpx_writer_adapter.py
scripts/hwpx/hwpx_template_engine.py
```

추가 CLI:

```text
python scripts/hwpx/hwpx_template_engine.py paragraph-add
```

## 동작 방식

`paragraph-add`는 기존 문단을 clone하지 않는다.

대신 아래 최소 구조를 직접 생성한다.

```text
p
└─ run
   └─ t
└─ linesegarray
   └─ lineseg
```

스타일 참조는 기존 section의 첫 문단에서 아래 값을 추론한다.

```text
paraPrIDRef
styleIDRef
charPrIDRef
```

문단 id는 기존 p id 중 최대값 + 1로 생성한다.

## 테스트

명령:

```text
python scripts/hwpx/hwpx_template_engine.py paragraph-add \
  --template tmp\hwpx_writer_poc\template_seed.hwpx \
  --output tmp\hwpx_modularization_check\generated_paragraph.hwpx \
  --text "P4 structure builder generated paragraph" \
  --validate \
  --report-json tmp\hwpx_modularization_check\generated_paragraph_report.json
```

결과:

```text
status: PASS
add_result.status: GENERATED_PARAGRAPH_APPEND_PASS
entry: Contents/section0.xml
paragraph_id: 2147483649
ZIP validation: PASS
XML validation: PASS
expected value: found
```

추가 validate:

```text
python scripts/hwpx/hwpx_template_engine.py validate \
  --input tmp\hwpx_modularization_check\generated_paragraph.hwpx \
  --report-json tmp\hwpx_modularization_check\generated_paragraph_validate_report.json
```

결과:

```text
status: PASS
zip_ok: true
xml_ok: true
section_entries: 1
```

## 판정

P4 foundation 판정: `PASS`

의미:

```text
HWPX 문단을 기존 문단 clone 없이 직접 생성하는 최소 builder 계층이 생겼다.
```

## 제한

아직 아래는 후속이다.

```text
문단 서식 세부 제어
글자 서식 세부 제어
줄/위치 layout 정밀 계산
새 표 구조 직접 생성
visible picture XML 직접 생성
머리말/꼬리말/쪽번호
```

## 다음 단계

1. P5: generated table builder
2. P6: style/char/paragraph property resolver
3. P7: visible picture template 기반 clone/rebind 성공 케이스
4. P8: Python API layer (`DocumentBuilder`)
