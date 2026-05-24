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
from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view,
)
from scripts.hwpx.web_office.save_apply_bridge import (  # noqa: E402
    apply_cell_save_request,
)


FIXTURE = PR / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frontend_command_log_reaches_backend_writer_readback(tmp_path):
    source_sha_before = _sha(FIXTURE)
    source_mtime_before = FIXTURE.stat().st_mtime_ns
    doc = import_hwpx_as_ro_view(FIXTURE)
    target = next(c for c in doc.cells if c.row == 3 and c.col == 0)
    cmd = make_set_cell_text_command(
        cell_id=target.cellId,
        table_index=0,
        before=target.text,
        after="BRIDGE_43_CELL_OK",
        source_document_hash=doc.sourceDocumentHash,
    )

    response = apply_cell_save_request({
        "operation": "CELL_SAVE_APPLY",
        "requestId": "bridge-43-test",
        "sourcePath": "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx",
        "sourceDocumentHash": doc.sourceDocumentHash,
        "commandLog": [cmd.to_dict()],
    }, project_root=PR, output_dir=tmp_path)

    assert response["verdict"] == "PASS", response
    assert response["outputCreated"] is True
    assert response["sourceUnchanged"] is True
    assert response["verify7Verdict"] == "PASS"

    out_doc = import_hwpx_as_ro_view(Path(response["outputPath"]))
    out_cell = next(c for c in out_doc.cells if c.cellId == target.cellId)
    assert out_cell.text == "BRIDGE_43_CELL_OK"
    assert _sha(FIXTURE) == source_sha_before
    assert FIXTURE.stat().st_mtime_ns == source_mtime_before


def test_save_apply_bridge_rejects_absolute_source_path(tmp_path):
    response = apply_cell_save_request({
        "operation": "CELL_SAVE_APPLY",
        "sourcePath": str(FIXTURE.resolve()),
        "commandLog": [],
    }, project_root=PR, output_dir=tmp_path)
    assert response["verdict"] == "REJECTED"
    assert response["reason"] == "INVALID_REQUEST"
