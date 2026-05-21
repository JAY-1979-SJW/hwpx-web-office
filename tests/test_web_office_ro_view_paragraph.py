"""RO_VIEW_PARAGRAPH_01 계약 테스트.

ro_view_importer 가 hp:p / hp:run / hp:t XML 을 직접 순회해
paragraph 별 parPrIDRef + run 별 charPrIDRef + containerScope 를
발급하는지 검증한다. 원본 무수정 + writer 미실행 + 다운스트림
writer 입구(paragraph_edits) 호환성도 검증한다.
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

from scripts.hwpx.web_office.document_model import (  # noqa: E402
    WebOfficeParagraph,
)
from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view,
)
from scripts.hwpx.web_office.render_payload import (  # noqa: E402
    build_render_payload,
)
from scripts.hwpx.hwpx_edit_tool import validate_edit_plan  # noqa: E402
from scripts.ops.audit_web_office_ro_view_paragraph import audit  # noqa: E402


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
NEED3 = pytest.mark.skipif(len(FIXTURES) < 3, reason="need >=3 fixtures")


# ── 시나리오 1~3: paragraph/run 추출 ─────────────────────────────

@NEED3
def test_sample_0_paragraph_runs_extracted():
    f = FIXTURES[0]
    doc = import_hwpx_as_ro_view(f)
    assert doc.paragraphs, f"no paragraphs in {f.name}"
    total_runs = sum(len(p.runs) for p in doc.paragraphs)
    assert total_runs >= len(doc.paragraphs), (
        "runs must be >= paragraphs (each paragraph has >=1 run)")


@NEED3
def test_sample_1_paragraph_runs_extracted():
    f = FIXTURES[1]
    doc = import_hwpx_as_ro_view(f)
    assert doc.paragraphs
    total_runs = sum(len(p.runs) for p in doc.paragraphs)
    assert total_runs >= len(doc.paragraphs)


@NEED3
def test_sample_2_paragraph_runs_extracted():
    f = FIXTURES[2]
    doc = import_hwpx_as_ro_view(f)
    assert doc.paragraphs
    total_runs = sum(len(p.runs) for p in doc.paragraphs)
    assert total_runs >= len(doc.paragraphs)


# ── 4: cell paragraph containerScope ─────────────────────────────

@NEED3
def test_cell_paragraph_container_scope_kind_cell():
    f = FIXTURES[0]
    doc = import_hwpx_as_ro_view(f)
    cell_pars = [p for p in doc.paragraphs
                          if p.containerScope and
                              p.containerScope.get("kind") == "cell"]
    assert cell_pars, "expected >=1 cell paragraph with containerScope"
    sample = cell_pars[0]
    sc = sample.containerScope
    for k in ("tableIndex", "rowIndex", "colIndex", "paragraphIndex"):
        assert k in sc, f"missing {k} in cell containerScope"
        assert isinstance(sc[k], int)


# ── 5: body paragraph containerScope ─────────────────────────────

@NEED3
def test_body_paragraph_container_scope_kind_block():
    # 3 fixture 중 body paragraph 가 한 건이라도 있으면 검사, 없으면 skip
    for f in FIXTURES:
        doc = import_hwpx_as_ro_view(f)
        body_pars = [p for p in doc.paragraphs
                              if p.containerScope and
                                  p.containerScope.get("kind") == "block"]
        if body_pars:
            sc = body_pars[0].containerScope
            for k in ("sectionIndex", "blockIndex", "paragraphIndex"):
                assert k in sc, f"missing {k} in block containerScope"
                assert isinstance(sc[k], int)
            return
    pytest.skip("no body paragraphs in fixtures")


# ── 6: paragraphId 중복 0 ────────────────────────────────────────

@NEED3
def test_paragraph_id_unique_all_samples():
    for f in FIXTURES:
        doc = import_hwpx_as_ro_view(f)
        ids = [p.paragraphId for p in doc.paragraphs]
        assert len(ids) == len(set(ids)), f"dup paragraphId in {f.name}"


# ── 7: runId 중복 0 ──────────────────────────────────────────────

@NEED3
def test_run_id_unique_all_samples():
    for f in FIXTURES:
        doc = import_hwpx_as_ro_view(f)
        run_ids = [r.runId for p in doc.paragraphs for r in p.runs]
        assert len(run_ids) == len(set(run_ids)), (
            f"dup runId in {f.name}")


# ── 8: charPrIDRef 추출 ──────────────────────────────────────────

@NEED3
def test_at_least_one_run_has_char_pr_id_ref():
    found = False
    for f in FIXTURES:
        doc = import_hwpx_as_ro_view(f)
        for p in doc.paragraphs:
            for r in p.runs:
                if r.charPrIDRef:
                    found = True
                    break
            if found:
                break
        if found:
            break
    assert found, "no run.charPrIDRef extracted across all fixtures"


# ── 9: parPrIDRef 추출 ───────────────────────────────────────────

@NEED3
def test_at_least_one_paragraph_has_par_pr_id_ref():
    for f in FIXTURES:
        doc = import_hwpx_as_ro_view(f)
        if any(p.parPrIDRef for p in doc.paragraphs):
            return
        # 분해 불가 시 RO_VIEW_RUN_PRECISION_DEGRADED warning 적재
        codes = {w.get("code") for w in doc.warnings
                        if isinstance(w, dict)}
        if "RO_VIEW_RUN_PRECISION_DEGRADED" in codes:
            return
    pytest.fail("no parPrIDRef extracted and no degrade warning")


# ── 10: RenderPayload 포함 ───────────────────────────────────────

@NEED3
def test_render_payload_paragraph_runs_and_container_scope():
    f = FIXTURES[0]
    doc = import_hwpx_as_ro_view(f)
    payload = build_render_payload(doc)
    # block paragraph 가 있으면 거기서 검사. 없으면 cell 의 paragraph 가
    # 직접 노출되진 않으므로 doc.paragraphs 의 to-dict 형태로 검사.
    any_paragraph_block = False
    for blk in payload.get("blocks", []):
        if blk.get("type") == "paragraph" and "paragraph" in blk:
            p = blk["paragraph"]
            assert "runs" in p
            assert isinstance(p["runs"], list)
            assert "containerScope" in p
            any_paragraph_block = True
            break
    if not any_paragraph_block:
        # 최소 1개 paragraph 의 containerScope 가 None 이 아님을 검사
        assert any(p.containerScope is not None
                          for p in doc.paragraphs)


# ── 11: writer paragraph_edits plan validate_edit_plan PASS ────

@NEED3
def test_paragraph_edit_plan_validate_pass_with_ro_view_paragraph():
    f = FIXTURES[0]
    doc = import_hwpx_as_ro_view(f)
    cell_pars = [p for p in doc.paragraphs
                          if p.containerScope and
                              p.containerScope.get("kind") == "cell"
                              and p.runs and (p.runs[0].text or "")]
    if not cell_pars:
        pytest.skip("no cell paragraph with non-empty run")
    par = cell_pars[0]
    run = par.runs[0]
    before = run.text
    after = before + "X"
    item = {
        "commandId": "cmd_test_001",
        "paragraphId": par.paragraphId,
        "runId": run.runId,
        "rangeStart": len(before),
        "rangeEnd": len(before),
        "expectedBefore": "",
        "afterText": "X",
        "sourceDocumentHash": doc.sourceDocumentHash,
        "commandType": "TYPE_TEXT",
        "containerScope": par.containerScope,
        "applyCharPrIDRef": run.charPrIDRef,
    }
    result = validate_edit_plan({"paragraph_edits": [item]})
    assert result["status"] == "PASS", (
        f"validate_edit_plan FAIL: {result}")


# ── 12: 원본 sha/mtime 무변경 ────────────────────────────────────

@NEED3
def test_original_hwpx_sha_and_mtime_unchanged():
    for f in FIXTURES:
        sha_before = _sha(f)
        mt_before = f.stat().st_mtime_ns
        _ = import_hwpx_as_ro_view(f)
        assert _sha(f) == sha_before, f"sha changed for {f.name}"
        assert f.stat().st_mtime_ns == mt_before, (
            f"mtime changed for {f.name}")


# ── 13: writer 실행 0건 정적 검증 ────────────────────────────────

def test_ro_view_importer_no_writer_tokens():
    src = (PR / "scripts/hwpx/web_office/ro_view_importer.py"
              ).read_text(encoding="utf-8")
    for tok in ("apply_edit_plan", "hwpx_edit_tool",
                       "set_table_cell_text", "write_package",
                       "HwpxValidator", "EditCommand",
                       "package.write_xml", "package.save"):
        assert tok not in src, f"forbidden token in importer: {tok}"


# ── 부가: containerScope default None / audit PASS ──────────────

def test_web_office_paragraph_container_scope_default_none():
    p = WebOfficeParagraph(paragraphId="x", text="y")
    assert p.containerScope is None


def test_audit_returns_pass():
    out = audit()
    assert out["verdict"] == "PASS", f"audit findings: {out}"
    assert out["summary"]["sampleCount"] >= 3
    assert out["summary"]["shaPreservedAll"] is True
