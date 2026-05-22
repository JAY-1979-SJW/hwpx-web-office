# HWPX Direct Writer P20 Cell Layout

## 목적

HWPX direct writer의 생성 표에 셀 레이아웃 속성을 적용한다. 이번 단계는 셀의 세로 정렬, 텍스트 방향, 줄바꿈 방식, 셀 여백을 기능별 모듈로 분리하고, 생성된 HWPX XML에 실제 속성이 반영되는지 검증하는 작업이다.

## 구현

- `hwpx_table_cell_layout_style.py`를 추가해 셀 레이아웃 style normalization을 분리했다.
- composer는 table style에서 layout refs를 받아 generated table factory로 전달한다.
- element factory는 `hp:subList`의 `vertAlign`, `textDirection`, `lineWrap`과 `hp:cellMargin`을 style refs 기반으로 생성한다.
- 전역 스타일과 셀 주소별 override를 모두 지원한다.
- job schema는 layout map과 margin object 형태를 검증한다.

## 지원 속성

| 속성 | 전역 키 | 셀별 override |
| --- | --- | --- |
| 세로 정렬 | `cell_vertical_align`, `vertical_align`, `vert_align` | `cell_vertical_align_map` |
| 텍스트 방향 | `cell_text_direction`, `text_direction` | `cell_text_direction_map` |
| 줄바꿈 | `cell_line_wrap`, `line_wrap` | `cell_line_wrap_map` |
| 셀 여백 | `cell_margin` | `cell_margin_map` |

## 테스트

- job validation: PASS
- compose: PASS
- ZIP/XML validation: PASS
- XML attribute inspection: PASS
- Java `HwpxParser` roundtrip: PASS

## XML 검증 결과

| 셀 | 검증 항목 | 결과 |
| --- | --- | --- |
| `0,0` | 기본 layout | `CENTER`, `HORIZONTAL`, `BREAK`, margin `600/600/200/200` |
| `0,2` | text direction override | `VERTICAL` |
| `1,0` | vertical align override | `TOP` |
| `1,2` | vertical align override | `BOTTOM` |
| `2,1` | cell margin override | `1200/1200/400/400` |
| `2,2` | line wrap override | `SQUEEZE` |

## Java Parser Roundtrip

| 항목 | 결과 |
| --- | --- |
| parse_status | PASS |
| paragraph_count | 2 |
| table_count | 1 |
| diagnostics_exists | true |
| quality_score | 7 |
| warning_count | 0 |
| error_count | 0 |

## 제한

- 이번 단계는 생성 표의 셀 레이아웃 적용이다.
- 기존 표에 대한 layout mutation operation은 아직 구현하지 않았다.
- 한컴 GUI 시각 확인은 수행하지 않았다.

## 결론

P20은 PASS다. HWPX direct writer는 생성 표의 셀 정렬/텍스트 방향/줄바꿈/여백을 모듈화된 style refs로 적용하고, ZIP/XML 및 Java parser roundtrip을 통과했다.

## 다음 단계

1. P21: 기존 표 셀 레이아웃 변경 operation
2. P22: 페이지/섹션 레이아웃
3. P23: 목록/번호 매기기
