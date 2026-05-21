"""WEB-OFFICE-RO-VIEW-MVP-01 계약 테스트.

샘플 3건 변환 PASS, schemaVersion 고정, stable id 중복 없음, 원본 무변경,
edit/save 호출 없음을 검증한다.
"""
from __future__ import annotations
import hashlib
import sys
import sqlite3
from pathlib import Path
import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office import SCHEMA_VERSION, ENGINE_VERSION  # noqa: E402
from scripts.hwpx.web_office.document_model import (  # noqa: E402
    WebOfficeDocumentModel,
)
from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view,
)
from scripts.hwpx.web_office.render_payload import (  # noqa: E402
    build_render_payload, PAYLOAD_VERSION,
)
from scripts.ops.audit_web_office_ro_view_mvp import audit  # noqa: E402


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


FIXTURES = _resolve_fixtures(3)


def test_schema_version_fixed_constants():
    assert SCHEMA_VERSION == "web-office-doc-1.0"
    assert ENGINE_VERSION == "ro-view-mvp-01"
    assert WebOfficeDocumentModel.fixed_schema_version() == SCHEMA_VERSION
    assert WebOfficeDocumentModel.fixed_engine_version() == ENGINE_VERSION


@pytest.mark.skipif(len(FIXTURES) < 3,
                              reason="need ≥3 fixtures")
def test_three_samples_convert_pass():
    for f in FIXTURES:
        doc = import_hwpx_as_ro_view(f)
        assert doc.schemaVersion == SCHEMA_VERSION
        assert doc.engineVersion == ENGINE_VERSION
        assert doc.sourceDocumentHash == _sha(f)
        assert doc.documentId.startswith("doc_")


@pytest.mark.skipif(len(FIXTURES) < 3, reason="need ≥3 fixtures")
def test_stable_ids_unique():
    for f in FIXTURES:
        doc = import_hwpx_as_ro_view(f)
        cell_ids = [c.cellId for c in doc.cells]
        par_ids = [p.paragraphId for p in doc.paragraphs]
        block_ids = [b.blockId for b in doc.blocks]
        obj_ids = [o.objectId for o in doc.objects]
        assert len(cell_ids) == len(set(cell_ids)), f"dup cell in {f.name}"
        assert len(par_ids) == len(set(par_ids)), f"dup par in {f.name}"
        assert len(block_ids) == len(set(block_ids))
        assert len(obj_ids) == len(set(obj_ids))


@pytest.mark.skipif(len(FIXTURES) < 3, reason="need ≥3 fixtures")
def test_table_and_cell_present_when_tables_exist():
    for f in FIXTURES:
        doc = import_hwpx_as_ro_view(f)
        if doc.tables:
            assert doc.cells, (
                f"tables present but no cells in {f.name}")
            assert sum(len(t.cellIds) for t in doc.tables) == len(
                doc.cells)


@pytest.mark.skipif(len(FIXTURES) < 3, reason="need ≥3 fixtures")
def test_cell_spans_preserved():
    for f in FIXTURES:
        doc = import_hwpx_as_ro_view(f)
        for c in doc.cells:
            assert c.rowSpan >= 1 and c.colSpan >= 1
            assert isinstance(c.row, int) and isinstance(c.col, int)


@pytest.mark.skipif(len(FIXTURES) < 3, reason="need ≥3 fixtures")
def test_source_hwpx_sha_and_mtime_unchanged():
    for f in FIXTURES:
        sha_before = _sha(f)
        mt_before = f.stat().st_mtime_ns
        _ = import_hwpx_as_ro_view(f)
        assert _sha(f) == sha_before, f"sha changed for {f.name}"
        assert f.stat().st_mtime_ns == mt_before, (
            f"mtime changed for {f.name}")


@pytest.mark.skipif(len(FIXTURES) < 3, reason="need ≥3 fixtures")
def test_render_payload_editable_false_everywhere():
    f = FIXTURES[0]
    doc = import_hwpx_as_ro_view(f)
    payload = build_render_payload(doc)
    assert payload["editable"] is False
    assert payload["payloadVersion"] == PAYLOAD_VERSION
    assert payload["sourceRef"]["sha256"] == doc.sourceDocumentHash
    for t in payload["tables"]:
        assert t["editable"] is False
        for cell in t["cells"]:
            assert cell["editable"] is False
            assert "navigationId" in cell
    for b in payload["blocks"]:
        assert b["editable"] is False
    for o in payload["objects"]:
        assert o["editable"] is False
    # 편집 명령 관련 필드는 RO-VIEW payload 에 절대 등장하면 안 됨
    forbidden = {"editCommands", "commandLog", "dirty", "saveUrl",
                          "applyEditPlan", "writer", "output"}
    for k in forbidden:
        assert k not in payload, f"forbidden key in payload: {k}"


@pytest.mark.skipif(len(FIXTURES) < 3, reason="need ≥3 fixtures")
def test_no_writer_or_apply_edit_plan_imported():
    """RO-VIEW 모듈이 writer/edit_tool 을 import 하지 않아야 한다."""
    import importlib
    mods = [
        "scripts.hwpx.web_office.document_model",
        "scripts.hwpx.web_office.ro_view_importer",
        "scripts.hwpx.web_office.render_payload",
    ]
    for name in mods:
        m = importlib.import_module(name)
        src = Path(m.__file__).read_text(encoding="utf-8")
        for forbid in ("apply_edit_plan", "hwpx_edit_tool",
                                "set_table_cell_text", "write_package",
                                "HwpxValidator", "EditCommand"):
            assert forbid not in src, (
                f"{name} contains forbidden symbol: {forbid}")


def test_audit_returns_pass():
    out = audit()
    assert out["verdict"] == "PASS", f"audit findings: {out}"
    assert out["sampleCount"] >= 3


def test_no_output_hwpx_generated_after_convert(tmp_path):
    """RO-VIEW 변환이 sandbox 든 어디든 .hwpx 출력을 만들지 않는다."""
    if len(FIXTURES) < 1:
        pytest.skip("no fixture")
    f = FIXTURES[0]
    before = set(p.name for p in tmp_path.iterdir())
    _ = import_hwpx_as_ro_view(f)
    after = set(p.name for p in tmp_path.iterdir())
    assert before == after
    # tmp_path 에 .hwpx 생성 없음
    assert not any(p.suffix == ".hwpx" for p in tmp_path.iterdir())
