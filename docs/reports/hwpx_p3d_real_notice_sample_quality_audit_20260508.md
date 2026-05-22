# HWPX P3D Real Notice Sample Quality Audit

## 기준 HEAD

- local: `4f4662e3304ca7ecb3c5418a160bed0622aa11be`
- github/main: `4f4662e3304ca7ecb3c5418a160bed0622aa11be`
- server/main: `4f4662e3304ca7ecb3c5418a160bed0622aa11be`
- server working tree: `4f4662e3304ca7ecb3c5418a160bed0622aa11be`
- server working tree status: clean

## 감사 목적

P3C semantic key-value extraction baseline은 서버 기준 PASS로 마감됐다.
P3D 첫 단계에서는 구현을 변경하지 않고 실제 공고문 HWPX 샘플 기준으로 현재 추출 품질을 감사하려 했다.

이번 감사에서 확인할 목표 필드는 다음과 같다.

- 공고명
- 공사명
- 발주처
- 입찰마감일
- 개찰일
- 입찰참가자격
- 제출서류
- 낙찰방법
- 유의사항

핵심 section 기준은 다음과 같다.

- `document_overview`
- `bid_qualification`
- `submission_documents`
- `schedule`
- `award_method`
- `caution_notes`

## 샘플 인벤토리

### 실제 공고문 후보

실제 공고문 HWPX 후보는 확인되지 않았다.

- local actual notice candidates: `0`
- git tracked HWPX files: `0`
- server actual notice candidates: `0`

### 로컬 HWPX 파일

로컬 작업트리에는 HWPX 파일이 확인됐지만, 대부분 나라장터/입찰 공고문이 아니라 `건설공사 품질관리 업무지침` 별지/별표 양식이다.
따라서 P3D의 "실제 공고문 HWPX" 품질 감사 대상에서는 제외했다.

- `samples/` 하위 HWPX: `27`
- 문서 성격: 건설공사 품질관리 업무지침 별지/별표 양식
- 판정: 실제 공고문 후보가 아니라 참고 샘플

### 테스트/생성 샘플

다음 파일은 테스트 또는 생성 샘플로 분류했다.

- local: `p1f-validate.hwpx`
- local: `smoke-test.hwpx`
- server: `build/tmp/hwpx-p1k/smoke.hwpx`

### 제외 샘플

다음 유형은 이번 품질 감사에서 제외했다.

- synthetic smoke sample
- unit test fixture
- P3C 검증용 임시 생성 샘플
- 공고문이 아닌 행정 양식 HWPX

## 현재 파서 표면 확인

코드 기준으로 다음 연결을 확인했다.

- public parse endpoint: `/parse-hwpx`
- UI proxy endpoint: `/api/hwpx/parse`
- upload UI: `/hwpx-upload`
- parser entry point: `HwpxParser`
- semantic section extractor: `SemanticSectionExtractor`
- key-value extractor: `SemanticKeyValueExtractor`
- response fields: `semanticSections`, `extractedFields`
- UI render fields: key, value, section_type, confidence, extraction_method, normalized_key, source

`HwpxParser`는 block/table 파싱 후 semantic section extraction을 수행하고, 이후 `SemanticKeyValueExtractor.extractKeyValues(response)`를 호출한다.

## 샘플별 결과

실제 공고문 HWPX 후보가 0건이므로 실제 공고문 기준 parse 품질 감사는 수행하지 않았다.

| 구분 | 값 |
| --- | --- |
| 실제 공고문 샘플 수 | 0 |
| parse 성공 | N/A |
| parse 실패 | N/A |
| semanticSections_count | N/A |
| extractedFields_count | N/A |
| paragraph/table source 분포 | N/A |
| normalized_key 분포 | N/A |
| 주요 누락 | 실제 공고문 샘플 부족으로 판정 불가 |

## 문제 유형 분류

| 유형 | 판정 | 근거 |
| --- | --- | --- |
| A. section 분류 누락 | 판정 보류 | 실제 공고문 샘플이 없어 section 누락 여부를 검증할 수 없음 |
| B. section_type 오분류 | 판정 보류 | 실제 공고문 샘플이 없어 오분류 사례를 수집할 수 없음 |
| C. key-value 패턴 미탐지 | 판정 보류 | 실제 공고문 샘플이 없어 핵심 필드 미탐지 여부를 검증할 수 없음 |
| D. table 2-column 추출 실패 | 판정 보류 | 실제 공고문 내 표 구조 샘플이 없음 |
| E. normalized_key 매핑 부족 | 개선 후보 | 실제 공고문 필드 어휘 기준 매핑 범위 검증 필요 |
| F. confidence 과대/과소 | 판정 보류 | 실제 샘플별 confidence 분포가 없음 |
| G. 중복 field 생성 | 판정 보류 | 실제 공고문 결과가 없어 중복 여부 확인 불가 |
| H. value가 너무 짧거나 잘림 | 판정 보류 | 실제 공고문 결과가 없어 value 품질 확인 불가 |
| I. 공고문 원문 구조 문제 | 판정 보류 | 실제 공고문 원문 구조 샘플이 없음 |
| J. 샘플 부족 | 확인 | 실제 공고문 HWPX 후보 0건 |

## 개선 후보

### P0. 실제 공고문 HWPX 샘플 확보

- 유형: J. 샘플 부족
- 원인: repo/local/server 안에 실제 공고문 HWPX 후보가 없음
- 영향: P3D 품질 개선을 근거 기반으로 시작할 수 없음
- 수정 예상 파일: 없음
- 테스트 추가 필요: 샘플 확보 후 batch audit fixture 또는 외부 샘플 메타데이터 필요
- 위험도: 낮음
- 우선순위: P0

### P1. 실제 공고문 batch audit 도구 또는 절차 고정

- 유형: A/B/C/D/G/H 판정 준비
- 원인: 샘플별 parse 결과를 같은 기준으로 집계하는 절차가 아직 문서화되지 않음
- 영향: 개선 전후 품질 비교가 어려움
- 수정 예상 파일: `scripts/` 또는 `src/test/` 하위 감사 전용 도구 후보
- 테스트 추가 필요: 실제 공고문 샘플 3~5건 기준 결과 요약
- 위험도: 중간
- 우선순위: P1

### P2. normalized_key 매핑 확장 후보 수집

- 유형: E. normalized_key 매핑 부족
- 원인: 실제 공고문 핵심 필드 어휘가 baseline 매핑에 충분히 포함됐는지 아직 검증되지 않음
- 영향: UI/API 소비자가 필드 의미를 안정적으로 사용하기 어려움
- 수정 예상 파일: `src/main/java/com/haehan/engine/parser/SemanticKeyValueExtractor.java`
- 테스트 추가 필요: 실제 공고문 필드명별 normalized_key 기대값 테스트
- 위험도: 중간
- 우선순위: P2

### P3. confidence 보정 기준 수립

- 유형: F. confidence 과대/과소
- 원인: 실제 공고문 결과 분포가 없어 confidence 임계값을 검증하지 못함
- 영향: 낮은 품질 추출이 UI/API에서 과신될 수 있음
- 수정 예상 파일: `src/main/java/com/haehan/engine/parser/SemanticKeyValueExtractor.java`
- 테스트 추가 필요: 샘플별 confidence 최소/평균/최대 회귀 테스트
- 위험도: 중간
- 우선순위: P3

### P4. 실제 공고문 결과 기반 UI 표시 개선

- 유형: P3D 후속 UX 개선
- 원인: UI는 P3C 기준 필드 표시가 완료됐지만, 실제 공고문 결과에서 정렬/중복/빈값 처리 요구가 생길 수 있음
- 영향: 추출 결과 검토 효율 저하 가능
- 수정 예상 파일: `src/main/java/com/haehan/engine/http/HwpxUploadHandler.java`
- 테스트 추가 필요: 실제 extractedFields 표시 snapshot 또는 HTML source 검증
- 위험도: 낮음
- 우선순위: P4

## 다음 구현 제안

### P3D-1. 실제 공고문 HWPX 샘플 확보

나라장터/공고/입찰/소방/공사 성격의 실제 HWPX 샘플을 최소 3건 확보한다.
샘플은 git 포함 전 민감정보와 저작권/보관 정책을 확인해야 한다.

### P3D-2. 샘플별 batch quality audit 실행

확보된 샘플마다 다음 지표를 같은 형식으로 집계한다.

- parse 성공 여부
- paragraph count
- table count
- semanticSections count
- extractedFields count
- section_type 분포
- source 분포
- normalized_key 분포
- confidence 최소/평균/최대
- 빈 value 개수
- 중복 key 개수
- 누락된 핵심 섹션
- 오탐 추출 의심 항목

### P3D-3. 근거 기반 extractor 개선

batch audit 결과에서 반복되는 누락 패턴만 P3D 구현 대상으로 올린다.
예상 수정 범위는 section keyword, key-value pattern, table extraction, normalized_key mapping, confidence calibration이다.

## 최종 판정

WARN

P3C 기능은 서버 기준 PASS/CLOSED 상태다.
다만 P3D 품질 감사는 실제 공고문 HWPX 샘플이 없어 샘플 부족으로 제한됐다.
다음 단계는 구현이 아니라 실제 공고문 HWPX 샘플 확보와 batch audit 기준 고정이다.
