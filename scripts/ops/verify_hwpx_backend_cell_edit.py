"""Backend cell read/write/edit verification baseline runner.

Runs one real safe-HWPX cell replace scenario and validates:
- output creation
- source immutability
- verify7 PASS
- output reread matches replacement text
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import uuid
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.cell_save_pipeline import save_cell_edits  # noqa: E402
from scripts.hwpx.web_office.edit_command_model import (  # noqa: E402
    make_set_cell_text_command,
)
from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view,
)

TASK_NAME = "HWPX-BACKEND-CELL-VERIFICATION-SCRIPT-40"
SAFE_FIXTURE = PR / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"
LOCAL_TMP_ROOT = Path(tempfile.gettempdir()) / "hwpx-web-office"
TARGET_CELL_ID = "cell_t_s0_000_r3_c0"
REPLACE_AFTER = "CELL_VERIFY_OK_005"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> dict:
    if not SAFE_FIXTURE.is_file():
        return {
            "task": TASK_NAME,
            "verdict": "SKIP",
            "reason": "safe fixture missing",
            "fixture": str(SAFE_FIXTURE.relative_to(PR)),
        }

    source_sha_before = _sha(SAFE_FIXTURE)
    source_mtime_before = SAFE_FIXTURE.stat().st_mtime_ns
    doc = import_hwpx_as_ro_view(SAFE_FIXTURE)
    target = next((c for c in doc.cells if c.cellId == TARGET_CELL_ID), None)
    if target is None:
        return {
            "task": TASK_NAME,
            "verdict": "FAIL",
            "fixture": str(SAFE_FIXTURE.relative_to(PR)),
            "reason": "target cell missing",
        }
    table_index_by_id = {table.tableId: idx for idx, table in enumerate(doc.tables)}
    table_index = table_index_by_id.get(target.tableId)
    if table_index is None:
        return {
            "task": TASK_NAME,
            "verdict": "FAIL",
            "fixture": str(SAFE_FIXTURE.relative_to(PR)),
            "reason": "target table index missing",
        }

    findings: list[dict] = []
    LOCAL_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    td = LOCAL_TMP_ROOT / f"hwpx_cell_verify_{uuid.uuid4().hex}"
    td.mkdir(parents=True, exist_ok=False)
    out = td / "cell_verify_out.hwpx"

    cmd = make_set_cell_text_command(
        cell_id=target.cellId,
        table_index=table_index,
        before=target.text,
        after=REPLACE_AFTER,
        source_document_hash=doc.sourceDocumentHash,
    )
    res = save_cell_edits(
        source_path=SAFE_FIXTURE,
        output_path=out,
        command_log=[cmd],
        project_root=PR,
        dry_run_only=False,
    )

    if res.get("verdict") != "PASS":
        findings.append({
            "code": "PIPELINE_NOT_PASS",
            "level": "FAIL",
            "detail": res.get("verdict"),
        })
    if res.get("outputCreated") is not True:
        findings.append({"code": "OUTPUT_NOT_CREATED", "level": "FAIL"})
    if res.get("sourceUnchanged") is not True:
        findings.append({"code": "SOURCE_MUTATED_FLAG", "level": "FAIL"})

    verify7 = res.get("verify7") or {}
    if verify7.get("verdict") != "PASS":
        findings.append({
            "code": "VERIFY7_NOT_PASS",
            "level": "FAIL",
            "detail": verify7,
        })

    if out.is_file():
        out_doc = import_hwpx_as_ro_view(out)
        out_cell = next((c for c in out_doc.cells if c.cellId == target.cellId), None)
        if out_cell is None:
            findings.append({"code": "OUTPUT_CELL_MISSING", "level": "FAIL"})
        elif out_cell.text != REPLACE_AFTER:
            findings.append({
                "code": "OUTPUT_TEXT_NOT_APPLIED",
                "level": "FAIL",
                "detail": out_cell.text,
            })
    else:
        findings.append({"code": "OUTPUT_FILE_MISSING", "level": "FAIL"})

    if _sha(SAFE_FIXTURE) != source_sha_before:
        findings.append({"code": "SOURCE_SHA_CHANGED", "level": "FAIL"})
    if SAFE_FIXTURE.stat().st_mtime_ns != source_mtime_before:
        findings.append({"code": "SOURCE_MTIME_CHANGED", "level": "FAIL"})

    return {
        "task": TASK_NAME,
        "fixture": str(SAFE_FIXTURE.relative_to(PR)),
        "targetCell": target.cellId,
        "targetTable": target.tableId,
        "targetRow": target.row,
        "targetCol": target.col,
        "beforeText": target.text,
        "afterText": REPLACE_AFTER,
        "paragraphCount": len(doc.paragraphs),
        "tableCount": len(doc.tables),
        "cellCount": len(doc.cells),
        "sourceUnchanged": not any(
            f["code"] in {"SOURCE_MUTATED_FLAG", "SOURCE_SHA_CHANGED", "SOURCE_MTIME_CHANGED"}
            for f in findings
        ),
        "findings": findings,
        "verdict": "PASS" if not findings else "FAIL",
    }


def main() -> int:
    payload = verify()
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
