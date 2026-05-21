# WEB-OFFICE PARA-EDIT E2E 통합 시운전 설계서 (E2E_INTEGRATION_01)

> 본 문서는 WEB-OFFICE 단지의 PARA-EDIT 동선 — `ro_view → state →
> command → plan → writer → verify7 → readback` — 을 단일 fixture 로
> 관통 시운전하는 회로의 시방서이다. 본 공정은 신규 기능을 정착하지
> 않는다. 기존 자재 호출 (orchestration) + 감사 + 테스트 + 본 시방서
> 4 세대만 신축한다.

baseline commit : **81e86e9** (CONTAINERSCOPE_BRIDGE_01)

---

## 1. 단지 완공 등기 (진척도)

```
[RO-VIEW PARA-RUN 측량 동]  ████████ 100%  (51cfe49)
[WRITER PARA-PLAN 본동]      ████████ 100%  (1a999e3)
[CONTAINERSCOPE BRIDGE 동]   ████████ 100%  (81e86e9)
[E2E INTEGRATION 시운전동]   ████████ 100%  ← 본 공정
```

본 공정은 **시운전 동** — 본 동만 단독 정착되며, 기존 14 세대
(hwpx_edit_tool 외 13)는 **잠금 (LOCKED)** 상태로 유지된다.

---

## 2. 동선 흐름도 (자재 라우팅)

```
              ┌────────────────────────────────────────────┐
   HWPX  ──▶  │ ① ro_view_importer.import_hwpx_as_ro_view  │
 (원본)       │   sha256 측량, paragraph/run 좌표 추출       │
              └────────────────────────────────────────────┘
                          │  WebOfficeDocumentModel
                          ▼
              ┌────────────────────────────────────────────┐
              │ ② para_edit_e2e_pipeline._ro_paragraph_to_  │
              │    model + _build_target                    │
              │   RO-VIEW → Paragraph + ParagraphTarget     │
              │   containerScope 그대로 전사                │
              └────────────────────────────────────────────┘
                          │  Paragraph, ParagraphTarget
                          ▼
              ┌────────────────────────────────────────────┐
              │ ③ para_edit_model.make_*_command            │
              │   TYPE / REPLACE / DELETE — EditCommandV2   │
              │   forward / inverse 양방향 패치 + scope     │
              └────────────────────────────────────────────┘
                          │  EditCommandV2
                          ▼
              ┌────────────────────────────────────────────┐
              │ ④ paragraph_edit_plan.build_dry_run_*       │
              │   plan_edits + reject 게이트                │
              └────────────────────────────────────────────┘
                          │  paragraph_edits[]
                          ▼
              ┌────────────────────────────────────────────┐
              │ ⑤ paragraph_save_pipeline.save_paragraph_  │
              │   edits (allow_writer=True)                │
              │   → paragraph_writer_adapter →             │
              │     hwpx_edit_tool.apply_edit_plan         │
              └────────────────────────────────────────────┘
                          │  output.hwpx (sandbox)
                          ▼
              ┌────────────────────────────────────────────┐
              │ ⑥ paragraph_save_verify7.verify7_paragraphs │
              │   V1~V7 게이트                              │
              └────────────────────────────────────────────┘
                          │  verify7.results
                          ▼
              ┌────────────────────────────────────────────┐
              │ ⑦ import_hwpx_as_ro_view(output) — readback │
              │   paragraph.text 가 예상과 일치             │
              └────────────────────────────────────────────┘
```

---

## 3. 각 동의 입출력 명세

| # | 동 | 입력 | 출력 | LOCK |
|---|-----|------|------|------|
| ① | ro_view_importer | HWPX path | WebOfficeDocumentModel | LOCKED |
| ② | e2e_pipeline (신규 orchestration) | RO model + scenario | Paragraph + ParagraphTarget | NEW |
| ③ | para_edit_model.make_* | Paragraph + Target + container_scope | EditCommandV2 | LOCKED |
| ④ | paragraph_edit_plan | [EditCommandV2] | plan_edits[] | LOCKED |
| ⑤ | paragraph_save_pipeline | plan_edits + source/output | dict(verdict, accepted, rejected, verify7) | LOCKED |
| ⑤a| paragraph_writer_adapter → hwpx_edit_tool | plan_edits + package | applied / rejected | LOCKED |
| ⑥ | paragraph_save_verify7 | source/output + applied | V1~V7 results | LOCKED |
| ⑦ | ro_view_importer (재호출) | output HWPX | WebOfficeDocumentModel | LOCKED |

**NEW** 는 본 공정 신축 동, **LOCKED** 는 baseline 81e86e9 대비 무수정
대상. 변경되면 audit `LOCKED_FILE_CHANGED` 로 차단.

---

## 4. V1~V7 의 의미 및 본 부분 준공 게이트

| # | 코드 | 의미 | 본 공정 게이트 |
|---|------|------|---------------|
| V1 | RANGE_POSITION_OK | output readback paragraph (anchor~focus) 매칭 | DEFERRED |
| V2 | NO_CROSS_PARAGRAPH_LEAK | output blob 내 afterText 누출 없음 | REQUIRED |
| V3 | UNTOUCHED_RUNS_PRESERVED | 적용 안 한 paragraph 의 text 동일 | REQUIRED |
| V4 | CHARPR_PRESERVED | applied 의 charPrIDRef ⊆ 원본 char_pr_set | DEFERRED |
| V5 | PARPR_PRESERVED | applied paragraph 의 parPrIDRef 무변경 | REQUIRED |
| V6 | OUTPUT_ISOLATED | output != source && sandbox 하위 | REQUIRED |
| V7 | READBACK_MATCH | V1 PASS && output 존재 | DEFERRED |

### 4-A. 부분 준공 사유 (LOCKED 모듈 제약)

본 공정은 신규 4 파일만 신축한다. 다음 LOCKED 모듈 제약으로 V1/V4/V7
은 PASS 화 불가:

- **V1 / V7**: `paragraph_save_verify7` 는 paragraph readback parser
  미지원 → `V1_READBACK_UNSUPPORTED` 로 V1 항상 FAIL, V7 은 V1 의존.
- **V4**: `paragraph_writer_adapter.applied` 는 `applyCharPrIDRef`
  필드를 적재하지 않음 (현재 `charPrIDRef` 만). verify7 는
  `entry.get("applyCharPrIDRef")` 로 검증 → None 으로 인식되어 FAIL.

위 제약은 본 공정에서 **수정 금지** (§11-9 false-positive PASS 금지).
다음 활성화 트리거 (§9) 에서 별도 공정으로 해소한다.

### 4-B. TYPE_TEXT 부분 준공

`EditCommandV2.expectedBefore` 가 `paragraph.text` 전체로 채워지는
반면, writer adapter 는 `rt[rangeStart:rangeEnd]` 슬라이스와 비교한다.
caret_offset=0 의 경우 슬라이스는 `""` 이고 expectedBefore 는 paragraph
전체 → mismatch → REJECTED. 본 공정에서는 회로 정합 (rejected reason 이
`EXPECTED_BEFORE_MISMATCH` 인지) 만 검증한다. PASS 화는 expectedBefore
계약 정렬 트리거에서 별도 진행.

---

## 5. 차단 회로 (방화구획)

| 위반 | 게이트 | 검출 위치 |
|------|--------|----------|
| outputPath == sourcePath | OUTPUT_EQUALS_SOURCE | paragraph_save_pipeline 진입부 |
| body paragraph 편집 | BODY_PARAGRAPH_NOT_SUPPORTED | paragraph_writer_adapter |
| multi-run 범위 | MULTI_RUN_RANGE_NOT_SUPPORTED | paragraph_writer_adapter |
| sandbox 외부 출력 | V6_OUTPUT_NOT_ISOLATED | paragraph_save_verify7 |
| 원본 sha/mtime 변경 | SOURCE_TOUCHED | paragraph_save_pipeline 사후 검증 |
| baseline LOCKED 파일 수정 | LOCKED_FILE_CHANGED | audit_web_office_para_edit_e2e_integration |
| e2e_pipeline 내 writer 함수 정의 | FORBIDDEN_WRITER_DEF | audit (정적) |

본 공정은 **호출**만 한다. `apply_edit_plan` / `_apply` / `write_package`
등의 본 실행 함수 **정의**는 e2e_pipeline.py 에 0건이어야 한다.

---

## 6. 시나리오 명세

### 6-1. SCENARIO_TYPE (= "TYPE_TEXT")

caret 위치 (`range_anchor`) 에 `insert_text` 삽입. paragraph 의 첫 run
앞부분이면 charPrIDRef 가 보존된다. forward/inverse 모두 containerScope
보유.

### 6-2. SCENARIO_REPLACE (= "REPLACE_TEXT_RANGE")

`range_anchor`~`range_focus` 구간을 `replace_after` 로 치환. range 가
단일 run 텍스트 길이를 초과하면 writer adapter 가 MULTI_RUN 또는
RANGE_OUT_OF_BOUNDS 로 reject.

### 6-3. SCENARIO_DELETE (= "DELETE_TEXT_RANGE")

`range_anchor`~`range_focus` 구간 삭제. 동일한 multi-run 제약.

---

## 7. fixture 정책

- `data/recognition_corpus/corpus.sqlite3` 의 `fillable_form` 분류에서
  `file_size BETWEEN 30000 AND 80000` 범위 첫 건.
- 선정된 fixture 에서 `containerScope.kind == "cell"` 이고
  `parPrIDRef` 와 첫 run `charPrIDRef` 가 있는 paragraph 첫 건만 사용.
- fixture 미존재 → 본 공정 audit `partialCompletion=True` (PASS 유지).
  pytest 는 `pytest.skip` 으로 건너뜀.

---

## 8. 정합 검증 (cross-circuit)

본 공정은 **신규 normalizer / validator / extractor 를 만들지 않는다**
(§11-6). 모든 검증은 기존 자재 (paragraph_writer_adapter 직접 호출
포함) 만 사용한다. test 13/14 는 save_paragraph_edits 직접 호출로
회로 정합을 별도 검증한다.

---

## 9. 다음 활성화 트리거

본 공정 부분 준공의 다음 트리거:

1. **paragraph readback parser** — `paragraph_save_verify7` V1 의
   readback 지원 → V1/V7 PASS 화.
2. **adapter applyCharPrIDRef 보강** — `paragraph_writer_adapter.applied`
   가 `applyCharPrIDRef` 필드를 적재 → V4 PASS 화.
3. **TYPE_TEXT expectedBefore 계약 정렬** — `make_type_text_command`
   가 `expectedBefore=""` (caret slice) 로 발급하도록 조정 →
   TYPE_TEXT writer 본 실행 PASS.
4. **multi-run writer** — 다중 run 범위 편집 활성화 → test 14 의
   reject 회로가 PASS 회로로 전환.
5. **body writer** — body (cell 외) paragraph 편집 활성화 → test 13 의
   reject 회로가 PASS 회로로 전환.
6. **표/이미지/도장 편집** — 본 공정 범위 외, 별도 동 신축 필요.

각 트리거 활성화 시점에 본 시방서의 §5 차단 회로 표 및 audit 정책을
재정비한다.

---

## 10. 본 공정 commit

```
commit  : (commit 후 갱신)
baseline: 81e86e9
파일    : 4 세대 신축, 0 세대 수정
```

산출물:

- `scripts/hwpx/web_office/para_edit_e2e_pipeline.py` (orchestration)
- `scripts/ops/audit_web_office_para_edit_e2e_integration.py` (감사)
- `tests/test_web_office_para_edit_e2e_integration.py` (15 시나리오)
- `docs/architecture/web_office_para_edit_e2e_integration.md` (본 문서)

---

*생성 : E2E_INTEGRATION_01 (2026-05-21)*
*근거 : §1·§4-A·§11-6·§11-8 (CLAUDE.md)*

> **저장소 분리 기준**: e04d325 (hwpx-web-office 신규 저장소 초기 커밋, 2026-05-22)
