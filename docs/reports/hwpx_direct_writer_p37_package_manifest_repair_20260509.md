# HWPX Direct Writer P37 Package Manifest Repair

## Purpose

P37 adds package-level manifest and spine repair to the HWPX direct writer. The
goal is to keep `Contents/content.hpf`, `META-INF/container.xml`, package
entries, and visible document sections/images aligned after direct XML/package
editing.

## Implementation

Updated files:

```text
scripts/hwpx/hwpx_manifest_ops.py
scripts/hwpx/hwpx_composer.py
scripts/hwpx/hwpx_job_schema.py
scripts/hwpx/hwpx_document_builder.py
scripts/hwpx/hwpx_compose_schema_reference.py
```

New module:

```text
hwpx_manifest_ops.py
```

Responsibilities:

```text
inspect_package_manifest()
repair_package_manifest()
create Contents/content.hpf when missing
ensure META-INF/container.xml rootfile references Contents/content.hpf
ensure content.hpf manifest items for Contents/*.xml, settings.xml, BinData/*
ensure spine itemrefs for header/section entries
```

Composer behavior:

```text
package_manifest repair runs by default near the end of compose.
It can be disabled with package_manifest.enabled=false.
```

Schema field:

```json
{
  "package_manifest": {
    "enabled": true
  }
}
```

## Validation

Python AST:

```text
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
package_manifest.enabled documented
```

## Smoke Test: Metadata Document

Job:

```text
tmp/hwpx_p37_manifest/manifest_smoke_job.json
```

Output:

```text
tmp/hwpx_p37_manifest/manifest_smoke.hwpx
```

Result:

```text
compose status: PASS
package_manifest: PACKAGE_MANIFEST_REPAIR_PASS
content.hpf: exists
manifest missing entries: []
spine missing sections: []
ZIP/XML validation: PASS
missing expected values: []
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

## Smoke Test: Image Without Existing content.hpf

Job:

```text
tmp/hwpx_p37_manifest/manifest_image_no_metadata_job.json
```

Output:

```text
tmp/hwpx_p37_manifest/manifest_image_no_metadata.hwpx
```

Result:

```text
compose status: WARN
WARN reason: EXPERIMENTAL_SYNTHETIC_PICTURE_XML
package_manifest: PACKAGE_MANIFEST_REPAIR_PASS
created_content_hpf: true
container: CONTAINER_ROOTFILE_ADDED
added manifest items:
- ../BinData/p37_marker_no_metadata.png
- Contents/section0.xml
spine itemrefs:
- section0
manifest missing entries: []
spine missing sections: []
ZIP/XML validation: PASS
```

The WARN is from the existing synthetic visible picture XML policy, not from
manifest repair.

Java parser roundtrip:

```text
parse_status: PASS
paragraph_count: 1
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
  "package_manifest": {
    "enabled": "yes"
  }
}
```

Validation result:

```text
status: FAIL
error: PACKAGE_MANIFEST_ENABLED_NOT_BOOLEAN
```

## Result

```text
content.hpf generation: PASS
manifest item repair: PASS
spine itemref repair: PASS
container rootfile repair: PASS
schema validation: PASS
invalid input guard: PASS
Java parser roundtrip: PASS
```

## Limits

```text
Advanced RDF package metadata is not generated.
Preview/PrvText.txt is not regenerated.
Synthetic visible picture XML remains separately marked WARN.
Visual Hancom GUI verification was not executed.
```

## Next Step

```text
P38: preview text generation and package text summary entry.
```
