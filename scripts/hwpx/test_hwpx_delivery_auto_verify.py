from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hwp_to_hwpx_standalone import write_text_hwpx
from hwpx_delivery_auto_verify import verify_hwpx_delivery


def test_verify_hwpx_delivery_runs_machine_gates_without_hancom(tmp_path: Path) -> None:
    hwpx = tmp_path / "sample.hwpx"
    write_text_hwpx(hwpx, ["본문", "표 셀"])

    report = verify_hwpx_delivery(hwpx, strict=False, hancom="off", work_dir=tmp_path / "verify")
    checks = {item["name"]: item["status"] for item in report["checks"]}

    assert report["status"] in {"PASS", "WARN"}
    assert checks["file_exists"] == "PASS"
    assert checks["zip_open"] == "PASS"
    assert checks["xml_parse"] == "PASS"
    assert checks["hancom_render"] == "WARN"


def test_verify_hwpx_delivery_fails_for_missing_file(tmp_path: Path) -> None:
    report = verify_hwpx_delivery(tmp_path / "missing.hwpx", strict=False, hancom="off", work_dir=tmp_path / "verify")
    checks = {item["name"]: item["status"] for item in report["checks"]}

    assert report["status"] == "FAIL"
    assert checks["file_exists"] == "FAIL"
    assert checks["zip_open"] == "FAIL"
