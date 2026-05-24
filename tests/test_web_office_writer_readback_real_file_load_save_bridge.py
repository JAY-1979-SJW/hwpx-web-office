from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.edit_command_model import (  # noqa: E402
    make_set_cell_text_command,
)
from scripts.hwpx.web_office.editor_file_bridge import (  # noqa: E402
    load_and_apply_cell_save,
    load_hwpx_for_editor,
)
from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view,
)


SOURCE_PATH = "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"
FIXTURE = PR / SOURCE_PATH


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_hwpx_load_returns_cells_text_header_and_safe_paths():
    response = load_hwpx_for_editor({
        "operation": "HWPX_EDITOR_LOAD",
        "sourcePath": SOURCE_PATH,
    }, project_root=PR)

    assert response["verdict"] == "PASS", response
    assert response["sourcePath"] == SOURCE_PATH
    assert response["sourceDocumentHash"] == _sha(FIXTURE)
    assert response["documentModel"]["sourceDocumentPath"] == SOURCE_PATH
    assert response["renderPayload"]["sourceRef"]["path"] == SOURCE_PATH
    assert response["renderPayload"]["editable"] is False

    cells = response["documentModel"]["cells"]
    assert cells
    target = next(c for c in cells if c["row"] == 3 and c["col"] == 0)
    assert target["cellId"].startswith("cell_")
    assert isinstance(target["text"], str)
    assert "header" in target
    assert "headerCell" in target
    assert response["summary"]["cells"] == len(cells)
    assert response["summary"]["tables"] >= 1


def test_real_hwpx_load_then_save_writes_output_and_readback(tmp_path):
    sha_before = _sha(FIXTURE)
    mtime_before = FIXTURE.stat().st_mtime_ns
    load_response = load_hwpx_for_editor({
        "operation": "HWPX_EDITOR_LOAD",
        "sourcePath": SOURCE_PATH,
    }, project_root=PR)
    doc = load_response["documentModel"]
    target = next(c for c in doc["cells"] if c["row"] == 3 and c["col"] == 0)
    cmd = make_set_cell_text_command(
        cell_id=target["cellId"],
        table_index=0,
        before=target["text"],
        after="LOAD_SAVE_44_OK",
        source_document_hash=doc["sourceDocumentHash"],
    )

    result = load_and_apply_cell_save(
        {
            "operation": "HWPX_EDITOR_LOAD",
            "sourcePath": SOURCE_PATH,
        },
        {
            "operation": "CELL_SAVE_APPLY",
            "requestId": "load-save-44",
            "sourcePath": SOURCE_PATH,
            "sourceDocumentHash": doc["sourceDocumentHash"],
            "commandLog": [cmd.to_dict()],
        },
        project_root=PR,
        output_dir=tmp_path,
    )

    assert result["verdict"] == "PASS", result
    assert result["load"]["summary"]["cells"] >= 1
    assert result["save"]["verdict"] == "PASS"
    assert result["save"]["outputCreated"] is True
    assert result["save"]["sourceUnchanged"] is True
    assert result["save"]["verify7Verdict"] == "PASS"

    out_doc = import_hwpx_as_ro_view(Path(result["save"]["outputPath"]))
    out_cell = next(c for c in out_doc.cells if c.cellId == target["cellId"])
    assert out_cell.text == "LOAD_SAVE_44_OK"
    assert _sha(FIXTURE) == sha_before
    assert FIXTURE.stat().st_mtime_ns == mtime_before


def test_real_hwpx_load_rejects_absolute_source_path():
    response = load_hwpx_for_editor({
        "operation": "HWPX_EDITOR_LOAD",
        "sourcePath": str(FIXTURE.resolve()),
    }, project_root=PR)
    assert response["verdict"] == "REJECTED"
    assert response["reason"] == "INVALID_REQUEST"
