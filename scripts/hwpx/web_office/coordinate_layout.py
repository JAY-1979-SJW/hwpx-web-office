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
    return _own_runs(p)[0]


def _own_runs(p):
    """문단 직속 텍스트 + run 별 charPr 구간.

    반환: (txt, spans) — spans = [{"s": start, "e": end, "cp": charPrIDRef}].
    txt 는 _own_text 와 동일하게 조립되어 lineseg 의 textpos 인덱스와 정렬된다.
    각 구간은 원본 run 의 charPrIDRef(서식 참조)를 그대로 보존한다.
    """
    parts = []
    spans = []
    pos = 0
    for run in p:
        if ln(run.tag) != "run":
            continue
        cref = run.attrib.get("charPrIDRef")
        for c in run:
            if ln(c.tag) == "t":
                t = "".join(c.itertext())
                if t:
                    parts.append(t)
                    spans.append({"s": pos, "e": pos + len(t), "cp": cref})
                    pos += len(t)
            elif ln(c.tag) == "lineBreak":
                parts.append("\n")
                spans.append({"s": pos, "e": pos + 1, "cp": cref})
                pos += 1
    return "".join(parts), spans


def _slice_segments(txt, spans, a, b):
    """텍스트 구간 [a,b) 를 run 별 서식 조각으로 분해.

    한 줄(lineseg)이 여러 서식(run)에 걸치면 조각이 여러 개가 된다. 어떤
    span 과도 겹치지 않으면(서식 정보 없음) charPr=None 단일 조각으로 대체.
    """
    out = []
    for sp in spans:
        s = max(a, sp["s"])
        e = min(b, sp["e"])
        if s < e:
            out.append({"text": txt[s:e], "charPr": sp["cp"]})
    if not out and a < b:
        out.append({"text": txt[a:b], "charPr": None})
    return out


def _parse_para_aligns(z):
    """header.xml 의 paraPr → {id: 'LEFT'|'CENTER'|'RIGHT'|'JUSTIFY'|...}.
    가운데/오른쪽 정렬 문단의 수평 배치를 재현하기 위함."""
    hdr = [n for n in z.namelist() if n.lower().endswith("header.xml")]
    if not hdr:
        return {}
    root = ET.fromstring(z.read(hdr[0]))
    out = {}
    for pp in root.iter():
        if ln(pp.tag) != "paraPr":
            continue
        pid = pp.attrib.get("id")
        al = pp.attrib.get("align", "")
        if not al:
            ach = next((c.attrib for c in pp if ln(c.tag) == "align"), {})
            al = ach.get("horizontal", "") or ach.get("align", "")
        if pid is not None:
            out[pid] = (al or "LEFT").upper()
    return out


def _css_align(a):
    """HWPX 수평정렬 → CSS text-align (LEFT/기본은 None)."""
    if a in ("CENTER",):
        return "center"
    if a in ("RIGHT",):
        return "right"
    if a in ("JUSTIFY", "DISTRIBUTE"):
        return "justify"
    return None


def _parse_char_prs(z):
    """header.xml 의 charPr 정의 → {id: {...서식...}} (style_parser 재사용).

    실패해도 {} 반환 — 좌표(위치) 재현은 서식 없이도 계속된다.
    """
    hdr = [n for n in z.namelist() if n.lower().endswith("header.xml")]
    if not hdr:
        return {}
    try:
        hb = z.read(hdr[0])
        from scripts.hwpx.parser.style_parser import (
            parse_char_pr_defs, parse_font_face_table)
        return parse_char_pr_defs(hb, parse_font_face_table(hb))
    except Exception:
        return {}


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


def _fill_color(bf_el):
    """borderFill 의 fillBrush 채움색(faceColor 등) → '#RRGGBB' 또는 None.
    'none'/흰색은 None(칠하지 않음 — 흰 배경 위 덧칠 방지)."""
    fb = next((c for c in bf_el if ln(c.tag) == "fillBrush"), None)
    if fb is None:
        return None
    for el in fb.iter():
        for attr in ("faceColor", "color", "startColor"):
            v = (el.attrib.get(attr) or "").strip()
            if not v or v.lower() == "none":
                continue
            h = v[1:] if v.startswith("#") else v
            if len(h) == 8:      # AARRGGBB/RRGGBBAA → 앞 6자리
                h = h[:6]
            if len(h) == 6 and all(c in "0123456789abcdefABCDEF" for c in h):
                col = "#" + h.upper()
                return None if col in ("#FFFFFF",) else col
            return v if v.startswith("#") else None
    return None


def _parse_border_fills(z):
    """header.xml 의 borderFill → {id: {"sides": {...}, "fill": '#RRGGBB'|None}}."""
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
            out[bid] = {"sides": sides, "fill": _fill_color(bf)}
    return out


def extract(path):
    z = zipfile.ZipFile(path)
    secname = [n for n in z.namelist()
               if "section0" in n.lower() and n.endswith(".xml")][0]
    root = ET.fromstring(z.read(secname))
    parent_map = {c: p for p in root.iter() for c in p}
    border_fills = _parse_border_fills(z)
    char_prs = _parse_char_prs(z)
    para_aligns = _parse_para_aligns(z)

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
        txt, spans = _own_runs(p)
        segs = _direct_linesegs(p)
        align = _css_align(para_aligns.get(p.attrib.get("paraPrIDRef")))
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
            bl = float(s.get("baseline", "0")) * HU
            line = {"text": line_txt,
                    "segments": _slice_segments(txt, spans, a, b),
                    "x": round(x, 1),
                    "y": round(y, 1), "w": round(w, 1),
                    "h": round(h, 1),
                    "baseline": round(bl, 1), "cell": False}
            if align:
                line["align"] = align
            lines.append(line)
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

    def walk_table(tbl, base_x, base_y):
        """tbl 을 (base_x, base_y) 를 좌상단으로 배치. 이 tbl 의 직속 셀만
        그리고, 셀 안 중첩표는 그 셀 내용 좌상단에서 재귀 배치한다.
        반환: 표 하단 y(px)."""
        cells = [_cell_info(tc) for tc in tbl.iter()
                 if ln(tc.tag) == "tc" and _nearest_tbl(tc) is tbl]
        if not cells:
            return base_y
        ncol = max((c["col"] + c["colSpan"] for c in cells), default=1)
        nrow = max((c["row"] + c["rowSpan"] for c in cells), default=1)
        col_w = _solve_axis(cells, ncol, "col", "colSpan", "w")
        row_h = _solve_axis(cells, nrow, "row", "rowSpan", "h")
        # 한컴이 선언한 표 총 크기(sz)에 정규화 — 셀 폭/높이 합의 근사 오차가
        # 표 전체 폭·높이로 누적되지 않도록 비례 보정(저장 치수 신뢰).
        sz = next((ch.attrib for ch in tbl if ln(ch.tag) == "sz"), {})
        tw = float(sz.get("width", "0")) * HU
        th = float(sz.get("height", "0")) * HU
        sw = sum(col_w)
        if tw > 0 and sw > 0:
            col_w = [w * tw / sw for w in col_w]
        sh = sum(row_h)
        if th > 0 and sh > 0:
            row_h = [h * th / sh for h in row_h]
        col_x = [0.0] * (ncol + 1)
        for i in range(ncol):
            col_x[i + 1] = col_x[i] + col_w[i]
        row_y = [0.0] * (nrow + 1)
        for i in range(nrow):
            row_y[i + 1] = row_y[i] + row_h[i]
        table_bottom = base_y
        for c in cells:
            cx = base_x + col_x[c["col"]]
            cy = base_y + row_y[c["row"]]
            cw = col_x[min(c["col"] + c["colSpan"], ncol)] - col_x[c["col"]]
            ch = row_y[min(c["row"] + c["rowSpan"], nrow)] - row_y[c["row"]]
            # 이 셀 직속 문단만 (중첩표 안 문단 제외)
            cell_lines = []
            for cp in c["tc"].iter():
                if ln(cp.tag) == "p" and _nearest_cell(cp) is c["tc"]:
                    cell_lines.extend(_cell_para_lines(cp))
            text_h = max((cl["ry"] + cl["h"] for cl in cell_lines), default=0)
            avail = ch - c["mt"] * 2
            va = c["vAlign"]
            voff = (max(0.0, (avail - text_h) / 2) if va == "CENTER"
                    else max(0.0, avail - text_h) if va == "BOTTOM"
                    else 0.0)
            for cl in cell_lines:
                cline = {
                    "text": cl["text"],
                    "segments": cl.get("segments", []),
                    "x": round(cx + c["ml"] + cl["rx"], 1),
                    "y": round(cy + c["mt"] + voff + cl["ry"], 1),
                    "w": round(cl["w"], 1), "h": round(cl["h"], 1),
                    "baseline": round(cl.get("baseline", 0), 1),
                    "cell": True}
                if cl.get("align"):
                    cline["align"] = cl["align"]
                lines.append(cline)
            box = {"x": round(cx, 1), "y": round(cy, 1),
                   "w": round(cw, 1), "h": round(ch, 1)}
            bf = border_fills.get(c["bfRef"])
            if bf:
                box["border"] = _border_sides_css(bf["sides"])
                if bf.get("fill"):
                    box["fill"] = bf["fill"]
            boxes.append(box)
            # 이 셀 직속 중첩표 → 셀 내용 좌상단에서 재귀 배치
            for nt in c["tc"].iter():
                if ln(nt.tag) == "tbl" and _nearest_cell(nt) is c["tc"]:
                    walk_table(nt, cx + c["ml"], cy + c["mt"])
            table_bottom = max(table_bottom, cy + ch)
        st["flow_y"] = table_bottom + 4
        st["max_y"] = max(st["max_y"], table_bottom)
        return table_bottom

    def _nearest_tbl(el):
        """el 의 가장 가까운 조상 tbl (없으면 None)."""
        x = parent_map.get(el)
        while x is not None:
            if ln(x.tag) == "tbl":
                return x
            x = parent_map.get(x)
        return None

    def _nearest_cell(el):
        """el 의 가장 가까운 조상 tc (없으면 None)."""
        x = parent_map.get(el)
        while x is not None:
            if ln(x.tag) == "tc":
                return x
            x = parent_map.get(x)
        return None

    def _cell_para_lines(p):
        """셀 문단 → 셀 상대 라인 [{rx, ry, w, h, text, segments, align}]."""
        txt, spans = _own_runs(p)
        segs = _direct_linesegs(p)
        align = _css_align(para_aligns.get(p.attrib.get("paraPrIDRef")))
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
                "baseline": float(s.get("baseline", "0")) * HU,
                "text": txt[a:b],
                "align": align,
                "segments": _slice_segments(txt, spans, a, b)})
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

    def _para_top_y(p):
        """문단 첫 lineseg 의 전역 top(px). 페이지 상태(prev_vpos/page_idx)도
        emit_para 와 동일 규칙으로 갱신한다. lineseg 없으면 None."""
        segs = _direct_linesegs(p)
        if not segs:
            return None
        vpos = float(segs[0].get("vertpos", "0"))
        if st["prev_vpos"] >= 0 and vpos + 1 < st["prev_vpos"]:
            st["page_idx"] += 1
        st["prev_vpos"] = vpos
        return (st["page_idx"] * page_h) + m_top + vpos * HU

    def walk(el):
        for child in el:
            if ln(child.tag) != "p":
                continue
            # 이 문단의 최상위 표만(중첩표는 walk_table 이 재귀 배치)
            top_tbls = [t for t in child.iter()
                        if ln(t.tag) == "tbl" and _nearest_tbl(t) is None]
            if top_tbls:
                # 표 보유 문단: 빈 텍스트 lineseg(=표 높이)로 flow 를 밀지 않고
                # 표를 문단 top 에 직접 배치. 이후 flow 는 표 하단으로 전진.
                top = _para_top_y(child)
                base_y = top if top is not None else st["flow_y"] + 4
                for t in top_tbls:
                    base_y = walk_table(t, m_left, base_y) + 4
            else:
                emit_para(child)

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
        "charPrDefs": char_prs,
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
