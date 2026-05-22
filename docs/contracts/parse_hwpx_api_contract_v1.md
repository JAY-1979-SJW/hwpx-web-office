# /parse-hwpx API Contract v1.0

**문서 버전**: 1.0  
**작성일**: 2026-05-07  
**상태**: FROZEN  
**기준 커밋**: a2c584d (HWPX reader validation), d3f6b2e (runtime packaging)

---

## 1. 엔드포인트 정의

### 요청

```
Method: POST
Path: /parse-hwpx
Content-Type: application/octet-stream
Body: Binary HWPX file (ZIP-based XML format)
```

### 요청 헤더

| 헤더 | 필수 | 예시 |
|------|------|------|
| Content-Type | ✓ | `application/octet-stream` |
| Content-Disposition | ✗ | `attachment; filename="document.hwpx"` |

---

## 2. 성공 응답 (HTTP 200)

### 응답 헤더
```
Content-Type: application/json; charset=UTF-8
```

### 응답 본문 - 필수 키 (Top-level)

| 키 | 타입 | 필수 | 설명 |
|----|------|------|------|
| `schemaVersion` | string | ✓ | API 응답 스키마 버전 (현재: "1.0") |
| `engineVersion` | string | ✓ | 파서 엔진 버전 (현재: "1.0.0") |
| `requestId` | string | ✓ | UUID 형식의 요청 추적 ID |
| `inputFileName` | string | ✓ | 업로드된 파일명 (또는 생성된 임시명) |
| `inputFileType` | string | ✓ | 파일 타입 (항상: "hwpx") |
| `parsedAt` | string | ✓ | ISO 8601 timestamp (파싱 완료 시각) |
| `fullText` | string | ✓ | 문서 전체 텍스트 (누적) |
| `paragraphs` | array | ✓ | 문단 텍스트 배열 (순서 보존) |
| `blocks` | array | ✓ | 문서 블록 배열 (순서 보존) |
| `tables` | array | ✓ | 추출된 테이블 배열 |
| `warningCount` | integer | ✓ | 경고 개수 |
| `errorCount` | integer | ✓ | 오류 개수 |
| `warnings` | array | ✓ | 경고 메시지 배열 |
| `errors` | array | ✓ | 오류 메시지 배열 |
| `ok` | boolean | ✓ | 파싱 성공 여부 (true=성공, false=부분실패) |

### 응답 본문 - DocumentBlock 구조

```json
{
  "block_index": 0,
  "block_type": "paragraph|table",
  "text": "블록 텍스트 또는 'table_id=...'",
  "table_id_if_applicable": "table_0" // table 블록인 경우만 존재
}
```

| 키 | 타입 | 필수 | 설명 |
|----|------|------|------|
| `block_index` | integer | ✓ | 블록 순서 (0부터 시작) |
| `block_type` | string | ✓ | "paragraph" 또는 "table" |
| `text` | string | ✓ | paragraph: 본문, table: "table_id=table_0" |
| `table_id_if_applicable` | string | ✗ | table 블록인 경우만 테이블 ID |

### 응답 본문 - DocumentTable 구조

```json
{
  "table_id": "table_0",
  "row_count": 2,
  "col_count": 3,
  "source": "hwpx-xml",
  "block_index": 1,
  "rows": [ /* 2D array of DocumentCell */ ]
}
```

| 키 | 타입 | 필수 | 설명 |
|----|------|------|------|
| `table_id` | string | ✓ | 테이블 식별자 (table_0, table_1, ...) |
| `row_count` | integer | ✓ | 행 개수 |
| `col_count` | integer | ✓ | 열 개수 |
| `source` | string | ✓ | 추출 소스 (항상: "hwpx-xml") |
| `block_index` | integer | ✓ | blocks[] 배열에서의 위치 |
| `rows` | array | ✓ | 2D 배열: `List<List<DocumentCell>>` |

### 응답 본문 - DocumentCell 구조

```json
{
  "text": "셀 텍스트",
  "row": 0,
  "col": 1,
  "rowspan": 1,
  "colspan": 2,
  "is_header": false
}
```

| 키 | 타입 | 필수 | 설명 |
|----|------|------|------|
| `text` | string | ✓ | 셀 내용 텍스트 |
| `row` | integer | ✓ | 0 기반 행 인덱스 |
| `col` | integer | ✓ | 0 기반 열 인덱스 |
| `rowspan` | integer | ✓ | 행 병합 수 (기본: 1) |
| `colspan` | integer | ✓ | 열 병합 수 (기본: 1) |
| `is_header` | boolean | ✓ | 헤더 셀 여부 (기본: false) |

### 성공 응답 예시

```json
{
  "schemaVersion": "1.0",
  "engineVersion": "1.0.0",
  "requestId": "e8df2dfe-19b9-419c-8184-b954fce75523",
  "inputFileName": "document.hwpx",
  "inputFileType": "hwpx",
  "parsedAt": "2026-05-07T06:36:07.619020Z",
  "fullText": "문단 1\n문단 2",
  "paragraphs": ["문단 1", "문단 2"],
  "blocks": [
    {
      "block_index": 0,
      "block_type": "paragraph",
      "text": "문단 1"
    },
    {
      "block_index": 1,
      "block_type": "table",
      "text": "table_id=table_0",
      "table_id_if_applicable": "table_0"
    }
  ],
  "tables": [
    {
      "table_id": "table_0",
      "row_count": 2,
      "col_count": 2,
      "source": "hwpx-xml",
      "block_index": 1,
      "rows": [
        [
          {
            "text": "헤더1",
            "row": 0,
            "col": 0,
            "rowspan": 1,
            "colspan": 1,
            "is_header": false
          },
          {
            "text": "헤더2",
            "row": 0,
            "col": 1,
            "rowspan": 1,
            "colspan": 1,
            "is_header": false
          }
        ]
      ]
    }
  ],
  "warningCount": 0,
  "errorCount": 0,
  "warnings": [],
  "errors": [],
  "ok": true
}
```

---

## 3. 오류 응답

### HTTP 405 (Method Not Allowed)

```
GET /parse-hwpx → 405 Method Not Allowed
```

응답:
```json
{
  "error": "메서드 허용 안 함"
}
```

### HTTP 400 (Bad Request - Invalid HWPX)

입력 파일이 유효하지 않은 HWPX일 경우:

```json
{
  "schemaVersion": "1.0",
  "engineVersion": "1.0.0",
  "requestId": "...",
  "inputFileName": "...",
  "inputFileType": "hwpx",
  "parsedAt": "2026-05-07T...",
  "fullText": "",
  "paragraphs": [],
  "blocks": [],
  "tables": [],
  "warningCount": 1,
  "errorCount": 1,
  "warnings": ["Invalid ZIP structure"],
  "errors": ["File is not a valid HWPX (invalid ZIP)"],
  "ok": false
}
```

| 상황 | HTTP Code | ok 값 | 예시 |
|------|-----------|-------|------|
| 파일 없음 | 400 | false | errorCount=1, errors=["File not found"] |
| 유효하지 않은 ZIP | 400 | false | errorCount=1, errors=["File is not a valid HWPX"] |
| MIME type 무효 | 400 | false | errorCount=1, errors=["Invalid MIME type"] |

### HTTP 500 (Server Error)

```json
{
  "error": "서버 오류: <exception message>"
}
```

---

## 4. 버전 정책

### schemaVersion

응답 스키마 형식의 주요 버전. 다음 경우 증가:
- Top-level 필수 키 추가/제거
- DocumentBlock, DocumentTable, DocumentCell의 필수 키 변경
- 데이터 타입 변경

**현재**: "1.0" (고정)

### engineVersion

파서 엔진의 버전. 다음 경우 증가:
- 파싱 로직 개선
- 새 기능 추가
- 버그 수정

**현재**: "1.0.0" (고정)

---

## 5. requestId 정책

- UUID v4 형식 (36글자, 하이픈 포함)
- 모든 요청마다 새로운 값 생성
- 응답에 포함되어 로깅/추적용으로 사용
- 클라이언트는 이 ID를 로그에 기록하여 요청 추적

---

## 6. 순서 보존 보장

### blocks[] 배열
- 문서 원본의 블록 순서 그대로 보존
- 예: [paragraph, table, paragraph] → blocks[0]=paragraph, blocks[1]=table, blocks[2]=paragraph
- 모든 table 블록은 blocks[]에도 참조되고 tables[]에도 데이터 포함

### rows[] 배열 (테이블 내)
- 테이블 행의 순서 그대로 보존
- rows[0] = 첫 번째 행

### 각 행의 셀 순서
- 각 행 내 셀의 순서 보존
- rows[0][0], rows[0][1], ... = 첫 번째 행의 좌에서 우 순서

---

## 7. Known Limitations

| 제약 | 설명 | 계획 |
|-----|------|------|
| rowspan | 기본값 1 (HWPX spec 미정의) | P2에서 개선 |
| colspan | gridSpan attribute 지원 | ✓ 현재 지원 |
| 셀 높이/너비 | 픽셀/포인트 정보 미추출 | P2에서 검토 |
| 셀 배경색 | 추출되지 않음 | P2에서 검토 |
| 셀 정렬 | 추출되지 않음 | P2에서 검토 |
| 중첩 테이블 | 미지원 | P2 이후 |
| 다중 섹션 | 모두 fullText에 누적 | ✓ 현재 지원 |

---

## 8. 다른 앱 호출 제약

### 금지 사항

다음 앱의 경계를 침범하지 않는다:
- **price-classifier**: API 호출 금지 (분리된 마이크로서비스)
- **g2b-data-collector**: 데이터 공유 금지 (별도 workflow)
- **hancom-worker**: 로컬 워커 재호출 금지

### 허용 사항

다른 앱에서 호출 시:
- `POST /parse-hwpx`로 HWPX 파일 업로드
- 응답 JSON 전체 사용 가능
- 응답의 blocks[], tables[], fullText 활용 가능
- requestId를 로그에 기록하여 추적

### 호출 예시

```bash
curl -X POST \
  -H "Content-Type: application/octet-stream" \
  --data-binary @document.hwpx \
  http://localhost:8080/parse-hwpx
```

---

## 9. 문자 인코딩

- 요청: 바이너리 (ZIP)
- 응답: UTF-8
- 모든 텍스트 필드는 UTF-8로 인코딩
- 한글/중일문 지원

---

## 10. 지연 시간 예상

| 파일 크기 | 예상 시간 |
|-----------|----------|
| < 100KB | < 100ms |
| 100KB ~ 1MB | 100ms ~ 500ms |
| 1MB ~ 10MB | 500ms ~ 2s |
| \> 10MB | 2s 이상 |

---

## 11. 보안

### 파일 검증
- MIME type 검증: `application/hwp+zip` (Hancom Office HWPX) 또는 `application/vnd.hancom.hwpml` (대체 포맷)
- ZIP 구조 검증
- 최대 파일 크기: 50MB (하드 제한 없음, 현재 테스트됨)

### 임시 파일
- 파싱 후 자동 삭제
- /tmp 또는 OS 임시 디렉터리 사용
- 파일명 자동 생성 (사용자 입력 검증)

### 입력 검증
- Content-Type: application/octet-stream 필수
- 바이너리 데이터만 허용 (다른 형식 거부)

---

## 12. 체인지로그

### v1.0 (2026-05-07, FROZEN)

**확정 사항**:
- POST /parse-hwpx endpoint 확정
- 응답 스키마 v1.0 확정
- 성공/오류 응답 필수 키 확정
- blocks[] 순서 보존 확정
- tables[] row/col 구조 확정
- requestId UUID 추적 확정

**다음 버전 (v2.0) 검토 대상**:
- schemaVersion 변경 시 v2.0 (현재는 v1.0 고정)
- engineVersion 범위 (1.0.x = minor fix, 2.0.0 = feature)
- 추가 메타데이터 필드
- 대용량 파일 처리 (streaming 옵션)

---

## 13. 참고

- 구현: `src/main/java/com/haehan/engine/parser/HwpxParser.java`
- HTTP 핸들러: `src/main/java/com/haehan/engine/http/ParseHwpxHandler.java`
- 응답 계약: `src/main/java/com/haehan/engine/contract/DocumentParseResponse.java`
- 테스트: `src/test/java/com/haehan/engine/http/ParseHwpxHandlerTest.java`
