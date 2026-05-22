# HWPX Direct Writer P33 Visible Header Footer Body

## Purpose

P33 fixes the remaining page numbering failure in the direct HWPX writer path.
The previous implementation only wrote page numbering metadata and always
reported `HEADER_FOOTER_BODY_GENERATION_PENDING`. It did not create visible
header/footer body XML.

## Problem

The failing behavior was:

```text
page_numbering metadata: PASS
visible footer body XML: missing
compose example status: WARN
expected Page 3 text: missing
```

The first repro after adding `visible_footer=true` showed the exact blocker:

```text
page_numbering status: HEADER_NOT_FOUND
template: smoke-test.hwpx
missing expected value: Page 3
```

`smoke-test.hwpx` has no `Contents/header.xml`, so `apply_page_numbering()` was
returning before it reached section-level footer body generation.

## Fix

Implemented visible footer generation inside the page numbering module:

```text
module: scripts/hwpx/hwpx_header_footer_ops.py
function path: apply_page_numbering -> _apply_visible_footer
```

New page numbering fields:

```text
visible_footer: boolean
footer_text: string, supports {page}
footer_align: LEFT / CENTER / RIGHT
page_number_format: DECIMAL
```

The generated footer is inserted as section-level `hp:footer` XML with:

```text
id: generated-footer-{section_index}
type: BOTH_PAGE
text: footer_text with {page} replaced by start_page
```

This is deliberately scoped as visible static footer text. Native dynamic page
field generation remains a later step.

## Schema And API

Updated:

```text
scripts/hwpx/hwpx_job_schema.py
scripts/hwpx/hwpx_compose_schema_reference.py
scripts/hwpx/hwpx_compose_examples.py
scripts/hwpx/hwpx_document_builder.py
```

`DocumentBuilder.visible_footer()` now creates the same declarative job shape as
the CLI composer and registers the rendered footer text as an expected value.

## Verification

### Python AST

```text
PY_AST_OK scripts/hwpx/hwpx_header_footer_ops.py
PY_AST_OK scripts/hwpx/hwpx_job_schema.py
PY_AST_OK scripts/hwpx/hwpx_compose_examples.py
PY_AST_OK scripts/hwpx/hwpx_compose_schema_reference.py
PY_AST_OK scripts/hwpx/hwpx_document_builder.py
PY_AST_OK scripts/hwpx/hwpx_template_engine.py
```

### Example Generation

```text
command: hwpx_template_engine.py examples
status: PASS
example count: 3
```

### Compose Smoke

Input:

```text
tmp/hwpx_p33_visible_footer/examples/page_layout_numbering.json
```

Output:

```text
tmp/hwpx_p33_visible_footer/page_layout_numbering_v2.hwpx
```

Result:

```text
compose status: PASS
page_layout: PAGE_LAYOUT_SET_PASS
page_numbering: PAGE_NUMBERING_SET_PASS
visible_footer: VISIBLE_FOOTER_BODY_SET_PASS
header_status: HEADER_NOT_FOUND
expected values found:
- P27 page layout and numbering example
- Page 3
missing expected values: []
ZIP/XML validation: PASS
```

`HEADER_NOT_FOUND` is now informational for templates without
`Contents/header.xml`; it no longer blocks section-level visible footer body
generation.

### Java Parser Roundtrip

Input:

```text
tmp/hwpx_p33_visible_footer/page_layout_numbering_v2.hwpx
```

Result:

```text
parse_status: PASS
paragraph_count: 2
table_count: 0
diagnostics_exists: true
quality_score: 7
warning_count: 0
error_count: 0
```

The Java parser emitted the existing Log4j file appender permission warnings,
but `HwpxParser.parse()` returned `PASS`.

### DocumentBuilder Smoke

Input path:

```text
DocumentBuilder.visible_footer("Page {page}", start_page=9)
```

Result:

```text
status: PASS
expected values:
- Page 9
- Builder visible footer smoke
missing expected values: []
```

### Failure Case

Invalid footer alignment:

```text
footer_align: MIDDLE
```

Result:

```text
validate-job status: FAIL
error code: FOOTER_ALIGN_INVALID
```

## Remaining Limits

```text
native dynamic page field: pending
visual Hancom GUI verification: not executed
header body generation: pending
multiple section footer variants: pending
```

## Conclusion

P33 status:

```text
VISIBLE_FOOTER_BODY_GENERATION: PASS
HEADER_FOOTER_BODY_GENERATION_PENDING warning for visible_footer=true: fixed
minimal template without Contents/header.xml: fixed
schema/example/builder exposure: PASS
Java parser roundtrip: PASS
```

Next step:

```text
P34: native header/footer variants and dynamic page field discovery
```
