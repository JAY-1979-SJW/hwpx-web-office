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
from scripts.hwpx.web_office.editor_api_route import (  # noqa: E402
    SCHEMA_VERSION,
    call_cell_save_apply,
    call_health,
    call_hwpx_load,
    create_app,
)


SOURCE_PATH = "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"
FIXTURE = PR / SOURCE_PATH


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_backend_health_contract():
    response = call_health()
    assert response["schemaVersion"] == SCHEMA_VERSION
    assert response["status"] == "SUCCESS"
    assert response["sourceMutationAllowed"] is False
    assert response["data"]["loadEndpoint"] == "/api/web-office/hwpx-load"
    assert response["data"]["saveEndpoint"] == "/api/web-office/cell-save-apply"


def test_backend_load_api_reads_real_hwpx_without_raw_absolute_path():
    response = call_hwpx_load({
        "operation": "HWPX_EDITOR_LOAD",
        "sourcePath": SOURCE_PATH,
    }, project_root=PR)
    assert response["status"] == "SUCCESS", response
    data = response["data"]
    assert data["verdict"] == "PASS"
    assert data["sourcePath"] == SOURCE_PATH
    assert data["sourceDocumentHash"] == _sha(FIXTURE)
    assert data["summary"]["cells"] >= 1
    assert data["documentModel"]["sourceDocumentPath"] == SOURCE_PATH
    assert data["renderPayload"]["sourceRef"]["path"] == SOURCE_PATH
    assert str(PR) not in repr(response)


def test_backend_save_api_writes_real_hwpx_and_hides_output_path(tmp_path):
    load = call_hwpx_load({
        "operation": "HWPX_EDITOR_LOAD",
        "sourcePath": SOURCE_PATH,
    }, project_root=PR)["data"]
    target = next(c for c in load["documentModel"]["cells"]
                  if c["row"] == 3 and c["col"] == 0)
    cmd = make_set_cell_text_command(
        cell_id=target["cellId"],
        table_index=0,
        before=target["text"],
        after="BACKEND_API_45_OK",
        source_document_hash=load["sourceDocumentHash"],
    )

    response = call_cell_save_apply({
        "operation": "CELL_SAVE_APPLY",
        "requestId": "backend-api-45",
        "sourcePath": SOURCE_PATH,
        "sourceDocumentHash": load["sourceDocumentHash"],
        "commandLog": [cmd.to_dict()],
    }, project_root=PR, output_dir=tmp_path)

    assert response["status"] == "SUCCESS", response
    data = response["data"]
    assert data["verdict"] == "PASS"
    assert data["outputCreated"] is True
    assert data["verify7Verdict"] == "PASS"
    assert data["sourceUnchanged"] is True
    assert data["outputFileName"] == "backend-api-45.hwpx"
    assert "outputPath" not in data
    assert str(PR) not in repr(response)
    assert (tmp_path / "backend-api-45.hwpx").is_file()


def test_backend_api_rejects_absolute_load_path():
    response = call_hwpx_load({
        "operation": "HWPX_EDITOR_LOAD",
        "sourcePath": str(FIXTURE.resolve()),
    }, project_root=PR)
    assert response["status"] == "FAILED"
    assert response["data"]["verdict"] == "REJECTED"


def test_fastapi_app_routes_when_dependency_available(tmp_path):
    app = create_app()
    if app is None:
        return
    from fastapi.testclient import TestClient

    client = TestClient(app)
    health = client.get("/api/web-office/health")
    assert health.status_code == 200
    assert health.json()["status"] == "SUCCESS"

    load = client.post("/api/web-office/hwpx-load", json={
        "operation": "HWPX_EDITOR_LOAD",
        "sourcePath": SOURCE_PATH,
    })
    assert load.status_code == 200
    assert load.json()["status"] == "SUCCESS"
