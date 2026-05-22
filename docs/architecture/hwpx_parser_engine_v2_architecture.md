# HWPX Parser Engine V2 — 아키텍처 정의

**문서 코드**: HWPX-PARSER-ENGINE-V2-ARCHITECTURE-01  
**작성일**: 2026-05-17  
**기준 커밋**: 006106a  

---

## 1. 설계 원칙

```
문서 구조를 먼저 정확히 정의한다
→ 그 구조 위에 의미 분석을 얹는다
→ 그다음 입력칸 탐지와 편집 엔진을 연결한다
```

Parser Engine V2는 **읽기 전용(read-only)** 엔진이다.  
원본 HWPX 파일을 수정하지 않으며, edit plan을 실행하지 않는다.

---

## 2. Parser Engine V2가 해야 할 일

| # | 책임 | 모듈 |
|---|------|------|
| 1 | HWPX package 구조 읽기 (ZIP 엔트리, mimetype, hpf, container.xml) | package_reader |
| 2 | section XML 순서 읽기 (header.xml → section 파일 목록 결정) | package_reader |
| 3 | 본문 block 순서 복원 (section 내 para/table/image 순서 보존) | block_parser |
| 4 | paragraph 추출 (run → text 병합, 스타일 참조 기록) | block_parser |
| 5 | table 추출 (tbl 요소 → tableId 부여, 위치 기록) | table_parser |
| 6 | row/cell 추출 (tr/tc 순회, 좌표 할당) | table_parser |
| 7 | visual grid 생성 (병합셀 반영한 2D 좌표 계산) | table_parser |
| 8 | 병합셀 rowSpan/colSpan 해석 (isMergedOrigin / isCoveredByMerge 구분) | table_parser |
| 9 | 빈 셀 보존 (빈 tc 도 cellId 부여하여 grid 유지) | table_parser |
| 10 | 중첩표 탐지 (tc 내 tbl 요소 존재 여부) | table_parser |
| 11 | 이미지/도형 placeholder 탐지 (pic/drawing 요소 → block type 기록) | block_parser |
| 12 | style/layout 참조 추출 (charPrIDRef, paraPrIDRef) | style_parser |
| 13 | borderFill/색상 참조 추출 (borderFillIDRef, fillColor) | style_parser |
| 14 | header/label 후보 추출 (header normalizer 적용, FIELD_HINTS 매핑) | layout_classifier |
| 15 | table layout 분류 (layoutGuess, confidence, classificationEvidence) | layout_classifier |
| 16 | input slot 후보 산출을 위한 구조 제공 (cells + labels → slotHints) | input_slot_detector |

---

## 3. Parser Engine V2가 하지 않는 일

| 금지 항목 | 이유 |
|-----------|------|
| HWPX 원본 수정 | 읽기 전용 원칙 |
| 값 입력 (write_cells, set_value) | 편집 엔진(V2 writer) 영역 |
| 색 채우기 / 스타일 변경 | 편집 엔진 영역 |
| HWP 변환 (HWP→HWPX) | 별도 변환 공정 |
| OCR 실행 | 이미지 처리 별도 공정 |
| AI 문장 추론 | Semantic Extractor 영역 |
| 최종 edit plan 실행 | Writer/Editor 영역 |
| apply_edit_plan 호출 | 금지 (read-only) |
| write_package 호출 | 금지 (read-only) |
| repair_for_server 호출 | 금지 (read-only) |

---

## 4. 처리 흐름

```
HWPX 파일 (ZIP)
    │
    ▼
[PackageReader]
  - ZIP 엔트리 목록
  - mimetype 확인
  - header.xml → section 파일 목록
  - container.xml 메타
    │
    ▼
[BlockParser]
  - section XML 순차 파싱
  - paragraph / table / image / drawing 분리
  - blockIndex 할당 (문서 내 순서 보존)
    │
    ├──▶ [TableParser]
    │      - row/cell 추출
    │      - visual grid 생성
    │      - 병합셀 해석
    │      - 빈 셀 보존
    │      - 중첩표 탐지
    │
    ├──▶ [StyleParser]
    │      - charPr / paraPr 참조 추출
    │      - borderFill / fillColor 참조 추출
    │      - dangling ref 감지
    │
    └──▶ [LayoutClassifier]
           - header/label 후보 추출
           - header normalizer 적용
           - table layout 분류
           - confidence + evidence 산출
               │
               ▼
         [InputSlotDetector]  ← 별도 공정에서 구현
           - label_right / label_below
           - form_pair
           - schedule_bar_range
           - slotId + fieldGuess + confidence
               │
               ▼
         Parser V2 JSON 출력
         (schemaVersion: v2)
```

---

## 5. 모듈 목록 (예정)

| 모듈 경로 | 책임 | 현재 상태 |
|-----------|------|----------|
| `scripts/hwpx/parser/package_reader.py` | ZIP/package 읽기 | 설계 완료, 구현 예정 |
| `scripts/hwpx/parser/block_parser.py` | section → block 순서 복원 | 설계 완료, 구현 예정 |
| `scripts/hwpx/parser/table_parser.py` | table/row/cell/grid | 설계 완료, 구현 예정 |
| `scripts/hwpx/parser/style_parser.py` | charPr/paraPr/borderFill | 설계 완료, 구현 예정 |
| `scripts/hwpx/parser/layout_classifier.py` | layout 분류 (profiler에서 이식) | 설계 완료, 구현 예정 |
| `scripts/hwpx/parser/input_slot_detector.py` | 입력칸 후보 탐지 | 별도 공정 (HWPX-INPUT-SLOT-DETECTOR-01) |
| `scripts/hwpx/parser/parser_contract.py` | 출력 JSON 스키마 / 팩토리 | 설계 완료, 구현 예정 |

> 현재 `scripts/local/hwpx_corpus_profiler.py`에 위 기능이 단일 파일로 혼재되어 있다.  
> 대규모 리팩터링은 `HWPX-PARSER-V2-SKELETON-01` 공정에서 진행한다.

---

## 6. 기존 코드 활용

| 기존 파일 | 재사용 대상 |
|-----------|------------|
| `scripts/local/hwpx_corpus_profiler.py` | PackageReader, BlockParser, TableParser 로직의 원본 |
| `scripts/local/hwpx_corpus_profiler.py` | `classify_table_layout()`, `_compute_table_scores()` → LayoutClassifier로 이식 |
| `scripts/local/hwpx_corpus_profiler.py` | `normalize_header()`, `guess_field()` → 재사용 |
| `tests/fixtures/hwpx/corpus/` | 4개 fixture → V2 계약 회귀 검증 기준 |

---

## 7. 버전 정책

| 버전 | 내용 |
|------|------|
| v1 | corpus profiler (단일 파일, 분석 전용) |
| v2 | 모듈 분리 + 표준 JSON 계약 + InputSlotDetector 연결 |
| v3 (예정) | AI Semantic Extractor 연결 + edit plan 생성 |
