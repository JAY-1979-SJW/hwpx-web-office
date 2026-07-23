"""WEB-OFFICE-FIXTURE-CANDIDATE-SCAN — 코퍼스 구조 특성 스캔(fixture 선정용).

form_library(정부 서식 실제 문서) 전수를 XML 정규식으로 가볍게 스캔해 구조
극단치 순위표를 만든다. 목적은 M0 하네스 확장용 fixture 4개 선정 — 병합
많은 것·체크박스 있는 것·다단 있는 것·세로쓰기 있는 것을 코퍼스에서 골라
내는 것. read-only — 원본 무수정, 압축 해제 없이 zip 안에서 직접 읽는다.
"""
from __future__ import annotations

import json
import re
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "data/drafts/form_library"

_RE_ROWSPAN = re.compile(r'rowSpan="(\d+)"')
_RE_COLSPAN = re.compile(r'colSpan="(\d+)"')
_RE_COLCOUNT = re.compile(r'colCount="(\d+)"')
_RE_VERTICAL = re.compile(r'textDirection="VERTICAL')
_RE_TBL = re.compile(r'<hp:tbl\b')
_CHECKBOX_CHARS = "☑☐■□✓✔☒"


def scan_one(path: Path) -> dict | None:
    try:
        z = zipfile.ZipFile(path)
        sec_names = [n for n in z.namelist()
                     if re.search(r"section\d+\.xml$", n.lower())]
        if not sec_names:
            return None
        text_all = ""
        for n in sec_names:
            text_all += z.read(n).decode("utf-8", "ignore")
        bindata = sum(1 for n in z.namelist()
                      if n.startswith("BinData/"))
        rowspans = [int(m) for m in _RE_ROWSPAN.findall(text_all)]
        colspans = [int(m) for m in _RE_COLSPAN.findall(text_all)]
        colcounts = [int(m) for m in _RE_COLCOUNT.findall(text_all)]
        # 체크박스 문자 — <hp:t> 텍스트 노드 내부만(대략, 태그 밖 텍스트는
        # 원래 없으므로 전체에서 세도 근사로 충분)
        checkbox_n = sum(text_all.count(ch) for ch in _CHECKBOX_CHARS)
        return {
            "path": str(path.relative_to(ROOT)),
            "maxRowSpan": max(rowspans, default=1),
            "maxColSpan": max(colspans, default=1),
            "tableCount": len(_RE_TBL.findall(text_all)),
            "maxColCount": max(colcounts, default=1),
            "checkboxChars": checkbox_n,
            "verticalCells": len(_RE_VERTICAL.findall(text_all)),
            "images": bindata,
            "sizeKB": round(path.stat().st_size / 1024, 1),
        }
    except Exception as e:  # noqa: BLE001
        return {"path": str(path.relative_to(ROOT)), "error": str(e)[:100]}


def main() -> int:
    files = sorted(LIB.glob("*.hwpx"))
    print(f"스캔 대상: {len(files)}건", file=sys.stderr)
    t0 = time.time()
    results = []
    for i, p in enumerate(files):
        r = scan_one(p)
        if r and "error" not in r:
            results.append(r)
        if (i + 1) % 2000 == 0:
            print(f"  진행 {i+1}/{len(files)} ({time.time()-t0:.0f}s)",
                  file=sys.stderr)

    def top(key, n=8, reverse=True):
        return sorted(
            [r for r in results if r.get(key, 0) > 0],
            key=lambda r: r[key], reverse=reverse)[:n]

    summary = {
        "schemaVersion": "web_office_fixture_candidate_scan_v1",
        "scanned": len(results),
        "elapsedSec": round(time.time() - t0, 1),
        "topByRowSpan": [
            {"path": r["path"], "maxRowSpan": r["maxRowSpan"],
             "maxColSpan": r["maxColSpan"], "tableCount": r["tableCount"]}
            for r in top("maxRowSpan")],
        "topByColSpan": [
            {"path": r["path"], "maxColSpan": r["maxColSpan"]}
            for r in top("maxColSpan")],
        "topByCheckbox": [
            {"path": r["path"], "checkboxChars": r["checkboxChars"]}
            for r in top("checkboxChars")],
        "topByMultiColumn": [
            {"path": r["path"], "maxColCount": r["maxColCount"]}
            for r in top("maxColCount")],
        "topByVertical": [
            {"path": r["path"], "verticalCells": r["verticalCells"]}
            for r in top("verticalCells")],
        "topByImages": [
            {"path": r["path"], "images": r["images"]}
            for r in top("images")],
        "counts": {
            "withCheckbox": sum(1 for r in results if r["checkboxChars"] > 0),
            "withMultiColumn": sum(1 for r in results if r["maxColCount"] > 1),
            "withVertical": sum(1 for r in results if r["verticalCells"] > 0),
            "withImages": sum(1 for r in results if r["images"] > 0),
            "maxRowSpanEver": max((r["maxRowSpan"] for r in results),
                                  default=1),
        },
    }
    Path(ROOT / "tmp/fixture_candidate_scan.json").write_text(
        json.dumps({"summary": summary, "results": results},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
