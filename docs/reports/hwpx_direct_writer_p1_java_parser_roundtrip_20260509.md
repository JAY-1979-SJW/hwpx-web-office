# HWPX Direct Writer P1 Java Parser Roundtrip

## 목적

P0에서 HWPX ZIP/XML 직접 writer/editor로 생성한 산출물을 기존 Java `HwpxParser`로 다시 읽어 roundtrip 호환성을 검증했다.

이번 작업은 검증 단계이며, 한컴 실행, 한컴 COM, 한컴 GUI, HWP 변환, 서버 배포, Docker rebuild/restart를 수행하지 않았다.

## 기준

```text
HEAD = 2b7701c072bd36298317a18318c55fca8e747b66
P0 기능 commit = cfc858f feat(hwpx): add direct writer editor PoC
P0 devlog commit = 2b7701c docs: devlog cfc858f
```

P0 완료 범위:

```text
placeholder 치환 PASS
문단 추가 PASS
기존 표 셀 텍스트 치환 PASS
ZIP/XML validation PASS
```

## 대상 파일

P0 self-test 산출물 3개를 검증했다.

```text
tmp/hwpx_writer_poc/template_replaced.hwpx
tmp/hwpx_writer_poc/paragraph_added.hwpx
tmp/hwpx_writer_poc/table_updated.hwpx
```

## 검증 방법

서버를 띄우지 않고 기존 빌드 산출물의 classpath를 사용해 `HwpxParser`를 직접 호출했다.

임시 runner:

```text
tmp/hwpx_writer_poc/JavaRoundtripCheck.java
```

사용한 주요 classpath:

```text
%USERPROFILE%\.gradle-build\office-analysis-engine\classes\java\main
%USERPROFILE%\.gradle-build\office-analysis-engine\install\office-analysis-engine\lib\*
```

결과 산출물:

```text
tmp/hwpx_writer_poc/java_roundtrip_results.json
tmp/hwpx_writer_poc/java_roundtrip_results.csv
```

## 검증 항목

각 파일에 대해 아래를 확인했다.

```text
parse_status
paragraph_count
table_count
semantic_sections_count
extracted_fields_count
diagnostics_exists
quality_score
expected_values_found
missing_expected_values
error
```

## Roundtrip 결과

| 파일 | parse | paragraphs | tables | semanticSections | extractedFields | diagnostics | qualityScore | expected values |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| `template_replaced.hwpx` | PASS | 4 | 1 | 2 | 1 | true | 28 | 4/4 |
| `paragraph_added.hwpx` | PASS | 5 | 1 | 2 | 1 | true | 28 | 1/1 |
| `table_updated.hwpx` | PASS | 5 | 1 | 2 | 1 | true | 28 | 6/6 |

## Expected Value 검증

### template_replaced.hwpx

기대값:

```text
테스트 소방공사
2026-05-15
제한최저가
테스트 발주처
```

결과:

```text
found = 4
missing = 0
```

### paragraph_added.hwpx

기대값:

```text
HWPX direct writer/editor PoC에서 추가되었습니다
```

결과:

```text
found = 1
missing = 0
```

### table_updated.hwpx

기대값:

```text
공사명
테스트 소방공사
입찰마감일
2026-05-15
낙찰방법
제한최저가
```

결과:

```text
found = 6
missing = 0
```

## Parser 결과

3개 산출물 모두 기존 Java parser에서 `response.ok = true`로 처리됐다.

확인된 결과:

```text
parse success = true
paragraphs = 확인됨
tables = 확인됨
semanticSections = 확인됨
extractedFields = 확인됨
diagnostics = 확인됨
```

`paragraph_added.hwpx`는 P0에서 clone 추가한 문단이 parser 결과에 반영되어 paragraph count가 4에서 5로 증가했다.

`table_updated.hwpx`는 기존 표 구조를 유지한 셀 텍스트 치환 결과가 parser의 table/text 수집 경로에서 확인됐다.

## 주의 사항

Java runner 콘솔과 CSV를 PowerShell에서 표시할 때 일부 한글이 mojibake로 보인다. 다만 검증은 같은 JVM 문자열 내에서 expected value 포함 여부를 비교했고, `missing_expected_values = []`로 기록됐다.

따라서 이번 이슈는 parser 실패가 아니라 콘솔/CSV 표시 인코딩 문제로 분리한다.

또한 Java 실행 중 Log4j `RollingFileAppender`가 사용자 홈 하위 `app/haehan-platform/logs/*.log` 파일을 열지 못했다는 경고가 출력됐다. 이 경고는 로깅 파일 권한/경로 문제이며, `HwpxParser.parse()` 결과는 3개 파일 모두 `PASS`로 반환됐다.

## 문제 분리

| 구분 | 판정 | 근거 |
| --- | --- | --- |
| writer XML 구조 문제 | 없음 | Java parser가 3개 파일 모두 parse PASS |
| parser 문제 | 없음 | paragraphs/tables/diagnostics 생성 |
| semantic extraction 한계 | 경미 | semanticSections/extractedFields는 생성되지만 qualityScore 28로 낮음 |
| 표시 인코딩 문제 | 있음 | PowerShell 표시에서 한글 mojibake 발생 |
| Log4j 파일 appender 경고 | 있음 | parse 결과에는 영향 없음 |

## 결론

P1 roundtrip은 PASS다.

```text
P0 direct writer/editor 산출물
→ Java HwpxParser parse 성공
→ expected values 확인
→ paragraph/table 구조 확인
→ diagnostics 존재
```

이번 검증으로 HWPX direct writer/editor의 P0 결과물이 기존 Java parser와 호환된다는 것을 확인했다.

## 다음 단계

1. P2: 템플릿 엔진 CLI/API화
2. mapping JSON + table JSON 입력 스키마 고정
3. 결과 HWPX 생성 후 Java parser roundtrip을 자동 품질 게이트로 연결
4. P3: 이미지 포함 템플릿으로 `BinData` 교체 검증
5. 표시 인코딩 문제는 runner 출력 UTF-8/CSV BOM 정책으로 별도 정리
