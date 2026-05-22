# HWPX Direct Writer P52 Java Roundtrip Expected Split

## Purpose

P51 added the Java parser roundtrip gate, but the full scenario remained `WARN` because the Java parser gate compared all regression `expected_values` against parser `fullText`.

That was too broad. The regression expected list contains several validation domains:

- rendered body/header/footer/table text
- OPF/package metadata
- package audit values
- image/package labels

The Java parser `fullText` gate should only validate values expected to appear in parser-visible text. Package and metadata values remain covered by the Python package audit layer.

## Operating Rules Applied

- No Hancom COM/GUI execution.
- No HWP conversion.
- No Docker/server operation.
- No tmp/HWPX result staging.
- Existing dirty/untracked files preserved.
- Only focused HWPX direct writer modules and report are changed.

## Implementation

### Roundtrip Runner

File:

```text
scripts/hwpx/hwpx_java_roundtrip.py
```

Added explicit expected-value domains:

```text
parser_text_expected_values
package_expected_values
metadata_expected_values
```

`missing_expected_values` now evaluates only `parser_text_expected_values`.

The original `expected_values` field is still recorded for traceability and backward compatibility.

### Full Scenario

File:

```text
scripts/hwpx/hwpx_full_scenario.py
```

Added profile-specific Java parser text expectations for stable regression profiles:

```text
metadata_text_table
page_header_footer
image_chart
visible_picture_clone
multi_section
section_layout_header_footer
section_table_image_chart
```

Metadata and package-level expected values are reported as `metadata_expected_values`, but they no longer make the Java parser text gate WARN.

## Verification

### Syntax

```text
Python AST: PASS
hwpx_java_roundtrip.py --help: PASS
```

### Full Scenario

Command:

```text
python scripts/hwpx/hwpx_template_engine.py full-scenario --template smoke-test.hwpx --out-dir tmp\hwpx_p52_full_scenario_java --strict-regression --java-roundtrip --report-json tmp\hwpx_p52_full_scenario_java_report.json
```

Result:

```text
overall status: PASS
phase count: 6
pass phases: 6
warn phases: 0
fail phases: 0
example job count: 3
regression profile count: 7
```

Java roundtrip:

```text
status: PASS
count: 9
pass: 9
warn: 0
fail: 0
```

## Result

P52 status:

```text
PASS
```

The HWPX direct writer full scenario now supports this stable chain:

```text
generate schema/examples
→ compose example documents
→ API smoke
→ stable regression suite
→ Java HwpxParser roundtrip
→ PASS
```

## Remaining Work

- Log4j emits stderr appender warnings during Java parser CLI execution, but parser output and exit code are valid.
- Metadata/package validation remains in Python package audit, not Java parser fullText.
- Future work should add a committed visible-picture fixture so synthetic image regression bootstrapping can be replaced.
