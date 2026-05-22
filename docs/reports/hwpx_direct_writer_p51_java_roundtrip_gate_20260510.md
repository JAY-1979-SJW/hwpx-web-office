# HWPX Direct Writer P51 Java Parser Roundtrip Gate

## Purpose

This step wires the Java `HwpxParser` back into the HWPX direct writer toolchain as a callable roundtrip gate.

The goal is not to add a new HWPX writing feature. The goal is to make generated HWPX artifacts verifiable by the existing Java parser from the same scenario runner that creates them.

## Scope

- Added a Java parser CLI entry point.
- Added a Gradle `parseHwpxCli` task.
- Added a Python roundtrip runner.
- Connected `full-scenario --java-roundtrip`.
- Kept Hancom COM/GUI out of scope.
- Did not stage generated HWPX or tmp artifacts.

## Implementation

### Java CLI

File:

```text
src/main/java/com/haehan/engine/parser/HwpxParserCli.java
```

Behavior:

```text
HwpxParserCli <input.hwpx> [output.json]
```

It calls `HwpxParser.parse(...)`, writes the `DocumentParseResponse` as JSON, and exits with code `0` only when `response.ok` is true.

### Gradle Task

File:

```text
build.gradle.kts
```

Task:

```text
parseHwpxCli
```

Usage:

```text
.\gradlew.bat parseHwpxCli -PskipGitHooks=true -Pinput=<input.hwpx> -Poutput=<output.json>
```

`-PskipGitHooks=true` skips the repository hook setup task during parser roundtrip checks. This avoids unnecessary `.git/config` writes during verification.

### Python Roundtrip Runner

File:

```text
scripts/hwpx/hwpx_java_roundtrip.py
```

Capabilities:

- Run Java parser roundtrip for one or more generated HWPX files.
- Store parser JSON outputs under tmp.
- Summarize parse status, paragraph/table counts, semantic sections, extracted fields, diagnostics, and expected value checks.
- Use an isolated `GRADLE_USER_HOME` under the system temp directory unless already configured.
- Decode Gradle output with replacement to survive localized console output.

### Scenario Integration

Files:

```text
scripts/hwpx/hwpx_full_scenario.py
scripts/hwpx/hwpx_template_engine.py
scripts/hwpx/hwpx_api.py
```

New option:

```text
python scripts/hwpx/hwpx_template_engine.py full-scenario --java-roundtrip ...
```

The scenario now adds a `java_roundtrip` phase when enabled.

## Verification

### Syntax and Compile

```text
Python AST: PASS
full-scenario --help: PASS
compileJava: PASS
```

### Direct Java Parser CLI

Input:

```text
smoke-test.hwpx
```

Output:

```text
tmp/hwpx_p51_java_roundtrip/smoke_java.json
```

Result:

```text
parseHwpxCli: PASS
output JSON: created
```

### Full Scenario With Java Roundtrip

Command:

```text
python scripts/hwpx/hwpx_template_engine.py full-scenario --template smoke-test.hwpx --out-dir tmp\hwpx_p51_full_scenario_java3 --strict-regression --java-roundtrip --report-json tmp\hwpx_p51_full_scenario_java3_report.json
```

Result:

```text
overall status: WARN
phase count: 6
pass phases: 5
warn phases: 1
fail phases: 0
examples: PASS
examples batch: PASS
API smoke: PASS
regression: PASS
Java roundtrip: WARN
```

Java roundtrip summary:

```text
roundtrip count: 9
parse success: 9/9
PASS: 1
WARN: 8
FAIL: 0
```

The WARN cases are not parser failures. They come from `expected_values` that include metadata or package-level values not currently emitted into Java parser `fullText`.

## Roundtrip Results

```text
api_smoke_styled_table: PASS
api_smoke_visible_builder: WARN, parse_ok=true
regression_metadata_text_table: WARN, parse_ok=true
regression_page_header_footer: WARN, parse_ok=true
regression_image_chart: WARN, parse_ok=true
regression_visible_picture_clone: WARN, parse_ok=true
regression_multi_section: WARN, parse_ok=true
regression_section_layout_header_footer: WARN, parse_ok=true
regression_section_table_image_chart: WARN, parse_ok=true
```

All nine generated HWPX files were readable by the Java parser.

## Issues Found

### Gradle Wrapper Lock

Initial sandbox execution failed on the user Gradle wrapper lock file:

```text
gradle-8.7-bin.zip.lck access denied
```

Mitigation:

```text
hwpx_java_roundtrip.py uses an isolated GRADLE_USER_HOME under the system temp directory.
```

### Git Hook Task During Parser Gate

Gradle `compileJava` depended on `installGitHooks`, which attempted to write `.git/config` during parser CLI execution.

Mitigation:

```text
installGitHooks is skipped when -PskipGitHooks=true is present.
hwpx_java_roundtrip.py passes -PskipGitHooks=true.
```

### Expected Value Policy

The Java parser roundtrip gate currently checks all supplied expected values against `fullText`.

Some regression expected values are metadata/package values and are not body text. Those should be split into:

```text
parser_text_expected_values
package_expected_values
metadata_expected_values
```

Until that split exists, full scenario with Java roundtrip is expected to be `WARN`, not `FAIL`, when all parser calls succeed but metadata expected values are missing from `fullText`.

## Conclusion

P51 result:

```text
WARN
```

Reason:

```text
Java parser roundtrip execution is wired and all generated HWPX files parse successfully.
The remaining warning is expected-value policy refinement, not HWPX package failure.
```

## Next Steps

1. Split expected values by validation domain.
2. Make Java roundtrip PASS depend on parser-readable body text only.
3. Keep package/metadata checks in the Python audit layer.
4. Continue toward full HWPX direct writer coverage with modular validation gates.
