"""P14A tests: server-side artifactId for browser editor."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# 이 테스트가 검사하는 Java 백엔드(src/main/java/com/haehan/engine/...)는
# 02 저장소 분리(2026-05-22) 이전 시절의 흔적이다 — 33(office-analysis-engine)
# 소관. 2026-09-28 완성도 감사에서 실측 확인. 02↔33 통합 결정 대기.
pytestmark = pytest.mark.skip(
    reason="Java 백엔드(src/main/java/...)는 33 저장소 소관 — 02 분리 이후 범위 밖 (02↔33 통합 결정 대기)"
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/main/java/com/haehan/engine/http/HwpxUploadPageScripts.java"
STYLES = ROOT / "src/main/java/com/haehan/engine/http/HwpxUploadPageStyles.java"
PROXY = ROOT / "src/main/java/com/haehan/engine/http/HwpxProxyHandler.java"
HANDLER = ROOT / "src/main/java/com/haehan/engine/http/HwpxEditorApiHandler.java"
PARSE_RESP = ROOT / "src/main/java/com/haehan/engine/contract/DocumentParseResponse.java"
REGISTRY = ROOT / "src/main/java/com/haehan/engine/artifact/ArtifactRegistry.java"
METADATA = ROOT / "src/main/java/com/haehan/engine/artifact/ArtifactMetadata.java"
ID_GEN = ROOT / "src/main/java/com/haehan/engine/artifact/ArtifactIdGenerator.java"
GATE = ROOT / "scripts/audit_hwpx_editor_architecture_gate.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


scripts = _read(SCRIPTS)
proxy = _read(PROXY)
handler = _read(HANDLER)
parse_resp = _read(PARSE_RESP)
registry = _read(REGISTRY)


# 1. parse/upload 성공 응답에 artifactId 필드가 포함된다
def test_parse_response_includes_artifact_id_field():
    assert "artifactId" in parse_resp, "DocumentParseResponse must have artifactId field"


# 2. artifactId는 빈 값이 아니다 (ArtifactIdGenerator uses UUID)
def test_artifact_id_generator_uses_uuid():
    id_gen = _read(ID_GEN)
    assert "UUID.randomUUID" in id_gen, "ArtifactIdGenerator must use UUID.randomUUID"


# 3. artifactKind가 HWPX_EDITOR_SESSION으로 반환된다
def test_parse_response_includes_artifact_kind():
    assert "HWPX_EDITOR_SESSION" in parse_resp or "HWPX_EDITOR_SESSION" in proxy, (
        "artifactKind HWPX_EDITOR_SESSION must be set in parse response or proxy"
    )


# 4. artifactStatus가 READY로 반환된다
def test_parse_response_includes_artifact_status_ready():
    assert "READY" in parse_resp or "READY" in proxy, (
        "artifactStatus READY must be set in parse response or proxy"
    )


# 5. parse/upload 응답에 raw path/temp path/internal path가 포함되지 않는다
def test_proxy_does_not_leak_raw_paths():
    raw_patterns = ["/home/", "/tmp/", "/var/", "C:\\\\", "tempFile", "tempDir"]
    leaked = [p for p in raw_patterns if p in proxy]
    assert not leaked, f"HwpxProxyHandler must not include raw paths in response: {leaked}"


# 6. 기존 parse/upload response key가 유지된다
def test_existing_parse_response_keys_preserved():
    existing_keys = [
        "schemaVersion",
        "engineVersion",
        "requestId",
        "inputFileName",
        "paragraphs",
        "tables",
        "ok",
        "warningCount",
        "errorCount",
    ]
    missing = [k for k in existing_keys if k not in parse_resp]
    assert not missing, f"DocumentParseResponse must preserve existing keys: {missing}"


# 7. UI state가 parse/upload 응답 artifactId를 저장한다
def test_ui_state_stores_server_artifact_id():
    assert "state.artifactId" in scripts, "SCRIPT must store state.artifactId from parse response"
    assert "data.artifactId" in scripts or "artifactId" in scripts, (
        "loadParsed must extract artifactId from server response"
    )


# 8. validateDocument payload에 artifactId가 포함된다
def test_validate_document_payload_includes_artifact_id():
    assert "buildEditorCommand" in scripts
    # search in the SCRIPT_5 region where command dispatch lives
    s5_start = scripts.find("state.artifactId = null")
    script5 = scripts[s5_start:] if s5_start >= 0 else scripts
    assert "artifactId: state.artifactId" in script5, (
        "buildEditorCommand must use state.artifactId (server artifactId)"
    )


# 9. replaceText payload에 artifactId가 포함된다
def test_replace_text_payload_includes_artifact_id():
    # buildEditorCommand uses state.artifactId, replaceText calls buildEditorCommand
    assert "state.artifactId" in scripts
    assert "dryRunReplaceText" in scripts


# 10. updateTableCell payload에 artifactId가 포함된다
def test_update_table_cell_payload_includes_artifact_id():
    assert "state.artifactId" in scripts
    assert "dryRunUpdateTableCell" in scripts


# 11. artifactId 없이 replaceText 실행이 차단된다
def test_replace_text_blocked_without_artifact_id():
    idx = scripts.index("dryRunReplaceText")
    region = scripts[idx : idx + 400]
    assert "state.artifactId" in region, (
        "dryRunReplaceText must check state.artifactId before dispatch"
    )


# 12. artifactId 없이 updateTableCell 실행이 차단된다
def test_update_table_cell_blocked_without_artifact_id():
    idx = scripts.index("dryRunUpdateTableCell")
    region = scripts[idx : idx + 400]
    assert "state.artifactId" in region, (
        "dryRunUpdateTableCell must check state.artifactId before dispatch"
    )


# 13. artifactId 없이 validateDocument 실행이 차단 또는 명확한 validation error
def test_validate_document_guarded():
    assert "state.parsed" in scripts or "state.artifactId" in scripts, (
        "validateEditorDocument must guard parsed state or artifactId"
    )


# 14. sessionArtifactId만으로 실제 command 실행이 되지 않는다
def test_session_artifact_id_not_source_of_truth():
    s5_start = scripts.find("buildEditorCommand")
    script5 = scripts[s5_start:] if s5_start >= 0 else ""
    assert "artifactId: state.artifactId" in script5, (
        "buildEditorCommand must use state.artifactId, not sessionArtifactId as artifactId"
    )
    assert "artifactId: state.sessionArtifactId" not in script5, (
        "sessionArtifactId must not be used as artifactId in buildEditorCommand"
    )


# 15. dryRun=false 전송 경로가 없다
def test_no_dry_run_false_path():
    s5_start = scripts.find("buildEditorCommand")
    script5 = scripts[s5_start:] if s5_start >= 0 else ""
    assert "dryRun: false" not in script5 and '"dryRun":false' not in script5, (
        "Command dispatch must never send dryRun=false"
    )


# 16. raw path 입력 필드가 없다
def test_no_raw_path_input_fields():
    styles = _read(STYLES)
    raw_ids = ["filePath", "internalPath", "serverPath", "rawPath"]
    found = [r for r in raw_ids if f'id="{r}"' in styles or f"id='{r}'" in styles]
    assert not found, f"No raw path input fields allowed: {found}"


# 17. JS에서 XML/ZIP 직접 조작 코드가 없다 (SCRIPT_5)
def test_no_xml_zip_in_script5():
    start = scripts.find("buildEditorCommand")
    script5 = scripts[start:] if start >= 0 else ""
    forbidden = ["BinData/", "Contents/", ".xml", ".rels"]
    found = [f for f in forbidden if f in script5]
    assert not found, f"Script5 must not contain XML/ZIP references: {found}"


# 18. API가 artifactId 누락 payload를 422로 차단한다
def test_api_rejects_missing_artifact_id():
    assert "MISSING_ARTIFACT_ID" in handler, (
        "HwpxEditorApiHandler must reject missing artifactId with MISSING_ARTIFACT_ID"
    )
    assert "422" in handler or "sendJson(exchange, 422" in handler, (
        "Handler must return 422 for missing artifactId"
    )


# 19. API가 unknown artifactId를 명확한 에러로 차단한다
def test_api_rejects_unknown_artifact_id():
    assert "UNKNOWN_ARTIFACT_ID" in handler, (
        "HwpxEditorApiHandler must reject unknown artifactId with UNKNOWN_ARTIFACT_ID"
    )
    assert "artifactRegistry.exists" in handler or "registry.exists" in handler, (
        "Handler must check artifactId against registry"
    )


# 20. 기존 P13A/P13B architecture gate가 PASS 유지된다
def test_p13_architecture_gate_still_pass():
    assert GATE.exists(), "architecture gate script must exist"
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name
    subprocess.run([sys.executable, str(GATE), "--json", out], check=True, capture_output=True)
    result = json.loads(Path(out).read_text(encoding="utf-8"))
    assert result["status"] != "FAIL", (
        f"P13A/P13B architecture gate must not FAIL: {[f['rule'] for f in result['findings'] if f['severity'] == 'FAIL']}"
    )
    assert result["p13_readiness"] is True
