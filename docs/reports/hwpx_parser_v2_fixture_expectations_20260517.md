# HWPX Parser V2 — Fixture 기대값 정의

**문서 코드**: HWPX-PARSER-ENGINE-V2-ARCHITECTURE-01  
**작성일**: 2026-05-17  
**기준 커밋**: 006106a  

---

## 검증 원칙

- 기대값은 최소 조건(minimum expectation)으로 정의한다.
- layoutGuess를 완전히 고정하지 않는다 (분류기 개선 시 유지 가능하도록).
- "최소 1개 이상 감지"를 기준으로 한다.
- parse failure가 없어야 하는 것만 절대 조건으로 한다.

---

## Fixture 1: fx_many_tables_page_marker

**파일**: `fx_many_tables_page_marker.hwpx` (92KB)  
**카테고리**: many_tables_document

| 기대 항목 | 기대값 | 검증 수준 |
|-----------|--------|----------|
| tableCount | >= 10 | HARD |
| layoutGuess 중 page_marker_table 포함 | ≥ 1건 | HARD |
| layoutGuess 중 horizontal_table 또는 legal_complex_table | ≥ 1건 | SOFT |
| hasMergedCells | true (최소 1개 파일) | HARD |
| hasNestedTables | true (최소 1개 파일) | SOFT |
| parse failure | 0건 | HARD |
| ZIP_OPEN 실패 | 없음 | HARD |

**구조 특징**:
- 소방시설 자체점검 실시결과 보고서 (8쪽 구성)
- page_marker_table 10개, horizontal_table 2개, nested_table 포함
- 많은 표 + 페이지 번호 표가 혼재하는 복잡 문서

---

## Fixture 2: fx_metadata_form

**파일**: `fx_metadata_form.hwpx` (38KB)  
**카테고리**: metadata_table

| 기대 항목 | 기대값 | 검증 수준 |
|-----------|--------|----------|
| tableCount | >= 1 | HARD |
| layoutGuess 중 metadata_table 포함 | ≥ 1건 | HARD |
| headerTexts 중 공사명/접수번호/착공일 계열 | ≥ 1개 | SOFT |
| hasMergedCells | true | HARD |
| parse failure | 0건 | HARD |

**구조 특징**:
- 교육기관 대행 갱신신청서 법령서식
- 접수번호/공사명/현장명 류 라벨-값 쌍 패턴
- metadata_table 분류 테스트 핵심

---

## Fixture 3: fx_stamp_approval_legal

**파일**: `fx_stamp_approval_legal.hwpx` (31KB, 최소 크기)  
**카테고리**: stamp_or_approval_table

| 기대 항목 | 기대값 | 검증 수준 |
|-----------|--------|----------|
| tableCount | >= 1 | HARD |
| layoutGuess 중 stamp_or_approval_table 또는 legal_complex_table | ≥ 1건 | HARD |
| hasMergedCells | true | HARD |
| parse failure | 0건 | HARD |

**구조 특징**:
- 정보통신설비 유지보수관리자 선임신고증명서 법령서식
- 직인/결재 표 + 법령 양식 혼재
- 가장 작은 fixture (30KB) → 빠른 회귀 테스트용

---

## Fixture 4: fx_nested_legal_complex

**파일**: `fx_nested_legal_complex.hwpx` (64KB)  
**카테고리**: nested_container_table

| 기대 항목 | 기대값 | 검증 수준 |
|-----------|--------|----------|
| tableCount | >= 1 | HARD |
| layoutGuess 중 legal_complex_table 또는 stamp_or_approval_table | ≥ 1건 | HARD |
| hasNestedTables | true (최소 1개 파일) | SOFT |
| parse failure | 0건 | HARD |

**구조 특징**:
- 건설사업관리계획 제출 법령서식
- nested_container 감지 테스트 핵심
- 중첩표 경고(warning)는 허용

---

## V2 계약 검증 포인트 (추가)

Parser V2 구현 후 기존 fixture로 추가 검증:

| 검증 항목 | 대상 Fixture | 기대 |
|-----------|-------------|------|
| `package.xmlDecodeOk == true` | 전체 4개 | HARD |
| `cells[]` 비어있지 않음 | 전체 4개 | HARD |
| `cells[].cellId` 형식 유효 | 전체 4개 | HARD |
| `cells[].isMergedOrigin` 또는 `isCoveredByMerge` 구분 | fx_many_tables, fx_metadata | SOFT |
| `inputSlotHints[]` 비어있지 않음 | fx_metadata_form | SOFT |
| `schemaVersion == "v2"` | 전체 4개 | HARD (V2 구현 후) |
