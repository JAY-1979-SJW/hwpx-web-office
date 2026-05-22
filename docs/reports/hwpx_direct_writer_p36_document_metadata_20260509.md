# HWPX Direct Writer P36 Document Metadata

## Purpose

P36 adds document metadata editing to the direct HWPX writer. This improves
package completeness without running Hancom, COM, GUI automation, Docker, or
server-side conversion.

## Implementation

Updated files:

```text
scripts/hwpx/hwpx_metadata_ops.py
scripts/hwpx/hwpx_composer.py
scripts/hwpx/hwpx_job_schema.py
scripts/hwpx/hwpx_document_builder.py
scripts/hwpx/hwpx_compose_schema_reference.py
```

New module:

```text
hwpx_metadata_ops.py
```

Responsibilities:

```text
inspect_document_metadata()
apply_document_metadata()
create Contents/content.hpf when missing
update existing Contents/content.hpf when present
ensure META-INF/container.xml references Contents/content.hpf
```

Supported job field:

```json
{
  "document_metadata": {
    "title": "P36 Metadata Document",
    "language": "ko",
    "creator": "office-analysis-engine",
    "subject": "HWPX metadata direct writer",
    "description": "Metadata generated without Hancom execution",
    "keywords": ["hwpx", "metadata", "direct-writer"],
    "created_date": "2026-05-09T00:00:00Z",
    "modified_date": "2026-05-09T00:00:00Z",
    "date": "2026-05-09"
  }
}
```

## Validation

Python AST:

```text
PY_AST_OK scripts/hwpx/hwpx_metadata_ops.py
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

## Smoke Test: Missing content.hpf

Template:

```text
smoke-test.hwpx
```

Result:

```text
output: tmp/hwpx_p36_metadata/metadata_document.hwpx
status: PASS
created_content_hpf: true
container: CONTAINER_ROOTFILE_ADDED
ZIP/XML validation: PASS
missing_expected_values: []
```

Generated entries:

```text
Contents/content.hpf
META-INF/container.xml rootfile -> Contents/content.hpf
```

Java parser roundtrip:

```text
parse_status: PASS
paragraph_count: 2
table_count: 0
diagnostics_exists: true
quality_score: 7
warning_count: 0
error_count: 0
```

## Smoke Test: Existing content.hpf

Template:

```text
samples/[별지 10] 레미콘(아스콘) 공장 정기점검  결과 보고(건설공사 품질관리 업무지침).hwpx
```

Result:

```text
output: tmp/hwpx_p36_metadata/sample_metadata_updated.hwpx
status: PASS
created_content_hpf: false
container: CONTAINER_ROOTFILE_EXISTS
ZIP/XML validation: PASS
missing_expected_values: []
```

Updated fields:

```text
title
creator
ModifiedDate
keyword
```

## Failure Case

Invalid job:

```json
{
  "document_metadata": {
    "title": 123,
    "keywords": ["ok", 100]
  }
}
```

Validation result:

```text
status: FAIL
DOCUMENT_METADATA_FIELD_NOT_STRING
DOCUMENT_METADATA_KEYWORD_NOT_STRING
```

## DocumentBuilder

The fluent builder now supports:

```python
document("template.hwpx", "out.hwpx").metadata(
    title="Builder Metadata",
    creator="builder",
)
```

Builder smoke result:

```text
title: Builder Metadata
creator: builder
paragraph: Builder metadata paragraph
```

## Result

```text
new content.hpf generation: PASS
existing content.hpf update: PASS
container rootfile update: PASS
schema validation: PASS
invalid input guard: PASS
Java parser roundtrip: PASS
```

## Limits

```text
Advanced RDF metadata is not generated.
Preview text metadata is not regenerated.
Visual Hancom GUI verification was not executed.
```

## Next Step

```text
P37: package manifest and content.hpf manifest/spine completeness audit.
```
