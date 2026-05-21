# WEB-OFFICE PARA-EDIT E2E 정식 준공 등기 (FULL_CLOSEOUT_01)

> 공정명: **WEB-OFFICE-PARA-EDIT-E2E-FULL-CLOSEOUT-01**
> baseline commit : **56dc073** (TYPE_TEXT_CONTRACT_01)
>
> 본 문서는 WEB-OFFICE 단지 PARA-EDIT 동의 cell containerScope · 단일 run
> 범위 정식 준공을 등기한다. 본 공정은 **신규 writer 기능을 시공하지
> 않는다.** 기존 자재 + 감사 + 테스트 + 본 시방서만 신축한다.

---

## 1. 단지 진척도 (cell scope · 단일 run 한정)

```
[RO-VIEW PARA-RUN 측량 동]          ████████ 100%  (51cfe49)
[WRITER PARA-PLAN 본동]              ████████ 100%  (1a999e3)
[CONTAINERSCOPE BRIDGE 동]           ████████ 100%  (81e86e9)
[E2E INTEGRATION 시운전동]           ████████ 100%  (dabdf53)
[READBACK PARSER 정밀계측동]         ████████ 100%  (d3f8ed6)
[ADAPTER APPLYCHARPR 자물쇠동]       ████████ 100%  (ec3837e)
[TYPE_TEXT CONTRACT 출입문 정렬동]   ████████ 100%  (56dc073)
[FULL CLOSEOUT 준공 등기동]          ████████ 100%  ← 본 공정
```

```
PARA-EDIT 동 (cell containerScope · 단일 run)
  ├─ SET_CELL_TEXT (MVP-A)            ████████ 100%
  ├─ TYPE_TEXT V1~V7                  ████████ 100%
  ├─ REPLACE_TEXT_RANGE V1~V7         ████████ 100%
  └─ DELETE_TEXT_RANGE V1~V7          ████████ 100%
```

---

## 2. 공식 준공 범위 (IN_SCOPE)

본 공정에서 **정식 준공**으로 등기되는 항목:

### 2-1. 지원 commandType

| commandType | 상태 | 비고 |
|-------------|------|------|
| `SET_CELL_TEXT` | 정식 준공 (MVP-A) | LOCK_01 회로 위에서 안정화 |
| `TYPE_TEXT` | 정식 준공 (TYPE_TEXT_CONTRACT_01) | expectedBefore="" + 빈 range slice |
| `REPLACE_TEXT_RANGE` | 정식 준공 (E2E_INTEGRATION_01) | ANCHOR_CHARPR 기본 policy |
| `DELETE_TEXT_RANGE` | 정식 준공 (E2E_INTEGRATION_01) | DELETE = REPLACE(after="") |

### 2-2. 지원 컨테이너

- `containerScope.kind = "cell"` 한정
- 단일 run range (`runIndex` 고정, run-local offset 매칭)
- paragraph 1건 · edit 1건 시나리오

### 2-3. 지원 검증 (감리 게이트)

| 게이트 | 위치 | 상태 |
|--------|------|------|
| V1_RANGE_POSITION_OK | readback (para_edit_e2e_pipeline) | PASS |
| V2_NO_CROSS_PARAGRAPH_LEAK | verify7 | PASS |
| V3_UNTOUCHED_RUNS_PRESERVED | verify7 | PASS |
| V4_CHARPR_PRESERVED | verify7 + readback | PASS |
| V5_PARPR_PRESERVED | verify7 | PASS |
| V6_OUTPUT_ISOLATED | verify7 | PASS |
| V7_READBACK_MATCH | readback | PASS |

### 2-4. 지원 안전 장치

- `expectedBefore` 검증 (paragraph chain validate + writer slice 일치)
- `sourceDocumentHash` 검증 (RO-VIEW → command → plan → writer 전 구간)
- sandbox output (tmp_path 외부 생성 금지)
- readback parser (paragraphId / containerScope 4 키 매칭, text-only fallback 차단)
- charPrIDRef 보존 (적용 후 집합 ⊆ 원본 집합)
- parPrIDRef 보존 (변경 0건)

---

## 3. 공식 비지원 범위 (OUT_OF_SCOPE / FUTURE_INTEGRATION)

본 공정에서 **명시적으로 후속 공정으로 분리**되는 항목:

| 항목 | 현재 게이트 | 후속 공정 후보 |
|------|-------------|----------------|
| multi-run cross range | `MULTI_RUN_RANGE_NOT_SUPPORTED` reject | PARA-EDIT-MULTI-RUN-01 |
| body paragraph writer | **활성화** (WEB-OFFICE-BODY-PARAGRAPH-WRITER-01) — 단일 run + section/block index 기반. 과거 `BODY_PARAGRAPH_NOT_SUPPORTED` reject 는 해제 | — |
| paragraph add/delete | (factory 미존재) | PARA-EDIT-STRUCTURE-01 |
| 신규 charPr 생성 / ApplyFormat | `REASON_CHARPR_MISMATCH` reject | PARA-EDIT-FORMAT-01 |
| table structure editing | (PARA-EDIT 범위 외) | TABLE-STRUCTURE-EDIT-01 |
| image / stamp / signature | (PARA-EDIT 범위 외) | MEDIA-EDIT-01 |
| AI auto input | CLAUDE.md §10 게이트 | AUTO-FILL-MASTER 별도 회로 |
| collaborative editing | (단일 세션 가정) | COLLAB-01 |

**위 항목들은 본 공정 audit 가 정적으로 잠근다.**

---

## 4. 안전 게이트 잠금 목록

본 공정 audit 가 정적·동적으로 검사하는 게이트:

| 게이트 코드 | 위치 | 검사 방식 |
|-------------|------|----------|
| `OUTPUT_EQUALS_SOURCE` | paragraph_save_pipeline | 정적 grep + 동적 E2E reject |
| 원본 sha/mtime 무변경 | E2E pipeline | 동적 시운전 후 비교 |
| `applied=∅` vacuous PASS 차단 | readback (`V4 DEFERRED`) | readback 회로 |
| text-only fallback matching 금지 | readback `_match_output_paragraph` | 정적 검사 |
| `REQUIRES_REVIEW_NO_CONTAINER_SCOPE` | para_edit_state | JS state 회로 |
| `BODY_PARAGRAPH_NOT_SUPPORTED` | paragraph_writer_adapter | 정적 grep |
| `MULTI_RUN_RANGE_NOT_SUPPORTED` | paragraph_writer_adapter | 정적 grep |

---

## 5. V1~V7 증빙 요약 (cell scope · 단일 run)

본 공정의 audit 는 fixture 가용 시 3 시나리오 × 7 게이트 = **21 PASS 신호**
를 동적으로 수집한다. 정적 신호로는 다음 자재의 존재·구조를 잠근다:

- `scripts/hwpx/web_office/para_edit_model.py` — command factory + validator
- `scripts/hwpx/web_office/paragraph_edit_plan.py` — plan validator + entry map
- `scripts/hwpx/web_office/paragraph_writer_adapter.py` — slice 기준 expectedBefore
- `scripts/hwpx/web_office/paragraph_save_pipeline.py` — OUTPUT_EQUALS_SOURCE 등 안전 게이트
- `scripts/hwpx/web_office/paragraph_save_verify7.py` — V2~V6 verify7
- `scripts/hwpx/web_office/para_edit_e2e_pipeline.py` — V1/V4/V7 readback gate
- `scripts/hwpx/web_office/ro_view_importer.py` — containerScope 측량

---

## 6. RISK-LEDGER 갱신

본 공정에서 다음 위험 항목을 `MITIGATED` 로 전이:

| ID | 항목 | 상태 (이전 → 현재) | 잠금 회로 |
|----|------|--------------------|-----------|
| R-P3-02 | expectedBefore stale | OPEN → **MITIGATED** | sourceDocumentHash + paragraph chain validate |
| R-P3-03 | 문단 경계 cross-leak | OPEN → **MITIGATED** | V2_NO_CROSS_PARAGRAPH_LEAK + paragraphId/containerScope 매칭 |
| R-P3-04 | charPr/parPr 손상 | OPEN → **MITIGATED** | V4 + V5 (verify7 + readback) |

본 공정에서 **잔존하는 위험** (cell scope · 단일 run 범위 밖):

| ID | 항목 | 상태 | 후속 트리거 |
|----|------|------|-----------|
| R-P3-01 | run split/merge 스타일 손실 | PLANNED (단일 run 한정에서는 비활성) | PARA-EDIT-MULTI-RUN-01 |
| R-P3-05 | IME composition / undo 단위 | PLANNED (JS state 단위 잠금만) | PARA-EDIT-IME-LIVE-01 |
| R-P3-06 | Enter capture | PLANNED | PARA-EDIT-STRUCTURE-01 |
| R-P3-07 | commandGroup conflict | PLANNED | PARA-EDIT-BATCH-01 |

본 별책은 `web_office_para_edit_risk_ledger_update.md` 의 §10 변경 절차에
따라 append-only 로 갱신된다.

---

## 7. 다음 공정 후보

| 후속 공정 | 활성화 조건 | 결정 권한 |
|-----------|-------------|----------|
| PARA-EDIT-MULTI-RUN-01 | multi-run cross range writer 활성화 (R-P3-01) | 대표님 |
| PARA-EDIT-BODY-01 | body paragraph writer 활성화 | 대표님 |
| PARA-EDIT-IME-LIVE-01 | 브라우저 IME 실시간 시운전 (R-P3-05) | 대표님 |
| PARA-EDIT-BATCH-01 | multi-edit batch + commandGroup ordering (R-P3-07) | 대표님 |
| PARA-EDIT-STRUCTURE-01 | paragraph add/delete (R-P3-06) | 대표님 |
| PARA-EDIT-FORMAT-01 | ApplyFormat / 신규 charPr 생성 | 대표님 |

---

## 8. 본 공정 산출물

- `docs/architecture/web_office_para_edit_e2e_full_closeout.md` — 본 시방서 (신설)
- `scripts/ops/audit_web_office_para_edit_e2e_full_closeout.py` — 준공 검사 (신설)
- `tests/test_web_office_para_edit_e2e_full_closeout.py` — 감리 검사 (신설)

기존 writer / adapter / plan / model / ro_view_importer **무수정**.

---

*생성: WEB-OFFICE-PARA-EDIT-E2E-FULL-CLOSEOUT-01 (2026-05-21)*
