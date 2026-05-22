# HWPX Universal Form Recognition — 계약 문서

공정: HWPX-UNIVERSAL-FORM-RECOGNITION-AND-FILL-TEST-01  
HEAD 기준: a19af0e

---

## 목적

특정 서식에만 맞춘 인식이 아니라, 어떤 HWPX 서식이 들어와도
문서 구조를 읽고 입력칸을 찾아 안전하게 입력하는 범용 서식 인지 엔진.

---

## 1. formType 후보

| 코드 | 설명 |
|------|------|
| `metadata_form` | 기본정보표 위주 (공사명/시공사/작성일 등) |
| `application_form` | 신청서 계열 (접수번호/신청인/주소 등) |
| `inspection_form` | 검측/감리 일지 계열 |
| `material_inspection_form` | 자재 검수 계열 (품명/규격/수량/단가) |
| `schedule_form` | 공정표/일정표 계열 (gantt_like, calendar_like) |
| `contract_form` | 계약서 계열 (갑/을, 도급금액) |
| `agreement_form` | 합의서/협약서 계열 |
| `legal_form` | 법령 서식 (별지 제n호 서식) |
| `unknown_form` | 분류 불가 |

분류 기준:
- 서식 제목(fullText 첫 단락)
- 별지 서식 번호 패턴
- 표 구조와 라벨 분포
- inputSlotCandidates의 fieldGuess 분포

---

## 2. tableRole 후보

| 코드 | 설명 | 입력 가능 |
|------|------|----------|
| `basic_info` | 공사명/작성일 등 기본정보표 | YES |
| `data_table` | 반복 데이터 행 (품목/수량/단가 등) | YES (append) |
| `approval_stamp` | 직인/결재란 | **NO** |
| `page_marker` | 페이지 번호/쪽 표시 | **NO** |
| `legal_notice` | 법령 안내문/첨부서류 목록 | **NO** |
| `schedule_grid` | 공정 바(gantt) 그리드 | 조건부 |
| `attachment_table` | 첨부 서류 목록 | 조건부 |
| `unknown` | 분류 불가 | REVIEW_REQUIRED |

---

## 3. field 후보

| 필드명 | 대응 한글 키워드 |
|--------|----------------|
| `projectName` | 공사명, 사업명, 프로젝트명 |
| `siteName` | 현장명, 현장, 사업위치, 사업장소재지 |
| `contractorName` | 시공사, 도급사, 수급인, 업체명, 회사명, 상호 |
| `reportDate` | 작성일, 보고일, 제출일, 신고일자 |
| `receiptNumber` | 접수번호, 접수번, 문서번호 |
| `startDate` | 착수일, 착공일, 시작일 |
| `endDate` | 종료일, 완료일, 준공일 |
| `completionDate` | 준공일, 완공일 |
| `inspector` | 담당자, 검사자, 검토자, 감리원 |
| `materialName` | 품명, 자재명, 품목 |
| `quantity` | 수량, 규격수량 |
| `unit` | 단위 |
| `spec` | 규격, 사양 |
| `status` | 상태, 진행상태 |
| `remarks` | 비고, 참고, 특이사항 |
| `unknown` | 분류 불가 |

---

## 4. inputSlot 판단 결과 스키마

```json
{
  "slotId": "slot_t_s0_000_r4c1_0",
  "tableId": "t_s0_000",
  "tableRole": "basic_info",
  "fieldGuess": "projectName",
  "source": "label_right",
  "labelText": "공사명",
  "targetCell": {
    "tableId": "t_s0_000",
    "row": 4,
    "col": 1,
    "visualRow": 4,
    "visualCol": 1
  },
  "confidence": 0.93,
  "autoEditAllowed": true,
  "reviewRequiredReason": null,
  "evidence": [
    "known_label: 공사명",
    "source: label_right",
    "right_cell_empty",
    "tableRole: basic_info",
    "fieldGuess: projectName"
  ]
}
```

---

## 5. 탐지 규칙 우선순위

1. `label_right` — 라벨 오른쪽 빈칸 (confidence 0.85~0.93)
2. `label_below` — 라벨 아래 빈칸 (confidence 0.75~0.85)
3. `label_value_pair` — 2/4열 라벨-값 반복 구조 (confidence 0.80)
4. `merged_input_cell` — 병합된 대형 입력칸 (confidence 0.70)
5. `blank_after_known_header` — known field header 이후 빈칸 (confidence 0.75)
6. `metadata_form_slots` — 기본정보표 패턴 전체 (confidence 0.85)
7. `data_table_append_slot` — 반복 데이터표 마지막 빈 행 (confidence 0.70)

---

## 6. 안전 제외 규칙

다음 table/cell은 입력 대상에서 반드시 제외:
- `layoutGuess = stamp_or_approval_table` → tableRole = approval_stamp → **NO**
- `layoutGuess = page_marker_table` → tableRole = page_marker → **NO**
- `"쪽"` 또는 `"페이지"` 텍스트가 포함된 표 → **NO**
- `"직인"` / `"결재"` 텍스트가 포함된 표 → **NO**
- 법령 안내문 패턴 (`별지 제`, `처리절차`, `첨부서류`) → **NO**
- 모든 셀이 텍스트(text_ratio ≥ 0.9)이면서 입력 후보 없음 → **NO**

---

## 7. confidence 기준

| 범위 | 처리 |
|------|------|
| >= 0.90 | `AUTO_EDIT_ALLOWED = True` |
| 0.70 ~ 0.89 | plan 생성, `reviewRequiredReason` 기록 |
| < 0.70 | plan 생성 안 함, `REVIEW_REQUIRED` |
