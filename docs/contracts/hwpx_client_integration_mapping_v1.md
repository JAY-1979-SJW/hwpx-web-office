# HWPX 클라이언트 API 연동 규격 v1.0

## 1. 엔드포인트

```
POST /parse-hwpx
```

## 2. 요청 형식

**Method**: POST  
**Content-Type**: `application/octet-stream`  
**Body**: HWPX 파일 바이너리 데이터

### 예시 (curl)
```bash
curl -X POST \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@document.hwpx" \
  http://127.0.0.1:8080/parse-hwpx
```

## 3. 응답 형식

**Status Code**: 200 (성공) 또는 400/500 (오류)  
**Content-Type**: `application/json; charset=UTF-8`

### 필수 응답 스키마

```json
{
  "ok": boolean,
  "schemaVersion": "1.0",
  "engineVersion": "1.0.0",
  "requestId": "UUID string",
  "inputFileType": "hwpx",
  "fullText": "string",
  "paragraphs": [
    {
      "index": number,
      "text": "string"
    }
  ],
  "blocks": [
    {
      "index": number,
      "type": "paragraph|table|image|...",
      "text": "string"
    }
  ],
  "tables": [
    {
      "index": number,
      "rows": number,
      "cols": number,
      "cells": [
        {
          "row": number,
          "col": number,
          "text": "string"
        }
      ]
    }
  ],
  "warnings": ["string"],
  "errors": ["string"]
}
```

## 4. 필수 응답 키 (Smoke Test 검증)

모든 다음 키는 응답에 **반드시** 존재해야 합니다:

| Key | Type | 예시값 | 설명 |
|-----|------|--------|------|
| `ok` | boolean | `true` | 파싱 성공 여부 |
| `schemaVersion` | string | `"1.0"` | 응답 스키마 버전 (변경 금지) |
| `engineVersion` | string | `"1.0.0"` | 엔진 버전 |
| `requestId` | string | UUID | 요청 고유 식별자 |
| `inputFileType` | string | `"hwpx"` | 입력 파일 타입 |
| `fullText` | string | 전체 텍스트 | 문서 전체 텍스트 (길이 > 0) |
| `paragraphs` | array | `[]` | 문단 배열 |
| `blocks` | array | `[]` | 콘텐츠 블록 배열 |
| `tables` | array | `[]` | 표 배열 |
| `warnings` | array | `[]` | 경고 메시지 배열 |
| `errors` | array | `[]` | 오류 메시지 배열 |

## 5. 앱 화면 표시 권장 필드

### 주요 정보
- **fullText**: 문서 전체 텍스트 (검색, 미리보기)
- **paragraphs**: 구조화된 문단 (문단별 표시)
- **blocks**: 콘텐츠 블록 (레이아웃 유지)

### 보조 정보
- **requestId**: 디버깅 및 로그 추적용
- **engineVersion**: 처리된 엔진 버전 정보
- **warnings**: 사용자에게 알림 (파싱 주의사항)

### 숨김 정보
- **schemaVersion**: 내부 버전 관리
- **inputFileType**: 내부 타입 정보

## 6. 저장 가능 필드

**저장 가능** (비민감):
- `fullText`
- `paragraphs[].text`
- `blocks[].text`
- `tables[].cells[].text`
- `engineVersion`
- `requestId`

**저장 불가** (민감 또는 임시):
- `warnings`: 파싱 과정의 임시 정보
- `errors`: 오류 메시지 (민감할 수 있음)

**이미지 콘텐츠 (P2):**
- `blocks[].image` (현재 구현 안 됨)

## 7. 저장 금지 필드

다음은 저장하면 안 되는 필드입니다:

- **`warnings`**: 파싱 과정의 일회성 메시지 → 저장 시 이후 엔진 버전과 불일치 가능
- **`errors`**: 개인 정보 또는 시스템 경로 포함 가능성 → 저장 금지
- API 요청의 원본 바이너리 (`.hwpx` 파일)

## 8. 실패 시 사용자 메시지

| Error Type | HTTP Status | 사용자 메시지 | 권장 조치 |
|------------|-------------|-------------|---------|
| `ok=false` | 400 | "문서 파싱에 실패했습니다. 파일을 다시 확인하세요." | 파일 재업로드 |
| `PARSE_HTTP_FAIL` | 500 | "서버 오류가 발생했습니다." | 잠시 후 재시도 |
| `ENGINE_NOT_RUNNING` | 503 | "서비스가 일시적으로 사용 불가합니다." | 잠시 후 재시도 |
| `CONTRACT_KEY_MISSING` | 500 | "파싱 응답 형식이 잘못되었습니다." | 관리자 문의 |
| `EMPTY_TEXT` | 400 | "문서에서 텍스트를 추출할 수 없습니다." | 다른 파일 시도 |
| `TIMEOUT` | 504 | "파싱에 너무 오래 걸렸습니다." | 더 작은 파일 시도 |

## 9. TABLE_NOT_VERIFIED 제한 사항

현재 엔진 상태: **TABLE_NOT_VERIFIED**

### 표 처리 제한:
- `tables[].cells[].rowspan` 미구현 → 병합 셀 표시 불가
- `tables[].cells[].colspan` 미구현 → 병합 셀 표시 불가
- `tables[].cells[].style` 미구현 → 셀 스타일 표시 불가

### 클라이언트 권장:
1. `tables` 배열은 **데이터 저장용도로만 사용** (화면 렌더링 제외)
2. 표 렌더링이 필요하면 HTML 또는 간단한 텍스트 표로 대체
3. P2 단계에서 표 처리 개선 예정

## 10. 성공 판단 기준

다음 조건을 **모두** 만족하면 성공:

✓ HTTP 200 OK  
✓ JSON 응답 파싱 가능  
✓ `ok = true`  
✓ `schemaVersion = "1.0"`  
✓ `engineVersion = "1.0.0"`  
✓ `requestId` 존재  
✓ `fullText` 길이 > 0  
✓ `errors` 배열 비어 있음  

## 11. 버전 관리

- **API Version**: 1.0 (현재)
- **Schema Version**: 1.0 (응답 스키마)
- **Engine Version**: 1.0.0 (파서 엔진)

### 호환성:
- Schema Version 변경 → API 버전 업 필요
- Engine Version 변경 → 재빌드/배포 필요
- 응답 키 추가 → 후방 호환성 유지 (무시 가능)
- 응답 키 삭제 → **호환성 깨짐** (사용 금지)

## 12. 통합 예시 (Python)

```python
import requests
import json

def parse_hwpx(engine_url, hwpx_file_path):
    with open(hwpx_file_path, 'rb') as f:
        response = requests.post(
            f"{engine_url}/parse-hwpx",
            data=f.read(),
            headers={'Content-Type': 'application/octet-stream'},
            timeout=30
        )
    
    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        return None
    
    result = response.json()
    
    if not result.get('ok'):
        print(f"Parse failed: {result.get('errors', [])}")
        return None
    
    # 필수 키 검증
    required_keys = ['ok', 'schemaVersion', 'engineVersion', 'requestId', 
                     'inputFileType', 'fullText', 'paragraphs', 'blocks', 
                     'tables', 'warnings', 'errors']
    for key in required_keys:
        if key not in result:
            raise ValueError(f"Missing required key: {key}")
    
    print(f"✓ Parsed: {len(result['fullText'])} chars, {len(result['paragraphs'])} paragraphs")
    
    return result

# 사용 예
if __name__ == '__main__':
    result = parse_hwpx('http://127.0.0.1:8080', 'sample.hwpx')
    if result:
        print(json.dumps(result, indent=2, ensure_ascii=False))
```

## 참고사항

- **MIME Type**: HWPX는 ZIP 기반 형식 → Content-Type은 `application/octet-stream` 사용
- **파일 크기 제한**: 현재 무제한 (향후 제한 추가 가능)
- **동시 요청**: 엔진은 스레드풀 4개 사용 (동시 처리 가능)
- **캐싱**: 응답은 캐시 불가 (requestId가 고유하므로 매번 다름)
