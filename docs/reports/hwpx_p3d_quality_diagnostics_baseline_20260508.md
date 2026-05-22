# HWPX P3D Quality Diagnostics Baseline

## 목표

`semanticSections`와 `extractedFields` 품질을 사람이 눈으로만 확인하지 않고 자동 진단할 수 있도록 baseline diagnostics를 추가했다.

## 구현 내용

- `DocumentParseResponse.diagnostics` 응답 필드 추가
- `SemanticQualityDiagnostics` 분리 구현
- `HwpxParser` 파이프라인에 diagnostics 계산 연결
- `/hwpx-upload` 분석 품질 진단 요약 표시 추가
- `SemanticQualityDiagnosticsTest` 추가

## diagnostics 데이터

다음 항목을 포함한다.

- `section_count`
- `extracted_field_count`
- `paragraph_field_count`
- `table_field_count`
- `missing_core_sections`
- `missing_core_fields`
- `duplicate_keys`
- `empty_value_fields`
- `low_confidence_fields`
- `section_type_counts`
- `source_counts`
- `normalized_key_counts`
- `confidence_min`
- `confidence_avg`
- `confidence_max`
- `quality_score`
- `warnings`

## 품질 점수 산식

baseline 산식은 100점에서 시작한다.

- 핵심 섹션 누락 1개당 `-8`
- 핵심 필드 누락 1개당 `-5`
- 빈 value 1개당 `-4`
- 중복 key 1개당 `-3`
- low confidence field 1개당 `-2`
- `extractedFields_count = 0`이면 최대 `40`
- `semanticSections_count = 0`이면 최대 `30`
- 최종 점수는 `0~100`으로 제한

## 핵심 섹션 기준

- `document_overview`
- `bid_qualification`
- `submission_documents`
- `schedule`
- `award_method`
- `caution_notes`

## 핵심 필드 기준

- 공고명
- 공사명
- 발주처
- 입찰참가자격
- 제출서류
- 입찰마감일
- 개찰일
- 낙찰방법
- 유의사항

## UI 표시

`/hwpx-upload` 결과 영역에 "분석 품질 진단" 섹션을 추가했다.

표시 항목:

- 품질 점수
- `semanticSections` 수
- `extractedFields` 수
- source 분포
- section_type 분포
- normalized_key 분포
- confidence min/avg/max
- 누락 핵심 섹션
- 누락 핵심 필드
- low confidence count
- duplicate key count
- warnings

## 테스트 결과

| 항목 | 결과 |
| --- | --- |
| `SemanticQualityDiagnosticsTest` | PASS |
| `SemanticKeyValueExtractorTest` | PASS |
| `HwpxParserTest` | PASS |
| `ParseHwpxHandlerTest` | PASS |
| `compileJava` | PASS |
| `installDist` | PASS |
| 전체 `test` | WARN |

전체 테스트는 `237 tests completed, 1 failed`로 종료됐다.
실패 항목은 기존 `FormFieldLocatorIntegrationTest > initializationError` 1건이며, P3D diagnostics 신규 실패는 아니다.

## 제한 사항

- 품질 점수는 baseline 산식이다.
- 실제 공고문 HWPX 샘플 확보 후 점수 가중치와 core field alias 보정이 필요하다.
- G2B 첨부 확보, HWP 다운로드, HWP to HWPX 변환은 이번 범위에서 제외했다.
- `/hwpx-upload` UI는 HTML/JS source 기준으로 구현했으며 실제 브라우저 업로드 E2E는 이번 범위에서 수행하지 않았다.

## 다음 단계

- 실제 HWPX 샘플 확보 시 P3D batch quality audit 실행
- diagnostics 점수 기준 보정
- section/field rule 확장
- HWP만 확보될 경우 HWPX 변환 경로 확정 후 parser 투입

## 최종 판정

WARN

diagnostics baseline 구현, 최소 테스트, 빌드는 PASS다.
전체 테스트는 기존 `FormFieldLocatorIntegrationTest` 1건 실패가 남아 WARN으로 분리한다.
