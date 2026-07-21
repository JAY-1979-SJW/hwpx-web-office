# WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01 준공 closeout

> baseline: 5db3d7f  
> 기능 commit: 1f442ec  
> 준공일: 2026-05-21  
> 공정: Backspace at caret==0 → body paragraph merge (문단 삭제/병합)

---

## 1. 완료 범위 (IN_SCOPE)

### JS (frontend/web_office_viewer/)

| 자재 | 역할 |
|------|------|
| `para_edit_command.mjs` | `CT_PARA_DELETE`, `makeParaDeleteCommand`, `applyParaDeleteForwardToParagraphs` |
| `para_edit_state.mjs` | `mergeParagraphWithPrevious`, `deleteBackward` caret==0 분기, undo/redo PARA_DELETE 경로 |
| `para_edit_runtime.mjs` | `onKeyDown` Backspace 분기 → `deleteBackward` → `mergeParagraphWithPrevious` |
| `para_edit_structure_smoke.mjs` | 58개 시나리오 smoke (PARA_INSERT 22 + PARA_DELETE 22 + 기타 14) |

### Python (scripts/hwpx/web_office/)

| 자재 | 역할 |
|------|------|
| `para_edit_model.py` | `CT_PARA_DELETE`, `PARA_COMMAND_TYPES`, `make_para_delete_command`, `REASON_NO_PREV_PARAGRAPH`, `REASON_PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED` |
| `paragraph_writer_adapter.py` | `"PARA_DELETE"` command type 지원, `_apply_para_delete`, `_iter_paragraphs`, cell scope reject, `REASON_NO_PREV_PARAGRAPH` |
| `paragraph_save_verify7.py` | `_verify_v8_para_struct_integrity` — PARA_DELETE 적용 항목 removedParagraphId·prevParagraphId 무결성 확인 |

### 테스트·감사

| 자재 | 역할 |
|------|------|
| `tests/test_web_office_para_edit_structure_para_delete.py` | Python 감리검사 18항목 |
| `scripts/ops/audit_web_office_para_edit_structure_para_delete.py` | 준공검사 audit |

### 확정 동작

- `makeParaDeleteCommand`: prevParagraph + currentParagraph → forward(PARA_DELETE) / inverse(PARA_INSERT) 페어
- `applyParaDeleteForwardToParagraphs`: currentParagraph runs를 prevParagraph에 병합, current 제거
- `mergeParagraphWithPrevious`: caret==0 + block scope + same section → PARA_DELETE command 발행
- Backspace caret==0 → `mergeParagraphWithPrevious` → state 업데이트
- undo(PARA_DELETE) → synthetic PARA_INSERT inverse로 재분리 → 3개 paragraph 복원
- redo(PARA_DELETE) → applyParaDeleteForwardToParagraphs 재실행 → 2개 paragraph
- V8 검증: PARA_DELETE 적용 항목 removedParagraphId·prevParagraphId·mergedText 무결성 확인
- charPrIDRef / parPrIDRef — prevParagraph 기준 보존 (currentParagraph runs를 그대로 이어붙임)
- paragraph id 제거: currentParagraph.paragraphId 는 병합 후 배열에서 제거
- undo 시 paragraph id 복원: synthetic PARA_INSERT inverse → newParagraphId로 재삽입

### reject 정책 (안전 게이트)

| 조건 | reject 코드 |
|------|-------------|
| IME composition 중 | `IN_COMPOSITION` |
| range selection 상태 | `MULTI_PARA_RANGE_NOT_SUPPORTED` |
| 첫 번째 paragraph (이전 paragraph 없음) | `NO_PREV_PARAGRAPH` |
| containerScope.kind == "cell" | `PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED` |
| 이전 paragraph가 다른 sectionIndex | `SECTION_BOUNDARY_NOT_SUPPORTED` |
| activeParagraph 미발견 | `TARGET_PARAGRAPH_NOT_FOUND` |
| caret > 0 (Backspace 중간 위치) | PARA_DELETE 미발행 → `DELETE_TEXT_RANGE` 유지 |

---

## 2. 차단 범위 (OUT_OF_SCOPE)

| 항목 | 사유 |
|------|------|
| table cell paragraph merge | `PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED` — 표 구조 편집은 별도 공정 |
| header/footer paragraph merge | 현재 scope 미포함 — 별도 공정 |
| image/shape run special merge | run 타입 무관 단순 이어붙임만 허용 |
| section break merge | `SECTION_BOUNDARY_NOT_SUPPORTED` |
| list/numbering merge | reject — 구조 편집 별도 공정 |
| multi-paragraph selection merge | `MULTI_PARA_RANGE_NOT_SUPPORTED` |
| Shift+Enter soft break | `SOFT_BREAK_NOT_SUPPORTED` — 별도 공정 |
| table structure edit | 미착공 |
| media edit | 미착공 |
| 신규 charPr 생성 | `NEW_CHARPR_INTRODUCED` 금지 gate 유지 |
| header.xml mutation | 금지 — package.entries["header.xml"] 직접 write 금지 |
| Excel 공정 | 다른 창에서 처리 |
| 원본 HWPX 직접 수정 | outputPath == sourcePath reject 유지 |
| AI 자동 입력 | §10 별도 흐름 |

---

## 3. 감리 결과

| 검사 | 결과 |
|------|------|
| Python 단위 테스트 18항목 | PASS (18/18) |
| JS smoke 58항목 | PASS (58/58) |
| audit script | PASS |
| full regression | PASS (3155 passed / 0 기능 FAIL) |
| baseline sync | PASS (5db3d7f) |
| mixed commit 감사 | WARN_ACCEPTED (1f442ec, data/audit/mixed_commit_closeout_20260521_1f442ec.jsonl) |

---

## 4. 회귀 자재 목록

### Python 테스트
- `tests/test_web_office_para_edit_structure_para_delete.py`
- `tests/test_web_office_para_edit_structure_para_insert.py`

### JS smoke
- `frontend/web_office_viewer/para_edit_structure_smoke.mjs`

---

## 5. 다음 공정 후보

| 공정명 | 내용 |
|--------|------|
| `STRUCTURE-SOFT-BREAK-01` | Shift+Enter soft break 구현 |
| `STRUCTURE-PARA-DELETE-CELL-01` | cell scope Backspace merge (표 구조 편집) |
| `UNDO-REDO-STACK-LIMIT-01` | undo stack 크기 제한 및 메모리 관리 |
| `STRUCTURE-PARA-DELETE-SECTION-01` | section boundary merge 정책 고도화 |

> **baseline 갱신**: 98d64ed (SCOPE-BOUNDARY-REJECT-01 준공, 2026-05-21) — header/footer/non-body scope reject guard 추가. para_edit_state.mjs / para_edit_model.py 정당 변경 확인 후 베이스라인 갱신.

> **저장소 분리 기준**: e04d325 (hwpx-web-office 신규 저장소 초기 커밋, 2026-05-22)

> **baseline 갱신**: 4b0515f (WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01 준공, 2026-05-22) — charPr guard 추가로 잠금 파일 정당 변경 확인 후 베이스라인 갱신.
