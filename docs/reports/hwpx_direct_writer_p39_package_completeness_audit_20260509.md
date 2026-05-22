# HWPX Direct Writer P39 Package Completeness Audit

## Purpose

P0~P38에서 HWPX direct writer가 문단, 표, 이미지 BinData, visible picture, 스타일, 페이지 레이아웃, metadata, manifest/spine, preview text까지 확장됐다.

P39의 목적은 생성된 HWPX가 단순 ZIP/XML 통과에 그치지 않고, 실제 배포 가능한 패키지 구성 요소를 갖췄는지 검사하는 품질 게이트를 추가하는 것이다.

## Implementation

Implemented:

- `scripts/hwpx/hwpx_package_audit.py`
- `scripts/hwpx/hwpx_template_engine.py audit`

The audit module is read-only and does not mutate HWPX packages.

Checks:

- file exists
- ZIP open
- XML parse
- section entries
- expected text values
- placeholder remaining
- `Contents/content.hpf`
- `META-INF/container.xml`
- manifest items
- spine itemrefs
- document metadata
- `Preview/PrvText.txt`
- BinData image inventory
- XML image reference counts

Modes:

- non-strict: structural gaps are reported as warnings when the file is still parseable
- strict: missing package completeness entries such as metadata, preview, manifest, or container fail the audit

## Test Subject

Generated fresh in:

```text
tmp/hwpx_p39_audit/audit_subject.hwpx
```

Job:

```text
tmp/hwpx_p39_audit/audit_job.json
```

The subject document included:

- metadata title: `P39 Audit Subject`
- metadata creator: `office-analysis-engine`
- paragraphs:
  - `P39 audit paragraph one`
  - `P39 audit paragraph two`
- generated table:
  - `항목`, `값`
  - `audit`, `PASS`
  - `quality`, `gate`
- generated preview text
- repaired manifest/spine
- repaired container rootfile

## Audit Results

Strict single-file audit:

```text
command: python scripts/hwpx/hwpx_package_audit.py audit --strict
status: PASS
zip_ok: true
xml_ok: true
section_entries: 1
content_hpf: true
container_xml: true
preview_text: true
manifest_spine: PASS
metadata: PASS
placeholder_remaining: false
missing_expected_values: []
```

Template-engine wrapper audit:

```text
command: python scripts/hwpx/hwpx_template_engine.py audit --input-dir tmp/hwpx_p39_audit --glob audit_subject.hwpx --strict
status: PASS
file_count: 1
pass_count: 1
warn_count: 0
fail_count: 0
```

Failure case:

```text
case: missing expected value
expected: THIS_VALUE_SHOULD_BE_MISSING
status: FAIL
failure check: expected_values
output: tmp/hwpx_p39_audit/audit_missing_expected_report.json
```

The failure case proves that the audit gate fails when caller-declared content is absent even if the package structure is otherwise valid.

## Java Parser Roundtrip

Target:

```text
tmp/hwpx_p39_audit/audit_subject.hwpx
```

Result:

```text
parse_status: PASS
paragraph_count: 4
table_count: 1
semantic_sections_count: 0
extracted_fields_count: 0
diagnostics_exists: true
quality_score: 7
warning_count: 0
error_count: 0
errors: []
```

Java parser roundtrip confirms the audit subject remains compatible with the existing parser after metadata, manifest, preview, paragraph, and table generation.

## Conclusion

P39 result:

```text
PASS
```

The direct writer now has a reusable package completeness audit that can be used as a quality gate after compose/render operations.

## Remaining Work

- Add audit integration to API endpoints when HWPX composition is promoted beyond CLI.
- Add golden fixture regression once generated HWPX samples become stable fixtures.
- Extend audit rules when multi-section and visible image insertion become mandatory output profiles.

## Next Step

Recommended next development:

```text
P40: HWPX compose regression suite and golden job profiles
```

This should validate representative generated documents across paragraph, table, image, metadata, manifest, preview, and parser roundtrip scenarios.
