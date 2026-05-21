# WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01 준공 closeout

> baseline: 183bfa5  
> 준공일: 2026-05-21  
> 공정: Enter 키 → body paragraph split (문단 삽입)

---

## 1. 완료 범위 (IN_SCOPE)

### JS (frontend/web_office_viewer/)

| 자재 | 역할 |
|------|------|
| `para_edit_command.mjs` | `CT_PARA_INSERT`, `CT_PARA_DELETE`, `allocateNewParagraphId`, `makeParaInsertCommand`, `applyParaInsertToParagraphs`, `applyParaDeleteToParagraphs` |
| `para_edit_state.mjs` | `splitParagraphAtCaret`, `_appendCommandWithParas` |
| `para_edit_runtime.mjs` | `onKeyDown` Enter 분기 → `splitParagraphAtCaret` |
| `para_edit_structure_smoke.mjs` | 35개 시나리오 smoke (JS) |

### Python (scripts/hwpx/web_office/)

| 자재 | 역할 |
|------|------|
| `para_edit_model.py` | `CT_PARA_INSERT`, `CT_PARA_DELETE`, `make_para_insert_command`, reason code 상수 4종 |
| `paragraph_writer_adapter.py` | `"PARA_INSERT"` command type 지원, cell scope reject |
| `paragraph_save_verify7.py` | `_verify_v8_para_struct_integrity` (V8 신설) |

### 테스트·감사

| 자재 | 역할 |
|------|------|
| `tests/test_web_office_para_edit_structure_para_insert.py` | Python 감리검사 16항목 |
| `scripts/ops/audit_web_office_para_edit_structure_para_insert.py` | 준공검사 audit |

### 확정 동작

- `allocateNewParagraphId`: paragraphs 배열 max(id)+1 반환
- `makeParaInsertCommand`: caret 위치 text split, forward/inverse 페어 발급
- `applyParaInsertToParagraphs`: run 단위 분할, 빈 run 자동 발급
- `applyParaDeleteToParagraphs`: inverse undo — 빈 run 정리 후 병합
- `splitParagraphAtCaret`: state 레벨 Enter 처리, 새 paragraphId로 커서 이동
- Enter/Shift+Enter/Ctrl+Enter 분기 처리
- range selection Enter → `MULTI_PARA_RANGE_NOT_SUPPORTED` reject
- cell scope Enter → `PARA_INSERT_CELL_SCOPE_NOT_SUPPORTED` reject
- undo/redo 지원 (`CT_PARA_DELETE` inverse 페어)
- V8 검증: PARA_INSERT 적용 항목 신규 id·text 무결성 확인

---

## 2. 차단 범위 (OUT_OF_SCOPE)

| 항목 | 사유 |
|------|------|
| Shift+Enter (soft break) | `SOFT_BREAK_NOT_SUPPORTED` — 후속 공정 |
| 표(cell) 내부 Enter | `PARA_INSERT_CELL_SCOPE_NOT_SUPPORTED` — 표 구조 편집은 별도 공정 |
| section boundary paragraph split | `SECTION_BOUNDARY_NOT_SUPPORTED` — 섹션 재편 필요 |
| list item paragraph split | `LIST_ITEM_NOT_SUPPORTED` — 목록 구조 편집 별도 공정 |
| paragraph delete (Backspace at start) | 후속 공정 |
| paragraph merge | 후속 공정 |
| backend HWPX writer 직접 연동 | save pipeline 별도 공정 |
| image/stamp/signature 편집 | 미착공 |
| AI 자동 입력 | §10 별도 흐름 |
| 원본 HWPX 직접 수정 | C동 writer 경유 필수 |

---

## 3. 감리 결과

| 검사 | 결과 |
|------|------|
| Python 단위 테스트 16항목 | PASS (16/16) |
| JS smoke 35항목 | PASS (35/35) |
| audit script | PASS |

---

## 4. 회귀 자재 목록

### Python 테스트
- `tests/test_web_office_para_edit_structure_para_insert.py`

### JS smoke
- `frontend/web_office_viewer/para_edit_structure_smoke.mjs`

---

## 5. 다음 공정 후보

| 공정명 | 내용 |
|--------|------|
| `STRUCTURE-PARA-DELETE-01` | Backspace at paragraph start → paragraph merge |
| `STRUCTURE-SOFT-BREAK-01` | Shift+Enter soft break |
| `STRUCTURE-CELL-PARA-INSERT-01` | cell 내부 Enter |
| `APPLYFORMAT-FONT-ALIAS-MATCHING-01` | font alias fuzzy 매칭 |
| `B동-XML-DEEP-STRUCTURE-ANALYZER-01` | XML 정밀진단동 신축 (P1) |
