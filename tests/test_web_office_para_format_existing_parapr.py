"""WEB-OFFICE-PARA-FORMAT-01 (M2) — 문단서식(paraPr) 편집 계약 테스트.

핵심 계약:
  - APPLY_PARA_FORMAT 은 문단의 paraPrIDRef 만 교체한다(텍스트/run 무변경).
  - 대상 paraPr 은 반드시 header.xml 에 이미 존재해야 한다.
  - header.xml 은 수정하지 않는다(신규 paraPr 생성 금지, §4).
  - verify7 V5 가 신규 paraPr 도입을 탐지한다.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "hwpx"))

from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor  # noqa: E402
from scripts.hwpx.web_office.paragraph_writer_adapter import (  # noqa: E402
    _SUPPORTED_COMMAND_TYPES,
    _read_header_para_pr_ids,
    apply_paragraph_edits_plan,
)
from scripts.hwpx.web_office.paragraph_save_verify7 import (  # noqa: E402
    _header_para_pr_ids,
)
from hwpx_package import HwpxPackage  # noqa: E402

FIXTURE_REL = "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"
FIXTURE = ROOT / FIXTURE_REL
CLOSEOUT = ROOT / "docs/architecture/web_office_para_format_existing_parapr_closeout.md"
MATCHER = ROOT / "frontend/web_office_viewer/weboffice/format_parpr_matcher.mjs"


def _axes(d: dict) -> tuple:
    return (d.get("align", {}).get("horizontal"),
            d.get("lineSpacing", {}).get("value"),
            d.get("margin", {}).get("left", {}).get("value"))


@pytest.fixture()
def sandbox(tmp_path_factory) -> Path:
    """project-relative 로딩이 필요하므로 저장소 내 tmp/ 하위를 쓴다."""
    d = ROOT / "tmp" / "para_format_test"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(scope="module")
def loaded() -> dict:
    if not FIXTURE.is_file():
        pytest.skip("fixture 없음")
    return load_hwpx_for_editor(
        {"operation": "HWPX_EDITOR_LOAD", "sourcePath": FIXTURE_REL},
        project_root=ROOT)


@pytest.fixture(scope="module")
def target(loaded) -> tuple:
    """(문단, 현재 paraPr, 정렬만 다른 대체 paraPr)."""
    dm = loaded["documentModel"]
    sig = {pid: _axes(d) for pid, d in dm["styles"]["paraPrDefs"].items()}
    for p in dm["paragraphs"]:
        cur = str(p.get("parPrIDRef") or "")
        if cur not in sig or not (p.get("runs") or []):
            continue
        a, ls, ind = sig[cur]
        alt = next((pid for pid, (a2, l2, i2) in sig.items()
                    if l2 == ls and i2 == ind and a2 != a), None)
        if alt:
            return p, cur, alt
    pytest.skip("정렬만 다른 대체 paraPr 이 없는 문서")


def _plan(para: dict, tgt: str) -> list[dict]:
    return [{
        "commandId": "t1", "commandType": "APPLY_PARA_FORMAT",
        "paragraphId": para["paragraphId"],
        "targetParaPrIDRef": tgt,
        "expectedBefore": "".join(r.get("text", "") for r in para["runs"]),
        "containerScope": para.get("containerScope"),
    }]


# ── 1. 시방서 ──────────────────────────────────────────────
def test_closeout_doc_exists_and_states_no_header_mutation():
    assert CLOSEOUT.is_file(), CLOSEOUT
    text = CLOSEOUT.read_text(encoding="utf-8")
    assert "WEB-OFFICE-PARA-FORMAT-01" in text
    assert "header.xml" in text and "mutation" in text
    assert "신규 paraPr 생성" in text


# ── 2. 지원 명령 등록 ──────────────────────────────────────
def test_writer_supports_apply_para_format():
    assert "APPLY_PARA_FORMAT" in _SUPPORTED_COMMAND_TYPES


def test_matcher_module_exists_and_rejects_when_no_match():
    assert MATCHER.is_file()
    src = MATCHER.read_text(encoding="utf-8")
    # 매칭 실패 시 null 반환(=거부) 계약이 코드에 존재
    assert "matchParaAxisChange" in src
    assert "return null" in src


# ── 3. 적용 (텍스트 불변 · paraPr 교체) ────────────────────
def test_apply_para_format_changes_parapr_and_preserves_text(sandbox, target):
    para, before_ppr, tgt = target
    dst = sandbox / "applied.hwpx"
    shutil.copy2(FIXTURE, dst)
    pkg = HwpxPackage(dst)
    res = apply_paragraph_edits_plan(pkg, _plan(para, tgt))
    assert len(res.get("applied", [])) == 1, res.get("rejected")
    assert not res.get("rejected")
    applied = res["applied"][0]
    assert str(applied["afterParaPrIDRef"]) == str(tgt)
    assert applied["afterText"] == "".join(r.get("text", "") for r in para["runs"])
    pkg.write_package(dst)

    # 산출물 재로딩 — paraPr 반영 + 텍스트 동일
    out = load_hwpx_for_editor(
        {"operation": "HWPX_EDITOR_LOAD",
         "sourcePath": str(dst.relative_to(ROOT)).replace("\\", "/")},
        project_root=ROOT)
    p2 = next(x for x in out["documentModel"]["paragraphs"]
              if x["paragraphId"] == para["paragraphId"])
    assert str(p2["parPrIDRef"]) == str(tgt)
    assert ("".join(r.get("text", "") for r in p2["runs"])
            == "".join(r.get("text", "") for r in para["runs"]))


# ── 4. §4: header.xml 무수정 ───────────────────────────────
def test_header_parapr_set_unchanged(tmp_path, target):
    para, _before, tgt = target
    dst = tmp_path / "hdr.hwpx"
    shutil.copy2(FIXTURE, dst)
    pkg = HwpxPackage(dst)
    apply_paragraph_edits_plan(pkg, _plan(para, tgt))
    pkg.write_package(dst)
    assert _header_para_pr_ids(dst) == _header_para_pr_ids(FIXTURE)


# ── 5. 거부 계약 ───────────────────────────────────────────
def test_reject_parapr_not_in_header(tmp_path, target):
    para, _b, _t = target
    dst = tmp_path / "rej.hwpx"
    shutil.copy2(FIXTURE, dst)
    res = apply_paragraph_edits_plan(HwpxPackage(dst), _plan(para, "999999"))
    assert not res.get("applied")
    assert res["rejected"][0]["reason"] == "TARGET_PARAPR_NOT_IN_HEADER"


def test_reject_expected_before_mismatch(tmp_path, target):
    para, _b, tgt = target
    dst = tmp_path / "rej2.hwpx"
    shutil.copy2(FIXTURE, dst)
    plan = _plan(para, tgt)
    plan[0]["expectedBefore"] = "의도적으로 다른 텍스트"
    res = apply_paragraph_edits_plan(HwpxPackage(dst), plan)
    assert not res.get("applied")
    assert res["rejected"][0]["reason"] == "EXPECTED_BEFORE_MISMATCH"


# ── 6. verify7 V5 — 신규 paraPr 도입 탐지 ──────────────────
class _ParaStub:
    def char_pr_set(self):
        return {None}

    def text(self):
        return ""


def test_verify7_v5_flags_new_parapr(sandbox, target):
    from scripts.hwpx.web_office.paragraph_save_verify7 import verify7_paragraphs
    para, _b, _t = target
    dst = sandbox / "v5.hwpx"
    shutil.copy2(FIXTURE, dst)
    # header 에 없는 id 로 "적용됐다"고 위조한 결과를 넣으면 V5 가 잡아야 한다
    fake_applied = [{
        "paragraphId": para["paragraphId"],
        "commandType": "APPLY_PARA_FORMAT",
        "targetParaPrIDRef": "999999",
        "afterParaPrIDRef": "999999",
        "afterText": "x",
    }]
    out = verify7_paragraphs(
        source_path=FIXTURE, output_path=dst, project_root=ROOT,
        applied_plan_edits=fake_applied,
        paragraphs_by_id={para["paragraphId"]: _ParaStub()},
        pre_save_paragraph_texts={})
    assert out["results"]["V5_PARPR_PRESERVED"] == "FAIL"
    assert any(f["code"] == "V5_NEW_PARAPR_INTRODUCED" for f in out["findings"])
