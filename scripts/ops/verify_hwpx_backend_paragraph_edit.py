"""Backend paragraph read/write/edit verification baseline runner.

Runs one real safe-HWPX paragraph replace scenario and validates:
- output creation
- source immutability
- readback PASS
- verify7 PASS
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

from scripts.hwpx.web_office.para_edit_e2e_pipeline import (  # ruff: ignore[module-import-not-at-top-of-file]
    SCENARIO_REPLACE,
    run_para_edit_e2e,
)
from scripts.hwpx.web_office.ro_view_importer import (  # ruff: ignore[module-import-not-at-top-of-file]
    import_hwpx_as_ro_view,
)

TASK_NAME = "HWPX-BACKEND-PARAGRAPH-VERIFICATION-SCRIPT-39"
SAFE_FIXTURE = PR / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"
LOCAL_TMP_ROOT = Path(tempfile.gettempdir()) / "hwpx-web-office"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_pipeline_result(res: dict) -> list[dict]:
    findings: list[dict] = []
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

    readback = res.get("readback") or {}
    for gate in (
        "V1_RANGE_POSITION_OK",
        "V4_CHARPR_PRESERVED",
        "V7_READBACK_MATCH",
    ):
        if readback.get(gate) != "PASS":
            findings.append({
                "code": f"{gate}_FAIL",
                "level": "FAIL",
                "detail": readback.get(gate),
            })
    return findings


def _check_output_paragraph(out: Path, target_paragraph_id: str, after_text: str) -> list[dict]:
    if not out.is_file():
        return [{"code": "OUTPUT_FILE_MISSING", "level": "FAIL"}]
    out_doc = import_hwpx_as_ro_view(out)
    out_par = next(
        (p for p in out_doc.paragraphs if p.paragraphId == target_paragraph_id),
        None,
    )
    if out_par is None:
        return [{"code": "OUTPUT_PARAGRAPH_MISSING", "level": "FAIL"}]
    if not out_par.text.startswith(after_text):
        return [{"code": "OUTPUT_TEXT_NOT_APPLIED", "level": "FAIL", "detail": out_par.text}]
    return []


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
    target = next(
        (p for p in doc.paragraphs if p.paragraphId == "par_t_s0_000_r0_c0_p0"),
        None,
    )
    if target is None:
        return {
            "task": TASK_NAME,
            "verdict": "FAIL",
            "fixture": str(SAFE_FIXTURE.relative_to(PR)),
            "reason": "target paragraph missing",
        }

    findings: list[dict] = []
    after_text = "Q"

    LOCAL_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    td = LOCAL_TMP_ROOT / f"hwpx_paragraph_verify_{uuid.uuid4().hex}"
    td.mkdir(parents=True, exist_ok=False)
    out = td / "paragraph_verify_out.hwpx"
    res = run_para_edit_e2e(
        source_path=SAFE_FIXTURE,
        output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=target.paragraphId,
        range_anchor=0,
        range_focus=1,
        replace_after=after_text,
        allow_writer=True,
    )

    findings.extend(_check_pipeline_result(res))
    findings.extend(_check_output_paragraph(out, target.paragraphId, after_text))

    if _sha(SAFE_FIXTURE) != source_sha_before:
        findings.append({"code": "SOURCE_SHA_CHANGED", "level": "FAIL"})
    if SAFE_FIXTURE.stat().st_mtime_ns != source_mtime_before:
        findings.append({"code": "SOURCE_MTIME_CHANGED", "level": "FAIL"})

    return {
        "task": TASK_NAME,
        "fixture": str(SAFE_FIXTURE.relative_to(PR)),
        "targetParagraph": target.paragraphId,
        "scenario": "REPLACE_TEXT_RANGE",
        "replaceAfter": after_text,
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
