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

> **baseline 갱신**: 334d665 (WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01 준공, 2026-05-22) — charPr guard 추가로 잠금 파일 정당 변경 확인 후 베이스라인 갱신.

> **baseline 갱신**: b9782a5 (셀 문단 조회 좌표 결함 수리 준공, 2026-07-23) — `ro_view_importer._find_cell_elem` 이 셀 문단을 격자주소(`cellAddr/@colAddr`)로 찾아 확장(colSpan>1) 셀 뒤 칸에서 옆 칸을 집어오던 결함을 교정. 파서(`table_parser`)와 같은 규칙인 **셀 순번**으로 조회하도록 바꿨다. 좌표계 자체는 불변이라 `cellId`·`paragraphId` 키와 renderPayload 격자는 보존된다. 실측 표본 40건 불일치 380건 → 39건. 감사 지적은 `LOCKED_FILE_CHANGED` 뿐이고 기능 회귀 0건임을 회귀 대조(HEAD 28 실패 → 수리후 36, 신규 8건 전부 잠금)로 확인 후 베이스라인 갱신.

> **baseline 갱신**: 3f94c2a (셀 텍스트 손실·중첩 표 중복 수리 준공, 2026-07-23) — 잔존 불일치 39건을 파고드니 좌표가 아닌 결함 두 개였다. ① `table_parser._cell_raw_text` 가 `elem.text` 만 읽어 `<hp:fwSpace/>` 같은 인라인 자식 **뒤 글자(child.tail)를 통째로 버렸다** — `'(서명 또는 인)'` → `'(서명인)'`, `'[]천장재[]단열재…'` → `'[][][]'`. 이 손실은 `renderPayload.cells[].text` 를 타고 뷰어 표시와 라벨 추출까지 갔다. ② 중첩 표는 별도 표로 이미 실리는데 바깥 셀이 그 내용까지 삼켰고, 문단·run·인라인 세 경로를 모두 막아야 했다(중첩 표는 문단이 아니라 문단 안 `hp:run` 속에 있다). 표본 40건 비교 셀 12,727개에서 **불일치 39 → 0건, 영향 서식 13/40 → 0/40**. 정당 변경 확인 후 베이스라인 갱신. 다만 적재된 입력 스키마 31,350건의 라벨은 ①의 손실된 텍스트로 만들어졌으므로 재생성이 필요하다.

> **baseline 갱신**: 2f7db75 (텍스트 편집 시 lineseg 완전 제거 → 한컴 재조판 유도 준공, 2026-07-23) — paragraph_writer_adapter.py 에 _strip_lineseg() 추가(TYPE_TEXT/REPLACE_TEXT_RANGE/DELETE_TEXT_RANGE 저장 직전 호출). 실제 Hancom Office COM으로 줄바꿈 재조판 확인 후 정당 변경으로 베이스라인 갱신.

> **baseline 갱신**: e9517fc (머리말/꼬리말 텍스트 편집 준공, 2026-07-24) — paragraph_writer_adapter.py 에
> _resolve_header_footer_paragraph 추가(CLAUDE.md §4.2), hwpx_edit_tool.py 의 containerScope.kind
> 허용 집합에 header/footer 추가. 실제 Hancom Office COM 으로 머리말 텍스트 편집 확인 후
> 정당 변경으로 베이스라인 갱신.

> **baseline 갱신**: 517849c (빈 입력칸 기입 준공, 2026-07-24) — 서식의 빈 입력칸은 run 은 있는데 `<hp:t>` 텍스트 노드가 없어 writer 가 `RUN_TEXT_NODE_MISSING` 으로 거부했다. **자동채움이 노리는 칸은 정의상 전부 빈 칸이므로 채울 수 있는 칸이 하나도 없었다.** 삽입에 한해 빈 run 에 `<hp:t>` 를 생성하도록 교정(교체·삭제이거나 `hp:ctrl` 등 다른 자식이 있는 run 은 종전대로 거부). `charPrIDRef` 는 run 의 것을 그대로 쓰므로 신규 charPr 을 만들지 않는다. 전기사용신청서 HTTP 종단 시험 3/3 제자리·옆칸 유출 0. 잠금 파일 정당 변경 확인 후 베이스라인 갱신.

## 재고정 이력 (append-only)

- 2026-07-24: baseline → `6111a9e` (문단 텍스트 편집 시 lineseg 보존 로직 준공 — _strip_lineseg 전체삭제 대신 _fix_lineseg_on_text_edit 로 교체, 한컴 COM 실측 재검증 완료)

## 재고정 이력 (append-only)

- 2026-07-24: baseline → `f119308` (lineseg 추정 보정 로그 + 페이지 초과 가드 준공)

> **baseline 갱신**: b992ad6 (중첩 표 읽기/쓰기 대칭 준공, 2026-07-24) — `3f94c2a` 가 **읽기 쪽만** 중첩 표를 제외하도록 고쳐 비대칭이 생겼다. 쓰기 쪽 `hwpx_paragraph_ops` 탐색 헬퍼는 여전히 `.iter()` 로 중첩 표까지 세어, 같은 좌표를 두고 읽기는 '빈 칸'이라 하고 쓰기는 중첩 표 안 run 을 집었다. 전량 기입(200칸 동시) 시험에서 값 1개가 **다른 표로 샜다**. 중첩 표 서브트리로 내려가지 않는 순회기로 탐색 헬퍼 6개를 읽기와 같은 규칙에 맞췄다. 같은 서식·같은 200칸 직접 비교: 제자리 198→199, **유출 1→0**, 원본 무변경 유지. 남은 1칸은 `hp:ctrl` 이 섞인 run 이라 안전 조건에 걸린 정상 반려다. 잠금 파일 정당 변경 확인 후 베이스라인 갱신.


> **baseline 갱신**: cbe8cce (WebOfficeCell.tableIndex 계약 필드 준공, 2026-08-02) — folder-37(교육사이트) office_contract.py 가 documentModel.cells[].tableIndex 를 요구해 ro_view_importer.py 의 WebOfficeCell 생성에 tableIndex=ti 한 줄 추가(ti 는 같은 함수 안 containerScope 에서 이미 쓰던 값 재사용, 신규 계산 없음). 기능 회귀 0건, 잠금 파일 정당 변경 확인 후 베이스라인 갱신.
> **baseline 갱신**: 5b33ccd (hp:ctrl 텍스트유출 수리, 2026-08-05) — folder-37(교육사이트) site-docs 미리보기에서 자재검수요청서.hwpx 열람 시 hp:fieldBegin 필드명령 문자열·hp:shapeComment(이미지 대체텍스트)가 본문 텍스트로 새는 게 발견돼, ro_view_importer.py 의 _inline_text_content() 에 hp:tbl 과 같은 방식으로 hp:ctrl 스킵을 추가. 기능 회귀 0건(ro_view/inline_text 관련 테스트 전부 통과), 잠금 파일 정당 변경 확인 후 베이스라인 갱신.

> **baseline 갱신**: 9d201a3 (paragraph_writer_adapter.py ET 미정의 참조 수정, 2026-09-29) — audit-kit run(ruff F821)으로 발견: 모듈 최상단에 xml.etree.ElementTree import 가 없어 함수 시그니처(ET.Element)가 미정의 이름을 참조했다(지연평가 어노테이션이라 당장 크래시는 없었음). 상단에 import 추가, 가려져 있던 중복 지역 import 2곳 제거. 동작 변경 없음, 잠금 파일 정당 변경 확인 후 베이스라인 갱신.
