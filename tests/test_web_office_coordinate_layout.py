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


def test_lines_carry_charpr_segments_and_defs():
    """WEB-OFFICE-COORD-FORMAT-01 — 각 줄이 run 별 charPr 조각을 보존하고
    charPrDefs(서식 정의)가 함께 반출되는지. 위치+서식 동시 재현의 기반."""
    out = extract(str(PR / FORM))
    defs = out.get("charPrDefs")
    assert isinstance(defs, dict) and len(defs) > 0, "charPrDefs 반출 없음"
    # 모든 줄은 segments 를 가지며, 조각 텍스트 합 == 줄 텍스트(정렬 불변식)
    for line in out["lines"]:
        segs = line.get("segments")
        assert isinstance(segs, list)
        if segs:
            assert "".join(s["text"] for s in segs) == line["text"]
    # 실제 서식(charPr 참조)이 붙은 줄이 존재하고, 그 참조가 defs 에 있음
    styled = [s for l in out["lines"] for s in (l.get("segments") or [])
              if s.get("charPr") is not None]
    assert styled, "charPr 참조가 붙은 조각 없음"
    assert any(s["charPr"] in defs for s in styled), "조각 charPr 가 defs 미해결"


def test_lines_carry_hancom_baseline():
    """WEB-OFFICE-COORD-FIDELITY-01 — 한컴 저장 baseline(글자 기준선) 반출.

    baseline 은 줄 상단 기준 offset(px)이며 줄 높이 h 안에 있어야 한다.
    한컴 실행 화면과 수직 위치를 맞추기 위한 데이터."""
    out = extract(str(PR / FORM))
    withbl = [l for l in out["lines"] if l.get("baseline", 0) > 0]
    assert withbl, "baseline 반출 없음"
    for line in withbl:
        assert 0 < line["baseline"] <= line["h"] + 1, \
            f"baseline({line['baseline']}) 이 줄 높이({line['h']}) 밖"


def test_nested_table_placed_at_container_not_top():
    """WEB-OFFICE-COORD-FIDELITY-02 — 중첩표(처리절차)가 부모 셀 위치(하단)에
    배치되고 상단으로 새지 않는지. _nearest_tbl/_nearest_cell 회귀 가드."""
    out = extract(str(PR / FORM))
    ph = out["pageHeightPx"]
    flow = [l for l in out["lines"]
            if any(k in l["text"] for k in ("지정서", "갱신 허가"))]
    assert flow, "처리절차 흐름 텍스트를 찾지 못함"
    # 흐름 스텝은 문서 하단(페이지 60% 이하)에 있어야 한다(상단 유출 아님).
    assert all(l["y"] > ph * 0.6 for l in flow), \
        f"중첩표가 상단으로 유출됨: {[(l['text'], round(l['y'])) for l in flow]}"


def test_table_total_size_matches_declared_sz():
    """WEB-OFFICE-COORD-FIDELITY-04 — 렌더된 표 총 폭/높이가 한컴 선언
    치수(tbl>sz)와 일치하는지(±1.5%). 셀 폭 합 근사 오차가 표 전체로
    누적되지 않도록 sz 정규화 회귀 가드."""
    import zipfile
    import xml.etree.ElementTree as ET
    HU = 96 / 7200

    def lname(t):
        return t.rsplit("}", 1)[-1]

    z = zipfile.ZipFile(str(PR / FORM))
    sec = [n for n in z.namelist()
           if "section0" in n.lower() and n.endswith(".xml")][0]
    root = ET.fromstring(z.read(sec))
    pm = {c: p for p in root.iter() for c in p}

    def top_level(el):
        x = pm.get(el)
        while x is not None:
            if lname(x.tag) == "tbl":
                return False
            x = pm.get(x)
        return True
    tbl = next(e for e in root.iter()
               if lname(e.tag) == "tbl" and top_level(e))
    sz = next((c.attrib for c in tbl if lname(c.tag) == "sz"), {})
    decl_w = float(sz.get("width", "0")) * HU
    decl_h = float(sz.get("height", "0")) * HU

    out = extract(str(PR / FORM))
    bx = out["boxes"]
    w = max(b["x"] + b["w"] for b in bx) - min(b["x"] for b in bx)
    h = max(b["y"] + b["h"] for b in bx) - min(b["y"] for b in bx)
    assert abs(w - decl_w) / decl_w < 0.015, \
        f"표 폭 {w:.1f} vs 선언 {decl_w:.1f} ({(w/decl_w-1)*100:+.1f}%)"
    assert abs(h - decl_h) / decl_h < 0.015, \
        f"표 높이 {h:.1f} vs 선언 {decl_h:.1f} ({(h/decl_h-1)*100:+.1f}%)"


def test_cell_lines_do_not_overrun_their_cell():
    """WEB-OFFICE-COORD-FIDELITY-05 — 셀 텍스트 줄이 담긴 셀 박스를 가로로
    넘지 않는지. horzsize 가 셀보다 넓어도(공백 패딩 등) 셀 경계로 제한되어
    (전자우편 주소:)·(서명 또는 인) 등이 셀 밖으로 삐져나가지 않도록 가드."""
    out = extract(str(PR / FORM))
    boxes = out["boxes"]

    def cell_of(l):
        cx = l["x"] + 1
        cy = l["y"] + l["h"] / 2
        cs = [b for b in boxes
              if b["x"] - 1 <= cx <= b["x"] + b["w"] + 1
              and b["y"] - 1 <= cy <= b["y"] + b["h"] + 1]
        return min(cs, key=lambda b: b["w"] * b["h"]) if cs else None

    over = []
    for l in out["lines"]:
        if not l["cell"] or not l["text"].strip():
            continue
        b = cell_of(l)
        if b and (l["x"] + l["w"]) > (b["x"] + b["w"]) + 4:
            over.append((l["text"][:16], round(l["x"] + l["w"]),
                         round(b["x"] + b["w"])))
    assert not over, f"셀을 넘는 줄: {over}"


def test_multi_top_level_tables_flow_across_pages():
    """WEB-OFFICE-COORD-FIDELITY-07 — 다중 top-level 표(각 vertpos=0 흐름)가
    한 지점에 겹치지 않고 순차 flow 로 여러 페이지에 펼쳐지는지."""
    mt = "tests/fixtures/hwpx/corpus/fx_many_tables_page_marker.hwpx"
    out = extract(str(PR / mt))
    bx = out["boxes"]
    ymax = max(b["y"] + b["h"] for b in bx)
    assert ymax > out["pageHeightPx"] * 1.5, \
        f"표들이 flow 안 되고 한 페이지에 뭉침(ymax={ymax:.0f})"
    assert out["pages"] >= 2


def test_nested_table_below_preceding_cell_text():
    """WEB-OFFICE-COORD-FIDELITY-06 — 셀 안 중첩표(서명블록)가 앞선 본문
    문단 위로 겹치지 않고 아래에 배치되는지. 중첩표를 셀 최상단이 아닌
    담긴 문단 vertpos 에 두는 회귀 가드."""
    stamp = "tests/fixtures/hwpx/corpus/fx_stamp_approval_legal.hwpx"
    out = extract(str(PR / stamp))
    body = next((l for l in out["lines"] if "증명합니다" in l["text"]), None)
    sign = next((l for l in out["lines"] if "특별자치시장" in l["text"]), None)
    assert body is not None and sign is not None, "본문/서명 줄을 찾지 못함"
    assert sign["y"] > body["y"] + 20, \
        f"서명(y={sign['y']:.0f})이 본문(y={body['y']:.0f}) 아래에 있어야 함"


def test_header_cells_have_gray_fill():
    """WEB-OFFICE-COORD-FIDELITY-03 — 헤더 셀 배경(fillBrush)이 반출되는지."""
    out = extract(str(PR / FORM))
    filled = [b for b in out["boxes"] if b.get("fill")]
    assert filled, "채움색 있는 셀 없음"
    assert all(b["fill"].startswith("#") for b in filled)


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
