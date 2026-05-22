# HWPX Parser V2 — 모듈 분리 계획

**문서 코드**: HWPX-PARSER-ENGINE-V2-ARCHITECTURE-01  
**작성일**: 2026-05-17  

---

## 1. 현재 상태 (V1: corpus profiler 단일 파일)

`scripts/local/hwpx_corpus_profiler.py` 안에 다음 기능이 혼재:

| 기능 그룹 | 현재 위치 | 주요 함수/상수 |
|-----------|-----------|---------------|
| package inspector | hwpx_corpus_profiler.py | `scan_hwpx()` ZIP 열기, mimetype 확인, header.xml 읽기 |
| text extractor | hwpx_corpus_profiler.py | `extract_text_from_para()`, `get_full_text()` |
| table parser | hwpx_corpus_profiler.py | `build_grid()`, `get_cell_texts()`, `detect_header_rows()`, `cell_has_nested_table()` |
| header normalizer | hwpx_corpus_profiler.py | `normalize_header()`, `guess_field()`, `FIELD_HINTS` |
| table layout classifier | hwpx_corpus_profiler.py | `classify_table_layout()`, `_compute_table_scores()`, 각 KEYWORDS 상수 |
| schedule candidate detector | hwpx_corpus_profiler.py | `detect_schedule_candidates()`, `is_date_like()`, `DATE_HEADER_PATTERNS` |
| report writer | hwpx_corpus_profiler.py | `run_profiler()`, `_write_jsonl()`, `_write_csv()` |

---

## 2. 목표 상태 (V2: 모듈 분리)

```
scripts/hwpx/parser/
├── __init__.py
├── package_reader.py       ← ZIP/package 읽기
├── block_parser.py         ← section → block 순서 복원
├── table_parser.py         ← table/row/cell/grid
├── style_parser.py         ← charPr/paraPr/borderFill
├── layout_classifier.py    ← classify_table_layout 이식
├── input_slot_detector.py  ← 별도 공정 (HWPX-INPUT-SLOT-DETECTOR-01)
└── parser_contract.py      ← JSON 계약 팩토리/검증
```

---

## 3. 모듈별 분리 계획

### 3.1 package_reader.py

**이식 대상 (profiler → reader)**:
- ZIP 열기 (`zipfile.ZipFile`)
- mimetype 읽기 / compressType 확인
- `container.xml` 파싱
- `header.xml` 파싱 → section 파일 목록 결정
- `NS_HP`, `NS_HWPML` 네임스페이스 상수

**출력**: `PackageInfo` dataclass  
**상태**: 구현 예정 (`HWPX-PARSER-V2-SKELETON-01`)

---

### 3.2 block_parser.py

**이식 대상**:
- section XML 순차 읽기
- para / tbl / pic / drawing 구분
- blockIndex 부여
- `page_marker` 감지 (PAGE_MARKER_RE)

**출력**: `list[Block]`  
**상태**: 구현 예정

---

### 3.3 table_parser.py

**이식 대상**:
- `build_grid()` → VisualGrid 생성
- `get_cell_texts()` → cell 텍스트 추출
- `detect_header_rows()` → 헤더 행 감지
- `cell_has_nested_table()` → 중첩표 탐지
- 병합셀 rowSpan/colSpan 계산

**출력**: `Table`, `Row`, `Cell` dataclass  
**상태**: 구현 예정

---

### 3.4 style_parser.py

**이식 대상**:
- header.xml 내 `charPr`, `paraPr`, `borderFill` 파싱
- 참조 ID 추적
- dangling ref 감지

**출력**: `StyleRegistry` dataclass  
**상태**: 신규 구현 필요 (현재 profiler에 미구현)

---

### 3.5 layout_classifier.py

**이식 대상**:
- `classify_table_layout()` 전체
- `_compute_table_scores()`
- 모든 KEYWORDS 상수 (METADATA_LABEL_KEYWORDS, STAMP_KEYWORDS 등)
- `normalize_header()`, `guess_field()`, `FIELD_HINTS`
- `DATE_HEADER_PATTERNS`, `is_date_like()`

**출력**: `ClassificationResult(layout, confidence, evidence)`  
**상태**: 이식 예정 (로직 변경 없음)

---

### 3.6 input_slot_detector.py

**이식 대상**: 신규  
**설계**: `docs/architecture/hwpx_input_slot_detector_design.md` 참조  
**상태**: 별도 공정 `HWPX-INPUT-SLOT-DETECTOR-01`

---

### 3.7 parser_contract.py

**역할**:
- V2 JSON 출력 팩토리 함수
- schemaVersion / engineVersion 주입
- `docs/contracts/hwpx_parser_engine_v2_contract.md` 스키마 구현

**상태**: 구현 예정

---

## 4. 분리 우선순위

| 우선순위 | 모듈 | 이유 |
|----------|------|------|
| 1 | `layout_classifier.py` | 현재 테스트 가장 많음, 분리 리스크 낮음 |
| 2 | `table_parser.py` | V2 계약의 핵심 (cells, grid) |
| 3 | `package_reader.py` | 모든 모듈의 입력 |
| 4 | `block_parser.py` | blockIndex 순서 보존 필요 |
| 5 | `style_parser.py` | 신규 구현, 현재 테스트 없음 |
| 6 | `parser_contract.py` | 최종 출력 조립 |
| 7 | `input_slot_detector.py` | 별도 공정 |

---

## 5. 이행 원칙

- 분리 중에도 `hwpx_corpus_profiler.py`를 계속 사용 가능하게 유지
- 각 모듈 분리 시 기존 fixture 회귀 테스트(`tests/test_hwpx_corpus_fixtures.py`) 통과 확인
- 한 번에 하나의 모듈만 분리 (원자적 커밋)
- 분리 후 profiler에서 해당 모듈 import 전환
