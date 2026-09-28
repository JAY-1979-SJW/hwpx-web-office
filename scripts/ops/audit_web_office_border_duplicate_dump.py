"""WEB-OFFICE-BORDER-DUPLICATE-DUMP — 테두리 중복 진단(저비용, 재설계 근거).

인접 셀 테두리 중복제거가 두 번 연속(완전억제·zero_rows 제외 가드) 실패한
원인을 재설계 전에 규명하기 위한 진단 덤프. 각 표의 모든 내부 경계선에
대해 "몇 개 셀이 그 경계에 테두리를 선언하는지", "그 출처(cellId·방향·
borderFillIDRef)"를 나열한다. fixture 간 이 패턴이 다르면(인접 셀 단순
중복 vs 표 외곽 vs 페이지분할 프래그먼트 경계) 재설계 방향이 갈린다.

read-only — 원본 무수정.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/hwpx"))

from scripts.hwpx.web_office.coordinate_layout import build_layout  # ruff: ignore[module-import-not-at-top-of-file]


def _collect_edge_declarations(lay: dict):
    """경계선(수평/수직) 좌표 키로 그 위치에 테두리를 "그리겠다"고 선언한
    박스들을 모은다. 같은 경계에 2개 이상 몰리면 중복 후보."""
    h_edges: dict[tuple[int, float], list[dict]] = defaultdict(list)
    v_edges: dict[tuple[int, float], list[dict]] = defaultdict(list)
    frag_count = 0

    for pd in lay.get("pagesDetail", []):
        pno = pd["no"]
        for b in pd.get("boxes", []):
            if b.get("frag"):
                frag_count += 1
            bd = b.get("border") or {}
            y0, y1 = round(b["y"], 1), round(b["y"] + b["h"], 1)
            x0, x1 = round(b["x"], 1), round(b["x"] + b["w"], 1)
            if bd.get("t") and bd["t"] != "none":
                h_edges[pno, y0].append({
                    "cellId": b.get("cellId"),
                    "side": "top",
                    "x": x0,
                    "w": b["w"],
                    "spec": bd["t"],
                    "frag": bool(b.get("frag")),
                })
            if bd.get("b") and bd["b"] != "none":
                h_edges[pno, y1].append({
                    "cellId": b.get("cellId"),
                    "side": "bottom",
                    "x": x0,
                    "w": b["w"],
                    "spec": bd["b"],
                    "frag": bool(b.get("frag")),
                })
            if bd.get("l") and bd["l"] != "none":
                v_edges[pno, x0].append({
                    "cellId": b.get("cellId"),
                    "side": "left",
                    "y": y0,
                    "h": b["h"],
                    "spec": bd["l"],
                    "frag": bool(b.get("frag")),
                })
            if bd.get("r") and bd["r"] != "none":
                v_edges[pno, x1].append({
                    "cellId": b.get("cellId"),
                    "side": "right",
                    "y": y0,
                    "h": b["h"],
                    "spec": bd["r"],
                    "frag": bool(b.get("frag")),
                })
    return h_edges, v_edges, frag_count


def _overlapping_groups(edges, span_key):
    """같은 (page, coord) 키 안에서 span(x 또는 y 범위)이 겹치는
    선언들만 진짜 '같은 경계선 중복'으로 묶는다(단순 좌표 일치만으론
    표 폭 전체에 걸친 서로 다른 위치의 선까지 한 그룹으로 오인한다)."""
    groups = []
    for key, decls in edges.items():
        decls = sorted(decls, key=lambda d: d[span_key])
        used = [False] * len(decls)
        for i, d in enumerate(decls):
            if used[i]:
                continue
            grp = [d]
            used[i] = True
            s0, s1 = d[span_key], d[span_key] + d.get("w" if span_key == "x" else "h", 0)
            for j in range(i + 1, len(decls)):
                if used[j]:
                    continue
                e = decls[j]
                es0 = e[span_key]
                es1 = es0 + e.get("w" if span_key == "x" else "h", 0)
                if es0 < s1 - 1 and es1 > s0 + 1:  # 1px 이상 겹침
                    grp.append(e)
                    used[j] = True
            if len(grp) > 1:
                groups.append({"page": key[0], "coord": key[1], "declarations": grp})
    return groups


def _classify(groups):
    """패턴 분류 — 인접 셀(단순 이웃) vs frag(페이지분할 경계) 관여."""
    simple = frag = 0
    samples = []
    for g in groups:
        if any(d["frag"] for d in g["declarations"]):
            frag += 1
        else:
            simple += 1
        if len(samples) < 3:
            samples.append(g)
    return {"simpleAdjacent": simple, "fragBoundary": frag, "samples": samples}


def dump_one(rel: str) -> dict:
    lay = build_layout({"operation": "HWPX_COORD_LAYOUT", "sourcePath": rel}, project_root=ROOT)
    if lay.get("verdict") != "PASS":
        return {"path": rel, "error": lay.get("reason")}

    h_edges, v_edges, frag_count = _collect_edge_declarations(lay)
    h_dup = _overlapping_groups(h_edges, "x")
    v_dup = _overlapping_groups(v_edges, "y")

    return {
        "path": rel,
        "horizontalDupEdges": len(h_dup),
        "verticalDupEdges": len(v_dup),
        "fragBoxes": frag_count,
        "horizontalPattern": _classify(h_dup),
        "verticalPattern": _classify(v_dup),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", action="append", required=True)
    ap.add_argument("--out", default="tmp/border_duplicate_dump.json")
    args = ap.parse_args()

    results = [dump_one(rel) for rel in args.source]
    out = {"schemaVersion": "web_office_border_duplicate_dump_v1", "results": results}
    Path(ROOT / args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(ROOT / args.out).write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
