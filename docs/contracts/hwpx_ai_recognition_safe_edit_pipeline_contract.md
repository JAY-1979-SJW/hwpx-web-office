# HWPX AI Recognition Safe Edit Pipeline — 계약 문서

공정: HWPX-AI-RECOGNITION-TO-HANCOM-SAFE-EDIT-PIPELINE-01  
HEAD 기준: ae47c2e

---

## 파이프라인 목적

HWPX 문서를 Parser V2로 읽고, AI/규칙 기반 Planner가 입력칸을 인지하여 편집 계획을 수립하고,
Writer가 실제 XML을 수정한 뒤, 재파싱 검증과 한컴 호환성 검증을 통과한 HWPX를 출력한다.

원본 HWPX는 절대 수정하지 않는다. 결과물은 output 경로에만 생성한다.

---

## 파이프라인 단계

### 1. parse_before

- 입력: 원본 HWPX 경로
- 처리: `parse_hwpx_v2(path)` 호출
- 출력: `ParserV2Result`
  - package, document, blocks[], tables[], cells[], styles
  - inputSlotCandidates[], warnings[], errors[]
- 실패 조건: errors[] 비어 있지 않으면 파이프라인 중단

### 2. recognize

- 입력: `ParserV2Result`
- 처리: inputSlotCandidates + tables + blocks를 분석하여 필드별 입력 위치 후보 도출
- 출력: `RecognitionResult`
  - detectedLabels: list[str]
  - slotMap: dict[fieldName, InputSlotCandidate]
  - documentType: str
  - confidence: float
  - reviewRequired: bool
- 규칙: confidence < 0.70이면 reviewRequired=True, 파이프라인 진행 여부 호출자가 결정

### 3. plan

- 입력: `RecognitionResult` + 입력 데이터(fieldValues: dict)
- 처리: `plan_builder.build_edit_plan()` 호출
- 출력: `PlanResult`
  - editPlan: dict (apply_edit_plan 포맷)
  - plannedFields: list[str]
  - skippedFields: list[str] (REVIEW_REQUIRED)
  - reviewRequiredReasons: dict[fieldName, str]

edit plan 포맷 (hwpx_edit_tool.apply_edit_plan 호환):
```json
{
  "set_cells_by_label": [
    {
      "contains": "공사명",
      "value": "...",
      "shrink_to_fit": true,
      "solid_fill": {"color": "D9EAF7"},
      "vertical_align": "CENTER"
    }
  ]
}
```

지원 연산:
- `set_cells_by_label`: 라벨 텍스트로 셀 탐색 후 값 입력
- `set_cells`: 물리 좌표 (row, col)로 직접 입력
- `set_visual_cells`: 시각 좌표 (visual_row, visual_col)로 입력
- `set_cell_fills`: 색상만 적용
- `shrink_to_fit`: 텍스트 길면 폰트 자동 축소
- `solid_fill`: 배경색 적용 (`color`: hex 6자리)

### 4. edit

- 입력: 원본 HWPX 경로, `PlanResult.editPlan`, output 경로
- 처리: `hwpx_edit_tool.apply_edit_plan(input_path, output_path, plan)`
- 출력: output HWPX 파일 + `EditResult`
  - changedCells: list
  - warnings: list
  - errors: list
- 실패 조건: EditResult.errors 비어 있지 않으면 FAIL

### 5. parse_after

- 입력: output HWPX 경로 (편집 결과물)
- 처리: `parse_hwpx_v2(output_path)` 호출
- 출력: `ParserV2Result` (after)
- 비교 기준: parse_before 결과와 대조

### 6. compare

- 입력: before/after `ParserV2Result`, `PlanResult`
- 처리: `reparse_verifier.verify()` 호출
- 검증 항목:
  1. 입력값이 target cell에 존재 (normalizedText 일치)
  2. 라벨 셀 텍스트 훼손 없음
  3. 비대상 셀 텍스트 변경 없음
  4. shrink_to_fit 적용 시 charPr dangling 없음
  5. solid_fill 적용 시 borderFill dangling 없음
  6. after.warnings에 치명적 경고 없음
- 출력: `VerificationResult`
  - expectedFields: dict
  - actualFields: dict
  - matched: list
  - mismatched: list
  - warnings: list
  - decision: "PASS" | "REVIEW_REQUIRED" | "FAIL"

### 7. hancom_verify

- 입력: output HWPX 경로
- 처리: `hancom_safe_gate.verify()` → `hwpx_full_verify.verify()` 호출
- 검증 항목:
  - mimetype `application/hwp+zip` 또는 `application/owpml`
  - mimetype ZIP_STORED (무압축)
  - entry count 정상 (>= 5)
  - META-INF/container.xml 유효
  - Contents/content.hpf 유효
  - manifest/spine 참조 무결성
  - Contents/header.xml charPr/paraPr/borderFill 정의 추출
  - section XML well-formed + ID 참조 유효
  - 전체 XML UTF-8 decode 정상
- 출력: `HancomVerifyResult`
  - errors: list
  - warnings: list
  - verdict: "PASS" | "REVIEW_REQUIRED" | "FAIL"

### 8. final_decision

- 입력: `VerificationResult`, `HancomVerifyResult`
- 판정 규칙:
  - hancom_verify.errors == 0 AND compare.decision == "PASS" → **PASS**
  - hancom_verify.errors == 0 AND compare.decision == "REVIEW_REQUIRED" → **REVIEW_REQUIRED**
  - hancom_verify.errors > 0 OR compare.decision == "FAIL" → **FAIL**
- 출력: `PipelineResult.finalDecision`

---

## PipelineResult 스키마

```json
{
  "schemaVersion": "v1",
  "requestId": "...",
  "inputFile": "...(hash)...",
  "outputFile": "...(path)...",
  "stages": {
    "parse_before": "ok|error",
    "recognize": "ok|review_required|error",
    "plan": "ok|partial|error",
    "edit": "ok|error",
    "parse_after": "ok|error",
    "compare": "PASS|REVIEW_REQUIRED|FAIL",
    "hancom_verify": "PASS|REVIEW_REQUIRED|FAIL"
  },
  "finalDecision": "PASS|REVIEW_REQUIRED|FAIL",
  "recognition": { ... },
  "plan": { ... },
  "verification": { ... },
  "hancomVerify": { ... },
  "warnings": [],
  "errors": []
}
```

---

## 불변 원칙

- 원본 HWPX 수정 금지
- repair_for_server 사용 금지
- mimetype ZIP_STORED 유지 필수
- content.hpf / manifest / container 훼손 금지
- dangling charPr / paraPr / borderFill 참조 금지
- output 경로 외 파일 생성 금지
- UI 구현 이번 범위 제외
