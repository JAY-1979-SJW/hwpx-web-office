"""셀 좌표계 일치 회귀 — documentModel 과 renderPayload 가 같은 칸을 가리키는가.

발견 경위:
    문단 저장 결과를 readback 으로 검증(V1/V7)하려다, 파서가 한 셀의 내용을
    인접 셀 좌표에도 보여주는 현상을 만났다. 파고들어 보니 텍스트가 복제되는
    것이 아니라 **두 뷰가 서로 다른 좌표계를 쓰고 있었다.**

        renderPayload.tables[].cells[].col   격자 주소 (colSpan 반영)
        documentModel.paragraphs[].containerScope.colIndex   셀 순번

    colSpan 이 1 인 칸에서는 두 값이 우연히 같아 문제가 드러나지 않는다.
    확장·병합 셀 뒤부터 어긋난다. 실측(fx_metadata_form.hwpx, 셀 51개):

        표0 r5c2   render='전화번호'  model='성명'        ← r5c1(colSpan=6) 뒤
        표0 r8c2   render='대표자성명' model='명칭'
        표0 r3c6   render='120일'     model='처리일'

왜 중요한가:
  1) 문단 readback 검증(V1_RANGE_POSITION_OK / V7_READBACK_MATCH)을 이 위에
     얹으면 옆 칸을 제 칸으로 오인한다. V1 이 하드코딩 FAIL 로 남아 있던
     실질적 이유로 보인다.
  2) 입력칸 추출(form_field_roles.extract_field_cells)이 '빈 문단의 좌표'와
     '격자 셀 좌표'를 대조한다. 좌표계가 다르면 확장 셀 뒤의 칸에서 라벨이
     어긋날 수 있다.

이 테스트는 **수리 전까지 xfail(strict) 로 둔다.** 누군가 좌표계를 맞추면
xpass 가 되어 테스트가 실패하고, 그때 marker 를 지우면서 수리가 고정된다.
(strict=True 라 '고쳤는데 아무도 모르는' 상태가 생기지 않는다.)

수리 주체 주의: 이 영역(표 앵커·좌표 매핑)은 시각회귀 baseline 과 얽혀 있다.
좌표계를 바꾸면 baseline 재고정이 함께 필요하다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor  # noqa: E402
from scripts.hwpx.web_office.hwpx_sample_source import resolve_sample  # noqa: E402

FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "corpus" / "fx_metadata_form.hwpx"

# 한글 가운뎃점은 파일마다 U+119E / U+318D 로 갈린다. 좌표 결함과 무관한
# 정규화 차이라 비교에서 제외한다.
_MIDDOT = re.compile(r"[ᆞㆍ·]")


def _norm(s: str) -> str:
    return _MIDDOT.sub("", re.sub(r"\s+", "", s or ""))


def _cell_texts(doc: dict, render: dict) -> tuple[dict, dict]:
    """(격자 기준 셀 텍스트, 문단 기준 셀 텍스트)"""
    grid: dict[tuple, str] = {}
    for ti, table in enumerate(render.get("tables", [])):
        for c in table.get("cells", []):
            if not c.get("isCoveredByMerge"):
                grid[(ti, c["row"], c["col"])] = _norm(c.get("text"))
    model: dict[tuple, str] = {}
    for p in doc.get("paragraphs", []):
        cs = p.get("containerScope") or {}
        if cs.get("kind") != "cell":
            continue
        key = (cs.get("tableIndex"), cs.get("rowIndex"), cs.get("colIndex"))
        model[key] = model.get(key, "") + _norm(
            "".join(r.get("text", "") for r in p.get("runs", [])))
    return grid, model


def _mismatches(path: Path) -> list[tuple]:
    res = load_hwpx_for_editor(
        {"operation": "HWPX_EDITOR_LOAD",
         "sourcePath": path.resolve().relative_to(PROJECT_ROOT).as_posix()},
        project_root=PROJECT_ROOT)
    assert res.get("verdict") == "PASS", path
    grid, model = _cell_texts(res["documentModel"], res["renderPayload"])
    out = []
    for key in set(grid) & set(model):
        g, m = grid[key], model[key]
        # 빈 칸은 비교 대상이 아니다(양쪽 다 공백이면 구분 불가)
        if not g or not m:
            continue
        if g not in m:
            out.append((key, g, m))
    return sorted(out)


@pytest.mark.xfail(strict=True, reason=(
    "documentModel.containerScope.colIndex(셀 순번)과 "
    "renderPayload.cells.col(격자 주소)이 확장 셀 뒤에서 어긋난다 — 미수리"))
def test_cell_coordinate_systems_agree_on_fixture():
    """같은 칸을 가리키면 텍스트도 같아야 한다."""
    if not FIXTURE.is_file():
        pytest.skip(f"fixture 없음: {FIXTURE}")
    bad = _mismatches(FIXTURE)
    assert not bad, (
        f"좌표계 불일치 {len(bad)}건 — "
        + "; ".join(f"표{k[0]} r{k[1]}c{k[2]} render={g!r} model={m!r}"
                    for k, g, m in bad[:5]))


def test_mismatch_is_reproducible_and_bounded():
    """결함이 재현되고, 규모가 커지지 않는지 감시한다.

    xfail 테스트는 '실패한다'는 사실만 남기고 규모를 보지 않는다. 이 테스트는
    불일치가 발생한다는 현 상태를 기록하되, 비율이 크게 나빠지면 실패한다.
    수리되면 불일치 0 이 되어 이 테스트도 통과한다(하한만 두므로).
    """
    if not FIXTURE.is_file():
        pytest.skip(f"fixture 없음: {FIXTURE}")
    res = load_hwpx_for_editor(
        {"operation": "HWPX_EDITOR_LOAD",
         "sourcePath": FIXTURE.resolve().relative_to(PROJECT_ROOT).as_posix()},
        project_root=PROJECT_ROOT)
    grid, model = _cell_texts(res["documentModel"], res["renderPayload"])
    common = set(grid) & set(model)
    assert common, "비교할 셀이 없다"
    bad = _mismatches(FIXTURE)
    ratio = len(bad) / len(common)
    # 실측 시점 4/51 ≈ 7.8% (가운뎃점 정규화 2건 제외 후)
    assert ratio <= 0.20, (
        f"좌표 불일치가 {ratio:.1%} ({len(bad)}/{len(common)}) 로 악화 — "
        "확장 셀 좌표 매핑이 더 틀어졌다")


def test_defect_also_affects_a_catalog_sample():
    """수집 코퍼스의 실제 서식에서도 나타나는지 — 이 픽스처만의 특성이 아님."""
    sample = resolve_sample()
    if sample is None:
        pytest.skip("카탈로그 표본 없음")
    bad = _mismatches(sample)
    # 표본에 확장 셀이 없으면 불일치가 0 일 수 있다 — 정보 기록용이라
    # 실패시키지 않는다. 규모만 남긴다.
    assert isinstance(bad, list)
    print(f"\n[정보] {sample.name}: 좌표 불일치 {len(bad)}건")
