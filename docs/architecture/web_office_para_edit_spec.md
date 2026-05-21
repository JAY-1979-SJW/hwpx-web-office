# Phase 3 PARA-EDIT 시방서 (Web Office Editor)

> 공정명: WEB-OFFICE-PARA-EDIT-SPEC-01
> 작성일: 2026-05-20
> 기준 HEAD: `a2bd9bd` (MVP-A closeout 직후)
> 분류: §11-1 ② 시공 계획서 (Phase 3 PARA-EDIT 사전 시방서)
> 정책 준수: CLAUDE.md §1~§11, 설계서 `hwpx_web_office_editor_deep_architecture.md`,
> 등기서 `web_office_mvp_a_closeout.md`, 별책 `web_office_risk_ledger.md`
>
> **본 공정 범위**: 설계·감사·계약 잠금 전용. 실제 PARA-EDIT 코드 구현,
> writer 실행, output HWPX 생성, 원본 HWPX 접근 모두 **금지**.
> 본 시방서는 Phase 3 착공 조건 #2 (시방서 작성) 를 충족시킨다.

---

## 1. Phase 3 PARA-EDIT 목표

문단 (paragraph) 단위 텍스트 편집을 EditCommand v2 로 안전하게 도입한다.
사용자 입력은 모두 run 단위 변형으로 환원되며, 원본 HWPX 직접 수정은
영구 금지된다. MVP-A 의 SET_CELL_TEXT 회로와 안전 게이트는 그대로
유지하면서, 문단 본문 (cell 내부 paragraphs + top-level paragraphs) 의
부분 치환을 가능하게 만든다.

성공 기준:

- 문단 부분 치환 / 삽입 / 삭제가 brower 에서 수행 가능
- 모든 변경은 EditCommand v2 의 forward / inverse 로 환원
- charPrIDRef / parPrIDRef 가 보존 (V4·V5 회귀)
- 한 run 안의 부분 치환은 자동 split → 신규 run 삽입 → 인접 동일
  charPr run 자동 merge
- verify7 V1~V7 의 의미가 paragraph 까지 확장
- MVP-A 회귀 (현재 89/89) 무손상

## 2. 비목표 (Phase 3 한정)

- **표 구조 편집** (행/열 추가·삭제, 셀 병합/나누기) — Phase 4
- **이미지 / 도장 / 서명 편집** — Phase 5
- **AI 자동 입력** — Phase 6
- **PDF / XLSX export** — Phase 8/9
- **다중 사용자 협업 (CRDT)** — 영구 비목표
- **픽셀 단위 한컴 호환 페이지 렌더** — 영구 비목표 (설계서 §1-2)
- **임베디드 폰트 / 한자 변환 / IME 자동 완성 UX** — Phase 3+ 별도
  공정. 본 Phase 는 IME composition end 까지만 받음 (§14)

## 3. MVP-A 와의 경계

| 항목 | MVP-A (SET_CELL_TEXT) | PARA-EDIT (Phase 3) |
|------|----------------------|---------------------|
| 단위 | cell 전체 텍스트 교체 | run 단위 split / insert / delete |
| commandType | `SET_CELL_TEXT` 단독 | `TYPE_TEXT`, `REPLACE_TEXT_RANGE`, `DELETE_TEXT_RANGE`, `SET_PARAGRAPH_TEXT_SAFE`, `SPLIT_TEXT_RUN`, `MERGE_TEXT_RUNS` 6 종 추가 |
| 식별 | cellId 만 | cellId + paragraphId + runId + offset/range |
| 스타일 보존 | (적용 안 됨 — 셀 전체 텍스트라 charPr 비유관) | charPrIDRef / parPrIDRef 보존 의무 (V4·V5) |
| writer | `apply_edit_plan(set_cells)` | `apply_edit_plan` 확장 (Phase 3 별도 시공) — **본 시방서 범위 밖**, 후속 공정 SPEC →  IMPL 단계 분리 |
| 안전 게이트 | sourceHash / expectedBefore / output==source / applied=∅ / V1~V7 | 동일 게이트 + 문단 verify 확장 |

PARA-EDIT 도입 시 **MVP-A 의 SET_CELL_TEXT command 는 그대로 유지**되며,
`commandType` enum 에 추가 6 종이 등재될 뿐 기존 회로는 변형되지
않는다. CELL-EDIT 코드 변경 금지.

## 4. 문단 / Run 모델

RO-VIEW 의 `WebOfficeParagraph` / `WebOfficeTextRun` 을 그대로 사용.
PARA-EDIT 는 다음 invariant 를 추가:

- 모든 `WebOfficeParagraph.runs[]` 의 합산 text == `WebOfficeParagraph.text`
- 인접 두 run 이 동일 `charPrIDRef` 라면 정규화 단계에서 자동 merge
- run 텍스트가 빈 문자열이면 정규화 단계에서 제거 (단, paragraph 가
  완전히 비면 빈 run 1개 유지 — 빈 cell textNode 회로 인용)
- runId 는 stable id (`{paragraphId}_run{n}`) — split / merge 시 재계산
  되며, 이전 runId 는 commandLog 의 inverse 에 보존

## 5. ParagraphTarget 모델

```jsonc
ParagraphTarget = {
  "paragraphId": "par_{tableId}_r{r}_c{c}_p{n}" | "par_s{s}_b{b}_p{n}",
  "containerKind": "cell" | "block",   // 셀 내부인지 top-level 인지
  "containerId":   "cellId | blockId",
  "sourceRef":     { "sha256": "...", "path": "..." }
}
```

- containerKind 가 "cell" 이면 셀 좌표 (table, row, col) 도 sourceRef 에
  부속하여 writer plan 변환 시 사용.
- containerKind 가 "block" 이면 top-level paragraph block — Phase 3 의
  writer 연결 시 별도 plan key (`set_paragraph_runs`, 후속 공정) 필요.

## 6. TextRange 모델

```jsonc
TextRange = {
  "paragraphId": "...",
  "anchor": { "runId": "...", "offset": <int, UTF-16 code unit> },
  "focus":  { "runId": "...", "offset": <int> },
  "expectedBefore": "<문자열>",      // anchor..focus 범위의 현재 text
  "normalizedAnchor": { "runId": "...", "offset": <int> },  // split 후
  "normalizedFocus":  { "runId": "...", "offset": <int> }
}
```

- anchor ≤ focus 의 정규화는 클라이언트에서 사전에 수행
- offset 은 UTF-16 code unit (브라우저 DOM 표준과 호환)
- run 경계 정렬은 EditCommand 적용 시점에 SPLIT_TEXT_RUN 으로 자동
  수행 — 호출자는 run 경계를 알 필요 없음

## 7. commandType 설계 (EditCommand v2)

기존 v1 + 6 종 추가. 각 명령은 forward / inverse 동반.

| commandType | 목적 | forward 산출 (plan fragment) |
|-------------|------|------------------------------|
| `SET_CELL_TEXT` (MVP-A) | 셀 전체 텍스트 교체 | `set_cells: [{table,row,col,value}]` |
| `TYPE_TEXT` (신규) | caret 위치에 텍스트 삽입 | `set_paragraph_runs: [...]` |
| `REPLACE_TEXT_RANGE` (신규) | TextRange 의 텍스트를 새 텍스트로 치환 | `set_paragraph_runs: [...]` |
| `DELETE_TEXT_RANGE` (신규) | TextRange 의 텍스트 삭제 | `set_paragraph_runs: [...]` |
| `SET_PARAGRAPH_TEXT_SAFE` (신규) | 문단 전체 텍스트 교체 — 단일 run 으로 폴딩되어도 무방한 경우만 | `set_paragraph_runs: [...]` |
| `SPLIT_TEXT_RUN` (내부 명령) | 외부 명령 적용 전 run 경계 정렬 | inverse 는 MERGE_TEXT_RUNS |
| `MERGE_TEXT_RUNS` (내부 명령) | 인접 동일 charPr run 정규화 | inverse 는 SPLIT_TEXT_RUN |

SPLIT / MERGE 는 외부 noise 가 아니라 commandLog 에 정식 등재되어
undo/redo 가능. 사용자 액션 1건 = 외부 명령 1개 + 그에 부속한 내부
명령 N개 — 묶음 단위로 undo 한다 (commandGroupId 도입, §15).

## 8. TYPE_TEXT 정책

- caret 위치 = TextRange (anchor == focus)
- caret 이 위치한 run 의 charPrIDRef 를 상속한 신규 run 으로 텍스트 삽입
- caret 이 run 경계에 있으면 split 불필요 — 좌측 run 의 charPr 상속
- IME composition 중에는 commandLog 에 적재하지 않음 (composition end
  이벤트에서 단일 TYPE_TEXT command 1건 생성)
- 한글 조합 중 ESC → composition cancel → commandLog 변화 0
- 빈 문자열 삽입 → 명령 미생성 (MVP-A 의 `before == after` 정책 인용)

## 9. REPLACE_TEXT_RANGE 정책

- TextRange 의 expectedBefore 와 현재 텍스트 일치 검증 (V5 일반화)
- 치환 범위가 단일 run 안: 해당 run split 2회 → 가운데 run 교체
- 치환 범위가 여러 run 가로지름:
  - **policy = REQUIRES_REVIEW** 인 경우 사용자 확인 UI 필요
    (서로 다른 charPr 의 run 을 cross 하면 어느 charPr 을 신규 텍스트에
    적용할지 결정 불가)
  - **policy = ANCHOR_CHARPR** (기본): anchor run 의 charPrIDRef 적용
  - **policy = FOCUS_CHARPR**: focus run 의 charPrIDRef 적용
- 치환 후 인접 동일 charPr run 은 자동 merge
- 신규 텍스트 길이가 0 이면 DELETE_TEXT_RANGE 로 환원

## 10. DELETE_TEXT_RANGE 정책

- TextRange 의 expectedBefore 검증
- 단일 run 안 삭제: split 후 가운데 run 제거 → 인접 merge
- 여러 run 가로지름: 가장 안쪽 run 들 제거, anchor / focus 가 걸친 두
  run 은 split 후 외측만 잔류, 그 둘이 동일 charPr 이면 merge
- 삭제 후 paragraph 가 빈 경우 빈 run 1개 유지 (W-known)
- inverse 는 REPLACE_TEXT_RANGE (삭제 위치에 원 텍스트 복원, 원 run
  경계도 같이 복원해야 하므로 expectedBefore 에 원 run 구조 보존)

## 11. SET_PARAGRAPH_TEXT_SAFE 정책

- 문단 전체 텍스트 교체. 단, **문단의 모든 run 이 동일 charPrIDRef** 인
  경우에만 SAFE — 그 외에는 client 단계에서 reject (`UNSAFE_MULTI_STYLE_PARA`)
- expectedBefore = paragraph 전체 text
- inverse = SET_PARAGRAPH_TEXT_SAFE (이전 텍스트 + 동일 charPr)
- parPrIDRef 는 항상 유지

## 12. run split / merge 정책 (SPLIT_TEXT_RUN / MERGE_TEXT_RUNS)

### 12-1. SPLIT_TEXT_RUN

- 입력: `{ runId, offset }`
- 결과: 동일 paragraph 내 run 두 개 (좌측 = 기존 runId 유지, 우측 =
  신규 runId `{paragraphId}_run{n}`). 둘 다 원래 charPrIDRef 상속.
- offset == 0 또는 offset == len(run.text) 이면 split 미수행 (NOOP)
- inverse = MERGE_TEXT_RUNS

### 12-2. MERGE_TEXT_RUNS

- 입력: `{ leftRunId, rightRunId }`
- 두 run 이 인접해야 하며 charPrIDRef 가 일치해야 한다 — 일치하지
  않으면 reject (`MERGE_CHARPR_MISMATCH`)
- 결과: leftRunId 유지, rightRunId 제거, text 합쳐짐
- inverse = SPLIT_TEXT_RUN with 우측 시작 offset

### 12-3. 정규화 패스

외부 명령 적용 직후 paragraph 단위로 정규화 패스:
1. 빈 run 제거 (단, paragraph 가 완전히 비면 빈 run 1개 유지)
2. 인접 동일 charPrIDRef run merge

정규화 패스에서 발생한 SPLIT / MERGE 도 commandLog 에 commandGroupId
부속으로 적재 — undo 일관성 보장.

## 13. charPrIDRef 보존 정책

- **원칙**: 모든 외부 명령은 적용 전후 paragraph 의 charPrIDRef 집합을
  보존한다. 새 charPr 를 만들지 않는다.
- run split: 좌·우 run 모두 원래 charPrIDRef 상속
- run merge: charPrIDRef 일치 시에만 가능 (위반 시 reject)
- REPLACE_TEXT_RANGE: §9 policy 에 따라 ANCHOR_CHARPR / FOCUS_CHARPR /
  REQUIRES_REVIEW 중 하나 — 기본 ANCHOR_CHARPR
- TYPE_TEXT: caret 좌측 run 의 charPrIDRef 상속
- DELETE_TEXT_RANGE: 잔류 run 의 charPrIDRef 그대로
- **신규 charPr 생성은 Phase 3 범위 밖** (별도 ApplyFormat 명령은
  Phase 3-followup 에서 도입 검토)

## 14. parPrIDRef 보존 정책

- paragraph 의 `parPrIDRef` 는 모든 PARA-EDIT 명령에서 보존 — 변경 없음
- SET_PARAGRAPH_TEXT_SAFE 도 parPrIDRef 유지
- paragraph 자체가 삭제되는 경우는 Phase 3 범위 밖 (paragraph
  add/delete 는 Phase 3-followup)

## 15. expectedBefore / stale session 정책

- 모든 PARA-EDIT 명령은 `expectedBefore` 필드를 가진다 — TextRange 의
  현재 텍스트, paragraph 전체 텍스트, 또는 caret 위치의 charPrIDRef
- save 시 server 의 `cell_edit_plan` 동등 모듈 (PARA-EDIT 후속 공정에서
  `paragraph_edit_plan` 신설) 이 RO-VIEW 의 최신 snapshot 과 비교
- 불일치 시 reject (reason: `EXPECTED_BEFORE_MISMATCH_PARAGRAPH`)
- stale session 차단: 클라이언트가 들고 있는 RO-VIEW 의
  sourceDocumentHash 가 서버 측 현재 sha 와 다르면 `STALE_SESSION` 으로
  reject → 사용자에게 재로드 안내 (UX 는 Phase 3-followup)
- commandGroupId 단위로 atomic — 한 그룹 안 명령 1건이라도 reject 면
  전체 그룹 reject (`GROUP_ATOMIC_REJECT`)

### IME / 한글 조합 처리

- 브라우저의 `compositionstart` ~ `compositionend` 사이에는 commandLog
  에 적재하지 않음
- `compositionend` 시 단일 TYPE_TEXT command 발행
- ESC 등으로 cancel 되면 commandLog 변화 0

### 줄바꿈 / 문단 끝 처리

- Phase 3 은 paragraph 내부 편집만 — 줄바꿈 (paragraph add/delete) 은
  범위 밖
- 사용자가 Enter 키를 눌러도 본 Phase 에서는 paragraph 추가 명령을
  발행하지 않는다 (UI 레벨에서 차단)

## 16. undo / redo 정책

- commandGroupId 단위로 undo / redo (사용자 액션 1회 = 1 group)
- 그룹 안 명령들은 적재 순서의 역순으로 inverse 적용
- redo 는 그룹 안 명령들을 적재 순서대로 forward 재적용
- commandLog 는 **append-only** (MVP-A 정합) — undo 가 줄이지 않음
- 새 명령 발생 시 redoStack 비움 (MVP-A 정합)

## 17. save / verify 정책

PARA-EDIT 의 save 흐름은 MVP-A 의 `cell_save_pipeline` 패턴을 그대로
일반화:

```
commandLog
  ↓ paragraph_edit_plan.build_dry_run_paragraph_plan
dry-run plan { set_paragraph_runs: [...] }
  ↓ apply_edit_plan(dry_run=True)   ← Phase 3 IMPL 단계에서 신설
operations + LOCK_01 좌표 매칭 (paragraph 일반화)
  ↓ applied=∅ → 본 실행 차단
apply_edit_plan(dry_run=False)
  ↓
verify7 (paragraph 확장)
  ↓ PASS 시에만 sandbox output 유지
audit log append
```

- writer 본 실행은 Phase 3 IMPL 공정 (별도) — 본 시방서는 호출하지
  않음
- output 은 `data/drafts/web_office_para_save/` 또는 tmp_path
- 원본 sha256/mtime 사전=사후 게이트 유지 (V4)

## 18. readback 검증 기준 (V1~V7 paragraph 확장)

| V# | 항목 | 정의 |
|----|------|------|
| **V1_RANGE_POSITION_OK** | 치환 위치 검증 | 출력 paragraph 의 anchor..anchor+len(after) 가 after 와 일치 |
| **V2_NO_CROSS_PARAGRAPH_LEAK** | 문단 경계 leak 차단 | 다른 paragraphId 의 text 에 after 텍스트가 의도치 않게 등장하지 않음 (byte-count) |
| **V3_UNTOUCHED_RUNS_PRESERVED** | 적용 외 run 보존 | 명령 적용 외 runId 의 text + charPrIDRef 가 원본과 동일 |
| **V4_CHARPR_PRESERVED** | charPr 보존 | 명령 적용 후 paragraph 의 charPrIDRef 집합 ⊆ 원본 집합 (신규 0) |
| **V5_PARPR_PRESERVED** | parPr 보존 | paragraph 의 parPrIDRef 변경 없음 |
| **V6_OUTPUT_ISOLATED** | output 격리 | outputPath != sourcePath + sandbox 경로 하위 (MVP-A 정합) |
| **V7_READBACK_MATCH** | readback 일관성 | output 의 `import_hwpx_as_ro_view` 결과 paragraph text == 예상 |

### applied=∅ vacuous PASS 차단

- dry-run 후 accepted commands 가 0이면 본 실행 차단 (`DRY_RUN_NO_APPLIED`)
- verify7 의 V5 (또는 신규 V5p) 가 accepted=0 이면 FAIL
- MVP-A 의 `_filter_applied_cells_by_coord` 와 동등한 회로를
  paragraph (paragraphId, runId, offset) 좌표 기준으로 일반화 필요 —
  IMPL 공정에서 `_filter_applied_runs_by_coord` 신설

## 19. 위험대장 R-P3 항목 (별책 `web_office_para_edit_risk_ledger_update.md`)

본 절은 요약. 상세 게이트와 활성화 트리거는 별책 참조.

| ID | 위험 | 차단 게이트 (계획) |
|----|------|--------------------|
| **R-P3-01** | run split/merge 중 스타일 손실 | charPr 일치 시에만 merge 허용, split 시 양쪽 모두 원본 charPr 상속 |
| **R-P3-02** | expectedBefore stale (오래된 RO-VIEW) | sourceDocumentHash + paragraph 텍스트 sha 두 단계 비교 |
| **R-P3-03** | 문단 경계 cross-leak | V2_NO_CROSS_PARAGRAPH_LEAK (byte-count) |
| **R-P3-04** | charPrIDRef / parPrIDRef 손상 | V4 / V5 game over 게이트, 신규 charPr 생성 명령 0건 |
| **R-P3-05** | 한글 조합 / IME 입력 처리 | composition start/end 사이 commandLog 잠금 |
| **R-P3-06** | 줄바꿈 / 문단 끝 문자 처리 | paragraph add/delete 본 Phase 차단 |
| **R-P3-07** | 문단 편집과 셀 편집 command 충돌 | commandType enum 추가만 — SET_CELL_TEXT 회로 무수정, 동일 commandGroup 안 두 명령 동시 허용 금지 |

## 20. Phase 3 구현 순서 (예고)

본 시방서가 PASS 되면 다음 후속 공정들이 순차 진행 가능:

1. **WEB-OFFICE-PARA-EDIT-MODEL-01** — EditCommand v2 Python/JS 모델
   (TYPE_TEXT 포함 6 명령), 정규화 패스 헬퍼, JS 자체 시나리오 검증
2. **WEB-OFFICE-PARA-EDIT-BROWSER-01** — 브라우저 컴포넌트 (별도 entry
   유지 — RO viewer 잠금 무손상), IME composition handler
3. **WEB-OFFICE-PARA-EDIT-SAVE-VERIFY7-01** — `paragraph_edit_plan` +
   `apply_edit_plan` paragraph 확장 + verify7 paragraph 확장 +
   `_filter_applied_runs_by_coord` 신설
4. **WEB-OFFICE-PARA-EDIT-PARTIAL-CLOSEOUT-01** — Phase 3 부분 준공
   등기 + RISK-LEDGER 갱신

## 21. 착공 승인 조건 (요약)

본 시방서가 Phase 3 PARA-EDIT 의 **착공 조건 #2** (시방서 작성) 를
충족시킨다. 실제 시공 (WEB-OFFICE-PARA-EDIT-MODEL-01) 착공에는 다음이
**모두 충족**되어야 한다 — MVP-A closeout (`web_office_mvp_a_closeout.md` §6) 인용:

1. MVP-A 회귀 무손상 (현재 89/89 + 본 공정 추가분)
2. 본 시방서 PASS (audit + 계약 테스트)
3. **대표님 명시 승인** ("진행" / "시공 착수")
4. PARA-EDIT 회귀 시나리오 사전 설계 — 본 시방서 §18 V1~V7 + §19 R-P3
5. RISK-LEDGER R-P3 항목 정착 — 별책 본 공정에서 동시 등기

## 22. 금지사항 (본 시방서 정본)

- 실제 PARA-EDIT 코드 구현 (model/runtime/plan/save) — 본 공정 범위 밖
- writer 호출 (`apply_edit_plan`, `hwpx_edit_tool`)
- output HWPX 생성
- 원본 HWPX 접근 / 수정
- CELL-EDIT MVP-A 코드 변경
- 기존 MVP-A 테스트 완화
- AI 자동 입력 회로 구현
- 브라우저에서 HWPX XML 직접 파싱
- 표 구조 / 이미지 / 도장 / 서명 편집 선시공

위 항목 위반 시 본 공정 audit 가 FAIL 로 즉시 차단한다.

---

*생성: WEB-OFFICE-PARA-EDIT-SPEC-01 (2026-05-20)*

> **저장소 분리 기준**: e04d325 (hwpx-web-office 신규 저장소 초기 커밋, 2026-05-22)
