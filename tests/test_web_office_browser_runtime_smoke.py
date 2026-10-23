"""WEB-OFFICE-BROWSER-RUNTIME-SMOKE-01 계약 테스트.

audit 가 검증한 항목을 분해하여 회귀 잠금한다.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import pytest

from bs4 import BeautifulSoup

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.ops.audit_web_office_browser_runtime_smoke import (  # noqa: E402
    audit, SAMPLE_JSON, RUNTIME_SMOKE_JS, VIEWER_DIR,
)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _node_ok() -> bool:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                                          text=True, encoding="utf-8", errors="replace", timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


NODE_OK = _node_ok()


def test_sample_payload_fixture_exists_and_is_ro():
    assert SAMPLE_JSON.is_file()
    obj = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))
    assert obj["editable"] is False
    assert obj["sourceRef"]["sha256"]
    assert "warnings" in obj
    assert obj["payloadVersion"]


def test_runtime_smoke_script_exists():
    assert RUNTIME_SMOKE_JS.is_file()


@pytest.mark.skipif(not NODE_OK, reason="node not available")
def test_runtime_smoke_renders_html_with_4_panels():
    r = subprocess.run(["node", str(RUNTIME_SMOKE_JS)],
                                      capture_output=True, text=True,
                                      timeout=30, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    soup = BeautifulSoup(r.stdout, "html.parser")
    assert len(soup.select(".wo-toolbar")) >= 1
    assert len(soup.select(".wo-left-panel")) >= 1
    assert len(soup.select(".wo-center")) >= 1
    assert len(soup.select(".wo-right-panel")) >= 1


@pytest.mark.skipif(not NODE_OK, reason="node not available")
def test_runtime_smoke_renders_paragraph_table_cell_merged():
    r = subprocess.run(["node", str(RUNTIME_SMOKE_JS)],
                                      capture_output=True, text=True,
                                      timeout=30, encoding="utf-8")
    soup = BeautifulSoup(r.stdout, "html.parser")
    assert len(soup.select("table.wo-table")) >= 1
    assert len(soup.select(".wo-paragraph")) >= 1
    assert len(soup.select("td.wo-cell")) >= 1
    merged = [c for c in soup.select("td.wo-cell")
                      if c.has_attr("rowspan") or c.has_attr("colspan")]
    assert len(merged) >= 1, "merged cells (rowspan/colspan) missing"


@pytest.mark.skipif(not NODE_OK, reason="node not available")
def test_runtime_smoke_no_editable_dom():
    r = subprocess.run(["node", str(RUNTIME_SMOKE_JS)],
                                      capture_output=True, text=True,
                                      timeout=30, encoding="utf-8")
    soup = BeautifulSoup(r.stdout, "html.parser")
    assert soup.find_all("input") == []
    assert soup.find_all("textarea") == []
    ce_true = [t for t in soup.find_all(attrs={"contenteditable": True})
                        if str(t.get("contenteditable", "")).lower() == "true"]
    assert ce_true == []
    assert soup.find_all("button") == []
    # data-editable="false" 다수 부착
    assert len(soup.select('[data-editable="false"]')) >= 4


@pytest.mark.skipif(not NODE_OK, reason="node not available")
def test_runtime_smoke_no_writer_or_save_tokens_in_html():
    r = subprocess.run(["node", str(RUNTIME_SMOKE_JS)],
                                      capture_output=True, text=True,
                                      timeout=30, encoding="utf-8")
    text = r.stdout.lower()
    for tok in ("save", "apply", "edit-command",
                            "apply_edit_plan", "writer"):
        assert tok not in text, f"forbidden token in html: {tok}"


def test_source_hwpx_sha_and_mtime_unchanged():
    sample = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))
    rel = sample["sourceRef"]["path"]
    src = Path(rel) if Path(rel).is_absolute() else (PR / rel)
    if not src.is_file():
        pytest.skip(f"source hwpx not found: {src}")
    sha_before = _sha(src)
    mt_before = src.stat().st_mtime_ns
    # audit 호출 — 내부에서 node 실행 및 http server smoke 수행
    out = audit()
    assert out["verdict"] == "PASS"
    assert _sha(src) == sha_before
    assert src.stat().st_mtime_ns == mt_before


def test_no_unexpected_hwpx_output_in_viewer_dir():
    assert list(VIEWER_DIR.glob("*.hwpx")) == []


def test_audit_returns_pass():
    out = audit()
    assert out["verdict"] == "PASS", json.dumps(
        out, ensure_ascii=False, indent=2)[:2000]
