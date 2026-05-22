# HWPX 문서 구조 분석 vs 의미 분석 경계 정의

## 개요

HWPX 파서 V2는 두 가지 분석 계층을 명확히 분리한다.

- **구조 분석 (Structural Analysis)**: XML 요소의 물리적 배치를 파악한다.
- **의미 분석 (Semantic Analysis)**: 텍스트 내용과 레이아웃 패턴에서 의미를 추론한다.

두 계층을 분리함으로써 파서 엔진의 책임을 제한하고, 의미 추론의 오류가 구조 파싱을 오염시키지 않도록 한다.

---

## 구조 분석 (Structural Analysis)

### 정의

문서 XML에서 **객관적으로 확인 가능한** 물리적 구조를 추출한다.

### 포함 항목

| 항목 | 설명 |
|------|------|
| 테이블 구조 | 행/열 수, 병합 셀, span 범위 |
| 블록 순서 | paragraph / table / object 순서 |
| 셀 텍스트 | 셀 내부의 원시 텍스트 (정규화 전) |
| 스타일 참조 | charPr, paraPr, 폰트·크기·색상 |
| 레이아웃 메타 | 페이지 구분, 섹션 경계 |
| 객체 참조 | 이미지/도형 binData ID |

### 금지 항목

- 셀 텍스트의 의미 해석
- 레이블/값 관계 추론
- 양식 종류 분류

### 출력 타입

`ParserV2Result.blocks`, `ParserV2Result.tables`, `ParserV2Result.cells`

---

## 의미 분석 (Semantic Analysis)

### 정의

구조 분석 결과를 입력으로 받아 **도메인 지식 기반의 추론**을 수행한다.

### 포함 항목

| 항목 | 설명 |
|------|------|
| 입력 슬롯 감지 | label_right / label_below / label_value_pair 패턴 |
| 양식 유형 분류 | fillable_form / reference_table / empty_template |
| 테이블 역할 분류 | main_form / approval_stamp / page_marker |
| 필드 매핑 | labelText → fieldGuess (projectName 등) |
| 안전 대상 필터링 | page_marker / approval_stamp 테이블 제외 |

### 금지 항목

- XML 직접 파싱 (구조 분석 결과만 사용)
- HWPX 파일 쓰기
- OCR 또는 이미지 분석

### 출력 타입

`FormRecognitionResult.enhancedSlots`, `FormRecognitionResult.tableRoles`

---

## Confidence 정책

의미 분석 결과에는 신뢰도(confidence) 점수가 부여된다.

| 구간 | 판정 | 처리 |
|------|------|------|
| `confidence >= 0.80` | HIGH | 자동 실행 허용 |
| `0.70 <= confidence < 0.80` | MEDIUM | 자동 실행 허용 (주의) |
| `confidence < 0.70` | LOW | `reviewRequired = True`, 사람 검토 필수 |

- 구조 분석 결과에는 confidence를 부여하지 않는다.
- 슬롯 전체 평균 confidence가 `0.70` 미만이면 파이프라인은 `REVIEW_REQUIRED`로 처리한다.
- `fieldGuess == "unknown"` 슬롯은 계획 생성에서 제외된다.

---

## 계층 분리 원칙

```
[HWPX 파일]
    ↓ parse_hwpx_v2()
[ParserV2Result]          ← 구조 분석 결과 (read-only)
    ↓ recognize_form()
[FormRecognitionResult]   ← 의미 분석 결과
    ↓ build_edit_plan_from_form()
[PlanResult]              ← 편집 계획
```

파서 엔진(`parser/`)은 구조 분석만 담당한다.
의미 분석은 `pipeline/form_recognizer.py`와 `pipeline/plan_builder.py`가 담당한다.
두 계층 간 역방향 의존성(의미→구조)은 금지한다.
