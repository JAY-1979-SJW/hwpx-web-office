# HWPX Direct Writer P14 Border Fill Table Style

## 목적

HWPX direct writer의 표 스타일 기능을 확장해 `Contents/header.xml`에 새 `borderFill` 정의를 만들고, 생성 표가 해당 정의를 `borderFillIDRef`로 참조하도록 구현했다.

이번 단계는 브라우저 뷰나 한컴 실행 없이 HWPX ZIP/XML을 직접 수정하는 흐름이다.

## 구현

- `scripts/hwpx/hwpx_border_fill_style.py` 추가
  - `style_definitions.border_fills` 입력 처리
  - 기존 `borderFill` 구조 clone
  - 새 `id` 부여
  - left/right/top/bottom border 속성 설정
  - `fillBrush/winBrush` 배경색 설정
  - table style 이름을 `borderFillIDRef`로 변환
- `scripts/hwpx/hwpx_composer.py`
  - `apply_border_fill_definitions()` 호출
  - `table.style.border_fill_style`을 생성된 `borderFillIDRef`로 연결
- `scripts/hwpx/hwpx_job_schema.py`
  - `style_definitions.border_fills` validation 추가
  - unresolved `border_fill_style` warning 추가
- `scripts/hwpx/hwpx_style_ops.py`
  - `border_fill_style`을 table style 지원 키로 분리

## 테스트

입력 job:

```json
{
  "style_definitions": {
    "border_fills": {
      "summary_blue_fill": {
        "fill_color": "#DDEBFF",
        "border_type": "SOLID",
        "border_width": "0.12 mm",
        "border_color": "#1F5FBF"
      }
    }
  },
  "tables": [
    {
      "style": {
        "border_fill_style": "summary_blue_fill",
        "width": 42000,
        "row_height": 2600,
        "repeat_header": true
      }
    }
  ]
}
```

실행:

```text
validate-job: PASS
compose: PASS
ZIP/XML validation: PASS
Java HwpxParser roundtrip: PASS
```

## 결과

- 생성된 `borderFill` id: `6`
- `fillBrush/winBrush.faceColor`: `#DDEBFF`
- left/right/top/bottom border:
  - type: `SOLID`
  - width: `0.12 mm`
  - color: `#1F5FBF`
- 생성 table `borderFillIDRef`: `6`
- 생성 table cell `borderFillIDRef=6`: 6개
- Java parser:
  - parse_status: `PASS`
  - paragraph_count: 9
  - table_count: 3
  - semantic_sections_count: 4
  - diagnostics_exists: true
  - quality_score: 39
  - error_count: 0

## 제한

- 한컴 GUI 시각 확인은 하지 않았다.
- 셀 단위로 서로 다른 `borderFill`을 지정하는 기능은 아직 없다.
- 병합 셀/복합 테두리/그라데이션/패턴 fill은 후속으로 분리한다.
- named `hh:style` 객체 생성은 아직 PENDING이다.

## 결론

P14 판정: PASS

표 스타일의 핵심 기반인 header `borderFill` 정의 생성과 generated table 참조 연결이 동작한다. 다음 단계는 cell-level style map과 header row 전용 fill/border를 분리하는 것이다.

## 다음 단계

1. P15: table header row / body row cell-level `borderFillIDRef` 분리
2. P16: generated table column width / row height 안정화
3. P17: named style 객체 생성 검토
4. P18: HWPX API layer로 composer 기능 노출
