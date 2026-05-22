"""HWPX-STYLE-LAYOUT-PARSER-01 감사 스크립트.

14개 항목을 검사한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PARSER_PKG = PROJECT_ROOT / "scripts" / "hwpx" / "parser"
TESTS_DIR = PROJECT_ROOT / "tests"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


# ── 소스 로드 ─────────────────────────────────────────────────────────────────

sp_path = PARSER_PKG / "style_parser.py"
sp_src = sp_path.read_text(encoding="utf-8") if sp_path.exists() else ""

pc_path = PARSER_PKG / "parser_contract.py"
pc_src = pc_path.read_text(encoding="utf-8") if pc_path.exists() else ""

tp_path = PARSER_PKG / "table_parser.py"
tp_src = tp_path.read_text(encoding="utf-8") if tp_path.exists() else ""

pe_path = PARSER_PKG / "parser_engine.py"
pe_src = pe_path.read_text(encoding="utf-8") if pe_path.exists() else ""

test_path = TESTS_DIR / "test_hwpx_style_layout_parser.py"
test_src = test_path.read_text(encoding="utf-8") if test_path.exists() else ""

# ── C01–C05: style_parser.py 함수 존재 ───────────────────────────────────────

check("C01", "parse_char_pr_defs 함수 존재", "def parse_char_pr_defs" in sp_src)
check("C02", "parse_para_pr_defs 함수 존재", "def parse_para_pr_defs" in sp_src)
check("C03", "parse_border_fill_defs 함수 존재", "def parse_border_fill_defs" in sp_src)
check("C04", "extract_fill_color 함수 존재", "def extract_fill_color" in sp_src)
check("C05", "detect_dangling_refs ID 기반 구현",
      "charPr.keys()" in sp_src and "borderFill.keys()" in sp_src,
      "ID 비교 로직 없음")

# ── C06–C08: parser_contract.py CellInfo 필드 ────────────────────────────────

check("C06", "CellInfo.fontHeight 필드 존재", "fontHeight" in pc_src)
check("C07", "CellInfo.borderSummary 필드 존재", "borderSummary" in pc_src)
check("C08", "CellInfo.styleWarnings 필드 존재", "styleWarnings" in pc_src)

# ── C09–C10: StyleInfo 필드 ───────────────────────────────────────────────────

check("C09", "StyleInfo.charPr dict 필드 존재",
      "charPr: dict" in pc_src or "charPr=" in pc_src)
check("C10", "StyleInfo.colorPalette 필드 존재", "colorPalette" in pc_src)

# ── C11–C12: table_parser.py 연결 ─────────────────────────────────────────────

check("C11", "table_parser._extract_cell_style 함수 존재",
      "def _extract_cell_style" in tp_src)
check("C12", "parse_tables_from_section style_defs 파라미터 존재",
      "style_defs" in tp_src)

# ── C13: parser_engine.py 연결 ────────────────────────────────────────────────

check("C13", "parser_engine style_defs 전달 코드 존재",
      "_style_defs" in pe_src and "style_defs=_style_defs" in pe_src)

# ── C14: 테스트 파일 존재 ─────────────────────────────────────────────────────

check("C14", "test_hwpx_style_layout_parser.py 존재",
      test_path.exists() and len(test_src) > 500)

# ── 결과 출력 ─────────────────────────────────────────────────────────────────

pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-STYLE-LAYOUT-PARSER-01 감사 결과")
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
