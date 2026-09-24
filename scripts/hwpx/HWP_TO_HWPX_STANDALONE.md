# Standalone HWP to HWPX Converter

This tool converts binary `.hwp` files to valid text-only `.hwpx` packages
without launching Hancom Office, COM automation, GUI automation, or an external
converter.

## Install

```powershell
python -m pip install -r scripts\hwpx\hwp_to_hwpx_requirements.txt
```

## Single File

```powershell
scripts\hwpx\hwp2hwpx-standalone.cmd input.hwp output.hwpx --strict-quality
```

Use `--embed-original` when the output must carry the byte-exact source HWP
for preservation while still exposing AI-readable HWPX/XML text:

```powershell
scripts\hwpx\hwp2hwpx-standalone.cmd input.hwp output.hwpx --embed-original --report-json report.json
```

This writes the original file to `Original/original.hwp` inside the `.hwpx`
ZIP and records `Preview/OriginalManifest.json` with the source file name,
size, and SHA-256. The generated XML remains a text-only derivative; it is not
claimed to be a visual-identical HWPX conversion.

Use `--fidelity-policy strict` when the run must reject any HWP feature that
the standalone converter cannot fully reconstruct yet:

```powershell
scripts\hwpx\hwp2hwpx-standalone.cmd input.hwp output.hwpx --fidelity-policy strict --report-json report.json
```

## Batch Directory

```powershell
scripts\hwpx\hwp2hwpx-standalone.cmd input_dir output_dir --strict-quality --existing-policy fail
```

For operational reports:

```powershell
scripts\hwpx\hwp2hwpx-standalone.cmd input_dir output_dir --report-json report.json --report-csv report.csv --strict-quality
```

For large batches, use parallel workers:

```powershell
scripts\hwpx\hwp2hwpx-standalone.cmd input_dir output_dir --workers 4 --existing-policy skip --report-json report.json --report-csv report.csv
```

The converter always supports file logging. If `--log-file` is omitted, CLI
runs write `hwp2hwpx.log` under the output path.

```powershell
scripts\hwpx\hwp2hwpx-standalone.cmd input_dir output_dir --workers 4 --log-file logs\hwp2hwpx.log --log-level INFO
```

CLI runs also write JSONL audit records unless `--no-audit-log` is used. Use
forensic audit mode when you need hashes, gates, validation details, fidelity
risks, and batch item rows:

```powershell
scripts\hwpx\hwp2hwpx-standalone.cmd input_dir output_dir --audit-level forensic --audit-log logs\hwp2hwpx_audit.jsonl
```

For realtime folder monitoring, use the dedicated watcher. It updates the
summary JSON/Markdown on every scan cycle and appends cycle/item rows to the
audit JSONL immediately after each conversion:

```powershell
python scripts\hwpx\hwp_realtime_audit_watch.py input_dir output_dir `
  --interval-sec 2 `
  --audit-log logs\hwp_realtime_audit.jsonl `
  --audit-level forensic `
  --summary-json logs\hwp_realtime_summary.json `
  --summary-md logs\hwp_realtime_summary.md
```

Preview a large job without converting:

```powershell
scripts\hwpx\hwp2hwpx-standalone.cmd input_dir output_dir --dry-run --existing-policy skip --report-json plan.json --job-id nightly-001
```

There is also a convenience wrapper for repeatable bulk runs:

```powershell
scripts\hwpx\hwp2hwpx-bulk.cmd input_dir output_dir --workers 4
```

## Output Collision Policy

- `fail`: default. Do not touch an existing output file.
- `skip`: leave existing output in place and mark that file as skipped.
- `rename`: write to the next available name such as `sample_1.hwpx`.
- `overwrite`: replace the existing output only after the new package validates.

## Quality Gate

Use `--expected-text` to require important text in the converted result:

```powershell
scripts\hwpx\hwp2hwpx-standalone.cmd input.hwp output.hwpx --expected-text 건축법 --expected-text 시행규칙 --strict-quality
```

The converter writes a JSON report when `--report-json` is provided.
Use `--report-csv` for a spreadsheet-friendly summary. Reports include input
and output size plus SHA-256 hashes for integrity checks.

Audit logs include a `report_sha256` digest so downstream systems can detect
report tampering or accidental mutation.

Every successful conversion also runs a built-in round-trip text gate. The
converter reads text back from the generated HWPX `Contents/section*.xml`
entries and compares it with the HWP BodyText extraction. If source text is
missing from the HWPX, the conversion fails and the output is not promoted.

When HWP `TABLE` controls are detected, the converter now reconstructs table
text into HWPX `hp:tbl` nodes using one extracted text paragraph per row. The
report includes `table_reconstruction` with the reconstructed table count. Exact
cell geometry, borders, spans, and original dimensions are still reported as
fidelity risks until those HWP records are fully decoded.

The first native table-detail decoder reads source row and column counts from
each HWP `TABLE` record. These values are reported under
`feature_inventory.table_shapes` and `table_reconstruction.table_shapes`, and
serve as the baseline for later cell-span, border, and dimension reconstruction.

## Fidelity Gate

The converter inventories HWP BodyText record tags and `BinData` streams before
writing output. The report includes `fidelity_gate` and `feature_inventory`.

- `--fidelity-policy text`: default. Build a valid text-only HWPX and record
  unsupported HWP records as fidelity risks.
- `--fidelity-policy audit`: same output behavior as `text`, with explicit
  audit intent in reports.
- `--fidelity-policy strict`: fail without writing output when tables, images,
  embedded objects, shapes, rich styles, or other unsupported records are found.

This keeps the converter independent from Hancom while preventing silent
claims of full layout fidelity.

`--embed-original` does not mutate the source document. It packages the exact
HWP bytes next to the generated text-only HWPX content so downstream AI systems
can read XML text while audits can still recover and hash-check the original.

## Diagnostics

Small diagnostic scripts live under `scripts\hwpx\diagnostics`. Use them when a
file fails conversion, when a batch must be checked before running, or when a
warning needs to be traced to one isolated gate.

Run the full diagnostic chain:

```powershell
python scripts\hwpx\diagnostics\run_hwp_diagnostics.py input.hwp --out-dir tmp\hwp_diag --report-json tmp\hwp_diag\summary.json
```

Run individual probes:

```powershell
python scripts\hwpx\diagnostics\00_input_signature.py input.hwp --report-json tmp\hwp_diag\00_input_signature.json
python scripts\hwpx\diagnostics\01_extract_inventory.py input.hwp --report-json tmp\hwp_diag\01_extract_inventory.json
python scripts\hwpx\diagnostics\02_fidelity_gate.py input.hwp --policy audit --report-json tmp\hwp_diag\02_fidelity_gate.json
python scripts\hwpx\diagnostics\03_convert_smoke.py input.hwp tmp\hwp_diag\smoke.hwpx --fidelity-policy audit --report-json tmp\hwp_diag\03_convert_smoke.json
python scripts\hwpx\diagnostics\06_roundtrip_text_probe.py input.hwp tmp\hwp_diag\smoke.hwpx --report-json tmp\hwp_diag\06_roundtrip_text_probe.json
python scripts\hwpx\diagnostics\04_audit_log_probe.py input.hwp tmp\hwp_diag\audit_probe.hwpx --audit-log tmp\hwp_diag\audit.jsonl --report-json tmp\hwp_diag\04_audit_log_probe.json
python scripts\hwpx\diagnostics\05_batch_plan_probe.py input_dir output_dir --pattern *.hwp --report-json tmp\hwp_diag\05_batch_plan_probe.json
```

Statuses are intentionally separated:

- `PASS`: the checked layer is valid.
- `WARN`: conversion can continue, but the report found fidelity risk such as
  tables, controls, page definitions, embedded data, or other unsupported HWP
  records.
- `FAIL`: the checked layer has a blocking error such as an invalid input
  signature, extraction failure, invalid HWPX package, missing source text in
  the converted HWPX, or missing audit output.

## Batch Failure Handling

Batch conversion records a per-file `FAIL` row if one document cannot be
converted, then continues with the next file. Use `--fail-fast` when the batch
should stop immediately after the first failure.

`--workers N` enables parallel conversion. When `--fail-fast` is used, the
converter processes sequentially so the first failure can stop the batch
deterministically.

`--dry-run` writes a conversion plan with target paths, output paths, existing
file actions, input size, and input SHA-256 without creating HWPX files.

## Python SDK

Import `hwp_to_hwpx_sdk` from `scripts/hwpx` when embedding the converter in
another Python program:

```python
from pathlib import Path
from hwp_to_hwpx_sdk import HwpToHwpxConverter, HwpToHwpxOptions

options = HwpToHwpxOptions.from_values(
    expected_texts=["건축법", "시행규칙"],
    strict_quality=True,
    fidelity_policy="strict",
    embed_original=True,
    existing_policy="fail",
    workers=4,
    log_path="logs/hwp2hwpx.log",
    audit_log_path="logs/hwp2hwpx_audit.jsonl",
    audit_level="forensic",
)

converter = HwpToHwpxConverter(options)
report = converter.convert_file(Path("input.hwp"), Path("output.hwpx"))
converter.write_reports(report, json_path="report.json", csv_path="report.csv")
```

For batch jobs:

```python
report = converter.convert_directory("input_dir", "output_dir")
```

Use `convert_auto()` when the caller may pass either a file or a directory.
Use `plan_directory()` for a dry-run plan before starting a large conversion.
