"""P13B tests: browser editor command UI closeout."""

from __future__ import annotations

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
HANDLER = ROOT / "src/main/java/com/haehan/engine/http/HwpxEditorApiHandler.java"
USECASE = ROOT / "src/main/java/com/haehan/engine/usecase/HwpxEditorCommandUseCase.java"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


scripts = _read(SCRIPTS)
styles = _read(STYLES)
handler = _read(HANDLER)
usecase = _read(USECASE)


# 1. parse/upload 전 command 실행 차단 — state.parsed guard
def test_validate_document_guards_parsed_state():
    assert "state.parsed" in scripts, (
        "validateEditorDocument must guard state.parsed before dispatch"
    )


# 2. validateDocument payload dryRun=true
def test_validate_document_dry_run_true():
    assert "validateDocument" in scripts
    idx = scripts.index("validateDocument")
    region = scripts[idx : idx + 500]
    assert (
        "dryRun: true" in region
        or "dryRun !== false" in region
        or "opts.dryRun !== false" in scripts
    ), "validateDocument must always set dryRun: true"


# 3. replaceText payload dryRun=true
def test_replace_text_dry_run_true():
    assert "replaceText" in scripts
    idx = scripts.index("dryRunReplaceText")
    region = scripts[idx : idx + 600]
    assert "dryRun: true" in region or "dryRun !== false" in scripts, (
        "dryRunReplaceText must pass dryRun: true"
    )


# 4. replaceText target.paragraphIndex 필수
def test_replace_text_requires_paragraph_index():
    assert "paragraphIndex" in scripts, "dryRunReplaceText must use paragraphIndex in target"


# 5. replaceText artifact guard 없으면 차단 (P14A: state.artifactId로 업그레이드됨)
def test_replace_text_guards_session_artifact_id():
    idx = scripts.index("dryRunReplaceText")
    region = scripts[idx : idx + 300]
    assert "sessionArtifactId" in region or "state.artifactId" in region, (
        "dryRunReplaceText must guard sessionArtifactId or state.artifactId"
    )


# 6. updateTableCell payload dryRun=true
def test_update_table_cell_dry_run_true():
    assert "dryRunUpdateTableCell" in scripts
    idx = scripts.index("dryRunUpdateTableCell")
    region = scripts[idx : idx + 600]
    assert "dryRun: true" in region or "dryRun !== false" in scripts, (
        "dryRunUpdateTableCell must pass dryRun: true"
    )


# 7. updateTableCell tableIndex/row/col 필수
def test_update_table_cell_requires_table_row_col():
    idx = scripts.index("dryRunUpdateTableCell")
    region = scripts[idx : idx + 400]
    assert "tableIndex" in region, "updateTableCell must use tableIndex"
    assert "row" in region, "updateTableCell must use row"
    assert "col" in region, "updateTableCell must use col"


# 8. updateTableCell artifact guard 없으면 차단 (P14A: state.artifactId로 업그레이드됨)
def test_update_table_cell_guards_session_artifact_id():
    idx = scripts.index("dryRunUpdateTableCell")
    region = scripts[idx : idx + 300]
    assert "sessionArtifactId" in region or "state.artifactId" in region, (
        "dryRunUpdateTableCell must guard sessionArtifactId or state.artifactId"
    )


# 9. dryRun=false 생성 경로 없음 — SCRIPT_5 영역만 검사
def test_no_dry_run_false_in_command_dispatch():
    start = scripts.find("buildEditorCommand")
    script5 = scripts[start:] if start >= 0 else ""
    # opts.dryRun !== false means DEFAULT true — not the same as sending dryRun:false
    # actual false literal only acceptable inside opts check, not as sent value
    suspicious = "dryRun: false" in script5 or '"dryRun":false' in script5
    assert not suspicious, "Command dispatch must never send dryRun=false in P13B"


# 10. raw path/filePath/internalPath 입력 필드 없음
def test_no_raw_path_input_fields():
    raw_ids = ["filePath", "internalPath", "serverPath", "rawPath"]
    found = [r for r in raw_ids if f'id="{r}"' in styles or f"id='{r}'" in styles]
    assert not found, f"No raw path input fields allowed in UI: {found}"


# 11. JS에서 HWPX XML/ZIP 직접 조작 코드 없음 (SCRIPT_5 region)
def test_no_xml_zip_direct_in_script5():
    start = scripts.find("buildEditorCommand")
    script5 = scripts[start:] if start >= 0 else ""
    forbidden = ["BinData/", "Contents/", ".xml", ".rels"]
    found = [f for f in forbidden if f in script5]
    assert not found, f"Script5 must not contain XML/ZIP references: {found}"


# 12. CommandResultPanel GATE_REJECTED 표시
def test_command_result_panel_shows_gate_rejected():
    assert "GATE_REJECTED" in scripts, "renderEditorCommandResult must handle GATE_REJECTED status"
    assert "GATE 거부 사유" in scripts or "rejectionReason" in scripts, (
        "renderEditorCommandResult must show gate rejection reason"
    )


# 13. CommandResultPanel requestId/status/message 표시
def test_command_result_panel_shows_required_fields():
    assert "requestId" in scripts, "CommandResultPanel must show requestId"
    assert "status" in scripts, "CommandResultPanel must show status"
    assert (
        "warningCount" in scripts or "'warningCount'" in scripts or "warnings.length" in scripts
    ), "CommandResultPanel must show warningCount"
    assert "timestamp" in scripts, "CommandResultPanel must show timestamp"


# 14. command 실행 중 중복 실행 차단
def test_command_running_guard_prevents_duplicate_submit():
    assert "state.commandRunning" in scripts, (
        "state.commandRunning must exist for duplicate-submit guard"
    )
    assert "commandRunning = true" in scripts, "commandRunning must be set true before dispatch"
    assert "commandRunning = false" in scripts, (
        "commandRunning must be reset false in finally block"
    )


# 15. 기존 P13A architecture gate PASS 유지
def test_p13a_architecture_gate_still_pass():
    import json
    import subprocess
    import sys
    import tempfile

    gate = ROOT / "scripts" / "audit_hwpx_editor_architecture_gate.py"
    assert gate.exists(), "architecture gate script must exist"
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name
    subprocess.run([sys.executable, str(gate), "--json", out], check=True, capture_output=True)
    result = json.loads(Path(out).read_text(encoding="utf-8"))
    assert result["status"] != "FAIL", (
        f"P13A architecture gate must not FAIL: {[f['rule'] for f in result['findings'] if f['severity'] == 'FAIL']}"
    )
    assert result["p13_readiness"] is True, "p13_readiness must be True"
