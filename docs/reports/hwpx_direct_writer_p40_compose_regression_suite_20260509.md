# HWPX Direct Writer P40 Compose Regression Suite

## Purpose

P40 adds a reusable regression suite for the HWPX direct writer. The goal is to ensure that representative generated documents continue to pass composition, package completeness audit, and Java parser roundtrip checks as the writer grows.

This is not a browser-view task and does not use Hancom, COM, or GUI automation.

## Implementation

Implemented:

- `scripts/hwpx/hwpx_compose_regression.py`
- `scripts/hwpx/hwpx_template_engine.py regression-suite`

The implementation is modular:

- `hwpx_compose_regression.py` owns golden profile generation and suite execution.
- `hwpx_composer.py` remains the document composition engine.
- `hwpx_package_audit.py` remains the package completeness quality gate.
- `hwpx_template_engine.py` only exposes a thin CLI wrapper.

## Golden Profiles

### metadata_text_table

Coverage:

- document metadata
- paragraphs
- generated table
- preview text
- package manifest/spine
- package audit

Result:

```text
compose_status: PASS
audit_status: PASS
profile_status: PASS
```

### page_header_footer

Coverage:

- page layout
- visible header text
- visible footer page text
- paragraph content
- metadata
- preview text
- package audit

Result:

```text
compose_status: PASS
audit_status: PASS
profile_status: PASS
```

### image_chart

Coverage:

- dependency-free chart PNG generation
- generated visible picture XML
- BinData image entry
- manifest image item
- image reference audit
- metadata
- preview text
- package audit

Result:

```text
compose_status: WARN
compose_effective_status: PASS
audit_status: PASS
profile_status: PASS
```

The compose warning is expected and allowed for this profile:

```text
EXPERIMENTAL_SYNTHETIC_PICTURE_XML
```

The audit result proves that the generated package contains one image and valid XML references:

```text
bindata_images: 1
image_reference_count: 5
```

## CLI Verification

Standalone suite:

```text
python scripts/hwpx/hwpx_compose_regression.py run --template smoke-test.hwpx --out-dir tmp/hwpx_p40_regression --strict
```

Result:

```text
status: PASS
profile_count: 3
pass_count: 3
warn_count: 0
fail_count: 0
```

Template engine wrapper:

```text
python scripts/hwpx/hwpx_template_engine.py regression-suite --template smoke-test.hwpx --out-dir tmp/hwpx_p40_regression_wrapper --strict
```

Result:

```text
status: PASS
profile_count: 3
pass_count: 3
warn_count: 0
fail_count: 0
```

## Java Parser Roundtrip

Targets:

```text
tmp/hwpx_p40_regression/metadata_text_table.hwpx
tmp/hwpx_p40_regression/page_header_footer.hwpx
tmp/hwpx_p40_regression/image_chart.hwpx
```

Result:

```text
metadata_text_table: PASS
page_header_footer: PASS
image_chart: PASS
```

Observed parser output:

```text
metadata_text_table paragraph_count: 4
page_header_footer paragraph_count: 2
image_chart paragraph_count: 2
diagnostics_exists: true for all
error_count: 0 for all
```

## Conclusion

P40 result:

```text
PASS
```

The HWPX direct writer now has a golden-profile regression suite that covers:

- text generation
- table generation
- page/header/footer generation
- chart PNG generation
- visible image insertion path
- metadata
- preview text
- package manifest/spine
- strict package completeness audit
- Java parser roundtrip

## Remaining Work

- Add multi-section profiles.
- Add native header/footer object compatibility profiles when confirmed.
- Add broader style regression profiles for paragraph/list/table/cell styling.
- Add stable Java roundtrip integration inside the Python regression runner if needed.

## Next Step

Recommended next development:

```text
P41: multi-section document generation and regression profile
```

This is the next structural step toward complete HWPX generation.
