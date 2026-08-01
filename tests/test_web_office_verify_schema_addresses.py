"""좌표 검증(②단계) 감리.

고정하는 것:
  · 실재하는 paragraphId 는 OK, 실패 사유별로 정확히 분류된다
  · SOURCE_MISSING·PID_UNPARSEABLE 은 원본 없이도 잡힌다
  · PASS/FAIL 판정은 실패율 임계(2%)로 갈린다 — 재구현이 아니라
    form_direct_fill 의 프로덕션 함수를 그대로 쓴다(주소 규칙 일원화)
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.verify_schema_addresses import (  # noqa: E402
    PASS_MIN_RATIO, verify_one)

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _write_fixture(path: Path) -> None:
    """표 1개 · 2행 2열 — (0,0)(0,1)(1,0) 은 텍스트 run 있음, (1,1) 은 빈 run."""
    sec = (
        f'<hp:sec xmlns:hp="{HP}"><hp:tbl>'
        '<hp:tr>'
        '<hp:tc><hp:p paraPrIDRef="1"><hp:run charPrIDRef="1">'
        '<hp:t>성명</hp:t></hp:run></hp:p></hp:tc>'
        '<hp:tc><hp:p paraPrIDRef="1"><hp:run charPrIDRef="1">'
        '<hp:t>주소</hp:t></hp:run></hp:p></hp:tc>'
        '</hp:tr>'
        '<hp:tr>'
        '<hp:tc><hp:p paraPrIDRef="1"><hp:run charPrIDRef="1">'
        '<hp:t/></hp:run></hp:p></hp:tc>'
        '<hp:tc><hp:p paraPrIDRef="1"/></hp:tc>'   # run 자체가 없음 → NO_RUN
        '</hp:tr>'
        "</hp:tbl></hp:sec>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", sec)


def test_verify_one_all_resolve(tmp_path):
    _write_fixture(tmp_path / "f.hwpx")
    schema = [{"paragraphId": "par_t_s0_000_r0_c0_p0", "label": "성명"},
              {"paragraphId": "par_t_s0_000_r0_c1_p0", "label": "주소"},
              {"paragraphId": "par_t_s0_000_r1_c0_p0", "label": "빈칸"}]
    r = verify_one("f.hwpx", schema, project_root=tmp_path)
    assert r["status"] == "OK"
    assert r["total_cells"] == 3 and r["ok_cells"] == 3 and r["fail_cells"] == 0
    assert r["verdict"] == "PASS"


def test_verify_one_classifies_each_failure_reason(tmp_path):
    _write_fixture(tmp_path / "f.hwpx")
    schema = [
        {"paragraphId": "garbage"},                       # PID_UNPARSEABLE
        {"paragraphId": "par_t_s0_007_r0_c0_p0"},          # TABLE_NOT_FOUND
        {"paragraphId": "par_t_s0_000_r5_c0_p0"},          # ROW_NOT_FOUND
        {"paragraphId": "par_t_s0_000_r0_c9_p0"},          # CELL_NOT_FOUND
        {"paragraphId": "par_t_s0_000_r0_c0_p9"},          # PARAGRAPH_NOT_FOUND
        {"paragraphId": "par_t_s0_000_r1_c1_p0"},          # NO_RUN(빈 run)
    ]
    r = verify_one("f.hwpx", schema, project_root=tmp_path)
    import json
    reasons = json.loads(r["fail_reasons"])
    assert reasons == {
        "PID_UNPARSEABLE": 1, "TABLE_NOT_FOUND": 1, "ROW_NOT_FOUND": 1,
        "CELL_NOT_FOUND": 1, "PARAGRAPH_NOT_FOUND": 1, "NO_RUN": 1,
    }
    assert r["ok_cells"] == 0 and r["fail_cells"] == 6


def test_verify_one_source_missing():
    r = verify_one("no/such/file.hwpx", [{"paragraphId": "par_t_s0_000_r0_c0_p0"}],
                   project_root=Path("."))
    assert r["status"] == "SOURCE_MISSING"
    assert r["fail_cells"] == 1


def test_verdict_threshold(tmp_path):
    _write_fixture(tmp_path / "f.hwpx")
    # 3칸 중 1칸 실패 = 66.7% 성공 — 임계(98%) 아래라 FAIL
    schema = [{"paragraphId": "par_t_s0_000_r0_c0_p0"},
              {"paragraphId": "par_t_s0_000_r0_c1_p0"},
              {"paragraphId": "par_t_s0_000_r5_c0_p0"}]
    r = verify_one("f.hwpx", schema, project_root=tmp_path)
    ratio = r["ok_cells"] / r["total_cells"]
    assert ratio < PASS_MIN_RATIO
    assert r["verdict"] == "FAIL"
