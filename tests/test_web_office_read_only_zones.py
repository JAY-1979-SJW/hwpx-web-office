"""읽기 전용 구역 가드 감리 (§4.4).

원본 직접 수정(§4.3)이 카탈로그 템플릿 등 읽기 전용 자산을 덮어써
되돌릴 수 없이 파괴하는 것을 막는 장치. 데이터 파괴 방지가 목적이라
'반드시 막는 것'과 '잘못 막지 않는 것' 둘 다 고정한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.hwpx.web_office.read_only_zones import (  # noqa: E402
    READ_ONLY_PREFIXES, is_read_only, zone_of)


# ── 반드시 읽기 전용으로 막아야 하는 것 ─────────────────────────

def test_catalog_templates_are_read_only():
    assert is_read_only(
        "data/drafts/form_library/legacy_hwpx/242_전기사용신청서.hwpx")
    assert is_read_only(
        "data/drafts/form_library/kepco_hwpx/x.hwpx")


def test_other_read_only_zones():
    for rel in ("samples/foo.hwpx",
                "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx",
                "data/recognition_corpus/corpus.sqlite3"):
        assert is_read_only(rel), rel


def test_windows_backslash_path_still_caught():
    assert is_read_only(r"data\drafts\form_library\x.hwpx")


def test_leading_dot_slash_still_caught():
    assert is_read_only("./data/drafts/form_library/x.hwpx")


def test_zone_of_returns_matching_prefix():
    z = zone_of("data/drafts/form_library/x.hwpx")
    assert z == "data/drafts/form_library/"
    assert z in READ_ONLY_PREFIXES


# ── 잘못 막으면 안 되는 것 (사용자 문서·sandbox) ────────────────

def test_sandbox_output_is_writable():
    for rel in ("tmp/web_office_edits/para_save_ab.hwpx",
                "tmp/web_office_uploads/user.hwpx",
                "tmp/full_fill_probe/x.hwpx"):
        assert not is_read_only(rel), rel
        assert zone_of(rel) is None


def test_user_upload_is_writable():
    assert not is_read_only("uploads/내문서.hwpx")


def test_empty_and_garbage_not_read_only():
    for rel in ("", "   ", None):
        assert is_read_only(rel) is False


def test_prefix_boundary_not_over_matched():
    """'data/drafts/form_library_backup' 처럼 접두를 공유하지만 다른
    디렉터리는 막지 않는다 — 슬래시로 끝나는 접두라 경계가 정확하다."""
    assert not is_read_only("data/drafts/form_library_export/x.hwpx")


# ── 가드 배선: _apply_in_place_if_requested 가 읽기 전용을 거부 ──

def _fake_result(tmp_path):
    out = tmp_path / "sandbox_out.hwpx"
    out.write_bytes(b"EDITED")
    return {"verdict": "PASS", "outputPath": str(out)}, out


def test_in_place_refused_on_read_only_zone(tmp_path, monkeypatch):
    from scripts.hwpx.web_office import editor_api_route as R
    # 읽기 전용 원본을 흉내내는 파일
    proj = tmp_path
    src_rel = "data/drafts/form_library/template.hwpx"
    src = proj / src_rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"ORIGINAL_TEMPLATE")
    result, out = _fake_result(tmp_path)

    R._apply_in_place_if_requested(result, source_rel=src_rel, project_root=proj)

    assert result.get("editedInPlace") is False
    assert result.get("inPlaceRefused") == "READ_ONLY_ZONE"
    # 원본 템플릿은 그대로 — 덮이지 않았다
    assert src.read_bytes() == b"ORIGINAL_TEMPLATE"
    # 사본은 보존(사용자가 채워진 결과를 받을 수 있게)
    assert out.is_file()


def test_in_place_applied_on_user_document(tmp_path):
    from scripts.hwpx.web_office import editor_api_route as R
    proj = tmp_path
    src_rel = "uploads/user_doc.hwpx"
    src = proj / src_rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"ORIGINAL_USER")
    result, out = _fake_result(tmp_path)

    R._apply_in_place_if_requested(result, source_rel=src_rel, project_root=proj)

    assert result.get("editedInPlace") is True
    # 사용자 문서는 편집 결과로 덮인다(§4.3)
    assert src.read_bytes() == b"EDITED"
    assert not out.is_file()          # 사본은 반영 후 정리
