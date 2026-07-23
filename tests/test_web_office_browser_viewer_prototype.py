"""WEB-OFFICE-BROWSER-VIEWER-PROTOTYPE-01 계약 테스트.

RO-VIEW RenderPayload 를 viewer_core.mjs (node) 로 실 렌더링한 HTML 이
시방서 검증 항목을 충족하는지 검증한다. 편집 UI/save/edit-command 부재
정적 검사 포함.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
import sqlite3
import tempfile
from pathlib import Path
import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view)
from scripts.hwpx.web_office.render_payload import (  # noqa: E402
    build_render_payload)
from scripts.ops.audit_web_office_browser_viewer_prototype import (  # noqa: E402
    audit, VIEWER_DIR, SMOKE_JS, FORBIDDEN_HTML_TOKENS,
    FORBIDDEN_SRC_TOKENS,
)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _node_ok() -> bool:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                                          text=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _resolve_fixtures(limit: int = 3) -> list[Path]:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        return []
    conn = sqlite3.connect(db)
    rows = conn.execute("""
        SELECT d.source_path FROM hwpx_documents d
        JOIN document_classifications c ON c.document_id=d.document_id
        WHERE d.inventory_status='FOUND'
          AND c.document_type='fillable_form'
          AND d.file_size BETWEEN 30000 AND 120000
        ORDER BY d.first_seen_at LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [PR / r[0] for r in rows if (PR / r[0]).is_file()]


NODE_OK = _node_ok()
FIXTURES = _resolve_fixtures(3)


def test_viewer_files_exist():
    for rel in [
        "viewer_core.mjs", "index.html", "render_smoke.mjs",
        "components/WebOfficeViewer.tsx",
        "components/WebOfficeTableBlock.tsx",
        "components/WebOfficeParagraphBlock.tsx",
        "components/WebOfficePayloadSummary.tsx",
    ]:
        assert (VIEWER_DIR / rel).is_file(), f"missing {rel}"


def test_viewer_source_has_no_forbidden_tokens():
    files = [
        VIEWER_DIR / "viewer_core.mjs",
        VIEWER_DIR / "index.html",
        VIEWER_DIR / "render_smoke.mjs",
        VIEWER_DIR / "components/WebOfficeViewer.tsx",
        VIEWER_DIR / "components/WebOfficeTableBlock.tsx",
        VIEWER_DIR / "components/WebOfficeParagraphBlock.tsx",
        VIEWER_DIR / "components/WebOfficePayloadSummary.tsx",
    ]
    for p in files:
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_SRC_TOKENS:
            assert tok not in src, f"{p.name} has forbidden: {tok}"


@pytest.mark.skipif(not NODE_OK, reason="node not available")
@pytest.mark.skipif(len(FIXTURES) < 1, reason="need ≥1 fixture")
def test_render_sample_via_node_produces_html(tmp_path):
    f = FIXTURES[0]
    doc = import_hwpx_as_ro_view(f)
    payload = build_render_payload(doc)
    pj = tmp_path / "payload.json"
    pj.write_text(json.dumps(payload, ensure_ascii=False),
                          encoding="utf-8")
    r = subprocess.run(["node", str(SMOKE_JS), str(pj)],
                                      capture_output=True, text=True,
                                      timeout=30, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    html = r.stdout
    assert "<table" in html
    assert "wo-paragraph" in html
    assert "wo-cell" in html
    assert 'data-editable="false"' in html
    for tok in FORBIDDEN_HTML_TOKENS:
        assert tok.lower() not in html.lower(), (
            f"forbidden token in html: {tok}")


@pytest.mark.skipif(not NODE_OK, reason="node not available")
@pytest.mark.skipif(len(FIXTURES) < 1, reason="need ≥1 fixture")
def test_merged_cell_rendered_as_rowspan_or_colspan(tmp_path):
    f = FIXTURES[0]
    doc = import_hwpx_as_ro_view(f)
    payload = build_render_payload(doc)
    pj = tmp_path / "payload.json"
    pj.write_text(json.dumps(payload, ensure_ascii=False),
                          encoding="utf-8")
    r = subprocess.run(["node", str(SMOKE_JS), str(pj)],
                                      capture_output=True, text=True,
                                      timeout=30, encoding="utf-8")
    html = r.stdout
    has_merged = any(c.colSpan > 1 or c.rowSpan > 1 for c in doc.cells)
    if has_merged:
        assert ('rowspan=' in html.lower()
                    or 'colspan=' in html.lower())


@pytest.mark.skipif(not NODE_OK, reason="node not available")
@pytest.mark.skipif(len(FIXTURES) < 1, reason="need ≥1 fixture")
def test_source_sha_and_mtime_unchanged_after_render(tmp_path):
    f = FIXTURES[0]
    sha_before = _sha(f); mt_before = f.stat().st_mtime_ns
    doc = import_hwpx_as_ro_view(f)
    payload = build_render_payload(doc)
    pj = tmp_path / "payload.json"
    pj.write_text(json.dumps(payload, ensure_ascii=False),
                          encoding="utf-8")
    subprocess.run(["node", str(SMOKE_JS), str(pj)],
                            capture_output=True, text=True,
                            timeout=30, encoding="utf-8")
    assert _sha(f) == sha_before
    assert f.stat().st_mtime_ns == mt_before


def test_index_html_loads_via_editor_bridge_module_only():
    """브라우저는 editor_ui_bridge.mjs 모듈 경유로만 로드한다(모듈형 전환
    이후 계약 — 정적 payload.json 프로토타입은 폐기됨). HWPX XML 직접
    파싱은 여전히 금지."""
    src = (VIEWER_DIR / "index.html").read_text(encoding="utf-8")
    assert 'from "./editor_ui_bridge.mjs"' in src
    assert "mountWebOfficeEditor" in src
    # HWPX XML 직접 파싱 금지 — 모듈형 전환 후에도 유효한 안전검사
    forbidden_browser = ["DOMParser", "<hwpx", ".hwpx",
                                          "XMLHttpRequest"]
    for tok in forbidden_browser:
        assert tok not in src, f"index.html parses XML directly: {tok}"


def test_react_components_have_no_editable_inputs():
    """React 컴포넌트에 input/textarea/contentEditable 없음."""
    for name in ("WebOfficeViewer.tsx", "WebOfficeTableBlock.tsx",
                            "WebOfficeParagraphBlock.tsx",
                            "WebOfficePayloadSummary.tsx"):
        src = (VIEWER_DIR / "components" / name).read_text(
            encoding="utf-8")
        for tok in ("<input", "<textarea", "contentEditable",
                            "onSave", "applyEditPlan"):
            assert tok not in src, f"{name} has forbidden: {tok}"


@pytest.mark.skipif(len(FIXTURES) < 1, reason="need ≥1 fixture")
def test_audit_returns_pass():
    out = audit()
    assert out["verdict"] == "PASS", json.dumps(
        out, ensure_ascii=False, indent=2)[:2000]
    assert out["sampleCount"] >= 1
