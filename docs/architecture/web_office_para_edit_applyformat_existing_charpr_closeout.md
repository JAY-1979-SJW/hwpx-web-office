# WEB-OFFICE PARA-EDIT ApplyFormat (existing charPr) 부분 준공 등기

> 공정명: **WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-CLOSEOUT-01**
> baseline commit : **97c4095** (ApplyFormat existing-charPr 활성화)
>
> ApplyFormat 1차 본공사 (`WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-
> CHARPR-01`) 의 준공 범위를 공식 부분 준공으로 동결한다. 신규 시공 없음
> — 시방서 + audit + 테스트만 신축.

---

## 1. 단지 진척도

```
[CONTENT EDITING (TYPE/REPLACE/DELETE) CLOSEOUT]   ████████ 100%  (d61f10f)
[CHARPR INVENTORY (read-only)]                     ████████ 100%  (5459cd6)
[APPLYFORMAT EXISTING CHARPR (writer activated)]   ████████ 100%  (97c4095)
[APPLYFORMAT EXISTING CHARPR CLOSEOUT 등기]        ████████ 100%  ← 본 공정
```

```
PARA-EDIT 동 · ApplyFormat (existing charPr 전용)
  ├─ cell × single-run × full-run               ████████ 100%
  ├─ cell × single-run × partial-run            ████████ 100%
  ├─ cell × multi-run × cross-runs              ████████ 100%
  ├─ body × single-run × full-run               ████████ 100%
  ├─ body × single-run × partial-run            ████████ 100%
  ├─ body × multi-run × cross-runs              ████████ 100%
  └─ paragraph 전체 range                       ████████ 100%
```

---

## 2. 공식 완료 범위 (IN_SCOPE)

### 2-1. command 활성화

- `CT_APPLY_FORMAT = "APPLY_FORMAT"` enum
- `make_apply_format_command(target, paragraph, range_anchor, range_focus, target_char_pr_id, source_document_hash, container_scope)` factory
- `makeApplyFormatCommand` (JS, browser side)
- payload 필수 필드: `commandId`, `commandType=APPLY_FORMAT`, `paragraphId`, `containerScope`, `rangeStart`, `rangeEnd`, `expectedBefore`, `targetCharPrIDRef`, `sourceDocumentHash`, `createdAt`, `status`, `forward.beforeSegments`, `inverse.restoreSegments`

### 2-2. existing charPr 전용 적용

- `targetCharPrIDRef ∈ Contents/header.xml` 의 `<hh:charPr id="N">` 정의 집합 안에서만 허용
- 위반 시 `TARGET_CHARPR_NOT_IN_HEADER` reject
- 신규 charPr 생성 금지, header.xml mutation 금지

### 2-3. 지원 매트릭스

| 컨테이너 | run 수 | range 유형 |
|----------|--------|-----------|
| `containerScope.kind = "cell"` | single-run | full-run / partial-run |
| `containerScope.kind = "cell"` | multi-run | cross-runs (anchor/middle/focus split) |
| `containerScope.kind = "block"` (body paragraph) | single-run | full-run / partial-run |
| `containerScope.kind = "block"` | multi-run | cross-runs |
| 임의 | 임의 | paragraph 전체 range |

### 2-4. paragraph.text 무변경 원칙

- writer primitive `apply_charpr_to_range_existing` 사후 self-check: `paragraph_text(p_after) == paragraph_text(p_before)`
- 위반 시 `TEXT_CHANGED_UNEXPECTEDLY` reject
- 좌/중/우 split 시 각 단편의 `<hp:t>.text` 합은 원본과 동일

### 2-5. header.xml 무변경 원칙

- writer 단계에서 `target_char_pr_id ∈ _read_header_char_pr_ids(package)` 강제
- writer/adapter/ops 어디에서도 `package.entries["Contents/header.xml"] = ...` 패턴 0건
- output zip 의 `Contents/header.xml` bytes = 원본 bytes (동적 audit 검증)

### 2-6. 검증 게이트 (V1~V7 PASS)

| 게이트 | 위치 |
|--------|------|
| V1_RANGE_POSITION_OK | readback (paragraph.text 무변경 검증) |
| V2_NO_CROSS_PARAGRAPH_LEAK | verify7 (APPLY_FORMAT 면제 — split 으로 hp:t 분기 가능성) |
| V3_UNTOUCHED_RUNS_PRESERVED | verify7 |
| V4_CHARPR_PRESERVED | verify7 + readback (APPLY_FORMAT targetCharPrIDRef 는 src_set 에 ad hoc augment) |
| V5_PARPR_PRESERVED | verify7 |
| V6_OUTPUT_ISOLATED | verify7 |
| V7_READBACK_MATCH | readback (paragraph.text 무변경) |

### 2-7. 안전 게이트

- `TARGET_CHARPR_NOT_IN_HEADER` — header 부재 id 거부
- `EXPECTED_BEFORE_MISMATCH(_PARAGRAPH)` — paragraph slice 불일치 거부
- `SOURCE_HASH_MISMATCH` — sourceDocumentHash 불일치 거부
- `UNSAFE_RUN_CHILDREN` — 영향 run 에 hp:t 외 위험 child 있을 시 거부
- `EMPTY_RANGE` — rangeStart == rangeEnd 거부 (NOOP)
- `OUTPUT_EQUALS_SOURCE` — output 경로가 원본과 동일 시 reject
- 원본 sha256 / mtime_ns 사후 무변경 검증

### 2-8. inverse / undo 자료

- `forward.beforeSegments[]`: `{segmentStart, segmentEnd, charPrIDRef}` per 영향 run
- `inverse.restoreSegments[]`: 동일 — undo 시 영향 run 마다 원래 charPrIDRef 복원 가능

---

## 3. 공식 차단 범위 (OUT_OF_SCOPE)

| 항목 | 차단 게이트 | 후속 공정 후보 |
|------|-------------|----------------|
| **신규 charPr 생성** | `TARGET_CHARPR_NOT_IN_HEADER` + `NEW_CHARPR_INTRODUCED` | PARA-EDIT-APPLYFORMAT-NEW-CHARPR-01 |
| **header.xml charPr 추가/복제/삭제** | adapter/ops 의 header.xml write 경로 0건 (정적 grep) | PARA-EDIT-APPLYFORMAT-NEW-CHARPR-01 |
| **bold/italic/color/fontSize 직접 편집해서 새 style 생성** | model 미발급 | PARA-EDIT-APPLYFORMAT-NEW-CHARPR-01 |
| **toolbar UI 완성** | JS factory 만 노출, DOM 연결 없음 | PARA-EDIT-APPLYFORMAT-TOOLBAR-01 |
| **paragraph add/delete** | `UNSUPPORTED_COMMAND_TYPE` | PARA-EDIT-STRUCTURE-01 |
| **table structure edit** | 모듈 외 | TABLE-STRUCTURE-EDIT-01 |
| **image/stamp/signature edit** | 모듈 외 | MEDIA-EDIT-01 |
| **AI 자동 입력** | CLAUDE.md §10 게이트 | AUTO-FILL-MASTER |
| **원본 HWPX 직접 수정** | `OUTPUT_EQUALS_SOURCE` + sha/mtime 사후 검증 | — (영구 금지) |
| **문서 전체 스타일 일괄 변경** | 단일 paragraph 단위만 지원 | PARA-EDIT-FORMAT-BATCH-01 |
| **POLICY_CARET_RIGHT** | enum 미도입 | 별도 |

---

## 4. 핵심 시공 자재 (97c4095 기준)

| 파일 | 역할 |
|------|------|
| `scripts/hwpx/hwpx_paragraph_ops.py` | `apply_charpr_to_range_existing` primitive (run split + charPr 교체) |
| `scripts/hwpx/web_office/para_edit_model.py` | `CT_APPLY_FORMAT`, `make_apply_format_command`, `_apply_format` in-memory 시뮬레이션 |
| `scripts/hwpx/web_office/paragraph_edit_plan.py` | APPLY_FORMAT plan entry mapping + chain validate 면제 분기 |
| `scripts/hwpx/web_office/paragraph_writer_adapter.py` | APPLY_FORMAT dispatch + `_read_header_char_pr_ids` + 안전 게이트 |
| `scripts/hwpx/web_office/paragraph_save_verify7.py` | V2/V4 면제 분기 (APPLY_FORMAT 한정) |
| `scripts/hwpx/web_office/para_edit_e2e_pipeline.py` | `SCENARIO_APPLY_FORMAT` + readback V4 augment |
| `scripts/hwpx/hwpx_edit_tool.py` | paragraph_edits plan 검증에 APPLY_FORMAT 추가 |
| `frontend/web_office_viewer/para_edit_command.mjs` | `makeApplyFormatCommand` factory |

---

## 5. 핵심 회귀 자재 (테스트 파일 목록)

본 closeout 의 보호 대상:

- `tests/test_web_office_para_edit_applyformat_existing_charpr.py` (16건 — 본 공정 핵심)
- `tests/test_web_office_para_edit_format_charpr_inventory.py` (11건 — charPr inventory 회귀)
- `tests/test_web_office_para_edit_content_closeout.py` (TYPE/REPLACE/DELETE closeout 회귀)
- `tests/test_web_office_para_edit_e2e_full_closeout.py` (cell single-run E2E)
- `tests/test_web_office_para_type_text_contract.py` (TYPE_TEXT 계약)
- `tests/test_web_office_para_edit_e2e_integration.py` (cell single-run 통합)
- `tests/test_web_office_para_edit_model.py` (command factory)
- `tests/test_web_office_para_adapter_applycharpr.py` (V4 활성화)
- `tests/test_web_office_para_readback_parser.py` (V1/V7 readback)
- `tests/test_web_office_para_edit_save_verify7.py` (verify7 게이트)
- `tests/test_web_office_para_edit_container_scope_bridge.py`
- `tests/test_web_office_writer_para_plan.py`
- `tests/test_web_office_para_edit_ime_live.py` (IME live smoke)
- `tests/test_web_office_body_paragraph_writer.py` (body paragraph)
- `tests/test_web_office_para_edit_multi_run.py` (REPLACE/DELETE multi-run)
- `tests/test_web_office_para_edit_type_multi_run.py` (TYPE multi-run)

---

## 6. 다음 후보 공정

| 공정 | 활성화 조건 | 우선 |
|------|-------------|------|
| `PARA-EDIT-APPLYFORMAT-TOOLBAR-PREFLIGHT-01` | toolbar UI 사전 정찰 — 선택 charPr 후보 노출 방식 결정 | 1 |
| `PARA-EDIT-APPLYFORMAT-TOOLBAR-01` | 실제 toolbar 버튼 → makeApplyFormatCommand 연결 | 2 |
| `PARA-EDIT-APPLYFORMAT-NEW-CHARPR-PREFLIGHT-01` | header.xml 에 신규 charPr 추가 시 무결성 사전 정찰 | 3 |
| `PARA-EDIT-APPLYFORMAT-NEW-CHARPR-01` | bold/italic/color/fontSize 등 신규 style 생성 본공사 | 4 |
| `PARA-EDIT-STRUCTURE-PREFLIGHT-01` | paragraph add/delete + Enter capture 사전 정찰 | 5 |

---

## 7. RISK-LEDGER 상태

| ID | 항목 | 상태 |
|----|------|------|
| R-FMT-01 | 신규 charPr id 충돌 | PLANNED (NEW-CHARPR 공정에서 활성) |
| R-FMT-02 | dangling charPrIDRef | MITIGATED (header 존재 검증) |
| R-FMT-03 | run split 좌·우 단편 정합 손실 | MITIGATED (paragraph.text 사후 self-check) |
| R-FMT-04 | partial-run split 정합 | MITIGATED (좌/중/우 segment 생성 + attrib 복사) |
| R-FMT-05 | V4 정의 충돌 | MITIGATED (APPLY_FORMAT 한정 면제 + src_set augment) |
| R-FMT-06 | readback 서식 변경 검증 가능성 | MITIGATED (paragraphInventory + charPrIDRef 비교) |
| R-FMT-07 | viewer 렌더링 반영 | LOW (header 미수정으로 캐시 무효화 위험 없음) |
| R-FMT-08 | TYPE/REPLACE/DELETE 회귀 침해 | MITIGATED (236 passed 회귀 PASS) |
| R-FMT-09 | content closeout 잠금 위반 | MITIGATED (LOCKED 자재 갱신 명시) |

---

## 8. 본 공정 산출물

- `docs/architecture/web_office_para_edit_applyformat_existing_charpr_closeout.md` — 본 시방서 (신설)
- `scripts/ops/audit_web_office_para_edit_applyformat_existing_charpr_closeout.py` — closeout 준공검사 (신설)
- `tests/test_web_office_para_edit_applyformat_existing_charpr_closeout.py` — closeout 감리 (신설)

기존 writer / adapter / model / plan / ops / verify7 / readback / JS — **모두 무수정**.

---

*생성: WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-CLOSEOUT-01 (2026-05-21)*
*baseline : 97c4095*


---

> **baseline 갱신**: 1f442ec

> **baseline 갱신**: 98d64ed (SCOPE-BOUNDARY-REJECT-01 준공, 2026-05-21) — header/footer/non-body scope reject guard 추가. para_edit_state.mjs / para_edit_model.py 정당 변경 확인 후 베이스라인 갱신. (STRUCTURE-PARA-INSERT-01 준공, 2026-05-21) — 잠금 파일 정당 변경 확인 후 베이스라인 갱신.

> **저장소 분리 기준**: e04d325 (hwpx-web-office 신규 저장소 초기 커밋, 2026-05-22)

> **baseline 갱신**: 619f2e0 (WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01 준공, 2026-05-22) — charPr guard 추가로 잠금 파일 정당 변경 확인 후 베이스라인 갱신.
