from pathlib import Path
from zipfile import ZipFile

import hwpxjs_hwp_to_hwpx as adapter
from hwpxjs_hwp_to_hwpx import HWP_OLE_SIGNATURE, convert_with_hwpxjs


def test_convert_with_hwpxjs_uses_short_temp_output(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / (("doc_" + "\uac00" * 80) + ".hwpx")
    input_path.write_bytes(HWP_OLE_SIGNATURE + b"fixture")
    seen: dict[str, str] = {}

    monkeypatch.setattr(
        adapter,
        "discover_hwpxjs",
        lambda: {
            "status": "READY",
            "candidate": {
                "kind": "unit",
                "command": ["unit-hwpxjs"],
                "cwd": None,
                "evidence": "unit",
            },
        },
    )

    def fake_run(command, **_kwargs):
        temp_output = Path(command[-1])
        seen["temp_name"] = temp_output.name
        with ZipFile(temp_output, "w") as zf:
            zf.writestr("mimetype", "application/hwp+zip")
            zf.writestr("Contents/section0.xml", "<root/>")

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return Proc()

    monkeypatch.setattr(adapter.subprocess, "run", fake_run)

    report = convert_with_hwpxjs(input_path, output_path)

    assert report["status"] == "PASS"
    assert output_path.exists()
    assert seen["temp_name"].startswith(".hwpxjs_tmp.")
    assert len(seen["temp_name"]) < 50
