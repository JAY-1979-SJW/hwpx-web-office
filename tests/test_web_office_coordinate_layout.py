"""WEB-OFFICE-COORD-LAYOUT-01 — lineseg 좌표 레이아웃 추출 계약 테스트.

한컴 없이 HWPX 가 저장한 lineseg 좌표로 페이지 레이아웃을 재현하는
coordinate_layout 모듈의 불변식 + build_layout 보안(경로) + envelope 을
검증한다. read-only (원본 무수정).
"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.coordinate_layout import (  # noqa: E402
    extract, build_layout)

FORM = "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"


def _finite(v):
    return isinstance(v, (int, float)) and v == v and abs(v) < 1e7


def test_page_geometry_sane():
    out = extract(str(PR / FORM))
    assert out["pageWidthPx"] > 100 and out["pageHeightPx"] > 100
    assert out["pages"] >= 1


def test_lines_have_finite_coords_and_text_slices():
    out = extract(str(PR / FORM))
    assert len(out["lines"]) > 0
    for line in out["lines"]:
        assert all(_finite(line[k]) for k in ("x", "y", "w", "h"))
        assert line["y"] >= 0
    # 어떤 줄엔 실제 텍스트가 있어야 함(textpos 슬라이스 동작)
    assert any(l["text"].strip() for l in out["lines"])


def test_table_boxes_cover_cells_with_borders():
    out = extract(str(PR / FORM))
    boxes = out["boxes"]
    assert len(boxes) >= 40, f"expected many cell boxes, got {len(boxes)}"
    for b in boxes:
        assert all(_finite(b[k]) for k in ("x", "y", "w", "h"))
        assert b["w"] > 0 and b["h"] > 0
    # borderFill 이 반영된 박스가 존재
    assert any(b.get("border") for b in boxes)


def test_grid_columns_aligned_across_rows():
    """병합 solver 가 열 x 오프셋을 행 간 일관되게 맞췄는지(근사)."""
    out = extract(str(PR / FORM))
    xs: dict[float, int] = {}
    for b in out["boxes"]:
        key = round(b["x"], 0)
        xs[key] = xs.get(key, 0) + 1
    assert any(v >= 2 for v in xs.values()), "열 x 정렬 공유 없음"


def test_build_layout_rejects_absolute_and_non_hwpx():
    assert build_layout({"sourcePath": str(PR / FORM)},
                        project_root=PR)["verdict"] == "REJECTED"
    assert build_layout({"sourcePath": "README.md"},
                        project_root=PR)["verdict"] == "REJECTED"
    assert build_layout({}, project_root=PR)["verdict"] == "REJECTED"


def test_build_layout_pass_for_project_relative_hwpx():
    res = build_layout({"sourcePath": FORM}, project_root=PR)
    assert res["verdict"] == "PASS"
    assert res["sourcePath"] == FORM
    assert res["pages"] >= 1 and len(res["lines"]) > 0


def test_source_unchanged_after_extract():
    p = PR / FORM
    before = p.stat().st_mtime_ns, p.stat().st_size
    extract(str(p))
    after = p.stat().st_mtime_ns, p.stat().st_size
    assert before == after, "원본 파일 변경됨(RO 위반)"


def test_route_layout_endpoint_when_fastapi_available():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from scripts.hwpx.web_office.editor_api_route import app
    if app is None:
        pytest.skip("FastAPI app unavailable")
    client = TestClient(app)
    r = client.post("/api/web-office/hwpx-layout",
                    json={"sourcePath": FORM})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "SUCCESS"
    data = body["data"]
    assert data["pages"] >= 1 and len(data["lines"]) > 0
