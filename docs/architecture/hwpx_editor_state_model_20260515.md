# HWPX Editor State Model

**버전:** P11A  
**날짜:** 2026-05-15  
**상태:** CONFIRMED

---

## 1. 개요

브라우저 편집기는 클라이언트 상태(EditorState)와 서버 산출물(ArtifactRef)을 분리하여 관리한다.
브라우저는 HWPX 파일 자체를 보유하지 않고, artifact ID를 통해 서버 결과를 참조한다.

---

## 2. EditorState (브라우저 클라이언트)

```
EditorState {
  phase:        IDLE | UPLOADED | EDITING | SAVING | DONE | ERROR
  filename:     string                    // 업로드된 원본 파일명
  artifactId:   string | null             // 마지막 서버 산출물 UUID
  docStructure: DocStructure | null       // /parse-hwpx 파싱 결과
  pendingEdits: CommandEdit[]             // 미적용 command 목록
  draftReport:  DryRunReport | null       // dry-run 미리보기 결과
  lastError:    ErrorInfo | null
  sessionId:    string                    // 세션 식별자 (브라우저 local)
}
```

### 2.1 Phase 전이

```
IDLE
  → [파일 선택] → UPLOADED

UPLOADED
  → [/parse-hwpx 성공] → EDITING
  → [gate 거부/오류] → ERROR

EDITING
  → [command 추가] → EDITING (pendingEdits 증가)
  → [dry-run 요청] → EDITING (draftReport 갱신)
  → [저장 요청] → SAVING
  → [초기화] → IDLE

SAVING
  → [/api/hwpx/editor 성공] → DONE
  → [오류] → ERROR

DONE
  → [다운로드] → DONE
  → [계속 편집] → EDITING
  → [새 파일] → IDLE

ERROR
  → [재시도] → 이전 phase로 복귀
  → [초기화] → IDLE
```

---

## 3. DocStructure (파싱 결과 모델)

```
DocStructure {
  inputFileName:  string
  inputFileType:  "hwpx"
  paragraphs:     string[]
  blocks:         DocumentBlock[]
  tables:         DocumentTable[]
  fullText:       string
  warningCount:   int
  errorCount:     int
}

DocumentBlock {
  block_index:          int
  block_type:           "paragraph" | "table"
  text:                 string
  table_id_if_applicable: string | null
}

DocumentTable {
  table_id:    string
  row_count:   int
  col_count:   int
  block_index: int
  rows:        DocumentCell[][]
}

DocumentCell {
  text:    string
  row:     int
  col:     int
  rowspan: int
  colspan: int
  covered: boolean
}
```

---

## 4. CommandEdit (편집 의도)

```
CommandEdit {
  id:        string          // 브라우저 로컬 UUID
  type:      CommandType
  target:    CommandTarget
  value:     any
  appliedAt: string | null   // ISO 8601, 서버 적용 후 갱신
}

CommandType = 
  "paragraph_edit" | "cell_edit" | "row_add" | "row_delete" |
  "placeholder_fill" | "fill_cells" | "schedule_graph"

CommandTarget {
  paragraph_index?: int
  table_index?:     int
  row?:             int
  col?:             int
  after_row?:       int
}
```

---

## 5. ArtifactRef (서버 산출물 참조)

```
ArtifactRef {
  artifactId:    string    // UUID, X-Hwpx-Editor-Artifact-Id 헤더
  filename:      string    // Content-Disposition에서 추출
  schemaVersion: string    // X-Schema-Version
  engineVersion: string    // X-Engine-Version
  requestId:     string    // X-Request-Id
  savedRef:      string | null   // X-Hwpx-Editor-Saved-Path (artifact ID)
  reportRef:     string | null   // X-Hwpx-Editor-Saved-Report-Path
  sha256:        string | null   // X-Hwpx-Editor-Saved-Sha256
  timestamp:     string          // ISO 8601
}
```

브라우저는 artifactId만 보유하고 raw 파일 경로는 절대 보유하지 않는다.

---

## 6. DryRunReport (미리보기)

```
DryRunReport {
  status:              "PASS" | "WARN" | "FAIL"
  affected_paragraphs: int[]
  affected_tables:     int[]
  warnings:            string[]
  errors:              string[]
  preview_text:        string | null
}
```

---

## 7. ErrorInfo

```
ErrorInfo {
  code:      string    // GATE_CODE 또는 HTTP status
  message:   string
  requestId: string | null
  timestamp: string
}
```

---

## 8. 세션 정책

- 세션은 브라우저 메모리(또는 sessionStorage)에만 유지
- 서버는 세션 상태를 저장하지 않음 (stateless)
- artifactId를 통한 서버 재다운로드는 서버 아카이브 파일이 있는 경우만 가능
- 브라우저 새로고침 시 IDLE 상태로 복귀 (파일 재업로드 필요)
