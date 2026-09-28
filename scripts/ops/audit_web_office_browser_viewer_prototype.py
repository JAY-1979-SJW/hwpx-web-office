"""WEB-OFFICE-BROWSER-VIEWER-PROTOTYPE-01 감사 스크립트.

RO-VIEW 변환기로 RenderPayload 3건을 생성해 임시 파일로 저장한 뒤,
node 로 frontend/web_office_viewer/render_smoke.mjs 를 실행해 실제 HTML
렌더 결과를 받아 다음을 검증한다:
- 최소 1건 화면 렌더 PASS
- paragraph / table / cell DOM 노드 존재
- 병합 셀(rowspan/colspan 또는 data-has-merged) 표시
- editable=false 유지 (data-editable="false")
- input / textarea / contenteditable / save 등 금지 토큰 부재
- 프런트 소스 파일에 apply_edit_plan / writer 토큰 부재
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view)
from scripts.hwpx.web_office.render_payload import (  # noqa: E402
    build_render_payload)

VIEWER_DIR = PR / "frontend/web_office_viewer"
SMOKE_JS = VIEWER_DIR / "render_smoke.mjs"

FORBIDDEN_HTML_TOKENS = [
    "<input", "<textarea", 'contenteditable="true"', "contentEditable",
    "onSave", "applyEditPlan", "/save", "edit-command",
]

FORBIDDEN_SRC_TOKENS = [
    "apply_edit_plan", "hwpx_edit_tool", "EditCommand",
    "save-button", "<input", "<textarea",
]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


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


def _check_html(html: str) -> list[dict]:
    findings: list[dict] = []
    for tok in FORBIDDEN_HTML_TOKENS:
        if tok.lower() in html.lower():
            findings.append({"code": "FORBIDDEN_HTML_TOKEN",
                                      "level": "FAIL", "detail": tok})
    # 필수: data-editable="false" 최소 1개
    if 'data-editable="false"' not in html:
        findings.append({"code": "EDITABLE_FALSE_MISSING",
                                  "level": "FAIL", "detail": None})
    return findings


def _node_available() -> bool:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                                          text=True, encoding="utf-8", errors="replace", timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _render_via_node(payload_path: Path) -> tuple[str, int]:
    r = subprocess.run(
        ["node", str(SMOKE_JS), str(payload_path)],
        capture_output=True, text=True, timeout=30,
        encoding="utf-8")
    return r.stdout, r.returncode


def _audit_source_files() -> list[dict]:
    findings: list[dict] = []
    src_files = [
        VIEWER_DIR / "viewer_core.mjs",
        VIEWER_DIR / "index.html",
        VIEWER_DIR / "render_smoke.mjs",
        VIEWER_DIR / "components/WebOfficeViewer.tsx",
        VIEWER_DIR / "components/WebOfficeTableBlock.tsx",
        VIEWER_DIR / "components/WebOfficeParagraphBlock.tsx",
        VIEWER_DIR / "components/WebOfficePayloadSummary.tsx",
    ]
    for p in src_files:
        if not p.is_file():
            findings.append({"code": "VIEWER_FILE_MISSING",
                                      "level": "FAIL",
                                      "detail": str(p.relative_to(PR))})
            continue
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_SRC_TOKENS:
            if tok in src:
                findings.append({"code": "FORBIDDEN_SRC_TOKEN",
                                          "level": "FAIL",
                                          "detail": f"{p.name}: {tok}"})
    return findings


def audit() -> dict:
    if not _node_available():
        return {"task": "WEB-OFFICE-BROWSER-VIEWER-PROTOTYPE-01",
                    "verdict": "FAIL",
                    "reason": "node not available"}

    fixtures = _resolve_fixtures(3)
    if len(fixtures) < 1:
        return {"task": "WEB-OFFICE-BROWSER-VIEWER-PROTOTYPE-01",
                    "verdict": "FAIL",
                    "reason": f"need ≥1 fixture, got {len(fixtures)}"}

    per_file: list[dict] = []
    src_findings = _audit_source_files()

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        for f in fixtures:
            sha_before = _sha(f)
            mtime_before = f.stat().st_mtime_ns
            doc = import_hwpx_as_ro_view(f)
            payload = build_render_payload(doc)
            payload_json = td_path / f"{doc.documentId}.json"
            payload_json.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            html, rc = _render_via_node(payload_json)
            findings = _check_html(html)
            if rc != 0:
                findings.append({"code": "NODE_NONZERO_EXIT",
                                          "level": "FAIL", "detail": rc})
            if "<table" not in html and doc.tables:
                findings.append({"code": "TABLE_NOT_RENDERED",
                                          "level": "FAIL", "detail": None})
            if "wo-paragraph" not in html and doc.paragraphs:
                findings.append({"code": "PARAGRAPH_NOT_RENDERED",
                                          "level": "FAIL", "detail": None})
            if "wo-cell" not in html and doc.cells:
                findings.append({"code": "CELL_NOT_RENDERED",
                                          "level": "FAIL", "detail": None})
            merged_present = any(c.colSpan > 1 or c.rowSpan > 1
                                              for c in doc.cells)
            if merged_present and ('rowspan=' not in html.lower()
                                                  and 'colspan=' not in html.lower()):
                findings.append({"code": "MERGED_CELL_NOT_RENDERED",
                                          "level": "FAIL", "detail": None})
            sha_after = _sha(f)
            mtime_after = f.stat().st_mtime_ns
            if sha_after != sha_before:
                findings.append({"code": "SOURCE_SHA_CHANGED",
                                          "level": "FAIL", "detail": f.name})
            if mtime_after != mtime_before:
                findings.append({"code": "SOURCE_MTIME_CHANGED",
                                          "level": "FAIL", "detail": f.name})
            per_file.append({
                "path": str(f.relative_to(PR)),
                "documentId": doc.documentId,
                "htmlBytes": len(html.encode("utf-8")),
                "hasTable": "<table" in html,
                "hasParagraph": "wo-paragraph" in html,
                "hasCell": "wo-cell" in html,
                "hasMergedRendered": ('rowspan=' in html.lower()
                                                      or 'colspan=' in html.lower()),
                "srcUnchanged": (sha_after == sha_before
                                              and mtime_after == mtime_before),
                "findings": findings,
                "verdict": "PASS" if not findings else "FAIL",
            })

    all_findings = src_findings + [
        f for r in per_file for f in r["findings"]]
    fails = sum(1 for f in all_findings if f["level"] == "FAIL")
    return {
        "task": "WEB-OFFICE-BROWSER-VIEWER-PROTOTYPE-01",
        "sampleCount": len(per_file),
        "srcFindings": src_findings,
        "results": per_file,
        "verdict": "PASS" if fails == 0 else "FAIL",
    }


def main() -> int:
    out = audit()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
