# HWPX Direct Writer P35 Native Dynamic Page Field Guard

## Purpose

P34 added static visible header/footer generation and page numbering metadata.
P35 prevents the direct writer from pretending to support native dynamic page
fields before a cloneable `pageNumCtrl` or `autoNum` sample structure is
available.

## Background

Current supported path:

```text
page_number_mode=STATIC_TEXT
visible_header / visible_footer text generation
{page} replaced with start_page at render time
ZIP/XML validation
Java HwpxParser roundtrip
```

Current unsupported path:

```text
page_number_mode=NATIVE_DYNAMIC
native page field object generation
```

The repository discovery pass found static page numbering structures but no
native dynamic page field object:

```text
discovery status: PASS
file_count: 29
found_count: 27
beginNum: 27
startNum: 27
visibility: 27
pageNumCtrl: 0
autoNum: 0
```

## Implementation

Updated files:

```text
scripts/hwpx/hwpx_header_footer_ops.py
scripts/hwpx/hwpx_job_schema.py
scripts/hwpx/hwpx_compose_schema_reference.py
scripts/hwpx/hwpx_document_builder.py
```

Changes:

```text
page_number_mode added.
Supported values: STATIC_TEXT, NATIVE_DYNAMIC.
STATIC_TEXT remains the default.
NATIVE_DYNAMIC is schema-valid but compose-blocked.
Unsupported native requests return NATIVE_DYNAMIC_PAGE_FIELD_UNSUPPORTED.
Invalid modes return PAGE_NUMBER_MODE_UNSUPPORTED.
DocumentBuilder exposes page_number_mode() and native_dynamic_page_numbers().
```

## Validation

Python AST:

```text
PY_AST_OK scripts/hwpx/hwpx_header_footer_ops.py
PY_AST_OK scripts/hwpx/hwpx_job_schema.py
PY_AST_OK scripts/hwpx/hwpx_compose_schema_reference.py
PY_AST_OK scripts/hwpx/hwpx_document_builder.py
```

Static header/footer compose:

```text
job: tmp/hwpx_p35_dynamic_page_field_guard/static_job.json
status: PASS
output: tmp/hwpx_p35_dynamic_page_field_guard/static_header_footer.hwpx
page_number_mode: STATIC_TEXT
expected values found:
- Static Header 5
- Static Footer 5
missing expected values: []
ZIP/XML validation: PASS
```

Java parser roundtrip:

```text
file: tmp/hwpx_p35_dynamic_page_field_guard/static_header_footer.hwpx
parse_status: PASS
paragraph_count: 1
table_count: 0
diagnostics_exists: true
quality_score: 7
warning_count: 0
error_count: 0
```

Native dynamic page field guard:

```text
job: tmp/hwpx_p35_dynamic_page_field_guard/native_dynamic_job.json
schema validation: PASS
compose status: FAIL
failed step: PAGE_NUMBERING_INVALID
error: NATIVE_DYNAMIC_PAGE_FIELD_UNSUPPORTED
```

Invalid mode validation:

```text
job: tmp/hwpx_p35_dynamic_page_field_guard/invalid_mode_job.json
schema validation: FAIL
error: PAGE_NUMBER_MODE_UNSUPPORTED
```

Schema reference generation:

```text
status: PASS
page_number_mode: STATIC_TEXT, NATIVE_DYNAMIC
```

DocumentBuilder smoke:

```text
DocumentBuilder.native_dynamic_page_numbers()
page_number_mode: NATIVE_DYNAMIC
```

## Result

```text
STATIC_TEXT header/footer generation: PASS
Java parser roundtrip: PASS
NATIVE_DYNAMIC explicit guard: PASS
Invalid page number mode validation: PASS
Native dynamic field generation: BLOCKED_BY_MISSING_SAMPLE
```

## Limits

```text
No native dynamic page field object is generated.
No pageNumCtrl/autoNum sample exists in the repository sample set.
Visual Hancom GUI verification was not executed.
```

## Next Step

```text
P36: acquire or synthesize a safe native page field sample before enabling
NATIVE_DYNAMIC output.
```
