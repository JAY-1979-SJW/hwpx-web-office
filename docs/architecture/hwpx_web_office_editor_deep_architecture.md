# HWPX Web Office Editor 상세 아키텍처 설계서

> 공정명: HWPX-WEB-OFFICE-EDITOR-DEEP-ARCHITECTURE-01
> 작성일: 2026-05-20
> 기준 HEAD: `99a636f`
> 분류: §11-1 ② 시공 계획서 (매우 고도화 등급, 설계·문서화 전용)
> 정책 준수: CLAUDE.md §1~§11 전체
> 본 공정 범위: **설계/감사/문서화만 수행.** writer 실행, 원본 HWPX 수정,
> 출력 HWPX 생성은 금지.

---

## 1. 목표와 비목표

### 1-1. 목표

본 단지는 HWPX 문서를 단순 데이터 추출용이 아니라 **브라우저에서 원본
문서를 직접 수정하는 것처럼 편집 가능한 Web Office Editor**로 확장한다.

사용자 경험 (UX) 목표:

- 원본 HWPX 문서가 그대로 브라우저에 표시된다.
- 표·문단·셀·이미지·서명란을 마우스/키보드로 직접 편집한다.
- 자재DB, 계약내역서, 기성내역서, 외부 PDF, AI proposal 결과를 끌어와 셀에
  drop 한다.
- 저장 시 PDF, XLSX, HWPX 셋 중 선택해 출력한다.
- Undo/Redo 가 가능하다.
- AI 자동 채움은 사용자가 검토·확정 버튼을 누르기 전에는 반영되지 않는다.

내부 구조 목표:

- 원본 HWPX는 절대 덮어쓰지 않는다.
- `DocumentModel` (parser 결과 + 메타) + `EditCommand` (사용자/AI 입력) +
  `OutputModel` (writer 입력 plan) 3분리.
- writer는 출력 단계에서만 호출되며, 원본 → output 경로는 sandbox 격리.
- 모든 명령은 명령 객체로 기록되어 undo/redo, audit, 재현 가능.

### 1-2. 비목표 (Non-goals)

- **한컴 한글 완전 호환은 1차 목표가 아니다.** 우리↔우리 byte 동등
  (self-roundtrip) 이 호환 기준이다. 한컴 한글 호환은 향후 정밀
  자재(`hancom_*`) 분리 후 별도 공정으로 추진.
- 한컴 메뉴 1:1 복제는 비목표. HWPX 기능 카탈로그 단위로 구현한다.
- 풀 페이지네이션 / 줄바꿈 픽셀 단위 재현은 MVP 비목표. layoutGuess 와
  block 경계까지만 보장.
- 실시간 다중 협업 (CRDT 등) 은 비목표. 1인 편집 세션 단위로만 동작.

---

## 2. 기존 HWPX 엔진 자산 목록

본 단지의 자산은 §11-10 16+ 공정에서 검증된 자재만 인용한다. 외부 모듈
신규 도입은 본 설계 채택 후 별도 공정으로 검토.

### 2-1. Parser 계열 (read)

| 자재 경로 | 역할 | 회귀 잠금 |
|-----------|------|-----------|
| `scripts/hwpx/parser/parser_engine.py` | HWPX zip → DocumentTree | `test_hwpx_corpus_fixtures.py` |
| `scripts/hwpx/parser/table_parser.py` | 표 · 행 · 셀 추출 (병합 포함) | `test_hwpx_append_table_rows_*` |
| `scripts/hwpx/parser/input_slot_detector.py` | 라벨 셀 → 입력 후보 | `parser_contract.py` |
| `scripts/hwpx/parser/style_parser.py` | charPrIDRef / parPrIDRef | V4·V5 정착 |
| `scripts/hwpx/parser/object_parser.py` | 이미지·도형·OLE 객체 | — |
| `scripts/hwpx/parser/schedule_detector.py` | 공정표 막대 검출 | — |
| `scripts/hwpx/parser/layout_classifier.py` | 표 layoutGuess | — |
| `scripts/hwpx/parser/block_parser.py` | 본문 블록 (paragraph/table) | — |

### 2-2. Writer / Edit 계열 (write)

| 자재 경로 | 역할 |
|-----------|------|
| `scripts/hwpx/hwpx_package.py` | HWPX zip 패키지 read/write |
| `scripts/hwpx/hwpx_edit_tool.py::apply_edit_plan` | 통합 plan 적용 |
| `scripts/hwpx/hwpx_table_ops.py` | set_table_cell_text 등 셀 단위 |
| `scripts/hwpx/hwpx_header_footer_ops.py` | 머리말/꼬리말 |
| `scripts/hwpx/hwpx_metadata_ops.py` | 문서 메타데이터 |
| `scripts/hwpx/hwpx_visible_image_ops.py` | 표시 이미지 (도장·차트) |
| `scripts/hwpx/hwpx_image_ops.py` | BinData 매니페스트 |
| `scripts/hwpx/hwpx_writer_adapter.py` | editor facade |
| `scripts/hwpx/hwpx_section_ops.py` | 섹션 관리 |
| `scripts/hwpx/hwpx_picture_ops.py` | 그림 객체 |

### 2-3. AI proposal / Fill review

| 자재 경로 | 역할 |
|-----------|------|
| `scripts/hwpx/ai_proposal/ai_proposal_contract.py` | AI proposal 계약 |
| `scripts/hwpx/ai_proposal/target_resolver.py` | label → 좌표 |
| `scripts/hwpx/ai_proposal/format_normalizer.py` | 값 정규화 |
| `scripts/hwpx/ai_proposal/confidence_policy.py` | confidence 게이트 |
| `scripts/hwpx/ai_proposal/review_item_builder.py` | review item (AI_ASSISTED 강제) |
| `scripts/hwpx/fill_review/fill_review_contract.py` | fill review 계약 |
| `scripts/hwpx/fill_review/fill_review_live_pipeline.py` | live pipeline |
| `scripts/hwpx/fill_review/fill_review_ui_adapter.py` | UI adapter |

### 2-4. 검증 계열

| 자재 경로 | 역할 |
|-----------|------|
| `scripts/ops/verify_e2e_input_precision.py::verify_one` | V1~V7 정밀 검증 |
| `scripts/ops/claude_inline_full_integration_demo.py` | 5도메인 통합 데모 |
| `scripts/hwpx/parser/object_cell_confirmation_gate.py` | 셀 좌표 신뢰성 |

### 2-5. 마스터 회로 / 게이트

| 자재 경로 | 역할 |
|-----------|------|
| `scripts/hwpx/master_orchestration/auto_fill_master.py` | AI inject 게이트 |
| `scripts/hwpx/master_orchestration/live_smoke_harness.py` | 운영 시뮬 |

### 2-6. 회귀 잠금 (이미 정착된 회로)

- claude_inline W-01~W-08 (`0c0c084`)
- claude_inline 다중 셀 + applied=∅ 회귀 (`99a636f`)
- fill_review contract (`test_hwpx_fill_review_contract.py`)
- AI recognition safe edit pipeline (`test_hwpx_ai_recognition_safe_edit_pipeline.py`)

---

## 3. Web Office 전체 계층도

```
┌─────────────────────────────────────────────────────────────┐
│                       Browser (Client)                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ LayoutRenderModel   (canvas/SVG/HTMLGrid 렌더링)    │    │
│  │   ↑ DocumentModel snapshot                          │    │
│  │ SelectionCursorModel (셀/문단/이미지 선택, 캐럿)    │    │
│  │   ↓ 사용자 input                                    │    │
│  │ EditCommandModel    (insert/replace/delete/format)  │    │
│  │   ↓ command 객체                                    │    │
│  │ DocumentModel       (in-memory tree + dirty flag)   │    │
│  │   ↑                                                  │    │
│  │ AIValidationModel   (AI proposal review/confirm UI) │    │
│  └─────────────────────────────────────────────────────┘    │
│                          │ WebSocket / REST                   │
└──────────────────────────┼──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                    Engine Server (Java/Python)               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ HTTP Handlers (/document/load /command /save /export)│   │
│  │   ↓                                                  │    │
│  │ DocumentSession (메모리 DocumentModel, command log) │    │
│  │   ↓                                                  │    │
│  │ EditCommandTranslator (UI command → edit_plan)      │    │
│  │   ↓                                                  │    │
│  │ SaveOutputModel (출력 단계에서만 apply_edit_plan)   │    │
│  │   ↓                                                  │    │
│  │ Writer: hwpx_edit_tool / Apache POI / PDF renderer  │    │
│  └─────────────────────────────────────────────────────┘    │
│                          │                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 원본 HWPX (read-only, sha256 사전/사후 검증)         │   │
│  │ Output sandbox: data/drafts/sessions/{session_id}/  │    │
│  │ Audit log: data/audit/editor_actions/{date}.jsonl   │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

원본 HWPX는 read-only 마운트. writer 호출은 **save/export 단계에서만**
sandbox 경로로 산출.

---

## 4. DocumentModel schema

`parse_hwpx_v2` 결과를 베이스로 in-memory 트리를 구성한다.

```jsonc
DocumentModel = {
  "documentId": "uuid",
  "sourceHwpxSha256": "...",        // 원본 무결성 anchor
  "sourceHwpxPath": "path",          // read-only
  "loadedAt": "ISO-8601",
  "sections": [
    {
      "sectionIndex": 0,
      "pageMeta": { "width": ..., "height": ... },
      "headerFooter": { "header": "...", "footer": "..." },
      "blocks": [
        { "type": "paragraph", "blockId": "p_0_0",
          "runs": [{"runId":"r_0_0_0","text":"...","charPrIDRef":"3"}],
          "parPrIDRef": "5" },
        { "type": "table", "blockId": "t_s0_001", "tableIndex": 1,
          "rowCount": 5, "colCount": 3, "visualColCount": 3,
          "cells": [
            { "cellId": "t_s0_001_r0_c0",
              "row": 0, "col": 0, "rowSpan": 1, "colSpan": 1,
              "isHeader": false,
              "runs": [...],
              "borderId": "...", "fillId": "..." }
          ]
        },
        { "type": "image", "blockId": "img_0_2",
          "entry": "BinData/image001.png", "anchor": {...} }
      ]
    }
  ],
  "styles": { "charPr": {...}, "parPr": {...}, "borderFill": {...} },
  "manifest": { "BinData/...": "image/png" },
  "metadata": { "title": "...", "creator": "..." },
  "dirty": false,
  "commandLog": []      // EditCommand[] (append-only)
}
```

핵심 원칙:

- 모든 노드는 **stable id** (`blockId`, `cellId`, `runId`) 를 가진다.
- id는 `(sectionIndex, blockIndex, cellRow, cellCol, runIndex)` 기반
  결정적 해시. parser 재실행 시 동일 id 재생산.
- `runs` 단위 편집을 기본으로 하여 charPrIDRef / parPrIDRef 보존 (V4/V5).
- `dirty` 는 commit/save 시에만 false. command 적용 시 true.

---

## 5. Layout/Renderer 전략

### 5-1. 렌더 모델

- **HTML Grid / Canvas hybrid**:
  - 표·문단·셀 → HTML `<table>` 또는 CSS Grid (DOM 접근 용이)
  - 페이지 배경·여백·머리말/꼬리말 → SVG layer
  - 이미지 (BinData) → `<img>` blob URL
  - 도형·차트 → SVG (HWPX object → SVG 1차 변환)

- **`LayoutRenderModel`** = DocumentModel snapshot + 페이지 단위 layout
  계산 결과. parser 의 `layoutGuess` 를 1차 힌트로 사용.

- 픽셀 단위 정밀 재현은 비목표. 표 경계, 셀 텍스트, 문단 정렬, 이미지
  위치까지가 MVP 기준.

### 5-2. 가상 스크롤 / 페이지

- 페이지 단위 lazy render. 100 페이지 이상 문서 대비.
- 페이지 전환 시 DocumentModel 의 section 단위로 분리 렌더.

### 5-3. 폰트

- 브라우저 시스템 폰트 우선. HWPX 임베디드 폰트는 MVP 비목표.
- 한컴고딕/맑은고딕 등 한글 기본 폰트는 fallback 매핑.

---

## 6. Selection/Cursor 전략

### 6-1. 선택 단위

```jsonc
Selection = {
  "type": "caret" | "range" | "cell" | "cellRange" | "image",
  "anchor": { "blockId": "...", "runId": "...", "offset": 0 },
  "focus":  { "blockId": "...", "runId": "...", "offset": 0 }
}
```

- Caret: 문단 내 글자 사이 위치 (insert 지점)
- Range: 두 caret 사이 (replace/delete/format 대상)
- Cell / CellRange: 셀 단위 선택 (병합 셀 처리는 visual coord 변환)
- Image: 이미지 객체 단일 선택 (이동·크기조절은 MVP 비목표)

### 6-2. 좌표 시스템

- **logical** (row, col) — DocumentModel native
- **visual** (visual_row, visual_col) — 병합 셀 풀어낸 그리드
- 변환은 `_resolve_visual_coords` (이미 존재) 재사용

---

## 7. Table/Cell editing 전략

| 동작 | 명령 객체 | edit_plan key | 기존 자재 |
|------|----------|----------------|-----------|
| 셀 텍스트 변경 | `SetCellText` | `set_cells` | `set_table_cell_text` |
| 셀 라벨로 입력 | `SetCellByLabel` | `set_cells_by_label` | `set_cells_by_label` |
| 행 추가 | `AppendTableRows` | `append_table_rows` | `append_table_rows` |
| 행 삭제 | `DeleteTableRows` | `delete_table_rows` | `delete_table_rows` |
| 셀 병합 | `MergeCells` | `merge_cells` | `merge_cells` |
| 병합 해제 | `UnmergeCells` | `unmerge_cells` | `unmerge_cells` |
| 셀 스타일 | `SetCellStyle` | (vertical_align/fill_color 등) | post-edit options |

좌표 매칭은 LOCK_01 (`99a636f`) 의 `_filter_applied_cells_by_coord` 정책
적용 — (table, row, col) 기준. semantic label 의존 금지.

---

## 8. Paragraph editing 전략

### 8-1. Run 단위 편집

문단은 `runs[]` 의 시퀀스. 각 run 은 charPrIDRef 를 가짐. 편집 시:

- **TypeText** (caret) — caret 위치 run 을 split → 신규 run insert
  (charPrIDRef 는 이전 run 상속)
- **ReplaceTextRange** (range) — range 안 run 들을 제거 → 신규 run insert
- **DeleteRange** — range 안 run 제거 (병합 가능 시 인접 run 병합)
- **ApplyFormat** — range 안 run 들을 split 한 후 charPrIDRef 신규 등록

### 8-2. 스타일 보존

- charPrIDRef / parPrIDRef 가 같은 인접 run 은 자동 병합 (정규화)
- 신규 charPr 추가 시 `styles.charPr` 사전에 등록 후 ID 재사용

### 8-3. 빈 문단 / 빈 run

- HWPX writer 가 빈 cell textNode 요구 (W-known) — `append_table_rows`
  잠금 회로 (`test_hwpx_append_table_rows_empty_cell_textnode.py`) 인용.

---

## 9. Image/Stamp/Signature 전략

### 9-1. 이미지 객체 분류

| 종류 | 처리 |
|------|------|
| 인라인 이미지 (BinData) | `insert_generated_png_picture` 재사용 |
| 도장 / 직인 | 인라인 이미지의 특수형 + 위치 lock 옵션 |
| 서명 (sign pad) | 브라우저 canvas → PNG → BinData |
| 차트 (생성형) | PNG 생성 후 insert (현 5도메인 데모와 동일) |
| 인라인 SVG | MVP 비목표 |

### 9-2. 무결성

- 신규 이미지는 `BinData/<sessionId>_<n>.png` 경로로 추가 — 원본 BinData
  덮어쓰기 금지
- manifest 갱신은 `add_content_manifest_item` 만 사용
- 이미지 삭제는 MVP 비목표 (재배치만 허용)

### 9-3. 서명·날인 워크플로

- 사용자가 서명란을 클릭 → 모달 캔버스 → PNG 추출 → `EditCommand`
  `InsertSignaturePng` 발행
- 서명 위치는 셀/문단 anchor 좌표 기반. 절대 px 좌표 비사용.

---

## 10. EditCommand / Undo / Redo 전략

### 10-1. Command 객체

```jsonc
EditCommand = {
  "commandId": "uuid",
  "timestamp": "ISO-8601",
  "actor": "USER" | "AI_PROPOSAL" | "TEMPLATE",
  "type": "SetCellText" | "TypeText" | "ReplaceTextRange" | ...,
  "target": { "blockId": "...", "cellId": "...", "range": {...} },
  "payload": { "value": "...", "charPrIDRef": "..." },
  "inverse": { ... },       // undo 용 역연산
  "source": { "label": "...", "decisionSource": "AI_ASSISTED" }
}
```

- **모든 명령은 inverse 를 동반.** undo 시 inverse 를 forward 로 실행.
- Redo 는 forward 큐를 유지.
- AI 자동 입력은 `actor=AI_PROPOSAL` 로 기록되며, 사용자 confirm 전에는
  `pending=true` 상태로 별도 큐. confirm 시 commandLog 에 append.

### 10-2. 명령 적용 순서

1. EditCommand 검증 (id 유효성, range 범위, charPrIDRef 존재)
2. DocumentModel in-memory 변형 (inverse 함께 산출)
3. commandLog append
4. dirty=true
5. LayoutRenderModel 재계산 트리거 (부분 invalidate)

writer (`apply_edit_plan`) 는 step 1~5 에서 **호출되지 않는다.** save 시에만 호출.

### 10-3. 명령 → edit_plan 변환

save 시 `commandLog` 를 압축해 `apply_edit_plan` 의 입력 형태로 변환:

- `SetCellText` × N → `{"set_cells": [...]}` (단일 plan)
- `TypeText` / `ReplaceTextRange` → 문단 run 재구성 결과를
  `set_paragraph_runs` (신설 필요) 또는 `replace_text_nodes` 로
- `InsertSignaturePng` → `picture_inserts`

---

## 11. Save / Output 전략

### 11-1. 원본 보존

- 원본 HWPX 는 read-only 마운트. sha256 사전/사후 비교 게이트.
- 출력은 `data/drafts/sessions/{sessionId}/output_{timestamp}.hwpx`
  (sandbox)
- 승인 후 `data/approvals/` 로 이관 (불변 정책)

### 11-2. Save flow

```
[client] Save 요청
   ↓
[server] commandLog 압축 → edit_plan 산출
   ↓
[server] dry_run=True 로 apply_edit_plan 사전 검증
   ↓
[server] verify7 (V1~V7) 통과 시에만 dry_run=False 본 실행
   ↓
[server] 출력 sandbox 에 저장 + audit log append
   ↓
[server] 원본 sha256 사후 검증 (변경 없음 확인)
   ↓
[client] 다운로드 URL 반환
```

### 11-3. 동시성

- 1 세션 = 1 DocumentModel. 멀티 탭은 read-only 사본.
- save 시 세션 락. 다른 명령은 큐잉.

---

## 12. PDF / Excel / HWPX export 전략

| 출력 | 1차 경로 | MVP 여부 |
|------|----------|----------|
| HWPX | `apply_edit_plan` (기존 자재 그대로) | MVP-A |
| PDF | HWPX → 한컴 한글 (서버) 또는 HWPX → SVG → PDF (자체) | MVP-B (자체), C (한컴 경로) |
| XLSX | 표만 추출 → Apache POI (§9 강제) | MVP-B |

### 12-1. PDF 자체 경로 (a 후보)

- LayoutRenderModel 의 SVG → PDF (jsPDF / Cairo / WeasyPrint)
- 한글 폰트 임베드는 별도 정책

### 12-2. PDF 한컴 경로 (b 후보)

- 서버 사이드 hancom render — `scripts/hwpx/hancom_render_to_image.ps1`
  계열 자재 활용 가능성 검토 (단지 §6 nginx restart 금지 등 게이트 준수)

### 12-3. XLSX

- HWPX 표 → 셀 매트릭스 → Apache POI XSSFWorkbook (openpyxl 금지 §9)
- 스타일 1:1 매핑은 비목표. 텍스트·병합·테두리까지.

---

## 13. AI field mapping / validation 전략

### 13-1. 흐름 (§10 정책 준수)

```
AI proposal (ai_proposal_contract)
   ↓ confidence_policy 통과
ReviewItem (decisionSource=AI_ASSISTED 강제)
   ↓ UI pending 큐
사용자 confirm
   ↓
EditCommand(actor=AI_PROPOSAL, source=...)
   ↓
DocumentModel 적용
```

### 13-2. 게이트

- `master_orchestration/auto_fill_master.py::AI_REQUIRED_FOR_AUTO_FILL`
  게이트 유지 — AI inject 없으면 자동 채움 차단.
- 사람의 confirm 없이 commandLog 에 append 금지 (pending 상태에서 차단).
- AI 신뢰도 ≥ confidence_policy threshold 만 UI 표시 후보.

### 13-3. AIValidationModel

```jsonc
AIValidationModel = {
  "pending": [
    {
      "proposalId": "...", "targetCellId": "...",
      "proposedValue": "...", "semantic": "...",
      "confidence": 0.92,
      "rationale": "...", "evidenceSpan": "...",
      "userAction": null   // CONFIRM / REJECT / EDIT
    }
  ],
  "confirmed": [...]
}
```

---

## 14. 자재DB / 계약내역서 / 기성내역서 연동 전략

### 14-1. 외부 자재 소스

- 자재DB (price-classifier) → Drop-in 카드 (셀 dropable)
- 계약내역서 (XLSX) → 시트 단위 import (Apache POI)
- 기성내역서 (XLSX) → 변환 룰 14개 (`ce3cf1a` 등) 적용 후 import
- 외부 PDF → 표 추출은 비목표. 텍스트 copy/paste 만.

### 14-2. Drop 인터페이스

```jsonc
ExternalDropPayload = {
  "kind": "material" | "contract_line" | "progress_line" | "pdf_text",
  "items": [
    { "label":"콘크리트 28-180", "quantity":"100", "unit":"m3",
      "unitPrice":"82000", "amount":"8200000" }
  ],
  "targetCellId": "t_s0_001_r5_c0"
}
```

서버는 payload 를 `EditCommand[]` 로 expand. 외부 데이터는 pending → 사용자
confirm 강제.

---

## 15. 보안 / 원본보존 / 감사로그 정책

### 15-1. 원본 보존 (필수)

- 원본 HWPX 파일 시스템 권한: read-only (chmod 555 권장, 단 §6 chmod
  금지 — 운영 진입 시 별도 공정에서 확정)
- 모든 save 후: `sha256(원본) == sha256_at_load` 게이트
- 위반 시 즉시 ALERT + write 차단

### 15-2. Sandbox

- 세션 출력: `data/drafts/sessions/{sessionId}/`
- 승인: `data/approvals/{approval_id}/` (불변)
- 폐기: 7 일 후 자동 정리 (별도 ops 공정)

### 15-3. Audit log

- `data/audit/editor_actions/{YYYY-MM-DD}.jsonl` (append-only)
- 한 줄 = 1 EditCommand + 적용 결과 + actor + sessionId + sha256
- `data/audit/` 는 AUDIT 등급 (§8 창고 규칙)

### 15-4. 방화구획

- `data/sessions/` 은 BLOCKED (§8). 본 단지의 세션 ID 는 별도
  `data/drafts/sessions/` 로 격리.
- secret/token 노출 금지 (§6)

---

## 16. 오픈소스 라이선스 리스크 (요약)

상세는 `hwpx_web_office_open_source_review.md` 참조. 본 절은 정착 요약만.

| 영역 | 채택/보류/배제 |
|------|----------------|
| HWPX read/write | 자체 자재 (PASS) |
| Browser grid | Handsontable Community (보류) / AG Grid Community (채택 후보) |
| Renderer | 자체 SVG (PASS) / SlateJS (보류) |
| PDF output | jsPDF (보류) / WeasyPrint (보류) / 한컴 render (별도) |
| State / Command history | Immer.js + 자체 command stack (채택 후보) |

라이선스 불명확 / GPL 강전염 라이브러리는 core dependency 로 확정하지
않는다 (시방서 금지 조항).

---

## 17. Phase 별 구현 순서

| Phase | 코드명 | 범위 | 산출물 | 회귀 잠금 |
|-------|--------|------|--------|-----------|
| **Phase 0** | DESIGN-LOCK | 본 설계서 + audit + contract test | docs/architecture/* | 본 공정 |
| **Phase 1** | RO-VIEW | HWPX → DocumentModel → 브라우저 read-only 렌더 | client viewer, /document/load API | parser 회귀 |
| **Phase 2** | CELL-EDIT | 셀 텍스트 편집 + undo/redo + save (HWPX) | EditCommand, command log | verify7 V1~V7 |
| **Phase 3** | PARA-EDIT | 문단 run 편집 + 스타일 보존 | TypeText / ReplaceTextRange | V4·V5 회귀 |
| **Phase 4** | TABLE-OPS | 행 추가/삭제, 셀 병합/해제 | 기존 table_ops 라우팅 | 표 회귀 |
| **Phase 5** | IMAGE-STAMP | 이미지·도장·서명 | InsertSignaturePng | manifest 무결성 |
| **Phase 6** | AI-CONFIRM | AI proposal pending → confirm UI | AIValidationModel | §10 AI 게이트 |
| **Phase 7** | EXTERNAL-DROP | 자재DB / 계약·기성내역서 drop | ExternalDropPayload | classifier 회귀 |
| **Phase 8** | EXPORT-PDF | PDF 출력 (자체 또는 한컴) | export endpoint | — |
| **Phase 9** | EXPORT-XLSX | XLSX 출력 (Apache POI) | export endpoint | §9 |
| **Phase 10** | MULTI-SESSION | 세션 락, audit log, sha256 게이트 | 보안 게이트 | §15 |

각 Phase 는 ① 시방서 → ② 시공 계획 → ③ 승인 → ④ 시공 → ⑤ 감리 →
⑥ 준공 → ⑦ 회귀 → ⑧ commit 순서 적용 (§11-1).

---

## 18. MVP 부분 준공 기준

### 18-1. MVP-A (최소 가시 가치)

- Phase 0~2 완료
- 단일 HWPX 문서 로딩 → 셀 텍스트 편집 → HWPX 저장 → verify7 PASS
- AI / 외부 drop 미포함

부분 준공 표기 (§11-5):

```
MVP-A 부분 준공 — 셀 텍스트 편집·저장 only.
다음 활성화 트리거: Phase 3 (문단 편집) 착공 승인.
```

### 18-2. MVP-B (일반 사무용)

- Phase 0~5 완료
- 셀·문단·표·이미지 편집 + HWPX 저장
- 자재DB drop, AI confirm 미포함

### 18-3. MVP-C (감리 운영용)

- Phase 0~7 완료
- AI confirm + 자재 drop 포함
- PDF/XLSX export 미포함

### 18-4. v1.0 (정식)

- Phase 0~10 완료
- PDF/XLSX export, multi-session, audit log 게이트 모두 활성

---

## 19. 위험요소와 방어 게이트

| 위험 | 방어 게이트 |
|------|-------------|
| 원본 HWPX 오염 | sha256 사전/사후 게이트 (§15-1), 파일 권한 read-only |
| writer 부분 실패가 PASS 로 위장 | LOCK_01 회로 (`_filter_applied_cells_by_coord`) 적용 강제 |
| AI 자동 확정 | §10 게이트, AIValidationModel pending 강제 |
| 라이선스 사고 | 본 설계 채택 후 core dep 추가 시 별도 §11-1 공정 |
| 한컴 호환 강요 | 1차 목표 아님 명시. self-roundtrip 만 보장 |
| 풀 페이지네이션 픽셀 재현 압박 | layoutGuess 까지가 MVP 라 명시 (§5-1) |
| 다중 협업 요구 | 비목표 명시 (§1-2). 추후 별도 공정 |
| writer 잠금 우회 (`--no-verify` 등) | §6 절대 금지, CI 게이트 유지 |

---

## 20. 본 설계의 위치

본 설계서는 §11-1 ② **시공 계획서** 등급. 실제 시공 (Phase 1 이상) 은
대표님 명시 승인 후 별도 공정으로 착공한다. 본 공정은 설계·감사·문서화
까지만 수행하며 writer 호출·원본 수정·출력 생성을 **하지 않는다.**

다음 공정 후보:

1. 본 설계서 검토 → 수정 의견 반영
2. 오픈소스 후보 선정 (별책 참조)
3. Phase 1 (RO-VIEW) 시방서 작성

---

*생성: HWPX-WEB-OFFICE-EDITOR-DEEP-ARCHITECTURE-01 (2026-05-20)*
