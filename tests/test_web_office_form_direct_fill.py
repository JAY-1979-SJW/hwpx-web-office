"""서식 직접 채움 감리.

배치·에이전트 채움 경로 — 원본을 사본에 복사해 1회 파싱하고 기입 후 저장.
브라우저 증분 편집 브리지(1,100초)의 재파싱 낭비를 없앤 경로(0.2초)라,
그 대가로 무엇도 잃지 않았음을 고정한다:
  · 값이 지정한 칸에 · 옆칸으로 새지 않고 · 원본을 건드리지 않고
  · 이미 값 있는 칸은 덮지 않고 · 안전하지 않은 run 은 거부하고
  · 중첩 표 안 칸을 바깥 칸으로 오인하지 않는다(오늘 잡은 결함).
"""
from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.form_direct_fill import (  # noqa: E402
    fill_document_direct, parse_paragraph_id)

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


# ── paragraphId 파싱 ────────────────────────────────────────────

def test_parse_paragraph_id_valid():
    assert parse_paragraph_id("par_t_s1_002_r3_c4_p0") == (1, 2, 3, 4, 0)
    assert parse_paragraph_id("par_t_s0_000_r0_c0_p1") == (0, 0, 0, 0, 1)


def test_parse_paragraph_id_rejects_garbage():
    for bad in ("", "par_x", "par_t_s1_r3_c4_p0", "cell_t_s1_002_r3_c4_p0",
                "par_t_s1_002_r3_c4"):
        assert parse_paragraph_id(bad) is None, bad


# ── 최소 HWPX 픽스처 ────────────────────────────────────────────

def _run(char_pr, *children_xml):
    inner = "".join(children_xml)
    return f'<hp:run charPrIDRef="{char_pr}">{inner}</hp:run>'


def _t(text):
    return f"<hp:t>{text}</hp:t>"


def _para(para_pr, *runs):
    return (f'<hp:p paraPrIDRef="{para_pr}">' + "".join(runs) + "</hp:p>")


def _cell(*paras):
    addr = '<hp:cellAddr colAddr="0" rowAddr="0"/>'
    return f"<hp:tc>{addr}" + "".join(paras) + "</hp:tc>"


def _row(*cells):
    return "<hp:tr>" + "".join(cells) + "</hp:tr>"


def _table(*rows):
    return "<hp:tbl>" + "".join(rows) + "</hp:tbl>"


def _section(*blocks):
    return (f'<hp:sec xmlns:hp="{HP}">' + "".join(blocks) + "</hp:sec>")


def _write_hwpx(path: Path, section_xml: str) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", section_xml)


@pytest.fixture
def simple_form(tmp_path):
    """표 1개 · 2행 — 첫 행 라벨(채워짐), 둘째 행 빈 칸(입력칸)."""
    sec = _section(_table(
        _row(_cell(_para("1", _run("10", _t("성명")))),
             _cell(_para("1", _run("11")))),          # 빈 run (텍스트 노드 없음)
        _row(_cell(_para("1", _run("10", _t("주소")))),
             _cell(_para("1", _run("11")))),
    ))
    p = tmp_path / "form.hwpx"
    _write_hwpx(p, sec)
    return p


def _cell_text(hwpx: Path, section="Contents/section0.xml"):
    """저장본을 로더 없이 직접 읽어 (표,행,열) → 텍스트."""
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(hwpx) as z:
        root = ET.fromstring(z.read(section))

    def ln(e):
        return e.tag.rsplit("}", 1)[-1]
    out = {}
    tbls = [e for e in root.iter() if ln(e) == "tbl"]
    for ti, tbl in enumerate(tbls):
        rows = [e for e in tbl if ln(e) == "tr"]
        for ri, r in enumerate(rows):
            cells = [e for e in r if ln(e) == "tc"]
            for ci, c in enumerate(cells):
                # 직속 문단만(중첩 표 제외)
                txt = []

                def walk(el, root_=False):
                    if not root_ and ln(el) == "tbl":
                        return
                    if ln(el) == "t":
                        txt.append(el.text or "")
                    for ch in list(el):
                        walk(ch)
                walk(c, root_=True)
                out[(ti, ri, ci)] = "".join(txt)
    return out


# ── 채움 정확성 ─────────────────────────────────────────────────

def test_fills_empty_cell_and_leaves_source_untouched(simple_form, tmp_path):
    sha0 = hashlib.sha256(simple_form.read_bytes()).hexdigest()
    rel = simple_form.name
    out = fill_document_direct(
        rel, [{"paragraphId": "par_t_s0_000_r0_c1_p0", "value": "홍길동"},
              {"paragraphId": "par_t_s0_000_r1_c1_p0", "value": "서울시"}],
        output_dir=tmp_path / "out", project_root=tmp_path)

    assert out["verdict"] == "PASS", out
    assert out["filled"] == 2
    assert out["sourceUnchanged"] is True
    # 원본 진짜 무변경
    assert hashlib.sha256(simple_form.read_bytes()).hexdigest() == sha0

    texts = _cell_text(Path(out["outputPath"]))
    assert texts[(0, 0, 1)] == "홍길동"      # 겨냥한 칸
    assert texts[(0, 1, 1)] == "서울시"
    # 라벨 칸은 그대로
    assert texts[(0, 0, 0)] == "성명"
    assert texts[(0, 1, 0)] == "주소"


def test_no_leak_to_other_cells(simple_form, tmp_path):
    out = fill_document_direct(
        rel := simple_form.name,
        [{"paragraphId": "par_t_s0_000_r0_c1_p0", "value": "UNIQUE_A"}],
        output_dir=tmp_path / "out", project_root=tmp_path)
    texts = _cell_text(Path(out["outputPath"]))
    hits = [k for k, v in texts.items() if "UNIQUE_A" in v]
    assert hits == [(0, 0, 1)], f"값이 겨냥 밖 칸에 나타남: {hits}"


def test_output_is_separate_file(simple_form, tmp_path):
    out = fill_document_direct(
        simple_form.name,
        [{"paragraphId": "par_t_s0_000_r0_c1_p0", "value": "x"}],
        output_dir=tmp_path / "out", project_root=tmp_path)
    assert Path(out["outputPath"]) != simple_form
    assert Path(out["outputPath"]).is_file()


# ── 덮어쓰기 방지 ───────────────────────────────────────────────

def test_nonempty_cell_skipped_by_default(simple_form, tmp_path):
    """라벨 칸(성명)은 이미 값이 있으니 덮지 않는다."""
    out = fill_document_direct(
        simple_form.name,
        [{"paragraphId": "par_t_s0_000_r0_c0_p0", "value": "덮어쓰기시도"}],
        output_dir=tmp_path / "out", project_root=tmp_path)
    assert out["verdict"] == "NOOP"
    assert out["filled"] == 0
    assert out["skipped"] and out["skippedItems"][0]["reason"] == "CELL_NOT_EMPTY"


def test_overwrite_flag_allows_nonempty(simple_form, tmp_path):
    out = fill_document_direct(
        simple_form.name,
        [{"paragraphId": "par_t_s0_000_r0_c0_p0", "value": "새이름"}],
        output_dir=tmp_path / "out", project_root=tmp_path,
        overwrite_nonempty=True)
    assert out["filled"] == 1
    texts = _cell_text(Path(out["outputPath"]))
    assert "새이름" in texts[(0, 0, 0)]


# ── 반려 ────────────────────────────────────────────────────────

def test_bad_coordinates_rejected(simple_form, tmp_path):
    out = fill_document_direct(
        simple_form.name,
        [{"paragraphId": "par_t_s0_000_r9_c9_p0", "value": "x"},   # 범위 밖
         {"paragraphId": "par_t_s5_000_r0_c0_p0", "value": "y"},   # 없는 섹션
         {"paragraphId": "엉터리", "value": "z"}],                  # 파싱 불가
        output_dir=tmp_path / "out", project_root=tmp_path)
    reasons = {r["reason"] for r in out["rejected"]}
    assert "CELL_NOT_FOUND" in reasons or "ROW_NOT_FOUND" in reasons
    assert "TABLE_NOT_FOUND" in reasons
    assert "PID_UNPARSEABLE" in reasons
    assert out["filled"] == 0


def test_empty_value_rejected(simple_form, tmp_path):
    out = fill_document_direct(
        simple_form.name,
        [{"paragraphId": "par_t_s0_000_r0_c1_p0", "value": ""}],
        output_dir=tmp_path / "out", project_root=tmp_path)
    assert out["rejected"][0]["reason"] == "EMPTY_VALUE"


# ── 안전하지 않은 run 은 거부 ───────────────────────────────────

def test_run_with_ctrl_child_rejected(tmp_path):
    """hp:ctrl 등이 섞인 run 에는 쓰지 않는다(안전한 쪽으로 실패)."""
    sec = _section(_table(_row(
        _cell(_para("1", '<hp:run charPrIDRef="11"><hp:ctrl/></hp:run>')),
    )))
    p = tmp_path / "ctrl.hwpx"
    _write_hwpx(p, sec)
    out = fill_document_direct(
        p.name, [{"paragraphId": "par_t_s0_000_r0_c0_p0", "value": "x"}],
        output_dir=tmp_path / "out", project_root=tmp_path)
    assert out["filled"] == 0
    assert out["rejected"][0]["reason"] == "RUN_TEXT_NODE_MISSING"


# ── 중첩 표를 바깥 칸으로 오인하지 않는다 (오늘 잡은 결함) ────────

def test_nested_table_cell_not_confused_with_outer(tmp_path):
    """바깥 셀의 빈 문단에 쓰되, 그 셀 안 중첩 표 문단은 건드리지 않는다."""
    nested = _table(_row(_cell(_para("1", _run("10", _t("안쪽값"))))))
    # 바깥 셀: 빈 직속 문단 + 중첩 표
    outer_cell = f'<hp:tc><hp:cellAddr colAddr="0" rowAddr="0"/>' \
                 f'{_para("1", _run("11"))}{nested}</hp:tc>'
    sec = _section(_table(_row(outer_cell)))
    p = tmp_path / "nested.hwpx"
    _write_hwpx(p, sec)

    out = fill_document_direct(
        p.name, [{"paragraphId": "par_t_s0_000_r0_c0_p0", "value": "바깥값"}],
        output_dir=tmp_path / "out", project_root=tmp_path)
    assert out["filled"] == 1, out

    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(out["outputPath"]) as z:
        root = ET.fromstring(z.read("Contents/section0.xml"))

    def ln(e):
        return e.tag.rsplit("}", 1)[-1]
    texts = [e.text for e in root.iter() if ln(e) == "t"]
    # 바깥 문단에 값이 들어가고, 안쪽 값은 보존
    assert "바깥값" in texts
    assert "안쪽값" in texts
    # 안쪽값이 바깥값으로 덮이지 않았다
    assert texts.count("안쪽값") == 1
