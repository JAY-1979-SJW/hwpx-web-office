"""HWPX 구조 진단 CLI — 서식(문서)/문자(스타일)/셀(표) 단위로 훑어본다.

새 파서를 만들지 않는다. 이미 있는 scripts/hwpx/parser/parser_engine.py의
parse_hwpx_v2()가 만드는 ParserV2Result를 사람이 읽기 좋게 출력만 한다.
"왜 이 칸을 못 알아봤나" 같은 정밀 진단은 scripts/ops/diagnose_hwpx_recognition_gap.py
(corpus DB 필요)가 이미 하므로, 이 도구는 그보다 가벼운 "파일 하나 바로 확인"용이다.

read-only. 원본 무수정. writer 미호출.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from hwpx.parser import parse_hwpx_v2  # ruff: ignore[module-import-not-at-top-of-file]


def _print_document(result) -> None:
    doc = result.document
    pkg = result.package
    print("=" * 70)
    print("[서식] 문서 요약")
    print("=" * 70)
    print(f"  zip 정상        : {pkg.entryCount > 0}")
    print(f"  header.xml 정상 : {pkg.xmlDecodeOk}")
    print(f"  섹션 수         : {len(result.sections)}")
    print(f"  제목 후보       : {doc.titleCandidate!r}")
    print(f"  문단 수         : {doc.paragraphCount}")
    print(f"  전체 블록 수    : {doc.blockCount}")
    print(f"  표 수           : {doc.tableCount}")
    print(f"  이미지 수       : {doc.imageCount}")
    print(f"  드로잉 수       : {doc.drawingCount}")
    if result.errors:
        print(f"  [errors] {len(result.errors)}건")
        for e in result.errors:
            print(f"    - {e.code}: {e.detail}")
    if result.warnings:
        print(f"  [warnings] {len(result.warnings)}건")
        for w in result.warnings[:20]:
            print(f"    - {w.code}: {w.detail}")
        if len(result.warnings) > 20:
            print(f"    ... 외 {len(result.warnings) - 20}건")


def _print_styles(result) -> None:
    s = result.styles
    print()
    print("=" * 70)
    print("[문자] 스타일 요약")
    print("=" * 70)
    print(f"  charPr 정의 수     : {s.charPrCount}")
    print(f"  paraPr 정의 수     : {s.paraPrCount}")
    print(f"  borderFill 정의 수 : {s.borderFillCount}")
    print(f"  색상 팔레트        : {s.colorPalette[:10]}")
    if s.danglingRefs:
        print(f"  [WARN] 참조는 있는데 정의가 없는 스타일 ID: {s.danglingRefs[:10]}")
    if s.styleWarnings:
        for w in s.styleWarnings[:10]:
            print(f"  [WARN] {w}")


def _print_tables(result, max_cells: int, text_width: int) -> None:
    print()
    print("=" * 70)
    print(f"[셀] 표 {len(result.tables)}개")
    print("=" * 70)
    for t in result.tables:
        print(
            f"  표 {t.tableIndex} (tableId={t.tableId}) "
            f"— {t.rowCount}행 x {t.colCount}열"
            f"{' (병합 있음)' if t.hasMergedCells else ''}"
            f" — 분류: {t.layoutGuess} (신뢰도 {t.confidence:.2f})"
        )
        if t.warnings:
            for w in t.warnings[:5]:
                print(f"      [WARN] {w}")
        shown = t.cells[:max_cells]
        for c in shown:
            text = c.normalizedText.replace("\n", " ")[:text_width]
            span = f"span={c.rowSpan}x{c.colSpan}" if (c.rowSpan > 1 or c.colSpan > 1) else ""
            merge = "origin" if c.isMergedOrigin else ("covered" if c.isCoveredByMerge else "")
            flags = " ".join(x for x in (span, merge) if x)
            print(f"      [{c.row},{c.col}] {flags:<18} {text!r}")
        if len(t.cells) > max_cells:
            print(f"      ... 외 {len(t.cells) - max_cells}칸 (--max-cells 로 더 보기)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="hwpx 파일 경로")
    ap.add_argument("--json", action="store_true", help="ParserV2Result 전체를 JSON으로 출력")
    ap.add_argument("--max-cells", type=int, default=30, help="표마다 최대 몇 칸까지 출력할지")
    ap.add_argument("--text-width", type=int, default=40, help="셀 텍스트 미리보기 길이")
    args = ap.parse_args()

    path = Path(args.path)
    if not path.is_file():
        print(f"파일 없음: {path}", file=sys.stderr)
        return 1

    result = parse_hwpx_v2(path)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    _print_document(result)
    _print_styles(result)
    _print_tables(result, args.max_cells, args.text_width)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
