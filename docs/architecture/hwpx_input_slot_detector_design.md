# HWPX Input Slot Detector — 설계 문서

**문서 코드**: HWPX-PARSER-ENGINE-V2-ARCHITECTURE-01  
**작성일**: 2026-05-17  
**구현 공정**: HWPX-INPUT-SLOT-DETECTOR-01 (별도 승인)

---

## 1. 역할

Parser V2의 구조 분석 결과(`cells[]`, `tables[]`)를 받아  
"어디에 값을 입력할 수 있는가"를 판단하는 탐지기.

Semantic Extractor와 Writer 사이의 브릿지 역할:

```
Parser V2 (cells + labels)
    │
    ▼
[Input Slot Detector]
    │
    ▼
inputSlotCandidates[]
    │
    ▼
Semantic Extractor (어떤 값을 넣을지 결정)
    │
    ▼
Writer/Editor (실제 입력 실행)
```

---

## 2. 탐지 규칙

### 2.1 label_right

```
[라벨 셀] [빈 셀 ← 입력칸]
```

**조건**:
- `cell.isLikelyLabel == true` (또는 `cell.text in FIELD_HINTS`)
- 같은 행, 오른쪽 바로 옆 셀이 비어있음 (`cell.text == ""`)
- 오른쪽 셀이 isCoveredByMerge가 아님

**출력**:
- `source`: `label_right`
- `labelText`: 라벨 셀의 `normalizedText`
- `fieldGuess`: FIELD_HINTS 매핑 결과

---

### 2.2 label_below

```
[라벨 셀]
[빈 셀 ← 입력칸]
```

**조건**:
- `cell.isLikelyLabel == true`
- 바로 아래 행, 같은 열에 빈 셀
- 아래 셀이 isCoveredByMerge가 아님

**출력**:
- `source`: `label_below`

---

### 2.3 form_pair

```
[라벨] [값] [라벨] [값]
[라벨] [값] [라벨] [값]
```

**조건**:
- 표 전체가 라벨/값 쌍 패턴 (metadata_table, form_table layoutGuess)
- label_value_pair_score >= 0.6
- 현재 값 셀이 비어있음

**출력**:
- `source`: `form_pair`

---

### 2.4 table_append_row

```
[반복 데이터 행]
[반복 데이터 행]
[빈 행 ← 새 데이터 입력 위치]
```

**조건**:
- vertical_table 또는 horizontal_schedule layoutGuess
- 마지막 행이 비어있거나 template 패턴
- 위 행들이 동일한 컬럼 구조를 반복

**출력**:
- `source`: `table_append_row`
- `fieldGuess`: 컬럼 헤더 기반

---

### 2.5 schedule_bar_range

```
공종     | 5월 | 6월 | 7월 | 8월 |
○○공사  | [범위 입력 ← 시작~종료 셀]
```

**조건**:
- `table.layoutGuess == "gantt_like_table"`
- 날짜축 헤더 감지됨 (`timeAxisCandidate` 비어있지 않음)
- 해당 행의 날짜 열들이 비어있음

**출력**:
- `source`: `schedule_bar_range`
- `fieldGuess`: `scheduleStartDate`, `scheduleEndDate`, `scheduleRange`
- 범위: 시작 col ~ 종료 col

---

### 2.6 status_cell

**조건**:
- 셀 텍스트 또는 헤더가 상태값 키워드 포함
  - 검측상태, 자재상태, 진행률, 완료여부, 합격/불합격
- 현재 빈 셀이거나 드롭다운 후보

**출력**:
- `source`: `status_cell`
- `fieldGuess`: `inspectionStatus`, `materialStatus`, `completionStatus` 등

---

### 2.7 ignore (입력칸 제외 대상)

다음 패턴은 탐지에서 제외한다:

| 제외 패턴 | 이유 |
|-----------|------|
| `layoutGuess == "stamp_or_approval_table"` | 직인/결재란은 입력칸 아님 |
| `layoutGuess == "page_marker_table"` | 페이지 번호 표 |
| `layoutGuess == "layout_noise"` | 장식/구분선 표 |
| 법령 안내 텍스트 셀 (legal_form_score 높음) | 수정 불가 법령 텍스트 |
| `cell.text` 길이 > 50 (긴 텍스트 셀) | 설명 문장, 입력칸 아님 |

---

## 3. 출력 필드

```json
{
  "slotId": "slot_t_s0_001_r1c2",
  "tableId": "t_s0_001",
  "source": "label_right",
  "labelText": "공사명",
  "fieldGuess": "projectName",
  "row": 1,
  "col": 2,
  "visualRow": 1,
  "visualCol": 2,
  "confidence": 0.9,
  "autoEditAllowed": true,
  "reviewRequiredReason": null,
  "evidence": ["label='공사명' in FIELD_HINTS", "right cell is empty", "cell not merged"],
  "warnings": []
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| slotId | str | 고유 ID |
| tableId | str | 소속 표 |
| source | str | 탐지 규칙 |
| labelText | str | 연관 라벨 텍스트 |
| fieldGuess | str | FIELD_HINTS 매핑 결과 |
| row / col | int | 셀 좌표 |
| visualRow / visualCol | int | visual grid 좌표 |
| confidence | float | 신뢰도 |
| autoEditAllowed | bool | confidence >= 0.9 이면 true |
| reviewRequiredReason | str \| null | 검토 필요 이유 |
| evidence | list[str] | 탐지 근거 |
| warnings | list[str] | 경고 |

---

## 4. 탐지 우선순위

1. `schedule_bar_range` (공정표, 최고 우선순위)
2. `label_right`
3. `label_below`
4. `form_pair`
5. `table_append_row`
6. `status_cell`
7. `ignore` 적용

---

## 5. 구현 공정

`HWPX-INPUT-SLOT-DETECTOR-01` 공정에서 구현한다.  
이번 공정(`HWPX-PARSER-ENGINE-V2-ARCHITECTURE-01`)에서는 설계만 완료.
