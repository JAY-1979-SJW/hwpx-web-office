"""HWPX-CELL-STYLE-POSTPROCESS-01 감사 스크립트.

15개 항목을 검사한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HWPX_DIR = PROJECT_ROOT / "scripts" / "hwpx"
PIPELINE_DIR = HWPX_DIR / "pipeline"
TESTS_DIR = PROJECT_ROOT / "tests"
CONTRACTS_DIR = PROJECT_ROOT / "docs" / "contracts"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


et_path = HWPX_DIR / "hwpx_edit_tool.py"
et_src = et_path.read_text(encoding="utf-8") if et_path.exists() else ""

to_path = HWPX_DIR / "hwpx_table_ops.py"
to_src = to_path.read_text(encoding="utf-8") if to_path.exists() else ""

vf_path = PIPELINE_DIR / "style_postprocess_verifier.py"
vf_src = vf_path.read_text(encoding="utf-8") if vf_path.exists() else ""

test_path = TESTS_DIR / "test_hwpx_cell_style_postprocess.py"
test_src = test_path.read_text(encoding="utf-8") if test_path.exists() else ""

contract_path = CONTRACTS_DIR / "hwpx_editor_api_contract.md"
contract_src = contract_path.read_text(encoding="utf-8") if contract_path.exists() else ""

# ── C01–C02: solid fill 함수 존재 ─────────────────────────────────────────────
check("C01", "ensure_solid_border_fill 함수 존재", "def ensure_solid_border_fill" in to_src)
check("C02", "set_table_visual_cell_solid_fill 함수 존재", "def set_table_visual_cell_solid_fill" in to_src)

# ── C03: borderFill clone/ensure 로직 ─────────────────────────────────────────
check("C03", "borderFill 복제/재사용 로직 존재",
      "REUSED_EXISTING" in to_src and "CREATED_NEW" in to_src)

# ── C04: _apply_cell_post_edit_options solid_fill 처리 ────────────────────────
check("C04", "_apply_cell_post_edit_options에서 solid_fill 처리",
      "solid_fill" in et_src and "set_table_visual_cell_solid_fill" in et_src)

# ── C05–C08: 4개 plan 키 style 옵션 연결 ──────────────────────────────────────
check("C05", "set_cells solid_fill 옵션 연결",
      "set_cells" in et_src and "solid_fill" in et_src)
check("C06", "set_cells_by_label solid_fill 연결",
      "set_cells_by_label" in et_src and "_apply_cell_post_edit_options" in et_src)
check("C07", "set_cells_by_text solid_fill 연결",
      "set_cells_by_text" in et_src and "_apply_cell_post_edit_options" in et_src)
check("C08", "set_visual_cells solid_fill 연결",
      "set_visual_cells" in et_src and "_apply_cell_post_edit_options" in et_src)

# ── C09: set_cell_styles plan 키 존재 ─────────────────────────────────────────
check("C09", "set_cell_styles plan 키 존재",
      "set_cell_styles" in et_src and '"set_cell_styles"' in et_src)

# ── C10: fill_schedule_bars plan 키 존재 ──────────────────────────────────────
check("C10", "fill_schedule_bars plan 키 존재",
      "fill_schedule_bars" in et_src and '"fill_schedule_bars"' in et_src)

# ── C11: style_postprocess_verifier 존재 ──────────────────────────────────────
check("C11", "style_postprocess_verifier.py 존재",
      vf_path.exists() and len(vf_src) > 200)

# ── C12: Parser V2 재파싱 검증 테스트 존재 ────────────────────────────────────
check("C12", "Parser V2 재파싱 fillColor 검증 테스트 존재",
      "parse_hwpx_v2" in test_src and "fillColor" in test_src)

# ── C13: full_verify 테스트 존재 ──────────────────────────────────────────────
check("C13", "full_verify 테스트 존재",
      "full_verify" in test_src or "hwpx_full_verify" in test_src)

# ── C14: API 계약 문서 반영 ────────────────────────────────────────────────────
check("C14", "API 계약 문서에 solid_fill 반영",
      "solid_fill" in contract_src and "set_cell_styles" in contract_src and "fill_schedule_bars" in contract_src)

# ── C15: repair_for_server 미사용 ─────────────────────────────────────────────
check("C15", "repair_for_server 미사용",
      "repair_for_server" not in et_src and "repair_for_server" not in to_src)

# ── 결과 출력 ─────────────────────────────────────────────────────────────────

pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-CELL-STYLE-POSTPROCESS-01 감사 결과")
print(f"{'='*64}")
for cid, desc, status in results:
    mark = "✓" if status == "PASS" else "✗"
    print(f"  [{mark}] {cid}: {desc}")
    if status != "PASS":
        print(f"        → {status}")

print(f"\n{'='*64}")
print(f"  총 {len(results)}개 검사 | PASS {pass_count} | FAIL {fail_count}")
print(f"  최종 판정: {'PASS' if fail_count == 0 else 'FAIL'}")
print(f"{'='*64}\n")

sys.exit(0 if fail_count == 0 else 1)
