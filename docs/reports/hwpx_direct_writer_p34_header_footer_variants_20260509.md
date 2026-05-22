# HWPX Direct Writer P34 Header Footer Variants

## Purpose

P34 extends the direct HWPX writer from P33 footer-only static body generation to
both visible header and visible footer body generation. It also fixes the
header/footer discovery tool so it detects XML structures by local tag name
instead of relying on fragile namespace prefixes such as `hp:`.

## Problem

P33 closed visible footer generation, but two gaps remained:

```text
1. visible header body generation was still unsupported
2. discovery missed existing structures when XML prefixes were rewritten as ns0/ns1
```

A builder smoke also exposed a practical failure:

```text
DocumentBuilder.page_numbering(...)
  .visible_header(...)
  .visible_footer(...)

status: FAIL
page_numbering: SECTION_PROPERTIES_NOT_FOUND
```

The failure occurred when a minimal template did not already contain `secPr` and
`page_layout` had not been called first.

## Implementation

### Discovery

Updated:

```text
scripts/hwpx/hwpx_header_footer_discovery.py
```

The scanner now parses XML and collects local-name structure hits:

```text
header
footer
masterPage
pageNumCtrl
autoNum
newNum
startNum
beginNum
visibility
```

This avoids false negatives caused by rewritten XML prefixes.

### Header/Footer Body Generation

Updated:

```text
scripts/hwpx/hwpx_header_footer_ops.py
```

New and updated behavior:

```text
visible_header: creates hp:header body text
visible_footer: creates hp:footer body text
missing secPr: creates section properties automatically
missing Contents/header.xml: no longer blocks section body generation
```

The implementation remains modular inside header/footer ops and does not depend
on Hancom COM or GUI.

### Schema, Examples, Builder

Updated:

```text
scripts/hwpx/hwpx_job_schema.py
scripts/hwpx/hwpx_compose_schema_reference.py
scripts/hwpx/hwpx_compose_examples.py
scripts/hwpx/hwpx_document_builder.py
```

New job fields:

```text
visible_header
header_text
header_align
visible_footer
footer_text
footer_align
page_number_format
```

`DocumentBuilder.visible_header()` was added and
`DocumentBuilder.visible_footer()` remains available.

## Discovery Results

Repository-only scan:

```text
status: PASS
file_count: 29
found_count: 27
```

Local-name hit summary:

```text
beginNum: 27 files
startNum: 27 files
visibility: 27 files
header/footer/pageNumCtrl/native dynamic field samples: not found
```

Including tmp/generated outputs:

```text
status: PASS
file_count: 103
found_count: 82
```

Conclusion:

```text
Existing repository samples expose numbering metadata structures.
They do not currently provide a native dynamic page field sample to clone.
```

## Verification

### Python AST

```text
PY_AST_OK scripts/hwpx/hwpx_header_footer_discovery.py
PY_AST_OK scripts/hwpx/hwpx_header_footer_ops.py
PY_AST_OK scripts/hwpx/hwpx_job_schema.py
PY_AST_OK scripts/hwpx/hwpx_compose_examples.py
PY_AST_OK scripts/hwpx/hwpx_compose_schema_reference.py
PY_AST_OK scripts/hwpx/hwpx_document_builder.py
```

### Compose Example

Command target:

```text
tmp/hwpx_p34_header_footer_native/examples/page_layout_numbering.json
```

Output:

```text
tmp/hwpx_p34_header_footer_native/header_footer_v2.hwpx
```

Result:

```text
compose status: PASS
page_layout: PAGE_LAYOUT_SET_PASS
page_numbering: PAGE_NUMBERING_SET_PASS
visible_header: VISIBLE_HEADER_BODY_SET_PASS
visible_footer: VISIBLE_FOOTER_BODY_SET_PASS
expected values found:
- P27 page layout and numbering example
- Generated Header
- Page 3
missing expected values: []
ZIP/XML validation: PASS
```

### DocumentBuilder

Builder call:

```text
document("smoke-test.hwpx")
  .page_numbering(start_page=11)
  .visible_header("Header {page}", start_page=11)
  .visible_footer("Footer {page}", start_page=11)
```

Result:

```text
status: PASS
expected values:
- Header 11
- Footer 11
- Builder header footer smoke
missing expected values: []
```

This confirms that `page_numbering` can now create `secPr` directly without a
prior `page_layout` step.

### Java Parser Roundtrip

Input:

```text
tmp/hwpx_p34_header_footer_native/header_footer_v2.hwpx
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

The Java run emitted the known Log4j file appender permission warnings, but
`HwpxParser.parse()` returned `PASS`.

## Current Status

```text
visible header static text: PASS
visible footer static text: PASS
missing secPr recovery: PASS
prefix-independent structure discovery: PASS
Java parser roundtrip: PASS
native dynamic page field: PENDING
```

## Remaining Limits

```text
Native dynamic page field generation is not implemented.
No repository sample currently exposes pageNumCtrl/autoNum header-footer body structure.
Visual Hancom GUI verification was not executed.
Per-section odd/even/first-page variants are pending.
```

## Next Step

```text
P35: native dynamic page field sample acquisition and clone-based implementation
```

If no native sample is available, keep dynamic fields pending and proceed with
other HWPX completion areas such as section variants, document metadata, or
embedded object/layout fidelity.
