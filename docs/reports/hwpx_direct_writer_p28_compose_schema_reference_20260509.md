# HWPX Direct Writer P28 Compose Schema Reference

## 목적

HWPX direct writer의 compose job 계약을 문서화했다. P27에서 예시 job을 생성할 수 있게 되었고, 이번 P28에서는 어떤 필드를 넣을 수 있는지, 어떤 값이 지원되는지, 어떤 기능이 아직 pending인지 기계가 읽을 수 있는 reference 생성기로 고정했다.

## 구현

신규 파일:

```text
scripts/hwpx/hwpx_compose_schema_reference.py
```

역할:

```text
compose_schema_reference()
markdown_reference()
CLI --out-json / --out-md
```

생성 명령:

```text
python scripts/hwpx/hwpx_compose_schema_reference.py \
  --out-json tmp/hwpx_p28_schema_reference/schema_reference.json \
  --out-md tmp/hwpx_p28_schema_reference/schema_reference.md
```

결과:

```text
status: PASS
```

## Top-Level Fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `template` | `string` | yes | 입력 HWPX 템플릿 |
| `output` | `string` | no | 출력 HWPX 경로 |
| `mapping` | `object` | no | placeholder 치환 |
| `style_definitions` | `object` | no | char/para/border/list style 정의 |
| `paragraphs` | `array` | no | 생성 문단 |
| `tables` | `array` | no | 생성 표 |
| `table_operations` | `array` | no | 기존 표 조작 |
| `images` | `array` | no | PNG/차트 이미지 삽입 |
| `page_layout` | `object` | no | 용지/여백 설정 |
| `page_numbering` | `object` | no | 페이지 번호 metadata |
| `expected_values` | `array` | no | validation expected text |
| `validate` | `boolean` | no | 기본 true |

## Supported Values

### list presets

```text
bullet_dash
decimal
korean
mixed_legal
```

### table operations

```text
append_row
clone_table
delete_row
inspect
merge_cells
set_cell_layout
unmerge_cell
update_cells
```

### image modes

```text
chart_png
png_insert
```

## Style Fields

### paragraph style

```text
char_style
para_style
list_style
list_level
level
charPrIDRef
paraPrIDRef
styleIDRef
```

### table style

```text
width
row_height
row_heights
repeat_header
column_widths
merged_cells
border_fill_style
header_border_fill_style
body_border_fill_style
cell_border_fill_style
cell_border_fill_map
cell_vertical_align
cell_vertical_align_map
cell_text_direction
cell_text_direction_map
cell_line_wrap
cell_line_wrap_map
cell_margin
cell_margin_map
```

## Page Fields

### page_layout

```text
orientation: portrait | landscape
width: positive integer HWPUNIT
height: positive integer HWPUNIT
margins: left/right/top/bottom/header/footer/gutter
```

### page_numbering

```text
start_page: integer >= 1
page_starts_on: BOTH | EVEN | ODD
hide_first_page_number: boolean
hide_first_header: boolean
hide_first_footer: boolean
```

## 검증

### reference generator

```text
Python AST: PASS
CLI output: PASS
schema_reference.json: generated
schema_reference.md: generated
```

### P27 examples 연계

P27에서 생성한 sample 기반 job 3개와 대응된다.

```text
paragraph_list: PASS
styled_table: PASS
page_layout_numbering: WARN
```

`page_layout_numbering`의 WARN은 다음 제한 때문이다.

```text
HEADER_FOOTER_BODY_GENERATION_PENDING
```

ZIP/XML validation과 expected text validation은 정상이다.

## 제한

```text
visible header/footer body generation is pending
HWP conversion is out of scope for direct writer
complex native chart objects are out of scope; use chart_png image mode
visual Hancom GUI verification is separate from ZIP/XML and Java parser validation
```

## 판정

```text
P28_COMPOSE_SCHEMA_REFERENCE: PASS
```

## 다음 단계

1. P29: Python library facade/API wrapper 설계
2. P30: compose schema와 examples를 README/usage 문서로 통합
3. P31: visible header/footer fixture 확보 후 본문 표시 header/footer 생성
