# P11A HWPX Browser Editor Product Focus — 완료 보고서

**날짜:** 2026-05-15  
**상태:** PASS  
**작업:** OFFICE-ANALYSIS-P11A-HWPX-BROWSER-EDITOR-PRODUCT-FOCUS

---

## [작업 내용]

HWPX 브라우저 편집기의 제품 범위, command contract, editor state model, usecase plan을 문서화하고, 자동 검사 스크립트와 테스트를 추가했다.

---

## [제품 범위]

**1차 (MVP) 기능 9개:**
- HWPX 업로드, 문서 구조 보기, 문단 텍스트 편집, 표 셀 편집
- 행 추가/삭제, placeholder 치환, 저장/다운로드
- package validation, roundtrip validation

**2차 (Post-MVP) 기능 6개:**
이미지 교체, 차트 삽입, 스타일 편집, 공정표 builder 연결, 안전서류 builder 연결, Excel 분석 결과 binding

**영구 제외 5개:**
.hwp 직접 브라우저 편집, Hancom 자동 실행, 인증서/OTP/전자서명, 외부 사이트 제출/투찰, 서버 HWP 변환 직접 실행

---

## [Editor 구조]

```
Browser (command 생성만)
  └─→ POST /api/hwpx/editor
        └─→ HwpxEditorApiHandler
              └─→ [P12 신규] HwpxEditorCommandUseCase
                    └─→ HwpxEditorValidationGate (gate, no side effects)
                    └─→ EditPlan JSON 생성
              └─→ hwpx_edit_tool.py (기존, 변경 없음)
              └─→ HwpxDownloadExportUseCase (기존, 변경 없음)
```

외부 인터페이스(endpoint, 응답 구조) 변경 없음.

---

## [Command contract]

| Command | MVP | 설명 |
|---------|-----|------|
| paragraph_edit | ✅ | 문단 텍스트 교체 |
| cell_edit | ✅ | 표 셀 텍스트 교체 |
| row_add | ✅ | 행 추가 |
| row_delete | ✅ | 행 삭제 |
| placeholder_fill | ✅ | 키-값 치환 |
| fill_cells | - | 표 일괄 채우기 (post-processing) |
| schedule_graph | - | 공정표 삽입 (post-processing) |

endpoint: `POST /api/hwpx/editor`  
dry-run 지원: ✅

---

## [State model]

phases: `IDLE → UPLOADED → EDITING → SAVING → DONE / ERROR`

- 브라우저: command 큐(pendingEdits) + artifact ID 참조
- 서버: stateless (세션 DB 기록 없음)
- 브라우저에 raw 파일 경로 보관 금지
- artifact ID(UUID)로만 서버 결과 참조

---

## [Usecase plan]

| Phase | 내용 |
|-------|------|
| P12 | HwpxEditorCommandUseCase + HwpxEditorValidationGate |
| P13 | browser editor UI (업로드→편집→저장) |
| P14 | HwpxEditorSessionUseCase (연속 편집) |
| P15 | Post-MVP (이미지 교체, builder 연결) |

---

## [자동 검사]

- `scripts/audit_hwpx_browser_editor_structure.py` — status=**PASS**, finding_count=0
- `scripts/audit_api_meta_contract.py` — **PASS**
- `scripts/audit_new_code_structure_rules.py` — **PASS**

---

## [Test 상태]

- `pytest tests/test_hwpx_browser_editor_structure.py` — **11/11 PASS**
- `pytest tests/test_api_meta_contract.py` — **9/9 PASS**
- `./gradlew test` — **342 tests, 0 failed**
- secret scan — **0건**

---

## [Git]

커밋 대상: P11A 신규 파일만 (기존 파일 수정 없음)

---

## [다음 단계]

**P12:** `HwpxEditorCommandUseCase` + `HwpxEditorValidationGate` 구현 및 단위 테스트  
**P13:** browser editor UI (정적 HTML/JS, `/hwpx-editor` 확장)

**PASS**
