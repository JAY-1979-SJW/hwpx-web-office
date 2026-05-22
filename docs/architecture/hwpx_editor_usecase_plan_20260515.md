# HWPX Editor Usecase Plan

**버전:** P11A  
**날짜:** 2026-05-15  
**상태:** CONFIRMED

---

## 1. 구현 우선순위

| 순서 | Usecase | 레이어 | MVP |
|------|---------|--------|-----|
| 1 | HwpxUploadParseUseCase (기존) | usecase | ✅ 완료 |
| 2 | HwpxDownloadExportUseCase (기존) | usecase | ✅ 완료 |
| 3 | HwpxEditorCommandUseCase (신규) | usecase | ✅ P12 |
| 4 | HwpxEditorValidationGate (신규) | gate | ✅ P12 |
| 5 | browser editor UI (신규) | frontend | P13 |
| 6 | HwpxEditorSessionUseCase (신규) | usecase | P14 |
| 7 | 이미지 교체 command | usecase | Post-MVP |
| 8 | 공정표 builder 연결 | usecase | Post-MVP |

---

## 2. HwpxEditorCommandUseCase (P12 신규)

**목적:** 브라우저에서 받은 command 목록을 검증하고, edit plan JSON으로 변환한다.

```
입력:  List<CommandEdit>  (브라우저 command 목록)
출력:  EditPlan           (hwpx_edit_tool.py가 소비하는 plan JSON)
```

**처리 흐름:**
1. `HwpxEditorValidationGate.validate(commands)` — 유효성 검사
2. gate FAIL → UseCase 거부, 400 반환
3. gate PASS/WARN → command → edit plan 변환
4. post-processing 분리: fill_cells, schedule_graph는 main plan에서 분리
5. EditPlan 반환

**변환 규칙:**

| Command type | Edit plan 필드 |
|-------------|----------------|
| paragraph_edit | edits[].type="paragraph_edit", target.paragraph_index, value |
| cell_edit | edits[].type="cell_edit", target.{table_index, row, col}, value |
| row_add | edits[].type="row_add", target.{table_index, after_row}, template_row |
| row_delete | edits[].type="row_delete", target.{table_index, row} |
| placeholder_fill | edits[].type="placeholder_fill", mapping |
| fill_cells | plan.fill_cells (post-processing) |
| schedule_graph | plan.schedule_graph (post-processing) |

---

## 3. HwpxEditorValidationGate (P12 신규)

**목적:** command 목록의 유효성을 검사한다. side effect 없음.

```java
// 예시 구조
record HwpxEditorValidationResult(
    boolean allowed,
    String code,
    String message,
    Severity severity,
    List<String> invalidCommands
) {}
```

**검증 규칙:**

| 규칙 | 코드 | Severity |
|------|------|----------|
| commands 빈 목록 | EMPTY_COMMAND_LIST | FAIL |
| 알 수 없는 command type | UNKNOWN_COMMAND_TYPE | FAIL |
| paragraph_index < 0 | INVALID_PARAGRAPH_INDEX | FAIL |
| table_index < 0 | INVALID_TABLE_INDEX | FAIL |
| row < 0 또는 col < 0 | INVALID_CELL_COORDINATE | FAIL |
| value 필드 누락 (필수인 경우) | MISSING_VALUE | FAIL |
| placeholder mapping 빈 객체 | EMPTY_MAPPING | WARN |
| fill_cells rows 빈 배열 | EMPTY_ROWS | WARN |
| command 개수 > 500 | TOO_MANY_COMMANDS | WARN |
| 파일시스템 경로 포함 | FORBIDDEN_PATH_IN_COMMAND | FAIL |
| HWP 실행 지시 포함 | FORBIDDEN_HWP_EXEC | FAIL |

---

## 4. HwpxEditorSessionUseCase (P14 신규)

**목적:** 편집 세션의 의미적 연속성 관리 (artifact chain).

```
입력:  previousArtifactId (optional), CommandEdit[]
출력:  세션 컨텍스트 포함 EditPlan
```

**핵심 동작:**
- 이전 artifact ID 기반 연속 편집 지원
- 서버 아카이브 파일 존재 여부 확인 (파일 없으면 재업로드 요구)
- 세션 내 누적 command 이력 관리 (서버 메모리, 재시작 시 초기화)

**서버 stateless 원칙:** 세션 상태는 서버 메모리에만 보관, DB 기록 금지

---

## 5. browser editor UI (P13)

**현재 존재:** `GET /hwpx-editor` → `HwpxUploadHandler` → 정적 HTML 반환

**확장 계획:**

| 컴포넌트 | 기술 | 설명 |
|---------|------|------|
| 업로드 패널 | HTML form | 파일 선택 + /parse-hwpx 호출 |
| 문서 트리 뷰 | vanilla JS | blocks/tables 렌더링 |
| 편집 패널 | vanilla JS | 선택 블록 인라인 편집 |
| command 큐 뷰 | vanilla JS | pendingEdits 목록 표시 |
| dry-run 패널 | vanilla JS | 미리보기 결과 표시 |
| 저장/다운로드 버튼 | HTML | /api/hwpx/editor 호출 |

**기술 제약:**
- 외부 CDN 라이브러리 최소화
- HWPX binary blob 브라우저 내 보관 금지
- 상태는 JS 메모리 또는 sessionStorage

---

## 6. 기존 Handler 활용 계획

현재 `HwpxEditorApiHandler`가 edit plan을 직접 받아 처리한다.
P12에서 `HwpxEditorCommandUseCase`를 handler와 Python 실행 사이에 삽입한다.

```
Before (현재):
  Browser → HwpxEditorApiHandler → hwpx_edit_tool.py

After (P12 목표):
  Browser → HwpxEditorApiHandler
              → HwpxEditorCommandUseCase
                  → HwpxEditorValidationGate
                  → EditPlan 생성
              → hwpx_edit_tool.py
```

HwpxEditorApiHandler의 외부 인터페이스(endpoint, 응답 구조)는 변경하지 않는다.

---

## 7. 구현 순서 확정

```
P12: HwpxEditorCommandUseCase + HwpxEditorValidationGate + 단위 테스트
P13: browser editor UI (업로드 + 구조 보기 + 문단/셀 편집 + 저장)
P14: HwpxEditorSessionUseCase (연속 편집 세션)
P15: Post-MVP (이미지 교체, builder 연결)
```
