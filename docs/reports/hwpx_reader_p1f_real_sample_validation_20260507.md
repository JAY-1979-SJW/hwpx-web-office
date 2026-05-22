# HWPX Reader P1F — 샘플 검증 리포트

**작업명**: HWPX-READER-P1F-REAL-HWPX-SAMPLE-VALIDATION  
**작성일**: 2026-05-07  
**상태**: ⚠️ WARN (실제 샘플 미보유, fixture 기반 검증)

---

## 1. 기준 커밋

| 단계 | 커밋 | 메시지 |
|------|------|--------|
| P1C (기능) | a2c584d | feat(hwpx): complete reader validation and parse endpoint |
| P1 (배포) | d3f6b2e | feat(hwpx-engine): runtime packaging P1 complete |
| P1D (계약) | dfa2c6d | test(hwpx): freeze parse api contract |
| P1E (감사) | 1ddb151 | docs(hwpx): audit p1 closeout packaging and contract status |

---

## 2. 샘플 확인 결과

### 2.1 샘플 검색

**검색 범위**:
- 전체 repo: *.hwpx 파일
- src/test/resources: 테스트 리소스
- fixtures 디렉터리
- samples 디렉터리
- test_documents 디렉터리
- docs 디렉터리

**검색 결과**:

| 구분 | 결과 |
|------|------|
| 실제 관공사/실무형 HWPX | ❌ **없음** |
| test/resources HWPX | ❌ 없음 |
| fixtures 디렉터리 | ❌ 없음 |
| samples 디렉터리 | ❌ 없음 |
| test_documents 디렉터리 | ❌ 없음 |
| 최근 생성 fixture (smoke-test.hwpx) | ✅ 있음 (P1E 검증 시) |

**판정**: ⚠️ **REAL_HWPX_SAMPLE_NOT_AVAILABLE**

---

## 3. 검증 전략 변경

### 사유

Repo에 실제 HWPX 샘플이 없으므로, 다음 3가지 대체 검증 수행:

1. **테스트 기반 검증**: HwpxParserTest + ParseHwpxHandlerTest 모두 실행
2. **Fixture 기반 검증**: 테스트에서 사용하는 다양한 fixture로 주요 기능 검증
3. **계약 준수 검증**: API 계약 문서와 실제 응답 비교

### 정당성

P1C 단계에서 이미 8가지 시나리오를 fixture로 검증:
- Minimal HWPX (문단만)
- HWPX with Table (2x2 테이블)
- HWPX with Multiple Sections (section0, section1)
- Invalid ZIP (오류 처리)
- Non-existent File (파일 없음)
- Korean Text Extraction (한글 추출)
- Table Cell Level Extraction (표 셀 추출)
- Block Order Preservation (순서 보존)

---

## 4. 샘플별 검증 결과

### 4.1 Scenario 1: Minimal HWPX (문단만)

**특징**:
- 구조: 문단 1개만 포함
- 내용: 최소 구조 테스트

**검증 항목**:

| 항목 | 기대값 | 결과 | 상태 |
|------|--------|------|------|
| HTTP 200 | ✅ | OK | ✅ |
| ok 필드 | true | true | ✅ |
| schemaVersion | "1.0" | "1.0" | ✅ |
| engineVersion | "1.0.0" | "1.0.0" | ✅ |
| requestId 형식 | UUID v4 | UUID v4 | ✅ |
| inputFileType | "hwpx" | "hwpx" | ✅ |
| paragraphs[] | >= 1 | 1 | ✅ |
| blocks[] | >= 1 | 1 | ✅ |
| tables[] | 0 | 0 | ✅ |
| fullText | "최소 문단" | "최소 문단" | ✅ |
| 한글 추출 | ✅ | ✅ | ✅ |

**결론**: ✅ **MINIMAL_PASS**

---

### 4.2 Scenario 2: HWPX with Table

**특징**:
- 구조: 문단 1개 + 표 1개 (2행 2열)
- 내용: 실무 유형 구조 (제목 + 데이터 테이블)

**검증 항목**:

| 항목 | 기대값 | 결과 | 상태 |
|------|--------|------|------|
| HTTP 200 | ✅ | OK | ✅ |
| blocks[] 개수 | 2 | 2 (para + table) | ✅ |
| blocks[0].type | "paragraph" | "paragraph" | ✅ |
| blocks[1].type | "table" | "table" | ✅ |
| blocks[] 순서 | 문단→표 | 문단→표 | ✅ |
| tables[] 개수 | 1 | 1 | ✅ |
| 표 구조 | 2x2 | 2x2 | ✅ |
| 표 셀 개수 | 4 | 4 | ✅ |
| 셀 텍스트 추출 | "항목", "값" 등 | 정상 추출 | ✅ |
| 한글 추출 | "항목", "값" | ✅ | ✅ |

**결론**: ✅ **TABLE_PASS**

---

### 4.3 Scenario 3: Multi-Section HWPX

**특징**:
- 구조: section0.xml + section1.xml
- 내용: 여러 페이지/섹션 시뮬레이션

**검증 항목**:

| 항목 | 기대값 | 결과 | 상태 |
|------|--------|------|------|
| HTTP 200 | ✅ | OK | ✅ |
| fullText 누적 | "섹션1" + "섹션2" | 둘 다 포함 | ✅ |
| paragraphs[] 개수 | 2 | 2 | ✅ |
| blocks[] 개수 | 2 | 2 | ✅ |
| 섹션 순서 | section0 → section1 | 순서 보존 | ✅ |

**결론**: ✅ **MULTI_SECTION_PASS**

---

### 4.4 Error Handling Scenarios

**Invalid ZIP**:
- 입력: 유효하지 않은 ZIP 바이트
- 기대: HTTP 400, ok=false, errorCount > 0
- 결과: ✅ 모두 충족

**Non-existent File**:
- 입력: 파일 없음
- 기대: HTTP 400, ok=false, errors[] 포함
- 결과: ✅ 모두 충족

**판정**: ✅ **ERROR_HANDLING_PASS**

---

## 5. 계약 준수 검증

### 5.1 필수 키 검증 (14개)

```json
{
  "schemaVersion": "1.0",          ✅
  "engineVersion": "1.0.0",        ✅
  "requestId": "uuid-format",      ✅
  "inputFileName": "...",          ✅
  "inputFileType": "hwpx",         ✅
  "parsedAt": "2026-05-07T...",    ✅
  "fullText": "...",               ✅
  "paragraphs": [...],             ✅
  "blocks": [...],                 ✅
  "tables": [...],                 ✅
  "warningCount": 0,               ✅
  "errorCount": 0,                 ✅
  "warnings": [],                  ✅
  "errors": [],                    ✅
  "ok": true                       ✅
}
```

**판정**: ✅ **ALL_REQUIRED_KEYS_PRESENT**

---

### 5.2 응답 구조 검증

**DocumentBlock**:
- block_index: 정수 ✅
- block_type: "paragraph" | "table" ✅
- text: 문자열 ✅
- table_id_if_applicable: (table 블록인 경우만) ✅

**DocumentTable**:
- table_id: "table_0", "table_1", ... ✅
- row_count: 정수 ✅
- col_count: 정수 ✅
- source: "hwpx-xml" ✅
- rows: 2D array (List<List<DocumentCell>>) ✅

**DocumentCell**:
- text: 문자열 ✅
- row: 0 기반 인덱스 ✅
- col: 0 기반 인덱스 ✅
- rowspan: 기본 1 ✅
- colspan: 기본 1 ✅
- is_header: 기본 false ✅

**판정**: ✅ **ALL_STRUCTURES_VALID**

---

## 6. HWPX 테스트 결과

```
HwpxParserTest: 6/6 PASS ✅
├── testParseValidHwpx
├── testParseNonExistentFile
├── testParseInvalidZip
├── testParseHwpxWithTable
├── testParseMultipleSections
└── testBlocksOrderPreservation

ParseHwpxHandlerTest: 15/15 PASS ✅
├── testSuccessResponseHasRequiredKeys
├── testSchemaVersionFixed
├── testEngineVersionFixed
├── testRequestIdIsUuid
├── testInputFileTypeIsHwpx
├── testBlocksOrderPreserved
├── testTableStructureValid
├── testInvalidZipErrorResponse
├── testGetMethodReturns405
├── testParseAtIsIso8601
├── testWarningCountAndErrorCountAreIntegers
├── testOkFieldExists
├── testParseHwpxViaHttp
├── testParseHwpxWithTableViaHttp
└── testParseHwpxGetMethodNotAllowed

합계: 21/21 PASS ✅
```

---

## 7. Build 및 Smoke 결과

```
./gradlew build
BUILD SUCCESSFUL ✅

./gradlew run --args "serve 8080"
/health: ✅ {"status":"ok","engine":"office-analysis-engine","version":"0.1.0"}
/parse-hwpx (fixture): ✅ {"ok":true,"schemaVersion":"1.0",...}
```

---

## 8. 한글 텍스트 처리 검증

| 항목 | 결과 |
|------|------|
| 한글 추출 | ✅ "샘플", "항목", "값" 등 정상 |
| 인코딩 | ✅ UTF-8 정상 처리 |
| 깨진 문자 | ❌ 없음 |
| 특수 문자 | ✅ 공백, 숫자 정상 |

---

## 9. Known Limitations 검증

| 제약 | 해당 여부 | 확인 |
|-----|---------|------|
| rowspan | ℹ️ 기본값 1 | fixture에서 테스트 안 함 |
| colspan | ✅ gridSpan 지원 | 필요 시 확장 가능 |
| 중첩 테이블 | ✅ 미지원 (예정) | fixture에서 테스트 안 함 |
| 다중 섹션 | ✅ 지원 확인 | ✅ Multi-section test PASS |

---

## 10. 다음 단계 권장

### 10.1 실제 HWPX 샘플 추가 (P2+)

다음과 같은 실무형 샘플 확보 권장:

1. **표준 형식 HWPX**: 일반적인 문서 구조
   - 제목 + 본문 + 표
   - 일반 감리서류 형식

2. **복잡한 표 구조**:
   - rowspan/colspan 있는 표
   - 셀 병합이 많은 표

3. **다양한 포맷**:
   - 이미지 포함 HWPX (현재 미지원, 무시 가능)
   - 글머리 목록 포함
   - 페이지 레이아웃 다양한 문서

4. **문제 케이스**:
   - 깨진 구조의 HWPX
   - 매우 큰 파일 (10MB+)

### 10.2 실제 샘플 기반 추가 테스트 (P2+)

```
src/test/resources/real-samples/
├── standard-document.hwpx      (표준 문서)
├── complex-table.hwpx          (복잡한 표)
├── large-document.hwpx         (대용량)
└── edge-cases.hwpx             (엣지 케이스)

src/test/java/RealSampleValidationTest.java
├── testRealDocumentParsing()
├── testComplexTableExtraction()
├── testLargeFileParsing()
└── testErrorRecovery()
```

### 10.3 운영 샘플 로깅 (P2+)

실제 운영에서 들어오는 HWPX 파일:
- 월별 통계 (파일 크기, 파싱 시간, 오류율)
- 문제 케이스 수집
- 품질 메트릭 추적

---

## 11. 최종 판정

### ✅ 검증 결과 SUMMARY

| 항목 | 상태 |
|------|------|
| 최소 구조 HWPX | ✅ PASS |
| 표 포함 HWPX | ✅ PASS |
| 다중 섹션 HWPX | ✅ PASS |
| 오류 처리 | ✅ PASS |
| 한글 텍스트 | ✅ PASS |
| 표 셀 추출 | ✅ PASS |
| 블록 순서 보존 | ✅ PASS |
| API 계약 준수 | ✅ PASS |
| 필수 키 (14개) | ✅ ALL PRESENT |
| 응답 구조 | ✅ VALID |

### ⚠️ 제약 사항

- ❌ 실제 HWPX 샘플 없음 (fixture 기반 검증)
- ℹ️ rowspan/colspan 완전 구현은 P2+ 대상
- ℹ️ 이미지/고급 포맷은 현재 미지원

### 🎯 최종 판정: ⚠️ **WARN — FIXTURE_BASED_VALIDATION**

**상태**: 파싱 기능 및 API 계약 우수한 검증 완료.
**제약**: 실제 관공사 샘플 미보유로 fixture 기반 검증. 운영 단계에서 실제 샘플 수집 권장.
**진행**: P2 기능 개발 및 운영 배포 모두 진입 가능.

---

## 12. 참고 자료

- 계약 문서: docs/contracts/parse_hwpx_api_contract_v1.md
- 테스트: src/test/java/com/haehan/engine/parser/HwpxParserTest.java
- 테스트: src/test/java/com/haehan/engine/http/ParseHwpxHandlerTest.java
- 구현: src/main/java/com/haehan/engine/parser/HwpxParser.java
- 핸들러: src/main/java/com/haehan/engine/http/ParseHwpxHandler.java
