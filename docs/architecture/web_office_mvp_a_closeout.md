# Web Office MVP-A 부분 준공 등기서

> 공정명: WEB-OFFICE-MVP-A-PARTIAL-CLOSEOUT-RISK-LEDGER-01
> 작성일: 2026-05-20
> MVP-A 준공 기준 HEAD: `87b3428`
> 분류: §11-1 ⑥ 준공검사 + §11-5 부분 준공 등기
> 정책 준수: CLAUDE.md §1~§11 전체
> 본 공정 범위: **문서화/감사/계약 잠금 전용.** 코드 변경, writer 호출,
> output HWPX 생성, 원본 접근 모두 금지.

---

## 1. MVP-A 준공 범위

본 등기서는 Web Office Editor **Phase 2 CELL-EDIT MVP-A** 의 부분 준공
범위를 단지 정본으로 확정한다. 이 범위 밖의 모든 기능은 **미준공**
이며, 별도 Phase 공정 + 대표님 명시 승인 없이 시공할 수 없다.

### 1-1. 준공 시점 anchor

| 항목 | 값 |
|------|----|
| 준공 commit | `87b3428` |
| 회귀 잠금 commit 체인 | `467b4de` (DESIGN-LOCK) → `8f9fd4d` (RO-VIEW MVP) → `9818fc2` (VIEWER prototype) → `fe74cf1` (RUNTIME smoke) → `8bfbd8f` (CELL-EDIT MVP-A 안전 게이트) → `87b3428` (CELL-SAVE V1~V7) |
| 전체 회귀 시점 | 73/73 PASS (7.00s) |
| 본 등기 공정 (closeout) | (본 공정 commit 으로 갱신) |

---

## 2. 지원 기능 (MVP-A 준공 인정)

| 코드명 | 자재 | 회귀 잠금 테스트 |
|--------|------|-----------------|
| **SET_CELL_TEXT** | `edit_command_model.make_set_cell_text_command` | `test_web_office_cell_edit_mvp_a.test_edit_command_schema_required_fields` |
| **셀 선택** | `cell_edit_state.selectCell` + `data-navigation-id` | `cell_edit_self_test.mjs::selectCell` |
| **셀 텍스트 편집** | `cell_edit_state.commitCellText` + `WebOfficeCellEditor.tsx` | `cell_edit_self_test.mjs::commitChange/noChangeNoCommand` |
| **EditCommand v1** | `EditCommand` dataclass / JS object | `test_edit_command_schema_required_fields` |
| **forward / inverse** | `apply_forward` / `apply_inverse` | `test_forward_and_inverse_roundtrip` |
| **undo / redo** | `cell_edit_state.undo` / `redo` | `cell_edit_self_test.mjs::undo/redo/emptyUndo` |
| **save dry-run** | `cell_edit_plan.build_dry_run_edit_plan` | `test_empty_command_log_is_noop`·`test_ready_plan_for_valid_command` |
| **sandbox output** | `cell_save_pipeline.save_cell_edits` (outputPath sandbox 강제) | `test_output_equals_source_blocked`·`test_output_path_must_be_under_sandbox_via_v6` |
| **verify7 V1~V7** | `cell_save_verify7.verify7` | `test_single_set_cell_text_pass_full_pipeline` |
| **원본 sha/mtime 무변경 확인** | V4 + 사후 게이트 + 별도 회귀 테스트 | `test_source_sha_and_mtime_unchanged_after_all_scenarios` |

---

## 3. 비지원 기능 (MVP-A 범위 밖 — 시공 금지)

| 코드명 | 사유 / 향후 Phase |
|--------|------------------|
| **문단 run 편집** (TypeText/ReplaceTextRange) | Phase 3 PARA-EDIT 에서 시공. 한컴 완전 호환 1차 비목표 (§1-2) |
| **표 행/열 추가·삭제** | Phase 4 TABLE-OPS |
| **셀 병합 / 나누기** | Phase 4 TABLE-OPS |
| **이미지 / 도장 / 서명 편집** | Phase 5 IMAGE-STAMP |
| **AI 자동 입력** | Phase 6 AI-CONFIRM (§10 게이트 강제) |
| **브라우저에서 HWPX XML 직접 파싱** | RO-VIEW 정책 — 영구 금지 (DOMParser / XMLHttpRequest 정적 검사 잠금) |
| **원본 HWPX 직접 수정** | 영구 금지 — `outputPath == sourcePath` 차단 + V4/V6 게이트 |
| **다중 사용자 협업 (CRDT 등)** | 비목표 (설계서 §1-2) |
| **픽셀 단위 한컴 호환 렌더링** | 비목표 — layoutGuess + block 경계까지가 MVP |

---

## 4. 안전 게이트 (MVP-A 시점에 정착)

| 게이트 | 위치 | 회로 |
|--------|------|------|
| **sourceDocumentHash mismatch 차단** | `cell_edit_plan.build_dry_run_edit_plan` | `SAVE_DRY_RUN_REJECTED` + `reason=SOURCE_HASH_MISMATCH` |
| **expectedBefore mismatch 차단** | `edit_command_model.apply_forward` + plan 게이트 | `ValueError` + plan REJECTED |
| **outputPath == sourcePath 차단** | `cell_save_pipeline.save_cell_edits` | `OUTPUT_EQUALS_SOURCE` 즉시 REJECTED |
| **applied=∅ vacuous PASS 차단** | dry-run 후 검사 + V5_NO_ACCEPTED_COMMANDS | DRY_RUN_NO_APPLIED → 본 실행 차단 |
| **partial-success 분리 기록** | `_filter_applied_cells_by_coord` (LOCK_01 회로) | `applied_cells` / `rejected_cells` 좌표 매칭 |
| **verify7 PASS 전 본 실행 차단** | dry_run=True → applied 확인 → dry_run=False | 2-pass 흐름 |
| **원본 sha/mtime 사후 검증** | V4_SOURCE_HASH_OK | `_sha(source) == before` + `mtime_ns == before` |

---

## 5. 현재 한계

1. **SET_CELL_TEXT only** — 셀 텍스트 1종만 지원. 그 외 모든 편집 명령은
   미구현. EditCommand `commandType` enum 은 단일 값.
2. **문단 단위 편집 불가** — runs[] 단위 변형 (TypeText / split / merge /
   format) 회로 미구축. Phase 3 에서 도입.
3. **이미지 / 서명** — placeholder 구조만 있고 편집 UI / writer 연결 없음.
4. **AI 자동 채움 미연결** — 본 단지의 `ai_proposal_contract` 와 Web Office
   commandLog 사이 결합 없음. AI inject 게이트 (§10) 는 유효하나 UI 미구축.
5. **PDF / XLSX export 미구현** — Phase 8/9 에서 도입.
6. **multi-session / audit dashboard 미구현** — Phase 10.
7. **한컴 호환** — 비목표 명시 (설계서 §1-2). self-roundtrip 만 보장.
8. **풀 페이지네이션 렌더** — layoutGuess + block 경계까지. 픽셀 단위
   재현은 비목표.

---

## 6. Phase 3 PARA-EDIT 착공 조건

Phase 3 시공은 다음 조건이 **모두 충족** 된 후에만 ④ 시공 단계로 진입한다:

1. **MVP-A 회귀 73/73 PASS 유지** — 본 등기 commit 시점 회귀 결과를
   기준선으로 한다.
2. **Phase 3 시방서 작성 완료** — TypeText / ReplaceTextRange /
   ApplyFormat 명령 타입 정의 + charPrIDRef·parPrIDRef 보존 정책 포함.
3. **대표님 명시 승인** ("진행" / "시공 착수" 등) — §11-1 ③ 게이트.
4. **PARA-EDIT 회귀 시나리오 사전 설계** — run split/merge,
   stable runId 보존, V4/V5 (charPr/parPr) 회귀 추가 안건 포함.
5. **본 등기서의 위험대장(§8)에 PARA-EDIT 위험 항목이 등록되고
   완화 대책이 명시됨** — 본 closeout 의 다음 갱신 공정.

조건 미충족 시 PARA-EDIT 선시공은 §6 안전 금지선 위반과 동급으로 차단
한다 (cell_edit_plan / cell_save_pipeline 의 `commandType` 분기에
`TypeText` 등을 추가하는 PR 자체를 reject).

---

## 7. 회귀 테스트 목록 (MVP-A 잠금 자산)

| 테스트 파일 | 케이스 수 | 잠금 회로 |
|-------------|----------|-----------|
| `tests/test_hwpx_web_office_architecture_contract.py` | 9 | 설계서 필수 섹션 / writer 금지 문구 |
| `tests/test_web_office_ro_view_mvp.py` | 10 | DocumentModel v1 / stable id / src 무변경 |
| `tests/test_web_office_browser_viewer_prototype.py` | 8 | viewer 정적 검사 + node 실 렌더 |
| `tests/test_web_office_browser_runtime_smoke.py` | 9 | http.server + DOM smoke + read-only DOM |
| `tests/test_web_office_cell_edit_mvp_a.py` | 15 | EditCommand v1 + dry-run plan + JS state |
| `tests/test_web_office_cell_save_hwpx_verify7.py` | 13 | writer 연결 + V1~V7 + 8 시나리오 |
| `tests/test_claude_inline_partial_success_regression.py` | 9 | LOCK_01 (좌표 매칭 + applied=∅) |
| **합계** | **73** | **MVP-A 안전망 전체** |

---

## 8. 위험대장 (RISK-LEDGER 별책 `web_office_risk_ledger.md` 본 등기서 부속)

본 등기서가 정착시키는 핵심 위험과 대응은 별책 RISK-LEDGER 에 정본
보관한다 (단지 §11-5 부분 준공 원칙 — "다음 활성화 트리거와 결정 권한이
RISK-LEDGER 에 등기").

본 절은 요약만 인용. 항목별 상세는 별책 §2 ~ §N 참조.

| ID | 위험 | 차단 게이트 (현 시점) | 잔존 위험 |
|----|------|----------------------|-----------|
| R-MA-01 | 원본 HWPX 오염 | V4 + outputPath==sourcePath 차단 | 외부 ops 가 원본 권한을 write 로 바꾸면 우회 가능 |
| R-MA-02 | applied=∅ vacuous PASS | DRY_RUN_NO_APPLIED + V5_NO_ACCEPTED | — |
| R-MA-03 | expectedBefore stale | plan reject + V5 게이트 | 사용자 세션이 오래된 RO-VIEW 를 들고 있을 때 UX 처리 미구축 |
| R-MA-04 | PARA-EDIT 선시공 | 본 등기서 §6 / closeout audit grep | 사람이 commandType enum 을 임의 확장하면 우회 가능 — 본 공정 audit 가 잡음 |
| R-MA-05 | 라이선스 사고 | 외부 core dep 신규 도입 없음 (설계서 §16) | 향후 Phase 시공에서 도입 시 별도 ADR 필수 |
| R-MA-06 | AI 자동 확정 | §10 게이트 유지, MVP-A 에 AI 회로 미연결 | Phase 6 시공 시 별도 검토 |
| R-MA-07 | sha mismatch 사일런트 PASS | plan reject + V4 게이트 | — |
| R-MA-08 | 한컴 호환 강요 | 비목표 명시 (설계서 §1-2, 본 등기서 §3) | 외부 요구가 들어오면 별도 공정 |

---

## 9. 다음 공정 PARA-EDIT 범위 (예고)

다음 시공 공정 코드명: **WEB-OFFICE-PARA-EDIT-MVP-B-PRECURSOR-01**
(MVP-B 정식 진입 전 사전 시방서).

예상 범위 (확정 아님, 시방서 작성 단계에서 조정):

- `commandType ∈ { TypeText, ReplaceTextRange, DeleteRange, ApplyFormat }`
- run 단위 split / merge, charPrIDRef / parPrIDRef 보존
- charPr 신규 추가 시 styles.charPr 테이블 갱신
- 빈 paragraph / 빈 cell textNode 보존 (W-known)
- verify7 확장: V8_CHARPR_PRESERVED, V9_RUN_BOUNDARY_OK (예정)
- LOCK_01 좌표 매칭 회로는 셀 외부 (paragraph) 까지 일반화 필요

---

## 10. 금지사항 (본 단지 정본)

본 등기서 시점부터 다음 행위는 §6 안전 금지선과 동급:

- 원본 직접 수정 (writer 가 sourcePath 를 출력 경로로 받는 것 포함)
- writer 코드(`hwpx_edit_tool.apply_edit_plan` 등) 무단 수정
- `apply_edit_plan` 로직 변경 (시그니처 / 분기 / 부작용)
- output HWPX 가 sandbox 외부에 생성되는 경로 추가
- 원본 HWPX read-only 정책 무력화
- CELL-EDIT 기능을 임의로 확장 (commandType enum 추가 포함)
- PARA-EDIT / TABLE-OPS / IMAGE-STAMP 선시공
- AI 자동 입력을 §10 게이트 우회로 도입
- 브라우저에서 HWPX XML 직접 파싱 (DOMParser / XMLHttpRequest)
- 본 등기서 / 위험대장 무단 삭제 / 수정

위 항목 위반 시 본 공정 closeout audit 가 FAIL 로 즉시 차단한다.

---

*생성: WEB-OFFICE-MVP-A-PARTIAL-CLOSEOUT-RISK-LEDGER-01 (2026-05-20)*

> **저장소 분리 기준**: e04d325 (hwpx-web-office 신규 저장소 초기 커밋, 2026-05-22)
