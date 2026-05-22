# HWPX Direct Writer P8 Generated PNG Insert

## Purpose

Implement PNG insertion without running Hancom and without requiring a Hancom-authored visible-picture template.

Previous image stages supported:

- `image-seed`: add a `BinData` image entry only.
- `image-replace`: replace an existing `BinData` image.
- `visible-image-insert`: add an image and clone an existing visible picture object.

P8 adds an experimental generated picture path:

- add PNG to `BinData`
- add the image to `Contents/content.hpf`
- synthesize a minimal `hp:pic` object in `section.xml`
- bind the picture object to the generated image manifest id

## Implementation

Updated modules:

- `scripts/hwpx/hwpx_element_factory.py`
- `scripts/hwpx/hwpx_visible_image_ops.py`
- `scripts/hwpx/hwpx_writer_adapter.py`
- `scripts/hwpx/hwpx_template_engine.py`
- `scripts/hwpx/hwpx_picture_ops.py`

New CLI:

```powershell
python scripts/hwpx/hwpx_template_engine.py png-insert `
  --template template.hwpx `
  --output output.hwpx `
  --image image.png `
  --image-entry BinData/generated_picture001.png `
  --width 12000 `
  --height 9000 `
  --validate `
  --report-json report.json
```

## Technical Basis

The generated structure follows the known HWPX object model pattern where paragraph run items can include physical page objects. The open-source `gohwpxlib` documentation models `Picture` as a paragraph object and describes shape object fields such as size and position, plus picture-specific image data fields. This was used as a reference for a minimal generated `hp:pic` object.

Reference:

- https://pkg.go.dev/bitbucket.org/ownsoftware/gohwpxlib/object/content/section_xml/paragraph/paraobject

## Test

Command:

```powershell
python scripts/hwpx/hwpx_template_engine.py png-insert `
  --template tmp\hwpx_writer_poc\template_seed.hwpx `
  --output tmp\hwpx_modularization_check\png_insert_generated.hwpx `
  --image tmp\hwpx_image_replace_poc\replacement_marker.png `
  --image-entry BinData/generated_picture001.png `
  --width 12000 `
  --height 9000 `
  --validate `
  --report-json tmp\hwpx_modularization_check\png_insert_generated_report.json
```

Result:

```text
status: PASS
insert_result.status: GENERATED_PNG_PICTURE_INSERT_PASS
image_entry: BinData/generated_picture001.png
manifest_id: generated_picture001
ZIP validation: PASS
XML validation: PASS
picture-inspect: PASS
image referenced by section0.xml and content.hpf
```

## Java Parser Roundtrip

Input:

- `tmp/hwpx_modularization_check/png_insert_generated.hwpx`

Result:

```text
parse_status: PASS
paragraph_count: 4
table_count: 1
semantic_sections_count: 2
extracted_fields_count: 1
diagnostics_exists: true
quality_score: 28
warning_count: 0
error_count: 0
```

Log4j emitted local appender permission warnings for `%USERPROFILE%\app\haehan-platform\logs\*.log`, but parsing completed successfully and the output JSON was written.

## Failure Case

Missing PNG:

```text
status: FAIL
insert_result.status: REPLACEMENT_NOT_FOUND
output not written
```

## Limitations

- The generated `hp:pic` XML is experimental.
- Hancom visual verification has not been run in this step.
- Advanced picture options such as caption, crop, transparency, wrapping variants, and exact layout tuning remain future work.

## Conclusion

P8 result: PASS with visual-verification pending.

The engine can now insert a PNG into an HWPX package and synthesize a minimal picture object without running Hancom. ZIP/XML validation and Java parser roundtrip both pass.

## Next Step

1. User-present Hancom visual check for `png_insert_generated.hwpx`.
2. Add graph PNG generation and insert it using the same `png-insert` path.
3. Add API-level wrapper for document composition jobs.
