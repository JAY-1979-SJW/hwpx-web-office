# P12B Report: HWPX Editor UI Standard Lock

**날짜:** 2026-05-15  
**단계:** P12B  
**상태:** PASS

---

## 결과 요약

| 항목 | 결과 |
|------|------|
| audit_ui_design_system | PASS (finding 0) |
| test_ui_design_system (15 tests) | 15/15 PASS |
| audit_hwpx_browser_editor_structure | PASS (finding 0) |
| audit_api_meta_contract | PASS (finding 0) |
| ./gradlew test | BUILD SUCCESSFUL |

---

## 생성된 문서

| 파일 | 설명 |
|------|------|
| docs/architecture/ui_design_system_20260515.md | 브랜드 컬러, 타이포그래피, 스페이싱, 컴포넌트 기본 스타일 |
| docs/architecture/ui_design_system_20260515.json | 위 문서 JSON 버전 |
| docs/architecture/hwpx_editor_ui_layout_20260515.md | 전체 페이지 레이아웃 (ASCII + 컴포넌트 배치) |
| docs/architecture/hwpx_editor_ui_layout_20260515.json | 위 문서 JSON 버전 |
| docs/architecture/ui_component_rules_20260515.md | 17개 컴포넌트 규칙 (역할, 입력, 금지 사항) |
| docs/architecture/ui_component_rules_20260515.json | 위 문서 JSON 버전 |
| docs/architecture/hwpx_editor_ui_state_policy_20260515.md | 11개 UI phase 정의, 전이 다이어그램, 버튼 활성 조건 |
| docs/architecture/hwpx_editor_ui_state_policy_20260515.json | 위 문서 JSON 버전 |

---

## 브랜드 컬러 고정 값

| 토큰 | 값 | 용도 |
|------|----|------|
| primary | #F97316 | 버튼, 강조, top accent |
| primary-hover | #EA580C | hover |
| primary-soft | #FFF7ED | 배경 tint, drag-over |
| navy | #0F172A | HeaderBar 배경 |
| navy-secondary | #1E293B | 카드 배경 dark |
| navy-soft | #F1F5F9 | 사이드바 배경 |
| bg | #F5F7FA | 페이지 배경 |
| text-primary | #111827 | 본문 |
| text-secondary | #4B5563 | 보조 텍스트 |
| text-muted | #6B7280 | placeholder |
| border | #E5E7EB | divider |

---

## Top Accent Line

- 위치: 모든 페이지 최상단 fixed
- 높이: 4px
- 색상: #F97316
- CSS: `height:4px; background:#F97316; position:fixed; top:0; width:100%; z-index:1000`
- **제거/변경/숨김 금지**

---

## UI Phase 목록 (11개)

`IDLE → UPLOADING → UPLOADED → PARSING → READY → EDITING → VALIDATING → DRY_RUN → SAVING → EXPORTED → ERROR`

---

## 정책 고정 사항

- `artifactId`: UUID, 브라우저에서 앞 8자만 표시
- `raw_path`: 브라우저에서 절대 표시 금지
- `XML/ZIP`: 브라우저 직접 접근 금지
- `command`: READY/EDITING phase 이상에서만 dispatch
- `endpoint path`: 변경 금지
- `API response key`: 삭제/이름 변경 금지
- `push`: 금지
- `DB write`: 금지

---

## 다음 단계

**P13:** 브라우저 editor UI 명령 dispatch 구현  
- HwpxEditorCommandUseCase 실제 연결  
- 위 UI 표준을 Java HTML/CSS 생성 코드에 반영  
- TopAccentLine #F97316, HeaderBar navy #0F172A 적용
