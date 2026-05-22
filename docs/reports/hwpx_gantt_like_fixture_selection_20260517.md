# HWPX Gantt-Like Fixture Selection Report

**task**: HWPX-GANTT-LIKE-FIXTURE-SELECTION-01  
**date**: 2026-05-17  
**baseline**: fcdbc33  
**status**: PASS

---

## 1. 선정 목적

HWPX-SCHEDULE-AXIS-DETECTOR-01 (schedule axis + bar range 탐지기) 구현 시 사용할
재현 가능한 gantt_like_table 픽스처를 확보한다.

픽스처 요건:
- 파서 안정적으로 파싱 가능 (errors=[])
- 7×6 구조, header `공종|기간|5월|6월|7월|진척률`
- barType 다양성 — 완전 채움 / 빈 서식 / 부분 채움 각 1종
- 민감정보 없음 (template_labels_only)
- mimetype ZIP_STORED 준수

---

## 2. 후보 6건 요약

profiler 출처: `reports/hwpx_full_corpus_profile/schedule_candidates.jsonl`

| fileId | fileName | tableId | confidence | barType | inputSlots |
|---|---|---|---|---|---|
| f00068_2c8f293c31 | 감리결과보고서_공정표_그래프도식_통합.hwpx | s0:t0 | 0.90 | text_full (■+·) | 0 |
| f00069_ecee83e8bb | 감리결과보고서_공정표_그래프도식_통합_서식개선.hwpx | s0:t0 | 0.90 | empty | 18 |
| f00070_19c431d1c9 | 감리결과보고서_공종별_월별일별_공정표.hwpx | s0:t5 | 0.85 | text_partial | 12 |
| f00071_96a226f359 | 감리결과보고서_공종별_월별일별_공정표_맨앞표시.hwpx | s0:t5 | 0.85 | text_partial | 12 |
| f00072_2b35dc014e | 감리결과보고서_공종별_월별일별_공정표_서식색상.hwpx | s0:t0 | 0.90 | text_full (■+·) | 0 |
| f00073_118048298e | 감리결과보고서_공종별_월별일별_공정표_확인수정.hwpx | s0:t5 | 0.85 | text_partial | 12 |

공통 구조: rowCount=7, colCount=6, mergedCellCount=0, warnings=[]  
공통 header: `공종 | 기간 | 5월 | 6월 | 7월 | 진척률`  
공통 leftCol: `공종 / 착공및현장정리 / 배관공사 / 배선공사 / 장비설치 / 시험및시운전 / 준공정리`

---

## 3. 선정 fixture 3건

| fixtureName | 원본 fileId | 선정 사유 |
|---|---|---|
| fx_gantt_like_basic.hwpx | f00068_2c8f293c31 | text_full 대표 — 5월 ■ 완전 채움 + 6·7월 `·` 자리표시. 진척률 명시. 기준 fixture. |
| fx_gantt_like_template_empty.hwpx | f00069_ecee83e8bb | empty 대표 — 바 셀 전부 비어있음. inputSlot 탐지 대상. 서식 개선 버전. |
| fx_gantt_like_partial_filled.hwpx | f00071_96a226f359 | text_partial 대표 — 5월 바만 채움, 6·7월 비어있음 (row6은 6월 바). barRange 경계 테스트에 적합. |

---

## 4. 제외 fixture 3건 및 제외 사유

| fileId | 제외 사유 |
|---|---|
| f00070_19c431d1c9 | f00071과 동일 barType(text_partial), 동일 데이터. f00071 선정으로 중복 — tableId도 s0:t5로 동일. |
| f00072_2b35dc014e | f00068과 동일 barType(text_full), 동일 데이터. 서식 색상만 다름. 파서는 색상을 별도 탐지하지 않으므로 중복. |
| f00073_118048298e | f00071과 동일 barType(text_partial), 동일 데이터. manifest_fixed 변형으로 구조 동일. |

3개 제외 모두 **기능적 barType 중복**이 사유이며 민감정보 문제가 아님.  
향후 서식 색상 파서 구현 시 f00072 재검토 가능.

---

## 5. Privacy Assessment

| 항목 | 판정 | 근거 |
|---|---|---|
| 실제 주소 | 없음 | `주소:` 필드가 서식 라벨이며 값이 비어있음 |
| 개인 성명 | 없음 | 서명란 등 양식 라벨만 존재 |
| 연락처 | 없음 | 전화번호 패턴 없음 |
| 회사명 | 없음 | `엔지니어링 (정보 통신분야) 등록 번호 :` — 서식 설명 텍스트 |
| 공사 현장 특정 정보 | 없음 | 공사명/현장 소재지 필드가 비어있음 |

**최종 privacyAssessment: template_labels_only** — 3개 모두 SAFE_FOR_FIXTURE

---

## 6. Expected Signals (HWPX-SCHEDULE-AXIS-DETECTOR-01 검측 기준)

다음 공정에서 이 픽스처들을 사용할 때 기대하는 탐지 결과:

### fx_gantt_like_basic.hwpx
- `timeAxis`: `["5월", "6월", "7월"]` (header row, col 2–4)
- `taskColumn`: col 0 (`공종`)
- `dateRangeColumn`: col 1 (`기간`)
- `barCells`: col 2에 ■ 존재 (rows 1–6), col 3·4에 `·` 자리표시
- `progressColumn`: col 5 (`진척률`)
- barType: `text_symbol`
- scheduleType: `gantt_bar_schedule`

### fx_gantt_like_template_empty.hwpx
- `timeAxis`: `["5월", "6월", "7월"]`
- `barCells`: col 2–4 전부 빈 문자열 → 미입력 상태
- inputSlotCount: 18 (bar 셀 + 진척률 셀)
- 탐지기는 `barRange`를 빈 셀로 처리해야 함

### fx_gantt_like_partial_filled.hwpx
- `timeAxis`: `["5월", "6월", "7월"]`
- `barCells`: col 2 (5월)에만 ■ 존재, col 3 (6월)은 row6만 채움, col 4 (7월) 비어있음
- barRange 경계 탐지: 5월→6월 전환 행(row6) 처리 검증

---

## 7. 다음 공정

**HWPX-SCHEDULE-AXIS-DETECTOR-01**

- 입력: `tests/fixtures/hwpx/gantt/` 3개 픽스처
- 구현 대상:
  - `detect_time_axis(table)` — header row에서 월/주/일 축 탐지
  - `detect_bar_ranges(table, time_axis)` — ■ 기호 셀 범위 → (task, start_col, end_col) 추출
  - `detect_progress_column(table)` — % 패턴 열 탐지
- 테스트 기준: 위 6번 expectedSignals 충족 여부
