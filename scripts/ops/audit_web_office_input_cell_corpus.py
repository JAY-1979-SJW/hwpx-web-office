"""WEB-OFFICE-INPUT-CELL-CORPUS — 입력칸 분류·서식 전수 감리(코퍼스 학습 조사).

로컬 전체 HWPX 를 상대로 사례별 대응이 아닌 계통 검사를 수행한다:
  1) 파서 입력칸 분류 무결성 — 입력칸은 빈 텍스트(마커 제외), 병합커버 제외
  2) 마커([입력필요]) 해부 — 마커 수 = 라벨 부여 수 (누락 0)
  3) 원본 결함 감지 — 셀 폭 초과 텍스트(한컴도 겹쳐 그리는 주입 결함)
  4) 좌표 무결성 — 레이아웃 박스·모델 셀 연결률, 입력칸 줄 y 가 박스 안
  5) 레이아웃 품질(물림·겹침) 게이트

read-only — 원본 무수정. 한컴 미호출(캐시만 사용). 보고는 stdout(JSON).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/hwpx"))

os.environ.setdefault("HWPX_WEB_OFFICE_HANCOM_REFRESH", "0")  # 캐시만

PASS_VERDICT = "PASS_WEB_OFFICE_INPUT_CELL_CORPUS"
FAIL_VERDICT = "FAIL_WEB_OFFICE_INPUT_CELL_CORPUS"

_MARKER = re.compile(r"\[입력필요:\s*([^\]]+)\]")
# 한글 10pt 폭 근사(px) — 폭 초과 감지는 보수적으로(과검출 방지 1.15 여유)
_CHAR_PX = 13.0
_HU2PX = 96.0 / 7200.0


def _text_px(text: str) -> float:
    """텍스트 폭 근사 — 전각(한글 등) 1.0, 반각 0.55 문자폭."""
    w = 0.0
    for ch in text:
        w += 1.0 if ord(ch) > 0x2E80 else 0.55
    return w * _CHAR_PX


def audit_one(path: Path, project_root: Path) -> dict:
    rel = (str(path.relative_to(project_root))
           if path.is_relative_to(project_root) else str(path))
    rec: dict = {"path": rel, "verdict": "OK", "warnings": []}
    try:
        from scripts.hwpx.web_office.editor_file_bridge import (
            load_hwpx_for_editor)
        r = load_hwpx_for_editor(
            {"operation": "HWPX_EDITOR_LOAD", "sourcePath": rel},
            project_root=project_root)
        if r.get("verdict") != "PASS":
            rec["verdict"] = "ERROR"
            rec["error"] = f"LOAD:{r.get('reason')}"
            return rec
        model = r["documentModel"]
        cells = model.get("cells") or []
        origin = [c for c in cells if not c.get("isCoveredByMerge")]
        inp = [c for c in origin if c.get("isInputCell")]
        rec["cells"] = len(origin)
        rec["inputCells"] = len(inp)

        # 1) 분류 무결성 — 입력칸은 빈 텍스트 또는 마커
        bad_cls = [c["cellId"] for c in inp
                   if (c.get("text") or "").strip()
                   and not _MARKER.search(c.get("text") or "")]
        if bad_cls:
            rec["warnings"].append(f"CLASSIFY:{len(bad_cls)}")
            rec["badClassify"] = bad_cls[:5]

        # 2) 마커 해부 — 셀 마커 전부 라벨 부여됐는가
        marked = [c for c in origin if _MARKER.search(c.get("text") or "")]
        unlabeled = [c["cellId"] for c in marked
                     if not (c.get("isInputCell") and c.get("inputLabel"))]
        rec["markerCells"] = len(marked)
        if unlabeled:
            rec["warnings"].append(f"MARKER_UNLABELED:{len(unlabeled)}")

        # 3) 원본 결함 — 셀 폭 초과 텍스트(주입 결함: 한컴도 겹쳐 그림)
        overflow = []
        z = zipfile.ZipFile(path)
        for sec in [n for n in z.namelist()
                    if re.search(r"section\d+\.xml$", n.lower())]:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(z.read(sec))

            def _ln(t):
                return t.rsplit("}", 1)[-1] if "}" in t else t
            for tc in root.iter():
                if _ln(tc.tag) != "tc":
                    continue
                sz = next((e for e in tc.iter() if _ln(e.tag) == "cellSz"),
                          None)
                if sz is None:
                    continue
                w_px = float(sz.attrib.get("width", 0)) * _HU2PX
                if w_px <= 0:
                    continue
                for p in (e for e in tc.iter() if _ln(e.tag) == "p"):
                    txt = "".join(t.text or "" for t in p.iter()
                                  if _ln(t.tag) == "t")
                    if txt.strip() and _text_px(txt) > w_px * 1.15 + 8:
                        overflow.append(txt.strip()[:16])
                        break
        rec["textOverflowCells"] = len(overflow)
        if overflow:
            rec["warnings"].append(f"SOURCE_TEXT_OVERFLOW:{len(overflow)}")
            rec["overflowSamples"] = overflow[:4]

        # 4)+5) 레이아웃 — 연결률·입력칸 줄 포함·품질 (캐시만, 한컴 미호출)
        from scripts.hwpx.web_office.coordinate_layout import build_layout
        lay = build_layout(
            {"operation": "HWPX_COORD_LAYOUT", "sourcePath": rel},
            project_root=project_root)
        if lay.get("verdict") == "PASS":
            model_ids = {c["cellId"] for c in origin}
            box_ids = set()
            mis_line = 0
            for pd in lay.get("pagesDetail") or []:
                boxes = {}
                for b in pd.get("boxes") or []:
                    if b.get("cellId"):
                        box_ids.add(b["cellId"])
                        boxes.setdefault(b["cellId"], []).append(b)
                for ln in pd.get("lines") or []:
                    cid = ln.get("cellId")
                    if cid and cid in boxes:
                        ok = any(b["y"] - 2 <= ln["y"] <= b["y"] + b["h"] + 2
                                 for b in boxes[cid])
                        if not ok:
                            mis_line += 1
            link = (len(model_ids & box_ids) / len(model_ids)
                    if model_ids else 1.0)
            rec["cellLinkRate"] = round(link, 3)
            if link < 0.999:
                rec["warnings"].append(f"CELL_LINK:{round(link*100, 1)}%")
            if mis_line:
                rec["warnings"].append(f"LINE_OUT_OF_BOX:{mis_line}")
            q = lay.get("quality") or {}
            if q and not q.get("ok"):
                rec["warnings"].append(
                    f"QUALITY:{q.get('cellOverflow')}"
                    f"/{q.get('cellOverflowMaxPx')}px"
                    f"/ovl{q.get('bodyOverlap')}")
        else:
            rec["warnings"].append(f"LAYOUT:{lay.get('reason')}")
    except Exception as e:  # noqa: BLE001
        rec["verdict"] = "ERROR"
        rec["error"] = f"{type(e).__name__}: {e}"[:160]
        return rec
    if rec["warnings"]:
        rec["verdict"] = "WARN"
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", action="append", default=None,
                    help="HWPX 폴더/파일(반복). 기본: samples, uploads, fixtures")
    ap.add_argument("--limit", type=int, default=0, help="상한(0=전수)")
    ap.add_argument("--json", default=None, help="상세 결과 저장 경로")
    args = ap.parse_args()

    roots = args.root or [
        "samples", "tmp/web_office_uploads", "tests/fixtures/hwpx"]
    files: list[Path] = []
    for r in roots:
        base = Path(r) if Path(r).is_absolute() else ROOT / r
        if base.is_file():
            files.append(base)
        elif base.is_dir():
            files.extend(sorted(base.rglob("*.hwpx")))
    if args.limit:
        files = files[: args.limit]

    results = [audit_one(p, ROOT) for p in files]
    ok = sum(1 for r in results if r["verdict"] == "OK")
    warn = sum(1 for r in results if r["verdict"] == "WARN")
    err = sum(1 for r in results if r["verdict"] == "ERROR")
    # 경고 유형 집계 — 계통 결함 파악(사례 대응 아님)
    kinds: dict[str, int] = {}
    for r in results:
        for w in r.get("warnings", []):
            k = w.split(":", 1)[0]
            kinds[k] = kinds.get(k, 0) + 1
    summary = {
        "schemaVersion": "web_office_input_cell_corpus_v1",
        "verdict": PASS_VERDICT if err == 0 else FAIL_VERDICT,
        "scanned": len(results),
        "ok": ok, "warn": warn, "error": err,
        "warningKinds": kinds,
        "markerDocs": sum(1 for r in results if r.get("markerCells")),
        "sourceOverflowDocs": sum(
            1 for r in results if r.get("textOverflowCells")),
        "worst": [
            {"path": r["path"], "verdict": r["verdict"],
             "warnings": r.get("warnings", [])[:4],
             "error": r.get("error")}
            for r in results if r["verdict"] != "OK"
        ][:20],
    }
    if args.json:
        Path(args.json).write_text(
            json.dumps({"summary": summary, "results": results},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if summary["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
