# Web Office RISK-LEDGER

> 공정명: WEB-OFFICE-MVP-A-PARTIAL-CLOSEOUT-RISK-LEDGER-01 (별책)
> 정착 시점: MVP-A 준공 (`87b3428`)
> 본 대장은 §11-5 부분 준공 등기 원칙에 따라 "활성화 트리거 + 결정
> 권한 + 차단된 영역의 게이트" 를 정본으로 기록한다.
>
> 본 대장은 **append-mostly** 다 — 위험 추가는 자유, 삭제는 별도
> 공정 + 대표님 명시 승인 필요.

---

## 1. 운영 원칙

- 각 위험은 ID (`R-MA-NN`, `R-Pn-NN`) 로 식별. MA = MVP-A, Pn = Phase n.
- 상태 enum: `OPEN` / `MITIGATED` / `ACCEPTED` / `CLOSED`.
- 차단된 영역(부분 준공 미시공 범위)에 우회 진입 시 본 대장에 명시된
  게이트가 즉시 검출해야 한다 (closeout audit + 본 단지 회귀 73건).

---

## 2. MVP-A 시점 위험 항목

### R-MA-01 — 원본 HWPX 오염
- **상태**: MITIGATED
- **차단 게이트**:
  - `cell_save_pipeline`: `outputPath == sourcePath` 즉시 REJECTED
  - `cell_save_verify7.V4_SOURCE_HASH_OK` 사전/사후 sha256·mtime_ns 비교
  - `cell_save_verify7.V6_OUTPUT_ISOLATED` sandbox 경로 강제
  - 회귀: `test_output_equals_source_blocked` /
    `test_source_sha_and_mtime_unchanged_after_all_scenarios`
- **잔존 위험**: 외부 ops 가 fixture 파일 권한을 write 로 바꾸면
  V4 는 통과하나 동시성 사고 가능. 운영 도입 시 별도 권한 정책.
- **활성화 트리거**: 운영 환경 도입 공정에서 권한 게이트 보강

### R-MA-02 — applied=∅ vacuous PASS
- **상태**: MITIGATED
- **차단 게이트**: `DRY_RUN_NO_APPLIED` + `V5_NO_ACCEPTED_COMMANDS`
- **회귀**: `test_all_invalid_blocks_writer_no_vacuous_pass`,
  LOCK_01 `test_decide_verify7_skipped_when_applied_empty`

### R-MA-03 — expectedBefore stale (오래된 RO-VIEW 세션)
- **상태**: OPEN (부분 완화)
- **차단 게이트**: plan REJECTED + V5 게이트
- **잔존 위험**: 사용자 세션이 오래된 DocumentModel 을 들고
  편집한 후 save 하면 매번 reject. UX (재로드 안내) 미구축.
- **활성화 트리거**: Phase 1 후속 (multi-session) 또는 별도 ops 공정
- **결정 권한**: 대표님

### R-MA-04 — PARA-EDIT / TABLE-OPS 선시공
- **상태**: OPEN (영구 게이트)
- **차단 게이트**:
  - `make_set_cell_text_command` 외 명령 생성 함수 없음 (정적)
  - `cell_save_pipeline` 의 `cell_edit_plan` 분기는 `SET_CELL_TEXT` 단독
  - closeout audit (`audit_web_office_mvp_a_closeout.py`) 가 본 등기서
    범위 위반(파일/심볼) 을 정적 grep 으로 잡음
- **잔존 위험**: 사람이 임의로 `commandType` enum 을 확장하는 PR
- **활성화 트리거**: Phase 3 시공 시방서 + 대표님 명시 승인

### R-MA-05 — 외부 라이선스 사고
- **상태**: ACCEPTED (현재 외부 core dep 0건)
- **차단 게이트**: 설계서 §16 + 별책 open-source review
- **활성화 트리거**: 외부 dep 추가 PR 발생 시 별도 ADR 공정 + 대표님 승인

### R-MA-06 — AI 자동 확정
- **상태**: MITIGATED
- **차단 게이트**: §10 정책 + MVP-A 에 AI 회로 미연결
- **활성화 트리거**: Phase 6 (AI-CONFIRM) 시공 승인

### R-MA-07 — sourceHash mismatch silent PASS
- **상태**: MITIGATED
- **차단 게이트**: `cell_edit_plan` SAVE_DRY_RUN_REJECTED +
  V4_SOURCE_HASH_OK
- **회귀**: `test_source_hash_mismatch_blocks_writer`

### R-MA-08 — 한컴 호환 강요
- **상태**: ACCEPTED (비목표)
- **차단 게이트**: 설계서 §1-2, closeout §3, 본 등기서 §10
- **활성화 트리거**: 외부 비즈니스 요구 발생 시 별도 공정

### R-MA-09 — 회귀 무력화 PR
- **상태**: OPEN (운영 게이트)
- **차단 게이트**: CI / pre-commit (post-commit hook 으로 73 건 회귀)
- **잔존 위험**: `--no-verify` 우회 → §6 ABSOLUTE PROHIBITION 위반,
  CLAUDE.md 가 명시적으로 금지
- **활성화 트리거**: CI 게이트 명시 도입 ops 공정

### R-MA-10 — 본 등기서 / 위험대장 무단 수정
- **상태**: OPEN (영구 게이트)
- **차단 게이트**: closeout audit 가 필수 섹션 / 토큰 존재를 정적 검사.
  토큰 부재 시 audit FAIL → 회귀 FAIL → commit 차단.
- **잔존 위험**: audit 자체를 수정하는 PR — 본 단지의 시공
  표준 §11-1 ③ 승인 게이트로 통제

---

## 3. Phase 3+ 사전 등재 위험 (예고)

### R-P3-01 — run split/merge 중 charPrIDRef 유실
- **상태**: PLANNED (Phase 3 시공 시점에 게이트 설계)
- **활성화 트리거**: PARA-EDIT 시방서 작성

### R-P3-02 — 빈 paragraph 가 writer 에서 사라짐
- **상태**: PLANNED
- **회로 후보**: append_table_rows 의 empty cell textNode 회로 인용

### R-P4-01 — 표 행/열 추가 시 visual coord 무효화
- **상태**: PLANNED (Phase 4)

### R-P5-01 — 이미지 BinData 충돌
- **상태**: PLANNED (Phase 5) — `{sessionId}_{n}.png` 명명 규칙으로 회피

### R-P6-01 — AI proposal 자동 확정 사고
- **상태**: PLANNED — §10 게이트 유지, pending → confirm UX 강제

### R-P10-01 — 다중 세션 동시 save 충돌
- **상태**: PLANNED — 세션 락 + audit log + sha 게이트

---

## 4. 변경 절차

본 RISK-LEDGER 항목은 다음 절차로만 변경한다:

1. **추가** — 누구든지 §11-1 ② 시방서로 발의. 본 공정 audit 가 PASS
   유지하는 한 commit 가능.
2. **상태 전이** — MITIGATED ↔ OPEN ↔ ACCEPTED ↔ CLOSED 전이는
   회로 또는 게이트 추가/제거를 동반해야 한다. 회로 없는 상태 변경
   금지.
3. **삭제** — 별도 §11-1 공정 + 대표님 명시 승인 필요. 본 단지
   §6 ABSOLUTE PROHIBITION 과 동급 신중도.

---

*생성: WEB-OFFICE-MVP-A-PARTIAL-CLOSEOUT-RISK-LEDGER-01 (2026-05-20)*
