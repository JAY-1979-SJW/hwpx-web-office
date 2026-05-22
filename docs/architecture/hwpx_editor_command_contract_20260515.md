# HWPX Editor Command Contract

**버전:** P11A  
**날짜:** 2026-05-15  
**상태:** CONFIRMED

---

## 1. 개요

브라우저는 편집 의도를 **command 객체**로 표현하여 서버에 전송한다.
서버는 command를 수신하여 edit plan으로 변환하고, HWPX 수정을 실행한다.

---

## 2. Command 전송 방식

```
POST /api/hwpx/editor
Content-Type: multipart/form-data

parts:
  - file: <hwpx binary>       (operation=apply 시 필수)
  - plan: <JSON string>        (edit plan JSON)
  - [assets]: <image binary>   (이미지 삽입 시)
```

---

## 3. Command 유형 및 스키마

### 3.1 paragraph_edit — 문단 텍스트 편집

```json
{
  "operation": "apply",
  "edits": [
    {
      "type": "paragraph_edit",
      "target": {
        "paragraph_index": 0
      },
      "value": "수정할 텍스트"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `paragraph_index` | int (≥0) | 0-based 단락 인덱스 |
| `value` | string | 교체할 텍스트 |

---

### 3.2 cell_edit — 표 셀 텍스트 편집

```json
{
  "operation": "apply",
  "edits": [
    {
      "type": "cell_edit",
      "target": {
        "table_index": 0,
        "row": 1,
        "col": 2
      },
      "value": "셀 텍스트"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `table_index` | int (≥0) | 문서 내 표 순서 |
| `row` | int (≥0) | 0-based 행 인덱스 |
| `col` | int (≥0) | 0-based 열 인덱스 |
| `value` | string | 교체할 텍스트 |

---

### 3.3 row_add — 행 추가

```json
{
  "operation": "apply",
  "edits": [
    {
      "type": "row_add",
      "target": {
        "table_index": 0,
        "after_row": 2
      },
      "template_row": 1
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `after_row` | int (≥0) | 이 행 다음에 삽입 |
| `template_row` | int (≥0, 선택) | 복사 기준 행 |

---

### 3.4 row_delete — 행 삭제

```json
{
  "operation": "apply",
  "edits": [
    {
      "type": "row_delete",
      "target": {
        "table_index": 0,
        "row": 3
      }
    }
  ]
}
```

---

### 3.5 placeholder_fill — placeholder 치환

```json
{
  "operation": "apply",
  "edits": [
    {
      "type": "placeholder_fill",
      "mapping": {
        "{{공사명}}": "도로 확포장 공사",
        "{{발주처}}": "○○시청",
        "{{날짜}}": "2026-05-15"
      }
    }
  ]
}
```

---

### 3.6 fill_cells — 표 데이터 일괄 채우기 (post-processing)

```json
{
  "operation": "apply",
  "fill_cells": {
    "table_index": 0,
    "rows": [
      ["항목1", "규격1", "1", "1000", "1000"],
      ["항목2", "규격2", "2", "2000", "4000"]
    ]
  }
}
```

---

### 3.7 schedule_graph — 공정표 삽입 (post-processing)

```json
{
  "operation": "apply",
  "schedule_graph": {
    "insert_after_paragraph": 5,
    "gantt_data": [...]
  }
}
```

---

## 4. 공통 응답 계약

### 4.1 성공 응답 (binary download)

```
HTTP 200
Content-Type: application/owpml
Content-Disposition: attachment; filename="<safe_filename>.hwpx"
X-Hwpx-Editor-Status: PASS
X-Hwpx-Editor-Report: <base64>
X-Hwpx-Editor-Artifact-Id: <UUID>
X-Schema-Version: 1.0
X-Engine-Version: 0.6.2
X-Request-Id: <UUID>

<body: HWPX binary>
```

### 4.2 dry-run 응답 (JSON preview)

```json
{
  "status": "PASS",
  "dry_run": true,
  "preview": {
    "affected_paragraphs": [...],
    "affected_tables": [...],
    "warnings": []
  }
}
```

### 4.3 오류 응답

```json
{
  "error": "<message>",
  "code": "<GATE_CODE>",
  "requestId": "<UUID>"
}
```

| HTTP 코드 | 원인 |
|-----------|------|
| 400 | plan 누락, 파일 누락, unknown operation |
| 413 | 파일 크기 초과 (>80MB) |
| 415 | 파일 타입 거부 (.hwp 등) |
| 422 | HWPX_EDIT_FAILED (Python 실행 실패) |
| 500 | 서버 내부 오류 |

---

## 5. Dry-run 모드

`plan.dry_run: true` 또는 `X-Dry-Run: true` 헤더로 활성화.
HWPX 파일을 수정하지 않고 편집 결과 미리보기만 반환한다.

---

## 6. 서버 저장 모드

`plan.server_save: true` 또는 `plan.archive: true` 시 서버에 결과 파일 보존.
저장 경로는 응답 헤더로만 전달 (raw path 금지, artifact ID 사용).

---

## 7. 금지 사항

- 브라우저에서 HWPX ZIP/XML 직접 조작 금지
- command에 파일시스템 경로 포함 금지
- command에 HWP 직접 실행 지시 금지
- command에 인증서/OTP/서명 관련 필드 금지
