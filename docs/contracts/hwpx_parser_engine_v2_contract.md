# HWPX Parser Engine V2 — 출력 JSON 계약

**schemaVersion**: v2  
**engineVersion**: 0.1.0  
**문서 코드**: HWPX-PARSER-ENGINE-V2-ARCHITECTURE-01  
**작성일**: 2026-05-17  

---

## 최상위 구조

```json
{
  "schemaVersion": "v2",
  "engineVersion": "0.1.0",
  "requestId": "<uuid>",
  "inputFileName": "<fileNameHash>",
  "inputFileType": "hwpx",
  "parserMode": "HWPX_XML",
  "package": {},
  "document": {},
  "sections": [],
  "blocks": [],
  "tables": [],
  "styles": {},
  "semanticHints": {},
  "inputSlotCandidates": [],
  "warnings": [],
  "errors": []
}
```

---

## package 필드

```json
{
  "entryCount": 12,
  "hasMimetype": true,
  "mimetypeValue": "application/hwp+zip",
  "mimetypeCompressType": "ZIP_STORED",
  "hasContentHpf": true,
  "hasContainerXml": true,
  "hasHeaderXml": true,
  "sectionFileCount": 1,
  "xmlDecodeOk": true,
  "packageWarnings": []
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| entryCount | int | ZIP 엔트리 수 |
| hasMimetype | bool | mimetype 엔트리 존재 여부 |
| mimetypeValue | str | mimetype 문자열 |
| mimetypeCompressType | str | ZIP_STORED 또는 ZIP_DEFLATED |
| hasContentHpf | bool | Contents/content.hpf 존재 여부 |
| hasContainerXml | bool | META-INF/container.xml 존재 여부 |
| hasHeaderXml | bool | Contents/header.xml 존재 여부 |
| sectionFileCount | int | section XML 파일 수 |
| xmlDecodeOk | bool | 모든 XML 디코드 성공 여부 |
| packageWarnings | list[str] | 경고 메시지 목록 |

---

## document 필드

```json
{
  "titleCandidate": "소방시설 자체점검 실시결과 보고서",
  "fullText": "...",
  "paragraphCount": 120,
  "blockCount": 35,
  "tableCount": 14,
  "imageCount": 2,
  "drawingCount": 0
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| titleCandidate | str \| null | 문서 제목 후보 (첫 번째 문단 또는 메타데이터) |
| fullText | str | 전체 텍스트 (절단 가능) |
| paragraphCount | int | 전체 문단 수 |
| blockCount | int | 최상위 block 수 (para + table + image + drawing) |
| tableCount | int | 표 수 |
| imageCount | int | 이미지 수 |
| drawingCount | int | 도형 수 |

---

## blocks[] 필드

```json
[
  {
    "blockIndex": 0,
    "sectionIndex": 0,
    "type": "paragraph",
    "text": "소방시설 자체점검 실시결과 보고서",
    "tableId": null,
    "sourceXmlPath": "Contents/section0.xml",
    "orderKey": "s0:b000"
  },
  {
    "blockIndex": 1,
    "sectionIndex": 0,
    "type": "table",
    "text": null,
    "tableId": "t_s0_001",
    "sourceXmlPath": "Contents/section0.xml",
    "orderKey": "s0:b001"
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| blockIndex | int | 문서 내 전체 순서 |
| sectionIndex | int | 섹션 번호 |
| type | str | paragraph / table / image / drawing / page_marker / unknown |
| text | str \| null | 텍스트 블록의 내용 |
| tableId | str \| null | 표 블록의 tableId |
| sourceXmlPath | str | 원본 XML 경로 |
| orderKey | str | 정렬 키 (섹션:블록 인덱스) |

---

## tables[] 필드

```json
[
  {
    "tableId": "t_s0_001",
    "sectionIndex": 0,
    "blockIndex": 1,
    "tableIndex": 0,
    "layoutGuess": "metadata_table",
    "confidence": 0.85,
    "classificationEvidence": ["label_value_pair_score=0.8", "metadata_score=0.7"],
    "rowCount": 5,
    "colCount": 4,
    "visualRowCount": 6,
    "visualColCount": 4,
    "hasMergedCells": true,
    "hasNestedTables": false,
    "nestedTableCount": 0,
    "rows": [],
    "cells": [],
    "headerRowCandidates": [0],
    "headerTexts": ["공사명", "접수번호", "착공일", "완공일"],
    "headerConfidence": 0.9,
    "inputSlotHints": [],
    "warnings": []
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| tableId | str | 표 고유 ID (sectionIndex + tableIndex 조합) |
| sectionIndex | int | 섹션 번호 |
| blockIndex | int | 문서 내 블록 순서 |
| tableIndex | int | 섹션 내 표 순서 |
| layoutGuess | str | 분류 결과 |
| confidence | float | 분류 신뢰도 0.0~1.0 |
| classificationEvidence | list[str] | 분류 근거 목록 |
| rowCount | int | XML 기준 행 수 |
| colCount | int | XML 기준 열 수 |
| visualRowCount | int | 병합 반영 visual grid 행 수 |
| visualColCount | int | 병합 반영 visual grid 열 수 |
| hasMergedCells | bool | 병합셀 존재 여부 |
| hasNestedTables | bool | 중첩표 존재 여부 |
| nestedTableCount | int | 중첩표 수 |
| rows | list | 행 목록 (cells 포함) |
| cells | list | 전체 셀 목록 (flat) |
| headerRowCandidates | list[int] | 헤더 행 후보 인덱스 |
| headerTexts | list[str] | 헤더 텍스트 목록 |
| headerConfidence | float | 헤더 탐지 신뢰도 |
| inputSlotHints | list | 입력칸 힌트 (InputSlotDetector 연결 전 기초 정보) |
| warnings | list[str] | 표 수준 경고 |

---

## cells[] 필드

```json
{
  "cellId": "t_s0_001:r0:c0",
  "row": 0,
  "col": 0,
  "visualRow": 0,
  "visualCol": 0,
  "rowSpan": 1,
  "colSpan": 2,
  "isMergedOrigin": true,
  "isCoveredByMerge": false,
  "originCellId": null,
  "text": "공사명",
  "normalizedText": "공사명",
  "paragraphs": ["공사명"],
  "charPrIDRefs": ["cp_001"],
  "paraPrIDRefs": ["pp_001"],
  "borderFillIDRef": "bf_002",
  "fillColor": null,
  "horizontalAlign": "center",
  "verticalAlign": "middle",
  "hasNestedTable": false,
  "nestedTableIds": [],
  "isLikelyLabel": true,
  "isLikelyInputSlot": false,
  "warnings": []
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| cellId | str | 고유 ID (tableId:row:col) |
| row | int | XML 기준 행 인덱스 |
| col | int | XML 기준 열 인덱스 |
| visualRow | int | visual grid 행 인덱스 |
| visualCol | int | visual grid 열 인덱스 |
| rowSpan | int | 행 병합 수 (기본 1) |
| colSpan | int | 열 병합 수 (기본 1) |
| isMergedOrigin | bool | 병합 원점 셀 여부 |
| isCoveredByMerge | bool | 다른 셀에 의해 덮인 셀 여부 |
| originCellId | str \| null | 덮인 셀의 원점 cellId |
| text | str | 원본 텍스트 |
| normalizedText | str | 정규화된 텍스트 (NFKC + 한글 공백 제거) |
| paragraphs | list[str] | 셀 내 문단 목록 |
| charPrIDRefs | list[str] | 문자 스타일 참조 ID 목록 |
| paraPrIDRefs | list[str] | 문단 스타일 참조 ID 목록 |
| borderFillIDRef | str \| null | 테두리/채우기 참조 ID |
| fillColor | str \| null | 배경색 (hex 또는 null) |
| horizontalAlign | str | left / center / right / justify |
| verticalAlign | str | top / middle / bottom |
| hasNestedTable | bool | 셀 내 중첩표 여부 |
| nestedTableIds | list[str] | 중첩표 tableId 목록 |
| isLikelyLabel | bool | 라벨 셀 가능성 (header normalizer 결과) |
| isLikelyInputSlot | bool | 입력칸 가능성 (기초 판정) |
| warnings | list[str] | 셀 수준 경고 |

---

## styles 필드

```json
{
  "charPr": {
    "cp_001": {"fontSize": 9, "bold": false, "color": null}
  },
  "paraPr": {
    "pp_001": {"align": "center", "lineSpacing": 160}
  },
  "borderFill": {
    "bf_001": {"borderType": "solid", "fillType": "none", "fillColor": null},
    "bf_002": {"borderType": "solid", "fillType": "solid", "fillColor": "#D9D9D9"}
  },
  "referencedCharPrIds": ["cp_001"],
  "referencedParaPrIds": ["pp_001"],
  "referencedBorderFillIds": ["bf_001", "bf_002"],
  "danglingRefs": []
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| charPr | dict | 문자 스타일 ID → 속성 |
| paraPr | dict | 문단 스타일 ID → 속성 |
| borderFill | dict | 테두리/채우기 ID → 속성 |
| referencedCharPrIds | list[str] | 실제 참조된 charPr ID 목록 |
| referencedParaPrIds | list[str] | 실제 참조된 paraPr ID 목록 |
| referencedBorderFillIds | list[str] | 실제 참조된 borderFill ID 목록 |
| danglingRefs | list[str] | 정의 없이 참조된 ID (경고 대상) |

---

## semanticHints 필드

```json
{
  "detectedFields": {
    "projectName": "○○소방공사",
    "receiptNumber": null,
    "startDate": null,
    "contractorName": null
  },
  "headerDictionary": [
    {"normalizedHeader": "공사명", "fieldGuess": "projectName", "frequency": 1}
  ],
  "documentTypeCandidates": ["inspection_report", "legal_form"],
  "businessTypeCandidates": ["safety", "inspection"]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| detectedFields | dict | fieldGuess → 추출된 값 또는 null |
| headerDictionary | list | 헤더 사전 (normalizedHeader, fieldGuess, frequency) |
| documentTypeCandidates | list[str] | 문서 유형 후보 |
| businessTypeCandidates | list[str] | 업무 유형 후보 |

---

## inputSlotCandidates[] 필드

```json
[
  {
    "slotId": "slot_t_s0_001_r0c1",
    "tableId": "t_s0_001",
    "source": "label_right",
    "labelText": "공사명",
    "fieldGuess": "projectName",
    "row": 0,
    "col": 1,
    "visualRow": 0,
    "visualCol": 1,
    "confidence": 0.9,
    "reason": "label_right: 왼쪽 셀이 라벨('공사명'), 이 셀이 빈 입력칸",
    "warnings": []
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| slotId | str | 입력칸 고유 ID |
| tableId | str | 소속 표 ID |
| source | str | label_right / label_below / form_pair / table_append_row / schedule_bar_range / status_cell / manual_candidate |
| labelText | str | 연관 라벨 텍스트 |
| fieldGuess | str | 필드 추정명 (FIELD_HINTS 기반) |
| row | int | 셀 행 인덱스 |
| col | int | 셀 열 인덱스 |
| visualRow | int | visual grid 행 |
| visualCol | int | visual grid 열 |
| confidence | float | 탐지 신뢰도 |
| reason | str | 탐지 근거 설명 |
| warnings | list[str] | 경고 |

---

## warnings / errors 필드

```json
{
  "warnings": [
    {"code": "DANGLING_STYLE_REF", "detail": "charPrIDRef cp_999 not found in header.xml"},
    {"code": "EMPTY_SECTION", "detail": "section1.xml has no blocks"}
  ],
  "errors": [
    {"code": "XML_DECODE_FAIL", "detail": "Contents/section0.xml: UTF-8 decode error at line 42"}
  ]
}
```

| 코드 | 수준 | 설명 |
|------|------|------|
| DANGLING_STYLE_REF | warning | 스타일 참조 ID가 header.xml에 없음 |
| EMPTY_SECTION | warning | 섹션에 블록 없음 |
| MERGED_CELL_GRID_MISMATCH | warning | 병합셀 grid 계산 불일치 |
| XML_DECODE_FAIL | error | XML 파싱 실패 |
| ZIP_OPEN_FAIL | error | ZIP 열기 실패 |
| MISSING_REQUIRED_ENTRY | error | 필수 ZIP 엔트리 없음 |
