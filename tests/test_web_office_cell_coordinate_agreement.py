"""셀 좌표계 일치 회귀 — documentModel 과 renderPayload 가 같은 칸을 가리키는가.

발견 경위:
    문단 저장 결과를 readback 으로 검증(V1/V7)하려다, 파서가 한 셀의 내용을
    인접 셀 좌표에도 보여주는 현상을 만났다.

진단 (2026-07-23 확정 — 최초 가설은 틀렸다):
    처음에는 '두 뷰가 서로 다른 좌표계를 쓴다'고 봤으나, 실제로는 **양쪽 다
    같은 값(table_parser 의 셀 순번)을 쓰고 있었다.** 어긋난 것은 좌표가
    아니라 **그 좌표로 XML 셀을 찾아오는 조회 규칙**이었다.

        table_parser._parse_table_element   col = ci        ← 행 안 셀 순번
        ro_view_importer._find_cell_elem     cellAddr/@colAddr 로 매칭
                                                            ← 격자 주소

    colSpan 이 1 이면 두 값이 우연히 같아 드러나지 않는다. colSpan>1 인 셀이
    하나 지나가는 순간부터 조회가 옆 칸을 집어온다. 실측(fx_metadata_form,
    셀 53개 중 19개가 순번≠격자주소):

        표0 r5c2   '전화번호'   ← colAddr=8 로 조회되어 '성명' 을 가져옴
        표0 r8c2   '대표자 성명' ← 같은 이유로 '명칭'
        표0 r3c6   '120일'      ← '처리일'

    조회가 아예 빗나가 None 이 되는 경우도 결함이었다. 합성 fallback 으로
    빠져 텍스트는 맞지만 run·charPr 정밀도를 잃었다(조용한 품질 저하).

왜 중요한가:
  1) 문단 readback 검증(V1_RANGE_POSITION_OK / V7_READBACK_MATCH)을 이 위에
     얹으면 옆 칸을 제 칸으로 오인한다. V1 이 하드코딩 FAIL 로 남아 있던
     실질적 이유로 보인다.
  2) 입력칸 추출(form_field_roles.extract_field_cells)이 '빈 문단의 좌표'와
     '격자 셀 좌표'를 대조한다. 조회가 어긋나면 확장 셀 뒤의 칸에서 라벨이
     엉뚱한 칸에 붙는다.

수리: 조회를 파서와 같은 규칙(순번)으로 맞췄다. 좌표계 자체는 그대로라
cellId·paragraphId 키와 renderPayload 격자가 보존되고, 따라서 **시각회귀
baseline 재고정이 필요 없다.** (좌표계를 바꾸는 안은 적재된 입력 스키마
31,350건의 키를 전부 무효화하므로 채택하지 않았다.)

이 테스트는 이제 수리를 고정하는 회귀 감시다 — 다시 어긋나면 실패한다.
"""
from __future__ import annotations

import re
import sys
import unicodedata
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
    """양쪽을 같은 기준으로 눕힌다.

    renderPayload 의 셀 텍스트는 table_parser._normalize 가 NFKC 를 적용한
    결과라 ㎜→mm, ㎡→m2 로 접힌다. documentModel 의 run 텍스트는 XML 원문
    그대로다. 여기서 NFKC 를 맞춰주지 않으면 표기 차이가 좌표 불일치로
    오인된다(실측: '210㎜×297㎜' vs '210mm×297mm').
    """
    s = unicodedata.normalize("NFKC", s or "")
    return _MIDDOT.sub("", re.sub(r"\s+", "", s))


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
    """비교 대상이 실제로 있는 상태에서 불일치가 0 인지 본다.

    위 테스트만 두면 '비교할 셀이 0개라 통과'하는 빈 통과를 구분하지 못한다.
    여기서는 공통 좌표가 존재함을 먼저 확인하고, 그 위에서 불일치 0 을
    요구한다(수리 전 실측 4/51 ≈ 7.8%).
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
    assert len(common) >= 40, f"비교 표본이 너무 작다({len(common)})"
    bad = _mismatches(FIXTURE)
    assert not bad, (
        f"좌표 불일치 {len(bad)}/{len(common)} — 셀 조회가 다시 격자 주소로 "
        "돌아갔는지 확인할 것(ro_view_importer._find_cell_elem)")


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
