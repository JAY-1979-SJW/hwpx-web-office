# HWPX Fixture Selection Report

**작업명**: HWPX-FIXTURE-SELECTION-01  
**작성일**: 2026-05-17  
**기준 커밋**: d6310de  
**담당**: Claude Code (HWPX 문서 실측동)

---

## 1. 선정 목적

Corpus Profiler 및 Table Layout Classifier 결과를 기반으로,
향후 회귀 테스트 및 공정표 인식기 개발에 사용할
최소 대표 HWPX fixture 파일을 고정한다.

---

## 2. 선정 기준

| 우선순위 | 기준 |
|----------|------|
| 1 | 표 구조 다양성 (many_tables, merged_cell, nested_table) |
| 2 | layout classifier 카테고리 커버리지 |
| 3 | 파일 크기 최소 (회귀 테스트 속도 고려) |
| 4 | 법령서식 공개 문서 (개인정보 없음) |
| 5 | corpus profiler PASS 확인된 파일 |

---

## 3. 제외 기준

| 제외 항목 | 이유 |
|-----------|------|
| 개인정보 포함 문서 | 주소/이름/사번 등 실제 데이터 포함 |
| 대용량 문서 (>200KB) | 회귀 테스트 속도 영향 |
| 동일 layout 유형 중복 | 커버리지 중복 |
| f00000/f00006 중복 쌍 | 동일 내용 다른 경로, 1개만 선택 |
| reports/hwpx_corpus_smoke/ 전체 | 재생성 가능한 scan output, 로컬 경로 포함 가능 |
| logs/change_history.jsonl | KNOWN_HOLD 파일, 커밋 제외 |

---

## 4. 개인정보/로컬경로 처리 원칙

- 모든 fixture 파일명은 안전한 영문 식별자로 변경 (`fx_*.hwpx`)
- 원본 파일명은 `originalFileNameHash`(SHA-256 앞 16자)로만 기록
- 원본 절대경로는 `sourcePathHash`(SHA-256 전체)로만 기록
- fixture_manifest.json에 절대경로 미포함 (audit 스크립트로 검증)
- 선정 대상: 관보 공개 법령서식 템플릿 (빈 양식, 실제 개인정보 없음)

---

## 5. 카테고리별 후보 목록

| fileId | 크기 | 표 수 | layout 분포 | 선정 |
|--------|------|-------|-------------|------|
| f00000 | 92KB | 14 | page_marker×10, horizontal×2, unknown×2 | **선정** |
| f00001 | 62KB | 1 | legal_complex×1 | 보류 (f00019와 유사) |
| f00002 | 56KB | 2 | layout_noise×1, unknown×1 | 보류 |
| f00003 | 38KB | 2 | metadata_table×1, horizontal×1 | **선정** |
| f00004 | 66KB | 4 | stamp×1, unknown×2, horizontal×1 | 보류 |
| f00005 | 56KB | 1 | legal_complex×1 | 보류 |
| f00006 | 92KB | 14 | f00000과 동일 패턴 | **제외** (중복) |
| f00007 | 64KB | 2 | legal_complex×1, stamp×1 | **선정** |
| f00008 | 38KB | 1 | legal_complex×1 | 보류 |
| f00009 | 40KB | 1 | unknown×1 | 보류 |
| f00010 | 52KB | 1 | unknown×1 | 보류 |
| f00011 | 39KB | 2 | legal_complex×1, stamp×1 | 보류 (f00007과 유사) |
| f00012 | 40KB | 2 | legal_complex×1, stamp×1 | 보류 |
| f00013 | 40KB | 2 | metadata_table×1, unknown×1 | 보류 (f00003과 유사) |
| f00014 | 64KB | 4 | page_marker×3, stamp×1 | 보류 |
| f00015 | 31KB | 2 | legal_complex×1, stamp×1 | **선정** (최소 크기) |
| f00016 | 47KB | 1 | legal_complex×1 | 보류 |
| f00017 | 45KB | 1 | unknown×1 | 보류 |
| f00018 | 39KB | 1 | page_marker×1 | 보류 (f00000에 포함) |
| f00019 | 60KB | 1 | legal_complex×1 | 보류 |

---

## 6. 이번에 실제 복사한 fixture

| fixtureId | 파일명 | 크기 | 커버 카테고리 |
|-----------|--------|------|---------------|
| fx_many_tables_page_marker | fx_many_tables_page_marker.hwpx | 92KB | many_tables_document, page_marker_table |
| fx_metadata_form | fx_metadata_form.hwpx | 38KB | metadata_table |
| fx_stamp_approval_legal | fx_stamp_approval_legal.hwpx | 31KB | stamp_or_approval_table, legal_complex_table |
| fx_nested_legal_complex | fx_nested_legal_complex.hwpx | 62KB | nested_container_table, legal_complex_table |

**총 4개, 합계 223KB**

---

## 7. 복사 보류 목록

| fileId | 보류 이유 |
|--------|-----------|
| f00001~f00019 (선정 외) | 커버리지 중복 또는 이번 단계 불필요 |
| reports/hwpx_corpus_smoke/ | 재생성 가능한 scan output |

---

## 8. 다음에 추가 확보해야 할 문서 유형

| 유형 | 이유 |
|------|------|
| 공정표 (Gantt형) HWPX | schedule_candidates 0건, 핵심 분류 미검증 |
| 달력형 표 HWPX | calendar_like_table 미검증 |
| 도형/이미지 포함 HWPX | 그래픽 요소 파싱 미검증 |
| 실제 공사 내역서 HWPX | vertical_table / horizontal_table 실물 검증 |
| 중첩 3단계 이상 HWPX | nested_container 복잡 케이스 |
