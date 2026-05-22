# HWPX Direct Writer Editor PoC

## 목적

한컴 COM/GUI 없이 HWPX ZIP/XML 패키지를 직접 읽고 수정하는 writer/editor PoC를 구현했다.

이번 작업은 HWP 변환이 아니며, 한컴 프로그램 실행, COM 자동화, GUI 자동화, 레지스트리 변경을 수행하지 않았다. 목표는 검증된 HWPX 템플릿 구조를 유지하면서 텍스트 치환, 문단 추가, 표 데이터 치환이 가능한지 확인하는 것이다.

## 구현 파일

- `scripts/hwpx/hwpx_package_inspector.py`
- `scripts/hwpx/hwpx_writer_adapter.py`

## 입력 샘플

사용한 seed/template 후보:

```text
samples/[별표 8] 평가사 자격기준(제28조제2항 관련)(건설공사 품질관리 업무지침).hwpx
```

선정 이유:

- repo에 이미 존재하는 실제 HWPX 샘플
- 크기 9,826 bytes로 작음
- `mimetype`, `settings.xml`, `Contents/header.xml`, `Contents/section0.xml` 포함
- section XML과 표 후보가 존재해 writer/editor PoC에 적합

## Package Inspection

`hwpx_package_inspector.py`로 확인한 주요 구조:

| 항목 | 값 |
| --- | --- |
| ZIP | PASS |
| entry count | 10 |
| XML entries | 8 |
| section entries | 1 |
| has mimetype | true |
| has settings | true |
| has header | true |
| text node count | 40 |
| table candidate count | 1 |
| image candidate count | 0 |

산출물:

```text
tmp/hwpx_writer_poc/inspect.json
tmp/hwpx_writer_poc/inspect.txt
```

## Writer Adapter

구현한 기본 객체:

- `HwpxPackage`
  - ZIP 엔트리 읽기
  - XML 엔트리 식별
  - XML 읽기/쓰기
  - 패키지 재작성
- `HwpxEditor`
  - placeholder 주입
  - placeholder 치환
  - 기존 문단 노드 clone 후 문단 추가
  - 기존 표 노드의 셀 텍스트 치환
  - 기존 이미지 BinData 교체 후보 처리
- `HwpxValidator`
  - ZIP 검증
  - XML parse 검증
  - section/mimetype 존재 확인

CLI:

```text
python scripts/hwpx/hwpx_package_inspector.py --input <file.hwpx> --out <inspect.json>
python scripts/hwpx/hwpx_writer_adapter.py inspect --input <file.hwpx> --out <validate.json>
python scripts/hwpx/hwpx_writer_adapter.py replace --input <template.hwpx> --output <out.hwpx> --mapping-json <mapping.json>
python scripts/hwpx/hwpx_writer_adapter.py self-test --sample <sample.hwpx> --out-dir tmp/hwpx_writer_poc
```

## PoC 결과

### 1. Template Seed

기존 HWPX를 `tmp/hwpx_writer_poc/template_seed.hwpx`로 복사한 뒤, section XML의 안전한 text node 4개를 placeholder로 바꿨다.

주입 placeholder:

```text
{{PROJECT_NAME}}
{{BID_DEADLINE}}
{{AWARD_METHOD}}
{{CLIENT_NAME}}
```

결과:

```text
status = PASS
entry = Contents/section0.xml
ZIP/XML validation = PASS
```

### 2. Placeholder Replacement

mapping:

```json
{
  "PROJECT_NAME": "테스트 소방공사",
  "BID_DEADLINE": "2026-05-15",
  "AWARD_METHOD": "제한최저가",
  "CLIENT_NAME": "테스트 발주처"
}
```

출력:

```text
tmp/hwpx_writer_poc/template_replaced.hwpx
```

결과:

```text
status = PASS
replacements = 4
placeholder_remaining = false
replaced values found = true
ZIP/XML validation = PASS
```

### 3. Paragraph Append

기존 section XML에서 첫 문단 노드를 찾고, 그 문단을 clone한 뒤 텍스트만 바꿔 마지막에 추가했다.

추가 문단:

```text
이 문단은 HWPX direct writer/editor PoC에서 추가되었습니다.
```

출력:

```text
tmp/hwpx_writer_poc/paragraph_added.hwpx
```

결과:

```text
status = PASS
entry = Contents/section0.xml
cloned_tag = p
ZIP/XML validation = PASS
```

### 4. Table Update

기존 section XML에서 표 후보를 찾고, 기존 표 구조를 유지한 채 셀 text node를 치환했다.

입력 데이터:

```text
항목 | 값
공사명 | 테스트 소방공사
입찰마감일 | 2026-05-15
낙찰방법 | 제한최저가
```

출력:

```text
tmp/hwpx_writer_poc/table_updated.hwpx
```

결과:

```text
status = PASS
cell_text_nodes_updated = 8
ZIP/XML validation = PASS
```

### 5. Chart PNG Generation

`matplotlib`이 현재 Python 환경에 설치되어 있지 않아 PNG 그래프 생성은 보류했다.

결과:

```text
status = CHART_IMAGE_GENERATION_PENDING
reason = No module named 'matplotlib'
```

새 패키지 설치 금지 원칙에 따라 설치는 수행하지 않았다.

### 6. Image Insert / Replace

사용한 seed HWPX에는 `BinData` 이미지 엔트리가 없었다. 이번 PoC는 구조를 확신하지 못하는 새 이미지 참조 삽입을 강제로 수행하지 않았다.

결과:

```text
status = IMAGE_INSERT_PENDING
reason = chart_png_not_available
```

후속 작업에서는 이미지가 포함된 HWPX 템플릿을 기준으로 기존 BinData 교체 방식부터 검증하는 것이 안전하다.

### 7. New Document Generation

완전 신규 HWPX 생성은 이번 범위에서 보류했다.

결과:

```text
status = NEW_DOCUMENT_GENERATION_PENDING
reason = template-first PoC only
```

현재 전략은 새 HWPX를 처음부터 조립하는 것이 아니라, 한컴 또는 검증된 도구로 만든 템플릿 구조를 유지하면서 편집하는 방식이다.

## Roundtrip Validation

이번 self-test에서 생성된 HWPX 산출물은 모두 ZIP/XML 검증을 통과했다.

검증된 산출물:

```text
tmp/hwpx_writer_poc/template_seed.hwpx
tmp/hwpx_writer_poc/template_replaced.hwpx
tmp/hwpx_writer_poc/paragraph_added.hwpx
tmp/hwpx_writer_poc/table_updated.hwpx
```

검증 결과:

```text
zip_ok = true
xml_ok = true
xml_errors = []
has_mimetype = true
section_entries = 1
```

기존 Java `/parse-hwpx` parser roundtrip은 이번 작업에서 실행하지 않았다. 서버/Docker 작업 없이 가능한 ZIP/XML roundtrip까지만 수행했으므로, 기존 parser 연동 검증은 후속 단계로 둔다.

## 기능별 판정

| 기능 | 판정 | 근거 |
| --- | --- | --- |
| HWPX ZIP 구조 읽기 | PASS | entry/XML/section/BinData 식별 |
| XML 파일 읽기/쓰기 | PASS | XML parse 및 재패키징 성공 |
| placeholder 치환 | PASS | 4개 치환, placeholder 미잔존 |
| HWPX ZIP 재패키징 | PASS | 생성 산출물 ZIP 정상 |
| 문단 추가 | PASS | 기존 문단 clone 후 텍스트 변경 |
| 표 삽입/치환 | PASS | 기존 표 셀 text node 8개 치환 |
| 그래프 PNG 생성 | PENDING | matplotlib 미설치 |
| 이미지 삽입 | PENDING | seed에 BinData 이미지 없음 |
| 신규 HWPX 생성 | PENDING | template-first 범위 유지 |
| 기존 parser roundtrip | WARN | ZIP/XML validation만 수행 |

## 한계

- 복잡한 표 병합, row/col span 신규 생성은 미구현
- 한컴 native chart 객체 생성은 미구현
- 누름틀/필드 객체 신규 생성은 미구현
- 머리말/꼬리말, 쪽 번호, 목차 생성은 미구현
- 이미지 신규 삽입은 참조 구조 확정 전까지 보류
- ElementTree 재직렬화로 XML prefix 표현이 바뀔 수 있으므로, 생산용 엔진에서는 namespace/prefix 보존 전략이 필요

## 결론

HWPX를 한컴 실행 없이 직접 수정하는 기본 경로는 가능하다.

이번 PoC에서 확인된 즉시 가능한 범위:

```text
HWPX 템플릿 기반 placeholder 치환
기존 문단 구조 clone 후 문단 추가
기존 표 구조 유지 후 셀 값 치환
ZIP/XML 재패키징 및 검증
```

따라서 문서 작성/서식 자동화의 1차 전략은 다음이 타당하다.

```text
1. 한컴 또는 SDK로 골격 템플릿 HWPX를 만든다.
2. 애플리케이션은 HWPX ZIP/XML을 직접 수정한다.
3. 반복 데이터, 표, 문단, 기본 텍스트는 direct writer가 처리한다.
4. 이미지/그래프는 이미지 포함 템플릿 기반 교체부터 확장한다.
5. 완전 신규 HWPX 생성은 구조 안정화 후 진행한다.
```

## 다음 단계

1. HWPX template engine API 설계
2. 이미지가 포함된 HWPX 템플릿으로 BinData 교체 검증
3. 표 스타일/레이아웃 보존 테스트 확대
4. 기존 Java HWPX parser roundtrip 자동 검증 연결
5. 문서 작성 DSL 또는 Markdown-like 입력 변환기 설계
6. HWPX-first 문서 생성 엔진을 변환 router와 분리 구현
