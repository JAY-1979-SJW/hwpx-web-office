# HWPX Direct Writer P38 Preview Text

## Purpose

P38 adds direct generation of `Preview/PrvText.txt` to the HWPX writer. This
fills the package-level plain text preview/search entry without running Hancom,
COM, GUI automation, Docker, or server conversion.

## Implementation

Updated files:

```text
scripts/hwpx/hwpx_preview_ops.py
scripts/hwpx/hwpx_manifest_ops.py
scripts/hwpx/hwpx_composer.py
scripts/hwpx/hwpx_job_schema.py
scripts/hwpx/hwpx_document_builder.py
scripts/hwpx/hwpx_compose_schema_reference.py
```

New module:

```text
hwpx_preview_ops.py
```

Responsibilities:

```text
build_preview_text()
inspect_preview_text()
collect metadata text when requested
collect section text from hp:t nodes
deduplicate preview lines
write Preview/PrvText.txt as UTF-8
```

Composer behavior:

```text
preview_text generation runs by default near the end of compose.
package manifest repair then adds Preview/PrvText.txt to Contents/content.hpf.
```

Schema field:

```json
{
  "preview_text": {
    "enabled": true,
    "include_metadata": true,
    "max_chars": 4000
  }
}
```

## Validation

Python AST:

```text
PY_AST_OK scripts/hwpx/hwpx_preview_ops.py
PY_AST_OK scripts/hwpx/hwpx_manifest_ops.py
PY_AST_OK scripts/hwpx/hwpx_composer.py
PY_AST_OK scripts/hwpx/hwpx_job_schema.py
PY_AST_OK scripts/hwpx/hwpx_document_builder.py
PY_AST_OK scripts/hwpx/hwpx_compose_schema_reference.py
```

CLI help:

```text
compose: PASS
validate-job: PASS
```

Schema reference generation:

```text
status: PASS
preview_text.enabled documented
preview_text.include_metadata documented
preview_text.max_chars documented
```

## Smoke Test

Job:

```text
tmp/hwpx_p38_preview/preview_job.json
```

Output:

```text
tmp/hwpx_p38_preview/preview_smoke.hwpx
```

Result:

```text
compose status: PASS
preview_text: PREVIEW_TEXT_SET_PASS
entry: Preview/PrvText.txt
source_text_count: 7
unique_text_count: 7
length: 132
truncated: false
ZIP/XML validation: PASS
missing expected values: []
```

Preview text:

```text
P38 Preview Text
office-analysis-engine
2026-05-09T13:51:44Z
preview, text
smoke
P38 preview paragraph one
P38 preview paragraph two
```

Manifest repair result:

```text
package_manifest: PACKAGE_MANIFEST_REPAIR_PASS
added manifest item: Preview/PrvText.txt
media-type: text/plain
manifest missing entries: []
spine missing sections: []
```

Java parser roundtrip:

```text
parse_status: PASS
paragraph_count: 3
table_count: 0
diagnostics_exists: true
quality_score: 7
warning_count: 0
error_count: 0
```

## Failure Case

Invalid job:

```json
{
  "preview_text": {
    "enabled": "yes",
    "max_chars": 0
  }
}
```

Validation result:

```text
status: FAIL
PREVIEW_TEXT_ENABLED_NOT_BOOLEAN
PREVIEW_MAX_CHARS_INVALID
```

## DocumentBuilder

The fluent builder now supports:

```python
document("template.hwpx", "out.hwpx").preview_text(
    enabled=True,
    include_metadata=True,
    max_chars=120,
)
```

Builder smoke result:

```text
enabled: true
max_chars: 120
```

## Result

```text
Preview/PrvText.txt generation: PASS
metadata text inclusion: PASS
section text inclusion: PASS
manifest repair for preview entry: PASS
schema validation: PASS
invalid input guard: PASS
Java parser roundtrip: PASS
```

## Limits

```text
Preview text is plain UTF-8 text.
No binary preview image is generated.
Visual Hancom GUI verification was not executed.
```

## Next Step

```text
P39: package completeness audit command for generated HWPX artifacts.
```
