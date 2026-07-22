"""WEB-OFFICE-PARA-EDIT-FORMAT-CHARPR-INVENTORY-01 감리.

charPr inventory read-only helper 의 정확성 + 원본 무변경 + d61f10f
부분준공 잠금 자재 무수정 확인.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.hwpx.web_office.charpr_inventory import (  # noqa: E402
    paragraph_char_pr_inventory, char_pr_defs_only)
from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view)

BASELINE_COMMIT = "685e8c9"  # PARA_INSERT 준공 후 갱신 (d61f10f → bb0939b)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _fixture() -> Path | None:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        return None
    try:
        conn = sqlite3.connect(db)
        row = conn.execute("""
            SELECT d.source_path FROM hwpx_documents d
            WHERE d.inventory_status='FOUND'
              AND d.file_size BETWEEN 30000 AND 200000
            ORDER BY d.first_seen_at LIMIT 1
        """).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    p = PR / row[0]
    return p if p.is_file() else None


FIXTURE = _fixture()
need_fx = pytest.mark.skipif(
    FIXTURE is None, reason="fixture missing")


# ── 1. 모든 paragraph 의 모든 run charPr 가 수집되는지 ──────────

@need_fx
def test_all_runs_collected_in_paragraph_inventory():
    inv = paragraph_char_pr_inventory(FIXTURE)
    doc = import_hwpx_as_ro_view(FIXTURE)
    for par in doc.paragraphs:
        entries = inv["paragraphInventory"].get(par.paragraphId)
        assert entries is not None, par.paragraphId
        total = sum(e["usageCount"] for e in entries)
        assert total == len(par.runs), (par.paragraphId, total,
                                                                len(par.runs))


# ── 2. usageCount 정확성 ─────────────────────────────────────

@need_fx
def test_usage_count_matches_run_grouping():
    inv = paragraph_char_pr_inventory(FIXTURE)
    doc = import_hwpx_as_ro_view(FIXTURE)
    for par in doc.paragraphs[:20]:
        # ro_view 로부터 직접 카운트
        from collections import Counter
        expected = Counter(r.charPrIDRef for r in par.runs)
        entries = inv["paragraphInventory"][par.paragraphId]
        actual = {e["charPrId"]: e["usageCount"] for e in entries}
        assert actual == dict(expected), (par.paragraphId, actual,
                                                                          expected)


# ── 3. header.xml charPr 속성 매핑 ───────────────────────────

@need_fx
def test_header_charpr_attrs_mapped():
    inv = paragraph_char_pr_inventory(FIXTURE)
    assert inv["headerCharPrCount"] > 0
    # inHeader=True 인 entry 는 fontName/fontSizePt/textColor 등 속성을
    # 정확히 매핑한다 (적어도 fontFace 또는 fontName 중 하나는 존재).
    matched_with_attrs = 0
    for entry in inv["documentInventory"]:
        if entry["inHeader"]:
            assert entry["charPrId"] is not None
            # bold/italic/underline 은 명시적 bool
            assert isinstance(entry["bold"], bool)
            assert isinstance(entry["italic"], bool)
            assert isinstance(entry["underline"], bool)
            # fontSizePt 또는 height 중 하나는 보통 존재
            if entry["fontSizePt"] is not None:
                assert entry["fontSizePt"] > 0
                matched_with_attrs += 1
    assert matched_with_attrs > 0, "no charPr with fontSizePt mapped"


# ── 4. dangling charPrIDRef 검출 — 합성 case ──────────────────

@need_fx
def test_dangling_charpr_detected_via_synthetic(tmp_path):
    """fixture 를 복제 후 paragraph 의 첫 run charPrIDRef 를 header 에
    없는 id 로 덮어쓰고 새 ZIP 으로 패키징해 dangling 검출 확인.
    """
    src = FIXTURE
    dst = tmp_path / "synth_dangling.hwpx"
    # zip → 모든 entries 복사, section0.xml 만 mutate
    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if (info.filename.replace("\\", "/")
                    .endswith("section0.xml")):
                xml = data.decode("utf-8", "ignore")
                # 첫 charPrIDRef 를 9999 (header 에 없음 가정) 로 교체
                # 1 회만 치환
                fake_id = '999999'
                import re as _re
                new_xml, n = _re.subn(
                    r'charPrIDRef="\d+"',
                    f'charPrIDRef="{fake_id}"', xml, count=1)
                data = new_xml.encode("utf-8")
            zout.writestr(info, data)
    inv = paragraph_char_pr_inventory(dst)
    assert "999999" in inv["danglingCharPrIDRefs"], (
        inv["danglingCharPrIDRefs"][:10])


# ── 5. paragraph 단위와 문서 단위 inventory 구분 ──────────────

@need_fx
def test_paragraph_scope_vs_document_scope_distinct():
    doc = import_hwpx_as_ro_view(FIXTURE)
    target_pid = doc.paragraphs[0].paragraphId
    inv = paragraph_char_pr_inventory(FIXTURE,
                                                                    paragraph_id=target_pid)
    # paragraphInventory 는 target 1건만
    assert list(inv["paragraphInventory"].keys()) == [target_pid]
    # documentInventory 는 paragraph_id 필터와 무관하게 문서 전체
    assert (len(inv["documentInventory"])
                  >= len(inv["paragraphInventory"][target_pid]))


# ── 6. char_pr_defs_only 단독 호출 ──────────────────────────

@need_fx
def test_char_pr_defs_only_returns_header_definitions():
    defs = char_pr_defs_only(FIXTURE)
    assert isinstance(defs, dict)
    assert len(defs) > 0
    sample = next(iter(defs.values()))
    for key in ("bold", "italic", "underline", "fontFace"):
        assert key in sample, key


# ── 7. writer 호출 0건 (정적 grep) ──────────────────────────

def test_inventory_module_has_no_writer_calls():
    import re
    src = (PR / "scripts/hwpx/web_office/charpr_inventory.py"
              ).read_text(encoding="utf-8")
    forbidden = [
        r"\.write_xml\(",
        r"\.write_package\(",
        r"package\.entries\[[^\]]+\]\s*=",
        r"create_hwpx_document\(",
        r"save_paragraph_edits\(",
        r"apply_paragraph_edits_plan\(",
    ]
    for pat in forbidden:
        assert not re.search(pat, src), pat


# ── 8. 원본 sha256 / mtime_ns 무변경 ────────────────────────

@need_fx
def test_inventory_does_not_modify_source():
    sha_b = _sha(FIXTURE)
    mt_b = FIXTURE.stat().st_mtime_ns
    for _ in range(3):
        paragraph_char_pr_inventory(FIXTURE)
    assert _sha(FIXTURE) == sha_b
    assert FIXTURE.stat().st_mtime_ns == mt_b


# ── 9. d61f10f 잠금 자재 무수정 ─────────────────────────────

# WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01: ApplyFormat
# 활성화로 본 LOCKED 에서 제거 — para_edit_model, paragraph_edit_plan,
# paragraph_writer_adapter, paragraph_save_verify7,
# para_edit_e2e_pipeline, hwpx_paragraph_ops.
LOCKED = [
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01:
    # para_edit_state.mjs 는 applyFormatToSelection 추가로 본 LOCKED 에서 제거.
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]


def test_locked_d61f10f_files_unchanged():
    for rel in LOCKED:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", rel],
            capture_output=True, text=True, cwd=str(PR), timeout=20)
        assert r.returncode == 0, (rel, r.stderr)
        assert not r.stdout.strip(), (
            f"{rel} changed vs {BASELINE_COMMIT}")


# ── 10. ApplyFormat 흔적 없음 (정적) ────────────────────────

def test_no_applyformat_traces_in_writer_chain():
    """WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01:
    ApplyFormat 이 활성화되어 CT_APPLY_FORMAT / make_apply_format_command
    흔적은 허용. 신규 charPr 생성 함수 (def create_char_pr) 만 계속 차단.
    """
    import re
    forbidden = [
        r"def\s+create_char_pr\b",
    ]
    targets = [
        "scripts/hwpx/web_office/paragraph_writer_adapter.py",
        "scripts/hwpx/web_office/para_edit_model.py",
        "scripts/hwpx/web_office/paragraph_edit_plan.py",
        "scripts/hwpx/hwpx_paragraph_ops.py",
        "frontend/web_office_viewer/para_edit_command.mjs",
        "frontend/web_office_viewer/para_edit_state.mjs",
    ]
    for rel in targets:
        src = (PR / rel).read_text(encoding="utf-8")
        for pat in forbidden:
            assert not re.search(pat, src), (rel, pat)


# ── 11. audit verdict PASS ─────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_format_charpr_inventory \
        import audit
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
