"""Runtime smoke for the Web Office editor backend API.

Starts the FastAPI app in a real uvicorn process and verifies load/save over
HTTP against a real HWPX fixture.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE_PATH = "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"
FIXTURE = ROOT / SOURCE_PATH
PASS_VERDICT = "PASS_HWPX_EDITOR_BACKEND_RUNTIME_SMOKE"
FAIL_VERDICT = "FAIL_HWPX_EDITOR_BACKEND_RUNTIME_SMOKE"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request_json(
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 90,
) -> dict[str, Any]:
    if payload is None:
        req = urllib.request.Request(url, method="GET")
    else:
        raw = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=raw,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def _wait_health(base_url: str, proc: subprocess.Popen) -> dict[str, Any]:
    last_error = ""
    for _ in range(80):
        if proc.poll() is not None:
            raise RuntimeError(f"uvicorn exited early: {proc.returncode}")
        try:
            return _request_json(f"{base_url}/api/web-office/health")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"health endpoint did not become ready: {last_error}")


def run_runtime_smoke(
    *,
    project_root: Path = ROOT,
    runtime_output_dir: Path | None = None,
) -> dict[str, Any]:
    from scripts.hwpx.web_office.edit_command_model import (
        make_set_cell_text_command,
    )
    from scripts.hwpx.web_office.ro_view_importer import import_hwpx_as_ro_view

    source_sha_before = _sha(FIXTURE)
    source_mtime_before = FIXTURE.stat().st_mtime_ns
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    out_dir = runtime_output_dir
    if out_dir is None:
        audit_root = project_root / "data" / "audit" / "hwpx_editor_backend_runtime_smoke"
        out_dir = audit_root / f"run_{uuid.uuid4().hex[:12]}"
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    env["HWPX_WEB_OFFICE_API_OUTPUT_DIR"] = str(out_dir)
    log_path = out_dir / "server.log"
    log_handle = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "scripts.hwpx.web_office.editor_api_route:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(project_root),
        env=env,
        stdout=log_handle,
        stderr=log_handle,
    )
    try:
        stage = "health"
        health = _wait_health(base_url, proc)
        stage = "load"
        load = _request_json(f"{base_url}/api/web-office/hwpx-load", {
            "operation": "HWPX_EDITOR_LOAD",
            "sourcePath": SOURCE_PATH,
        })
        load_data = load.get("data") or {}
        doc = load_data.get("documentModel") or {}
        target = next(
            c for c in doc.get("cells", [])
            if c.get("row") == 3 and c.get("col") == 0
        )
        edit_value = "RUNTIME_SMOKE_46_OK"
        cmd = make_set_cell_text_command(
            cell_id=target["cellId"],
            table_index=0,
            before=target.get("text", ""),
            after=edit_value,
            source_document_hash=load_data["sourceDocumentHash"],
        )
        stage = "save"
        save = _request_json(f"{base_url}/api/web-office/cell-save-apply", {
            "operation": "CELL_SAVE_APPLY",
            "requestId": "runtime-smoke-46",
            "sourcePath": SOURCE_PATH,
            "sourceDocumentHash": load_data["sourceDocumentHash"],
            "commandLog": [cmd.to_dict()],
        })
        save_data = save.get("data") or {}
        output_file = out_dir / str(save_data.get("outputFileName", ""))
        stage = "readback"
        out_doc = import_hwpx_as_ro_view(output_file)
        out_cell = next(c for c in out_doc.cells if c.cellId == target["cellId"])
        absolute_leak = str(project_root) in repr(health) + repr(load) + repr(save)
        stage = "absolute_path_reject"
        abs_reject = _request_json(f"{base_url}/api/web-office/hwpx-load", {
            "operation": "HWPX_EDITOR_LOAD",
            "sourcePath": str(FIXTURE.resolve()),
        })
        checks = {
            "healthSuccess": health.get("status") == "SUCCESS",
            "loadSuccess": load.get("status") == "SUCCESS",
            "loadHasCells": bool(doc.get("cells")),
            "loadSafeSourcePath": load_data.get("sourcePath") == SOURCE_PATH,
            "saveSuccess": save.get("status") == "SUCCESS",
            "savePass": save_data.get("verdict") == "PASS",
            "outputCreated": save_data.get("outputCreated") is True,
            "verify7Pass": save_data.get("verify7Verdict") == "PASS",
            "outputPathHidden": "outputPath" not in save_data,
            "outputExists": output_file.is_file(),
            "readbackMatches": out_cell.text == edit_value,
            "sourceUnchanged": (
                _sha(FIXTURE) == source_sha_before
                and FIXTURE.stat().st_mtime_ns == source_mtime_before
            ),
            "absolutePathHidden": not absolute_leak,
            "absolutePathRejected": abs_reject.get("status") == "FAILED",
        }
        verdict = PASS_VERDICT if all(checks.values()) else FAIL_VERDICT
        return {
            "schemaVersion": "hwpx_editor_backend_runtime_smoke_v1",
            "verdict": verdict,
            "checks": checks,
            "http": {
                "baseUrl": base_url,
                "healthStatus": health.get("status"),
                "loadStatus": load.get("status"),
                "saveStatus": save.get("status"),
            },
            "output": {
                "outputFileName": save_data.get("outputFileName"),
                "outputHash": save_data.get("outputHash"),
            },
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        log_handle.close()


def main() -> int:
    try:
        payload = run_runtime_smoke()
    except Exception as exc:
        payload = {
            "schemaVersion": "hwpx_editor_backend_runtime_smoke_v1",
            "verdict": FAIL_VERDICT,
            "error": str(exc),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(payload["verdict"])
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
