# WEB-OFFICE PARA-EDIT 내용 편집 부분 준공 등기 (CONTENT_CLOSEOUT_01)

> 공정명: **WEB-OFFICE-PARA-EDIT-CONTENT-CLOSEOUT-01**
> baseline commit : **24f24d4** (TYPE multi-run 활성화)
>
> 본 문서는 PARA-EDIT 내용 편집 3종 (TYPE_TEXT / REPLACE_TEXT_RANGE /
> DELETE_TEXT_RANGE) 의 현재 부분 준공 범위를 공식 동결한다. 신규
> 시공 없음 — 문서 + audit + 테스트만 신축.

---

## 1. 단지 진척도

```
[RO-VIEW 측량 동]                  ████████ 100%  (51cfe49)
[WRITER PARA-PLAN 본동]            ████████ 100%  (1a999e3)
[CONTAINERSCOPE BRIDGE]            ████████ 100%  (81e86e9)
[E2E INTEGRATION]                  ████████ 100%  (dabdf53)
[READBACK PARSER]                  ████████ 100%  (d3f8ed6)
[ADAPTER APPLYCHARPR]              ████████ 100%  (ec3837e)
[TYPE_TEXT CONTRACT]               ████████ 100%  (56dc073)
[CELL SINGLE-RUN CLOSEOUT]         ████████ 100%  (c7810b3)
[IME LIVE SMOKE]                   ████████ 100%  (b0d7519)
[BODY PARAGRAPH WRITER]            ████████ 100%  (027f6bf)
[MULTI-RUN REPLACE/DELETE]         ████████ 100%  (df950f4)
[TYPE MULTI-RUN]                   ████████ 100%  (24f24d4)
[CONTENT CLOSEOUT 동결 등기]       ████████ 100%  ← 본 공정
```

```
PARA-EDIT 동 · 내용 편집 (cell + body, single + multi run)
  ├─ SET_CELL_TEXT (MVP-A)             ████████ 100%
  ├─ TYPE_TEXT
  │   ├─ cell single-run                ████████ 100%
  │   ├─ body single-run                ████████ 100%
  │   ├─ cell multi-run (caret-in-run)  ████████ 100%
  │   └─ body multi-run (caret-in-run)  ████████ 100%
  ├─ REPLACE_TEXT_RANGE
  │   ├─ cell single-run                ████████ 100%
  │   ├─ body single-run                ████████ 100%
  │   ├─ cell multi-run cross-runs      ████████ 100%
  │   └─ body multi-run cross-runs      ████████ 100%
  └─ DELETE_TEXT_RANGE
      ├─ cell single-run                ████████ 100%
      ├─ body single-run                ████████ 100%
      ├─ cell multi-run cross-runs      ████████ 100%
      └─ body multi-run cross-runs      ████████ 100%
```

---

## 2. 공식 완료 범위 (IN_SCOPE)

### 2-1. 지원 commandType

| commandType | single-run cell | single-run body | multi-run cell | multi-run body |
|-------------|:--:|:--:|:--:|:--:|
| `SET_CELL_TEXT` (MVP-A) | ✅ | — | — | — |
| `TYPE_TEXT` | ✅ | ✅ | ✅ | ✅ |
| `REPLACE_TEXT_RANGE` | ✅ | ✅ | ✅ | ✅ |
| `DELETE_TEXT_RANGE` | ✅ | ✅ | ✅ | ✅ |

### 2-2. 지원 컨테이너

- `containerScope.kind == "cell"` (table cell paragraph)
- `containerScope.kind == "block"` (body paragraph, `sectionIndex/blockIndex` 좌표)

### 2-3. 지원 범위 (run 단위)

- 단일 run 안의 부분 텍스트 편집
- 같은 paragraph 내 여러 run 을 가로지르는 REPLACE/DELETE
  (anchor / middle / focus run span)
- TYPE_TEXT 의 caret 가 임의의 run 안 (시작 / 내부 / 경계 / paragraph 끝)

### 2-4. 지원 검증 (감리 게이트)

| 게이트 | 위치 |
|--------|------|
| V1_RANGE_POSITION_OK | readback (`para_edit_e2e_pipeline`) |
| V2_NO_CROSS_PARAGRAPH_LEAK | verify7 |
| V3_UNTOUCHED_RUNS_PRESERVED | verify7 |
| V4_CHARPR_PRESERVED | verify7 + readback |
| V5_PARPR_PRESERVED | verify7 |
| V6_OUTPUT_ISOLATED | verify7 |
| V7_READBACK_MATCH | readback |

### 2-5. 지원 정책

- charPr 상속: `POLICY_ANCHOR_CHARPR` (기본), `POLICY_FOCUS_CHARPR` (REPLACE/DELETE multi-run 한정), `POLICY_REQUIRES_REVIEW` (writer reject 신호)
- TYPE_TEXT 의 caret 경계 모호 시: 좌측 run charPr 상속 (`locate_offset` default)

### 2-6. 지원 안전 장치

- `expectedBefore` 검증 (paragraph chain + writer slice)
- `sourceDocumentHash` 검증
- sandbox output (project_root 외 차단)
- `outputPath == sourcePath` reject
- `OUTPUT_EQUALS_SOURCE` 게이트
- `UNSAFE_RUN_CHILDREN` (hp:ctrl/hp:br/hp:fld 섞인 run 가드)
- `NEW_CHARPR_INTRODUCED` (신규 charPr 도입 차단)
- 원본 HWPX `sha256` / `mtime_ns` 무변경 사후 검증
- readback parser: paragraphId / containerScope 4 키 매칭 (text-only fallback 차단)

### 2-7. 지원 IME

- compositionstart / compositionupdate / compositionend → TYPE_TEXT 변환
- composition 잠금 (update 중 외부 입력 차단)
- compositionend cancel (`""`) → command 미생성
- undo / redo + commandLog append-only

---

## 3. 공식 차단 범위 (OUT_OF_SCOPE)

| 항목 | 차단 게이트 | 후속 공정 후보 |
|------|-------------|----------------|
| **ApplyFormat / 신규 charPr 생성** | `NEW_CHARPR_INTRODUCED` + `REASON_CHARPR_MISMATCH` | PARA-EDIT-FORMAT-01 |
| **paragraph add / delete** | `UNSUPPORTED_COMMAND_TYPE` | PARA-EDIT-STRUCTURE-01 |
| **table structure (행/열 add·delete·merge)** | 모듈 외 — model 미발급 | TABLE-STRUCTURE-EDIT-01 |
| **image / stamp / signature 편집** | 모듈 외 | MEDIA-EDIT-01 |
| **AI 자동 입력** | CLAUDE.md §10 게이트 | AUTO-FILL-MASTER 별 회로 |
| **원본 HWPX 직접 수정** | `OUTPUT_EQUALS_SOURCE` + sha/mtime 사후 검증 | — (영구 금지) |
| **POLICY_CARET_RIGHT** (TYPE_TEXT 경계에서 우측 run charPr 우선) | enum 미도입 | PARA-EDIT-FORMAT-01 또는 별도 |
| **위험 child 가 섞인 run 범위 편집** | `UNSAFE_RUN_CHILDREN` reject | — (안전 정책) |
| **collaborative editing** | 단일 세션 가정 | COLLAB-01 |

---

## 4. 핵심 회귀 자재 (테스트 파일 목록)

본 closeout 의 보호 대상 회귀 자재 (audit 가 존재성 정적 검증):

- `tests/test_web_office_para_edit_e2e_full_closeout.py` (cell single-run 정식 등기)
- `tests/test_web_office_para_type_text_contract.py` (TYPE_TEXT expectedBefore 계약)
- `tests/test_web_office_para_edit_e2e_integration.py` (cell single-run E2E)
- `tests/test_web_office_para_edit_model.py` (command factory)
- `tests/test_web_office_para_adapter_applycharpr.py` (V4 활성화)
- `tests/test_web_office_para_readback_parser.py` (V1/V7 readback)
- `tests/test_web_office_para_edit_save_verify7.py` (verify7 게이트)
- `tests/test_web_office_para_edit_container_scope_bridge.py` (containerScope 전파)
- `tests/test_web_office_writer_para_plan.py` (writer plan)
- `tests/test_web_office_para_edit_ime_live.py` (IME live smoke)
- `tests/test_web_office_body_paragraph_writer.py` (body paragraph 활성화)
- `tests/test_web_office_para_edit_multi_run.py` (multi-run REPLACE/DELETE)
- `tests/test_web_office_para_edit_type_multi_run.py` (TYPE multi-run)

---

## 5. 핵심 시공 자재 (소스 파일 목록)

- `scripts/hwpx/web_office/para_edit_model.py` — EditCommand v2 모델 + chain validate
- `scripts/hwpx/web_office/paragraph_edit_plan.py` — plan entry mapping
- `scripts/hwpx/web_office/paragraph_writer_adapter.py` — 단일/멀티 run + cell/body dispatch
- `scripts/hwpx/web_office/paragraph_save_pipeline.py` — save + 안전 게이트
- `scripts/hwpx/web_office/paragraph_save_verify7.py` — V2~V6 verify7
- `scripts/hwpx/web_office/para_edit_e2e_pipeline.py` — V1/V4/V7 readback gate
- `scripts/hwpx/web_office/ro_view_importer.py` — containerScope 측량
- `scripts/hwpx/hwpx_paragraph_ops.py` — paragraph/run XML primitive (single + multi-run)
- `frontend/web_office_viewer/para_edit_state.mjs` — JS 상태기계 (selection / IME / undo)
- `frontend/web_office_viewer/para_edit_command.mjs` — JS command factory
- `frontend/web_office_viewer/para_edit_runtime.mjs` — DOM event 핸들러

---

## 6. RISK-LEDGER 상태

본 closeout 시점 위험 항목:

| ID | 항목 | 상태 |
|----|------|------|
| R-P3-01 | run split/merge 스타일 손실 | **MITIGATED** (V4 + POLICY_ANCHOR/FOCUS + UNSAFE_RUN_CHILDREN) |
| R-P3-02 | expectedBefore stale | **MITIGATED** (sourceDocumentHash + chain validate) |
| R-P3-03 | 문단 경계 cross-leak | **MITIGATED** (V2 + paragraphId/containerScope 매칭) |
| R-P3-04 | charPr / parPr 손상 | **MITIGATED** (V4 + V5 + NEW_CHARPR_INTRODUCED 차단) |
| R-P3-05 | IME composition / undo 단위 | **MITIGATED** (compositionend 한정 발급 + JS state 잠금) |
| R-P3-06 | Enter capture (paragraph add/delete) | PLANNED (후속 공정) |
| R-P3-07 | commandGroup conflict / batch | PLANNED (후속 공정) |
| R-MR-01~06 | multi-run 위험 (charPr 손실, 비텍스트 child, boundary) | **MITIGATED** (24f24d4 + df950f4) |

---

## 7. 다음 공정 후보

| 후속 공정 | 활성화 조건 | 결정 권한 |
|-----------|-------------|----------|
| PARA-EDIT-FORMAT-01 | ApplyFormat / 신규 charPr / POLICY_CARET_RIGHT | 대표님 |
| PARA-EDIT-STRUCTURE-01 | paragraph add/delete / Enter capture | 대표님 |
| PARA-EDIT-BATCH-01 | multi-edit batch + commandGroup ordering | 대표님 |
| TABLE-STRUCTURE-EDIT-01 | 표 행/열 add·delete·merge | 대표님 |
| MEDIA-EDIT-01 | image / stamp / signature | 대표님 |

---

## 8. 본 공정 산출물

- `docs/architecture/web_office_para_edit_content_closeout.md` — 본 시방서 (신설)
- `scripts/ops/audit_web_office_para_edit_content_closeout.py` — closeout 준공검사 (신설)
- `tests/test_web_office_para_edit_content_closeout.py` — closeout 감리 (신설)

기존 writer / adapter / model / plan / ro_view_importer / verify7 / readback **무수정**.

---

*생성: WEB-OFFICE-PARA-EDIT-CONTENT-CLOSEOUT-01 (2026-05-21)*
*baseline : 24f24d4 (TYPE multi-run)*


---

> **baseline 갱신**: bb0939b (STRUCTURE-PARA-INSERT-01 준공, 2026-05-21) — 잠금 파일 정당 변경 확인 후 베이스라인 갱신.

> **저장소 분리 기준**: e04d325 (hwpx-web-office 신규 저장소 초기 커밋, 2026-05-22)

> **baseline 갱신**: 15364fe (WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01 준공, 2026-05-22) — charPr guard 추가로 잠금 파일 정당 변경 확인 후 베이스라인 갱신.
