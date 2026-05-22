# HWPX Editor UI Layout Standard

**버전:** P12B  
**날짜:** 2026-05-15  
**상태:** CONFIRMED

---

## 1. 전체 레이아웃 구조

```
┌─────────────────────────────────────────────────────────────────┐
│ [Top Accent Line — 4px #F97316]                                 │
├─────────────────────────────────────────────────────────────────┤
│ [Header Bar]                                                    │
│  제품명  |  문서 상태 badge  |  artifactId  |  engineVersion    │
├──────────────────────┬──────────────────────────────────────────┤
│ [Left Sidebar]       │ [Main Editor Area]                       │
│                      │                                          │
│  UploadCard          │  [Tab Bar]                               │
│  GateStatusPanel     │   Paragraphs | Tables | Preview          │
│                      │                                          │
│  EditorToolbar       │  [DocumentTree / BlockList]              │
│   · validate         │                                          │
│   · dry-run          │  [Selected Block Editor]                 │
│   · save             │                                          │
│   · download         │  [ValidationPanel]                       │
│                      │                                          │
│  PlaceholderPanel    │  [CommandResultPanel]                    │
│  TableCellEditor     │                                          │
│  BlockInspector      ├──────────────────────────────────────────┤
│                      │ [Bottom Status Bar]                      │
│  ArtifactInfoPanel   │  last artifact · engine/schema version   │
│  DownloadPanel       │  warnings · errors · save status         │
└──────────────────────┴──────────────────────────────────────────┘
```

---

## 2. Top Accent Line

- 높이: 4px
- 색상: `#F97316`
- 위치: 모든 화면 최상단 fixed
- 모든 페이지(HWPX 편집기, Excel 분석, 내역서 분석, 공정표, 안전서류)에 공통 적용

---

## 3. Header Bar

- 배경: `#0F172A` (navy)
- 텍스트: white
- 높이: 44px
- 구성:
  - 왼쪽: 제품 로고/이름 (font-size: 15px, font-weight: 600)
  - 중앙: 현재 문서명 + 상태 badge (StatusBadge)
  - 오른쪽: `artifactId` (앞 8자 + "…" 표시) + `engineVersion`
- 금지: raw filesystem path, secret, internal server path

---

## 4. Upload Panel (UploadCard)

- 위치: 좌측 사이드바 상단
- 파일 드래그/드롭 + 클릭 업로드
- 허용 타입 배지: `.hwpx` (PASS), `.hwp` (LOCAL_WORKER_REQUIRED)
- 게이트 결과: GateStatusPanel으로 표시
- 오류: ErrorBoundaryPanel로 표시
- 최대 파일 크기 표시: 80MB
- 금지: ZIP 내부 파일 업로드 선택 UI

---

## 5. Editor Toolbar

- 위치: 좌측 사이드바 (UploadCard 하단)
- 버튼 구성:

| 버튼 | 조건 | 설명 |
|------|------|------|
| Validate | READY 이상 | validateDocument command 전송 |
| Dry Run | READY 이상 | dry-run preview 요청 |
| Save | EDITING 이상 | 서버 저장 + artifact 생성 |
| Download | SAVED/EXPORTED | artifact 다운로드 |

- 버튼: primary (Save), secondary (나머지)
- 비활성 state: disabled 스타일 + cursor-not-allowed
- Loading state: spinner + 텍스트 변경 (e.g. "저장 중…")

---

## 6. Main Editor Area

### 6.1 Tab Bar
- Paragraphs | Tables | Preview
- 활성 탭: `border-bottom: 2px solid #F97316`, `color: #F97316`

### 6.2 Document Tree / Block List
- 좌측 정렬, 스크롤 가능
- Block item: `paragraph_index` 또는 `table_index` 표시
- 선택: `background: #FFF7ED`, `border-left: 3px solid #F97316`
- block_type에 따른 아이콘: ¶ (paragraph), ⊞ (table)

### 6.3 Selected Block Editor
- 선택된 block의 텍스트 인라인 편집 textarea
- 현재 값 표시 + 수정
- Command dispatch: "Apply" 버튼 클릭 시 command 생성 → 서버 전송
- 금지: HWPX XML 직접 노출, ZIP entry path 표시

### 6.4 Table Cell Editor (Tables 탭)
- 표 선택기 (table_index)
- 셀 클릭 → inline edit
- 행 추가/삭제 버튼 (row + / row -)
- 선택된 셀 highlight: `outline: 2px solid #F97316`

---

## 7. Right Inspector Panel (좌측 사이드바 하단부)

- BlockInspector: 선택된 block의 속성 (paragraph_index, block_type, text 요약)
- PlaceholderPanel: `{{키}}` 목록 + 입력 필드
- TableCellEditor: 셀 좌표 + 편집 필드
- Command form 제출: primary 버튼

---

## 8. ValidationPanel

- 위치: Main Editor Area 하단 또는 별도 탭
- 구성:
  - validation 상태 badge (PASS/WARN/FAIL)
  - warnings 목록 (yellow card)
  - errors 목록 (red card)
  - affected_paragraphs, affected_tables 수
- dry-run 결과 표시 가능

---

## 9. CommandResultPanel

- 위치: Main Editor Area 하단
- 구성:
  - commandType 표시
  - status badge
  - applied: true/false
  - dryRun: true/false
  - warnings/errors 목록
  - requestId (앞 8자)
- 금지: raw path, secret, internal error stack trace

---

## 10. Bottom Status Bar

- 배경: `#F9FAFB`, border-top: `1px solid #E5E7EB`
- 구성:
  - 왼쪽: 마지막 저장 artifact (ID 앞 8자 + 저장 시간)
  - 중앙: warning count, error count badge
  - 오른쪽: `schemaVersion` + `engineVersion`

---

## 11. Download/Export Panel (ArtifactInfoPanel + DownloadPanel)

- artifactId 표시 (앞 8자 + "…")
- 파일명 표시 (safeFilename)
- 저장 상태 badge (SAVED / EXPORTED)
- 다운로드 버튼 (primary)
- 금지:
  - raw filesystem path 표시
  - 서버 절대 경로 표시
  - ZIP/XML entry path 표시

---

## 12. 에러 처리

- gate 거부: GateStatusPanel (yellow WARN 또는 red FAIL card)
- parse 오류: ErrorBoundaryPanel (red)
- network 오류: toast 메시지 (3초 자동 소멸)
- validation FAIL: ValidationPanel (red card)
- 금지: stack trace 직접 표시, internal server error 상세 노출

---

## 13. 원칙 요약

| 원칙 | 내용 |
|------|------|
| 브라우저 역할 | command 생성 + 결과 표시만 |
| raw path 표시 | 금지 |
| XML/ZIP 노출 | 금지 |
| artifactId | 앞 8자 표시 허용 |
| secret/session | 금지 |
| 게이트 결과 | badge/card로 표시 |
| endpoint path | 변경 금지 |
