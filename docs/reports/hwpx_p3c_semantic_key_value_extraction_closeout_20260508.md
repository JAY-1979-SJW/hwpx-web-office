# HWPX P3C Semantic Key-Value Extraction Closeout

## 최종 판정

PASS

## 배포 기준

- local HEAD: `f4565233de6998eb61965bcd14c4876869148c55`
- github/main HEAD: `f4565233de6998eb61965bcd14c4876869148c55`
- server/main bare repo HEAD: `f4565233de6998eb61965bcd14c4876869148c55`
- server working tree HEAD: `f4565233de6998eb61965bcd14c4876869148c55`
- server HEAD: `f4565233de6998eb61965bcd14c4876869148c55`

## 구현 범위

- `ExtractedField` DTO 추가
- `DocumentParseResponse.extractedFields` 응답 필드 추가
- `SemanticKeyValueExtractor` 구현
- paragraph `key:value` / `key=value` 기반 semantic field 추출
- table 2-column header/value 기반 semantic field 추출
- `normalized_key` 생성
- `confidence` 계산
- `source` 추적: `paragraph` / `table`
- `/hwpx-upload` UI 표시

## 서버 검증 결과

- Docker rebuild/restart: PASS
- health: PASS
- `/parse-hwpx`: PASS
- semanticSections_count: `8`
- extractedFields_count: `12`
- paragraph source: `9`
- table source: `3`
- missing: `[]`

## UI 검증 결과

- 추출된 필드 섹션: PASS
- 정규 키 표시: PASS
- 출처 표시: PASS
- confidence 표시: PASS
- extraction_method 표시: PASS
- 기존 semanticSections 영향 없음

## 테스트 결과

- `SemanticKeyValueExtractorTest`: PASS
- `HwpxParserTest`: PASS
- `ParseHwpxHandlerTest`: PASS
- `compileJava`: PASS
- `installDist`: PASS
- 전체 테스트의 기존 `FormFieldLocatorIntegrationTest` 1건 실패는 P3C와 무관

## 남은 WARN

- `build/hwpx-parser-diag.log` write 실패 반복
- 브라우저 E2E 미실행
- 위 항목은 P3C 기능 실패가 아니라 후속 운영/검증 개선 항목으로 분리

## 다음 단계

- P3D: 실제 공고문 HWPX 샘플 기반 의미 추출 품질 개선
- 별도: `hwpx-parser-diag.log` write permission 경고 정리
