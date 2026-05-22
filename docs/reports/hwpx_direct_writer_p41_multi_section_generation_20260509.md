# HWPX Direct Writer P41 Multi-Section Generation

## Purpose

P41 extends the HWPX direct writer from a single-section document model to a multi-section document model.

The target is still pure HWPX ZIP/XML generation:

- no Hancom execution
- no COM
- no GUI automation
- no HWP conversion

## Implementation

Implemented:

- `scripts/hwpx/hwpx_section_ops.py`
- `HwpxPackage.section_entries()` numeric sort
- `HwpxEditor.inspect_sections()`
- `HwpxEditor.append_section()`
- `HwpxEditor.ensure_section_count()`
- composer job field: `sections`
- schema validation for `sections`
- package audit section inspection
- regression profile: `multi_section`

The section operation is intentionally modular:

- `hwpx_section_ops.py` owns section creation and inspection.
- `hwpx_composer.py` only invokes section preparation before content operations.
- existing paragraph/table/image operations continue to use `section_index`.
- `hwpx_manifest_ops.py` repairs new section manifest/spine entries.

## Job Shape

Supported shape:

```json
{
  "sections": {
    "count": 3,
    "clear_body": true
  }
}
```

The implementation clones an existing section XML and clears direct paragraph body content for new sections when `clear_body` is true.

## Direct Test

Target:

```text
tmp/hwpx_p41_multisection/multi_section_direct.hwpx
```

Content:

- section 0: `P41 section zero direct`
- section 1: `P41 section one direct`
- section 2: `P41 section two direct`
- section 2 table:
  - `Section`, `Value`
  - `two`, `table`

Result:

```text
compose_status: PASS
section_count: 3
ZIP/XML: PASS
manifest/spine: PASS
preview_text: PASS
strict audit: PASS
```

Manifest/spine repair added:

```text
Contents/section1.xml
Contents/section2.xml
spine itemref section1
spine itemref section2
```

## Regression Suite

P40 regression suite now includes a fourth profile:

```text
multi_section
```

Regression result:

```text
status: PASS
profile_count: 4
pass_count: 4
warn_count: 0
fail_count: 0
```

Profile checks:

```text
section_count: PASS
value: 3
```

## Java Parser Roundtrip

Targets:

```text
tmp/hwpx_p41_multisection/multi_section_direct.hwpx
tmp/hwpx_p41_multisection_regression/multi_section.hwpx
```

Result:

```text
multi_section_direct: PASS
multi_section regression: PASS
```

Both files parsed successfully with diagnostics present and no parser error.

## Conclusion

P41 result:

```text
PASS
```

The HWPX direct writer now supports multi-section generation and section-indexed content placement.

## Current Coverage

Now supported:

- section creation
- section inspection
- section-indexed paragraph insertion
- section-indexed table insertion
- manifest/spine repair for multiple sections
- preview text across multiple sections
- strict package audit for multiple sections
- regression suite coverage
- Java parser roundtrip

## Remaining Work

- section-specific page layout profiles
- section-specific header/footer profiles
- section-indexed visible image regression
- section deletion/reordering
- explicit section break semantics beyond separate section files

## Next Step

Recommended next development:

```text
P42: section-specific page layout and header/footer regression
```

That step should verify that each section can carry independent layout/header/footer settings without breaking package audit or parser roundtrip.
