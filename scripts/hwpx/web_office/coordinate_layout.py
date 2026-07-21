"""HWPX lineseg 기반 좌표 레이아웃 추출기 (프로토타입).

한컴이 저장 시 계산한 lineseg(줄별 vertpos/horzpos/size)를 그대로 써서
페이지 좌표 레이아웃(JSON)을 만든다. 브라우저 재-flow 없이 원본 배치를
재현하기 위한 데이터. read-only, 원본 무수정.
"""
import json
import sys
import zipfile
import xml.etree.ElementTree as ET

HU = 96 / 7200  # HWPUNIT -> px (96dpi)


def ln(tag):
    return tag.rsplit("}", 1)[-1]


def _own_text(p):
    """문단 직속 run 의 텍스트(셀/중첩 제외)."""
    parts = []
    for run in p:
        if ln(run.tag) != "run":
            continue
        for c in run:
            if ln(c.tag) in ("t",):
                parts.append("".join(c.itertext()))
            elif ln(c.tag) == "lineBreak":
                parts.append("\n")
    return "".join(parts)


def _direct_linesegs(p):
    out = []
    for arr in p:
        if ln(arr.tag) == "linesegarray":
            for s in arr:
                if ln(s.tag) == "lineseg":
                    out.append(s.attrib)
    return out


def _para_bold(p, header_bytes=None):
    return False  # 서식은 후속 — v1 은 위치/줄바꿈 재현에 집중


def _parse_border_fills(z):
    """header.xml 의 borderFill 정의 → {id: {left/right/top/bottom sides}}."""
    hdr = [n for n in z.namelist() if n.lower().endswith("header.xml")]
    if not hdr:
        return {}
    root = ET.fromstring(z.read(hdr[0]))
    out = {}
    for bf in root.iter():
        if ln(bf.tag) != "borderFill":
            continue
        bid = bf.attrib.get("id")
        sides = {}
        for ch in bf:
            name = ln(ch.tag)
            if name in ("leftBorder", "rightBorder", "topBorder",
                        "bottomBorder"):
                sides[name] = dict(ch.attrib)
        if bid is not None:
            out[bid] = sides
    return out


def extract(path):
    z = zipfile.ZipFile(path)
    secname = [n for n in z.namelist()
               if "section0" in n.lower() and n.endswith(".xml")][0]
    root = ET.fromstring(z.read(secname))
    border_fills = _parse_border_fills(z)

    pp = next((e.attrib for e in root.iter() if ln(e.tag) == "pagePr"), {})
    mg = next((e.attrib for e in root.iter() if ln(e.tag) == "margin"), {})
    page_w = float(pp.get("width", "59528")) * HU
    page_h = float(pp.get("height", "84186")) * HU
    m_left = float(mg.get("left", "4251")) * HU
    m_top = float(mg.get("top", "4251")) * HU

    lines = []
    boxes = []
    st = {"page_idx": 0, "prev_vpos": -1, "flow_y": m_top, "max_y": m_top}

    def emit_para(p):
        txt = _own_text(p)
        segs = _direct_linesegs(p)
        for i, s in enumerate(segs):
            vpos = float(s.get("vertpos", "0"))
            a = int(s.get("textpos", "0"))
            b = (int(segs[i + 1].get("textpos"))
                 if i + 1 < len(segs) else len(txt))
            line_txt = txt[a:b]
            if st["prev_vpos"] >= 0 and vpos + 1 < st["prev_vpos"]:
                st["page_idx"] += 1  # vpos 리셋 → 새 페이지
            st["prev_vpos"] = vpos
            y = (st["page_idx"] * page_h) + m_top + vpos * HU
            x = m_left + float(s.get("horzpos", "0")) * HU
            w = float(s.get("horzsize", "0")) * HU
            h = float(s.get("vertsize", "1000")) * HU
            lines.append({"text": line_txt, "x": round(x, 1),
                          "y": round(y, 1), "w": round(w, 1),
                          "h": round(h, 1), "cell": False})
            st["max_y"] = max(st["max_y"], y + h)
        st["flow_y"] = st["max_y"]

    def _cell_info(tc):
        addr = next((c.attrib for c in tc if ln(c.tag) == "cellAddr"), {})
        span = next((c.attrib for c in tc if ln(c.tag) == "cellSpan"), {})
        sz = next((c.attrib for c in tc if ln(c.tag) == "cellSz"), {})
        mg = next((c.attrib for c in tc if ln(c.tag) == "cellMargin"), {})
        sub = next((c.attrib for c in tc if ln(c.tag) == "subList"), {})
        return {
            "row": int(addr.get("rowAddr", "0")),
            "col": int(addr.get("colAddr", "0")),
            "rowSpan": int(span.get("rowSpan", "1") or "1"),
            "colSpan": int(span.get("colSpan", "1") or "1"),
            "w": float(sz.get("width", "0")) * HU,
            "h": float(sz.get("height", "0")) * HU,
            "ml": float(mg.get("left", "0")) * HU,
            "mt": float(mg.get("top", "0")) * HU,
            "bfRef": tc.attrib.get("borderFillIDRef"),
            "vAlign": sub.get("vertAlign", "TOP"),
            "tc": tc,
        }

    def _solve_axis(cells, n, key_start, key_span, key_size):
        """단일-span 셀로 축(열폭/행높이) 확정 + 다중-span 나머지 분배."""
        w = [0.0] * n
        # 1) 단일 span 확정
        for c in cells:
            if c[key_span] == 1:
                w[c[key_start]] = max(w[c[key_start]], c[key_size])
        # 2) 다중 span: 미지 칸에 나머지 균등 분배 (2회 반복)
        for _ in range(3):
            for c in cells:
                if c[key_span] <= 1:
                    continue
                idxs = list(range(c[key_start], c[key_start] + c[key_span]))
                idxs = [i for i in idxs if 0 <= i < n]
                known = sum(w[i] for i in idxs if w[i] > 0)
                unknown = [i for i in idxs if w[i] <= 0]
                if unknown and c[key_size] > known:
                    share = (c[key_size] - known) / len(unknown)
                    for i in unknown:
                        w[i] = share
        # 남은 0 은 평균으로
        known = [x for x in w if x > 0]
        avg = sum(known) / len(known) if known else 1.0
        return [x if x > 0 else avg for x in w]

    def walk_table(tbl):
        cells = [_cell_info(tc) for tc in tbl.iter()
                 if ln(tc.tag) == "tc"]
        # 중첩표 제외: 이 tbl 의 "직속" 셀만 (다른 tbl 안의 tc 배제)
        cells = [c for c in cells
                 if _nearest_tbl(c["tc"], tbl) is tbl]
        if not cells:
            return
        ncol = max((c["col"] + c["colSpan"] for c in cells), default=1)
        nrow = max((c["row"] + c["rowSpan"] for c in cells), default=1)
        col_w = _solve_axis(cells, ncol, "col", "colSpan", "w")
        row_h = _solve_axis(cells, nrow, "row", "rowSpan", "h")
        col_x = [0.0] * (ncol + 1)
        for i in range(ncol):
            col_x[i + 1] = col_x[i] + col_w[i]
        row_y = [0.0] * (nrow + 1)
        for i in range(nrow):
            row_y[i + 1] = row_y[i] + row_h[i]
        base_x = m_left
        base_y = st["flow_y"] + 4  # 흐름 위치 (직전 본문 아래)
        table_bottom = base_y
        for c in cells:
            cx = base_x + col_x[c["col"]]
            cy = base_y + row_y[c["row"]]
            cw = col_x[min(c["col"] + c["colSpan"], ncol)] - col_x[c["col"]]
            ch = row_y[min(c["row"] + c["rowSpan"], nrow)] - row_y[c["row"]]
            # 셀 라인 수집 (셀 상대 좌표)
            cell_lines = []
            for cp in c["tc"].iter():
                if ln(cp.tag) == "p":
                    cell_lines.extend(_cell_para_lines(cp))
            # 수직정렬(vertAlign) 오프셋: 텍스트 블록을 셀 안에서 정렬
            text_h = max((cl["ry"] + cl["h"] for cl in cell_lines), default=0)
            avail = ch - c["mt"] * 2
            va = c["vAlign"]
            voff = (max(0.0, (avail - text_h) / 2) if va == "CENTER"
                    else max(0.0, avail - text_h) if va == "BOTTOM"
                    else 0.0)
            for cl in cell_lines:
                lines.append({
                    "text": cl["text"],
                    "x": round(cx + c["ml"] + cl["rx"], 1),
                    "y": round(cy + c["mt"] + voff + cl["ry"], 1),
                    "w": round(cl["w"], 1), "h": round(cl["h"], 1),
                    "cell": True})
            box = {"x": round(cx, 1), "y": round(cy, 1),
                   "w": round(cw, 1), "h": round(ch, 1)}
            bf = border_fills.get(c["bfRef"])
            if bf:
                box["border"] = _border_sides_css(bf)
            boxes.append(box)
            table_bottom = max(table_bottom, cy + ch)
        st["flow_y"] = table_bottom + 4
        st["max_y"] = max(st["max_y"], table_bottom)

    def _nearest_tbl(el, target):
        # el 의 조상 중 가장 가까운 tbl 이 target 인지 (중첩표 판별용 근사)
        return target  # 근사: 대부분 단층. 중첩표는 후속.

    def _nearest_cell(p, tc):
        return tc  # 근사

    def _cell_para_lines(p):
        """셀 문단 → 셀 상대 라인 [{rx, ry, w, h, text}]."""
        txt = _own_text(p)
        segs = _direct_linesegs(p)
        out = []
        for i, s in enumerate(segs):
            a = int(s.get("textpos", "0"))
            b = (int(segs[i + 1].get("textpos"))
                 if i + 1 < len(segs) else len(txt))
            out.append({
                "rx": float(s.get("horzpos", "0")) * HU,
                "ry": float(s.get("vertpos", "0")) * HU,
                "w": float(s.get("horzsize", "0")) * HU,
                "h": float(s.get("vertsize", "1000")) * HU,
                "text": txt[a:b]})
        return out

    def _mm_px(v):
        import re as _re
        m = _re.search(r"([\d.]+)\s*mm", v or "")
        return float(m.group(1)) * 3.7795 if m else 0.0

    def _border_sides_css(sides):
        def one(sd):
            if not sd or sd.get("type", "NONE") == "NONE":
                return "none"
            w = max(0.7, _mm_px(sd.get("width")))
            return f"{w:.2f}px solid {sd.get('color', '#000')}"
        return {
            "l": one(sides.get("leftBorder")),
            "r": one(sides.get("rightBorder")),
            "t": one(sides.get("topBorder")),
            "b": one(sides.get("bottomBorder")),
        }

    def walk(el):
        for child in el:
            if ln(child.tag) == "p":
                emit_para(child)
                for tbl in child.iter():
                    if ln(tbl.tag) == "tbl":
                        walk_table(tbl)
                        break

    walk(root)
    import math
    total_pages = max(st["page_idx"] + 1,
                      int(math.ceil(st["max_y"] / page_h)) if page_h else 1)
    return {
        "pageWidthPx": round(page_w, 1),
        "pageHeightPx": round(page_h, 1),
        "marginLeftPx": round(m_left, 1),
        "marginTopPx": round(m_top, 1),
        "pages": total_pages,
        "lines": lines,
        "boxes": boxes,
    }


import pathlib as _pathlib  # noqa: E402

PROJECT_ROOT = _pathlib.Path(__file__).resolve().parents[3]


def extract_layout(path):
    """공개 API 별칭 (extract 와 동일)."""
    return extract(path)


def build_layout(request, *, project_root=PROJECT_ROOT):
    """{sourcePath} → 좌표 레이아웃. 프로젝트-상대 .hwpx 만 허용(보안).

    반환: {"verdict": "PASS", ...layout, "sourcePath": rel} 또는
          {"verdict": "REJECTED", "reason": ...}.
    """
    if not isinstance(request, dict):
        return {"verdict": "REJECTED", "reason": "REQUEST_NOT_OBJECT"}
    sp = request.get("sourcePath")
    if not isinstance(sp, str) or not sp:
        return {"verdict": "REJECTED", "reason": "SOURCEPATH_REQUIRED"}
    req = _pathlib.Path(sp)
    if req.is_absolute():
        return {"verdict": "REJECTED", "reason": "SOURCEPATH_MUST_BE_RELATIVE"}
    root = _pathlib.Path(project_root).resolve()
    cand = (root / req).resolve()
    if cand != root and root not in cand.parents:
        return {"verdict": "REJECTED", "reason": "SOURCEPATH_ESCAPES_ROOT"}
    if cand.suffix.lower() != ".hwpx":
        return {"verdict": "REJECTED", "reason": "NOT_HWPX"}
    if not cand.is_file():
        return {"verdict": "REJECTED", "reason": "NOT_FOUND"}
    layout = extract(str(cand))
    layout["verdict"] = "PASS"
    layout["sourcePath"] = cand.relative_to(root).as_posix()
    return layout


if __name__ == "__main__":
    out = extract(sys.argv[1])
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
    print(json.dumps({
        "pageWidthPx": out["pageWidthPx"], "pageHeightPx": out["pageHeightPx"],
        "pages": out["pages"], "lineCount": len(out["lines"]),
        "boxCount": len(out["boxes"]),
        "sampleLines": out["lines"][:4],
    }, ensure_ascii=False, indent=1))
