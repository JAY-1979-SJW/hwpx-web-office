# HWPX Direct Writer P7 Visible Image Insert Pipeline

## Purpose

Add a modular pipeline for visible image insertion in HWPX documents.

This stage keeps the template-first rule: the engine does not synthesize a new picture/control object blindly. It requires an HWPX template that already contains a visible picture object, then adds a new `BinData` image entry and clones/rebinds the existing visible picture object to that image.

## Implementation

Added module:

- `scripts/hwpx/hwpx_visible_image_ops.py`

Updated files:

- `scripts/hwpx/hwpx_writer_adapter.py`
- `scripts/hwpx/hwpx_template_engine.py`

New CLI:

```powershell
python scripts/hwpx/hwpx_template_engine.py visible-image-insert `
  --template template.hwpx `
  --output output.hwpx `
  --image image.png `
  --picture-index 0 `
  --image-entry BinData/visible_image001.png `
  --validate `
  --report-json report.json
```

## Behavior

The pipeline performs:

1. Inspect visible picture/control objects.
2. Require at least one existing visible picture object.
3. Add the replacement image as a `BinData` entry.
4. Clone the selected visible picture object.
5. Rebind the clone to the new image entry.
6. Write the output package only when insertion succeeds.
7. Validate ZIP/XML when requested.

## Local Test

Command:

```powershell
python scripts/hwpx/hwpx_template_engine.py visible-image-insert `
  --template tmp\hwpx_writer_poc\template_seed.hwpx `
  --output tmp\hwpx_modularization_check\visible_image_insert.hwpx `
  --image tmp\hwpx_image_replace_poc\replacement_marker.png `
  --picture-index 0 `
  --image-entry BinData/visible_image001.png `
  --validate `
  --report-json tmp\hwpx_modularization_check\visible_image_insert_report.json
```

Result:

```text
status: WARN
insert_result.status: VISIBLE_PICTURE_TEMPLATE_NOT_FOUND
picture_count: 0
```

This is expected for the current seed template because it has no existing visible picture/control object. The command did not create a damaged output package.

## Current Status

| Capability | Status |
|---|---|
| Modular visible image pipeline | PASS |
| CLI command | PASS |
| Failure handling for missing picture template | PASS |
| Visible image insertion into a real picture template | BLOCKED |

## Blocker

A valid template containing an existing visible HWPX picture/control object is required.

Current available seed/template files do not contain such an object:

```text
PICTURE_OBJECT_NOT_FOUND
```

## Conclusion

P7 result: WARN.

The modular insertion pipeline is implemented, but full PASS requires a visible-picture HWPX template. Once that template exists, the same CLI can perform the full insertion path and should be followed by ZIP/XML validation, Java parser roundtrip, and a user-present visual check in Hancom.

## Next Step

Create or obtain one small HWPX fixture with a visible image object:

1. Make a minimal HWPX in Hancom with one visible PNG.
2. Store it under `tmp/` only for testing.
3. Run `picture-inspect`.
4. Run `visible-image-insert`.
5. Validate ZIP/XML.
6. Run Java parser roundtrip.
7. Perform optional user-present Hancom visual check.
