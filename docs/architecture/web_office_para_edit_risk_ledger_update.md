# RISK-LEDGER 갱신 — Phase 3 PARA-EDIT 사전 등기

> 공정명: WEB-OFFICE-PARA-EDIT-SPEC-01 (별책)
> 본 문서는 `web_office_risk_ledger.md` §3 (Phase 3+ 사전 등재) 의
> 상세 갱신본이다. 본 공정 단계에서는 모든 항목이 `PLANNED` 상태이며,
> Phase 3 IMPL 시공 시점에 회로/게이트와 함께 `OPEN` 또는 `MITIGATED`
> 로 전이된다.
>
> **본 별책은 append-mostly.** 삭제는 별도 §11-1 공정 + 대표님 명시
> 승인 필요.

---

## 1. 운영 원칙 인용

- ID: `R-P3-NN`
- 상태: `PLANNED` → (Phase 3 IMPL 시점) → `OPEN` / `MITIGATED` /
  `ACCEPTED` / `CLOSED`
- 본 별책 항목은 본 단지의 회귀 잠금 (현재 89/89) 과 함께 차단 게이트로
  통합된다.

---

## 2. R-P3-01 — run split/merge 중 스타일 손실

- **상태**: PLANNED (Phase 3 IMPL 에서 OPEN → MITIGATED)
- **위험**: SPLIT 이후 좌·우 run 중 한쪽이 charPrIDRef 를 잃거나,
  MERGE 가 서로 다른 charPr 의 run 을 합쳐 스타일이 어느 한쪽으로
  소실되는 사고
- **차단 게이트 (계획)**:
  - SPLIT_TEXT_RUN: 좌·우 모두 원래 charPrIDRef 상속 (불변)
  - MERGE_TEXT_RUNS: charPrIDRef 일치 시에만 허용 (`MERGE_CHARPR_MISMATCH` reject)
  - REPLACE_TEXT_RANGE 의 multi-charPr cross 는 policy 명시
    (ANCHOR_CHARPR / FOCUS_CHARPR / REQUIRES_REVIEW)
  - V4_CHARPR_PRESERVED 회귀
- **활성화 트리거**: Phase 3 IMPL 공정 (`WEB-OFFICE-PARA-EDIT-MODEL-01`)
- **결정 권한**: 대표님

## 3. R-P3-02 — expectedBefore stale (오래된 RO-VIEW 세션)

- **상태**: PLANNED (MVP-A R-MA-03 의 paragraph 일반화)
- **위험**: 사용자가 오래된 RO-VIEW snapshot 으로 편집한 후 save 시도
  → 서버 측 현재 paragraph text 와 expectedBefore 불일치
- **차단 게이트 (계획)**:
  - 클라이언트 RO-VIEW 의 `sourceDocumentHash` ≠ 서버 현재 sha → `STALE_SESSION`
  - paragraph text sha (paragraph 단위 fingerprint) 추가 비교 — 같은
    sourceDocumentHash 안에서도 paragraph 단위 stale 가능성 검출
  - V5p_EXPECTED_BEFORE_OK 게이트
- **활성화 트리거**: Phase 3 IMPL `paragraph_edit_plan` 신설 시
- **잔존 위험**: 사용자 UX (재로드 버튼) 는 Phase 3-followup 으로 분리

## 4. R-P3-03 — 문단 경계 cross-leak

- **상태**: PLANNED
- **위험**: REPLACE_TEXT_RANGE / TYPE_TEXT 가 의도한 paragraphId 외 다른
  paragraph 의 text 까지 변경되거나 새 텍스트가 leak
- **차단 게이트 (계획)**:
  - V2_NO_CROSS_PARAGRAPH_LEAK: output blob 의 byte-count 비교
  - paragraphId 기반 좌표 매칭 (`_filter_applied_runs_by_coord`)
  - LOCK_01 회로의 paragraph 일반화
- **활성화 트리거**: Phase 3 IMPL save-verify7 공정

## 5. R-P3-04 — charPrIDRef / parPrIDRef 손상

- **상태**: PLANNED
- **위험**: 명령 적용 후 charPrIDRef / parPrIDRef 가 변경되어 문서
  스타일이 깨짐. 신규 charPr 가 무단 생성되어 styles 사전이 비대해짐
- **차단 게이트 (계획)**:
  - V4_CHARPR_PRESERVED: 적용 후 charPrIDRef 집합 ⊆ 원본 집합
  - V5_PARPR_PRESERVED: parPrIDRef 변경 0건
  - 신규 charPr 생성 명령은 Phase 3 범위 밖 (`ApplyFormat` 미도입)
- **활성화 트리거**: Phase 3 IMPL

## 6. R-P3-05 — 한글 조합 / IME 입력 처리

- **상태**: PLANNED
- **위험**: 한글 조합 중에 commandLog 가 너무 자주 적재되어 undo
  단위가 비정상이 되거나, composition 도중 ESC 로 cancel 된 입력이
  commandLog 에 남음
- **차단 게이트 (계획)**:
  - `compositionstart` ~ `compositionend` 사이 commandLog 적재 잠금
  - `compositionend` 에서 단일 TYPE_TEXT command 발행
  - composition cancel 시 commandLog 변화 0
- **활성화 트리거**: Phase 3 IMPL browser 공정
- **잔존 위험**: 일부 OS / IME 조합에서 compositionend 미발생 — 별도
  fallback (300ms idle) 검토

## 7. R-P3-06 — 줄바꿈 / 문단 끝 문자 처리

- **상태**: PLANNED → ACCEPTED (영구 차단)
- **위험**: 사용자가 Enter 키로 paragraph 를 신규 생성 / 분할하려 함
  → Phase 3 범위 밖
- **차단 게이트 (계획)**:
  - UI 레벨에서 Enter 키 capture → paragraph add 명령 발행 차단
  - paragraph add/delete 는 별도 Phase 3-followup
- **활성화 트리거**: 영구 차단 (Phase 3 범위)

## 8. R-P3-07 — 문단 편집과 셀 편집 command 충돌

- **상태**: PLANNED
- **위험**: 같은 commandGroup 안에 SET_CELL_TEXT (cell 전체) 와
  TYPE_TEXT (cell 내부 paragraph) 가 같은 cell 을 동시에 변경하려 함 —
  결과가 정의되지 않음
- **차단 게이트 (계획)**:
  - 같은 commandGroup 안 동일 cellId 에 대해 두 종류 명령 동시 등재 금지
  - validator 단계에서 reject (`COMMAND_TYPE_CONFLICT_IN_GROUP`)
  - SET_CELL_TEXT 자체 회로는 무수정 (CELL-EDIT 코드 변경 금지)
- **활성화 트리거**: Phase 3 IMPL model 공정

---

## 9. Phase 3 IMPL 공정에 전달할 게이트 체크리스트

Phase 3 IMPL (`WEB-OFFICE-PARA-EDIT-MODEL-01` 이후) 시공 시 본 별책의
모든 게이트는 정적/회귀 테스트로 잠금되어야 한다:

| ID | 게이트 코드 |
|----|-------------|
| R-P3-01 | charPr 일치 검증 회로 + V4_CHARPR_PRESERVED 회귀 |
| R-P3-02 | STALE_SESSION reject + V5p 회귀 |
| R-P3-03 | V2_NO_CROSS_PARAGRAPH_LEAK + paragraph 좌표 매칭 |
| R-P3-04 | V4 / V5 + ApplyFormat 미도입 정적 잠금 |
| R-P3-05 | composition lock 회로 + JS 자체 테스트 |
| R-P3-06 | Enter capture 회로 + 정적 검사 |
| R-P3-07 | commandGroup validator + 회귀 |

본 시방서 PASS 후, Phase 3 IMPL 공정의 audit 가 위 모든 게이트의 회로
존재를 정적으로 검사한다.

---

## 10. 변경 절차

본 별책은 `web_office_risk_ledger.md` 의 §4 (변경 절차) 와 동일한
정책을 따른다:

- 추가: ② 시방서 발의 + audit PASS 유지
- 상태 전이: 회로/게이트 동반
- 삭제: 별도 공정 + 대표님 명시 승인

---

*생성: WEB-OFFICE-PARA-EDIT-SPEC-01 별책 (2026-05-20)*

> **저장소 분리 기준**: e04d325 (hwpx-web-office 신규 저장소 초기 커밋, 2026-05-22)
