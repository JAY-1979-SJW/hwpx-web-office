# HWPX AI 인지 / Planner 경계 정의

공정: HWPX-AI-RECOGNITION-TO-HANCOM-SAFE-EDIT-PIPELINE-01  
HEAD 기준: ae47c2e

---

## 역할 분리 원칙

각 컴포넌트는 자신의 책임 범위만 처리한다.
Parser V2는 읽기만, Planner는 판단만, Writer는 쓰기만, Verifier는 검증만 한다.

---

## Parser V2가 제공하는 것

`parse_hwpx_v2(path) → ParserV2Result`

| 항목 | 설명 |
|------|------|
| `blocks[]` | 섹션별 순서가 있는 블록 목록 (paragraph / table / image / drawing / page_marker) |
| `tables[]` | 표 목록, 각 표의 행/열/병합 구조 |
| `cells[]` | 각 표의 셀 (row, col, normalizedText, isLikelyLabel, isLikelyInputSlot, isMergedOrigin, isCoveredByMerge) |
| `styles` | charPr/paraPr/borderFill 수량 및 참조 ID |
| `inputSlotCandidates[]` | 라벨-입력칸 쌍 후보 (source, labelText, fieldGuess, confidence) |
| normalized headers | normalizedText (공백/특수문자 정규화 완료) |

Parser V2가 **하지 않는 것**:
- 어떤 필드가 공사명인지 최종 판단 (hint만 제공)
- 어떤 값을 입력할지 결정
- XML 수정

---

## AI / Planner가 판단하는 것

`plan_builder.build_edit_plan(recognition_result, field_values) → PlanResult`

| 판단 항목 | 설명 |
|----------|------|
| 문서 유형 | 감리일지 / 검측요청서 / 착공신고서 등 |
| 필드-슬롯 매핑 | 어느 inputSlotCandidate가 공사명/현장명/담당자인지 |
| 입력칸 확정 | confidence >= 0.70이면 plan 생성, 미만이면 REVIEW_REQUIRED |
| 색상/상태값 | solid_fill 적용 여부 (규칙 기반 또는 AI 판단) |
| shrink_to_fit | 긴 텍스트 입력 시 자동 축소 여부 |
| confidence 판정 | 각 필드별 confidence + 전체 문서 confidence |

Planner가 **하지 않는 것**:
- XML 직접 접근
- 파일 읽기/쓰기
- 한컴 호환성 검증

---

## Writer가 하는 것

`hwpx_edit_tool.apply_edit_plan(input_path, output_path, plan)`

| 처리 항목 | 설명 |
|----------|------|
| `set_cells_by_label` | 라벨 텍스트로 셀 탐색 후 text node 수정 |
| `set_cells` | 물리 좌표 (row, col)로 직접 text node 수정 |
| `set_visual_cells` | 시각 좌표 (visual_row, visual_col)로 text node 수정 |
| `set_cell_fills` | borderFill ID 연결 또는 신규 생성 |
| `shrink_to_fit` | charPr fontSize 축소 적용 |
| `solid_fill` | 배경색 hex를 borderFill에 기록 |
| ZIP 재패키징 | mimetype ZIP_STORED 유지, namespace/XML declaration 보존 |
| 원본 보존 | input_path를 수정하지 않고 output_path에만 저장 |

Writer가 **하지 않는 것**:
- 어떤 셀에 무엇을 넣을지 판단
- Parser V2 호출
- 한컴 호환성 검증

---

## Verifier가 하는 것

### reparse_verifier

`reparse_verifier.verify(before, after, plan_result) → VerificationResult`

| 검증 항목 | 설명 |
|----------|------|
| 입력값 존재 확인 | after.cells에서 target cell normalizedText == 입력값 |
| 라벨 훼손 없음 | before/after 라벨 셀 텍스트 동일 |
| 비대상 셀 불변 | plan에 없는 셀 변경 없음 |
| dangling 없음 | after.styles.referencedCharPrIds ⊆ after.styles.charPrIds |
| 치명 경고 없음 | after.warnings에 XML_DECODE_FAIL / SECTION_READ_FAIL 없음 |

### hancom_safe_gate

`hancom_safe_gate.verify(output_path) → HancomVerifyResult`

`hwpx_full_verify.verify(path)` 결과를 래핑하여 판정 기준 적용:
- errors == 0 → PASS
- errors == 0, warnings > 0 → REVIEW_REQUIRED
- errors > 0 → FAIL

---

## 신뢰 방향 (단방향)

```
Parser V2 (읽기)
    ↓ ParserV2Result
Planner (판단)
    ↓ PlanResult
Writer (수정)
    ↓ output HWPX
Parser V2 (재읽기)
    ↓ after ParserV2Result
reparse_verifier (비교)
    ↓ VerificationResult
hancom_safe_gate (한컴 호환)
    ↓ HancomVerifyResult
final_decision
```

각 단계는 이전 단계의 출력만 소비한다. 역방향 의존 없음.

---

## confidence 기준표

| 범위 | 처리 |
|------|------|
| >= 0.90 | AUTO_EDIT_ALLOWED — plan 자동 생성, 확인 없이 실행 |
| 0.70 ~ 0.89 | REVIEW_SUGGESTED — plan 생성하되 reviewRequiredReason 기록 |
| < 0.70 | REVIEW_REQUIRED — plan 생성 안 함, 호출자에게 위임 |
