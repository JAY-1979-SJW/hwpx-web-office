"""HWPX lineseg 기반 좌표 레이아웃 추출기 (오케스트레이션 파사드).

한컴이 저장 시 계산한 lineseg(줄별 vertpos/horzpos/size)를 그대로 써서
페이지 좌표 레이아웃(JSON)을 만든다. 브라우저 재-flow 없이 원본 배치를
재현하기 위한 데이터. read-only, 원본 무수정.

모듈 구성(모듈화 분리):
  coord_xml    — 순수 XML/단위 헬퍼 (own_runs·slice_segments·sane_hu…)
  coord_styles — header.xml 스타일·페이지 규격 파싱
  coord_table  — 표 축 해석·정규화·앵커 압축·블록 페이지네이션(순수 계산)
  본 파일       — 문서 순회(walk)·표 방출(walk_table)·섹션 병합(extract)
"""
import json
import math
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

try:
    from .coord_xml import (
        HU, ln, own_text, own_runs, slice_segments, direct_linesegs, sane_hu)
    from .coord_styles import (
        parse_para_aligns, css_align, parse_char_prs, parse_border_fills,
        border_sides_css, parse_page_geometry)
    from .coord_table import (
        solve_axis, expand_rowspan_content, normalize_declared,
        compress_to_anchor, paginate_rows, col_rank_map)
except ImportError:                      # 스크립트 직접 실행 폴백
    from coord_xml import (
        HU, ln, own_text, own_runs, slice_segments, direct_linesegs, sane_hu)
    from coord_styles import (
        parse_para_aligns, css_align, parse_char_prs, parse_border_fills,
        border_sides_css, parse_page_geometry)
    from coord_table import (
        solve_axis, expand_rowspan_content, normalize_declared,
        compress_to_anchor, paginate_rows, col_rank_map)

# 하위호환 별칭(기존 내부명 참조 보호) — 신규 코드는 coord_* 모듈을 쓸 것.
_own_text = own_text
_own_runs = own_runs
_slice_segments = slice_segments
_direct_linesegs = direct_linesegs
_parse_para_aligns = parse_para_aligns
_css_align = css_align
_parse_char_prs = parse_char_prs
_parse_border_fills = parse_border_fills


def _extract_section(path, secname):
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read(secname))
    parent_map = {c: p for p in root.iter() for c in p}
    # 표 문서순 인덱스 — 문서모델(ro_view_importer)의 tableId
    # 't_s{sec}_{order:03d}' 와 동일 순서로 매겨 cellId 를 일치시킨다(편집 연결).
    _sec_idx = 0
    m_sec = re.search(r"section(\d+)", secname)
    if m_sec:
        _sec_idx = int(m_sec.group(1))
    tbl_order = {}
    for _i, _t in enumerate(e for e in root.iter() if ln(e.tag) == "tbl"):
        tbl_order[_t] = _i

    def _cell_id(tbl, row, col):
        return "cell_t_s%d_%03d_r%d_c%d" % (
            _sec_idx, tbl_order.get(tbl, 0), row, col)

    border_fills = parse_border_fills(z)
    char_prs = parse_char_prs(z)
    para_aligns = parse_para_aligns(z)

    geo = parse_page_geometry(root)
    page_w = geo["page_w"]
    page_h = geo["page_h"]
    m_left = geo["m_left"]
    m_top = geo["m_top"]
    content_h = geo["content_h"]

    lines = []
    boxes = []
    st = {"page_idx": 0, "prev_vpos": -1, "flow_y": m_top, "max_y": m_top}

    def emit_para(p):
        txt, spans = own_runs(p)
        segs = direct_linesegs(p)
        align = css_align(para_aligns.get(p.attrib.get("paraPrIDRef")))
        for i, s in enumerate(segs):
            vpos = float(s.get("vertpos", "0"))
            a = int(s.get("textpos", "0") or "0")
            b = (int(segs[i + 1].get("textpos", "0") or "0")
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
                    "segments": slice_segments(txt, spans, a, b),
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
        w = sane_hu(sz.get("width", "0"))
        h = sane_hu(sz.get("height", "0"))
        # 손상 여백 방어 — 일부 문서가 cellMargin 에 셀보다 큰 값
        # (예: 20520HU=274px)을 담아 행높이를 폭증시킨다. 여백 합이 셀
        # 크기를 잠식(90%↑)하면 한컴처럼 무시하고 기본값(≈141HU)으로.
        _DEF_MG = 1.9
        ml_raw = sane_hu(mg.get("left", "0"))
        mt_raw = sane_hu(mg.get("top", "0"))
        ml = ml_raw if (w <= 0 or ml_raw * 2 <= w * 0.9) else _DEF_MG
        mt = mt_raw if (h <= 0 or mt_raw * 2 <= h * 0.9) else _DEF_MG
        # 셀 직속 문단의 실제 내용 높이(저장 lineseg ry+h 최대) — 행높이가
        # cellSz(최소값일 수 있음)보다 작아 내용이 넘치는 것을 막기 위함.
        content = 0.0
        compact = 0.0   # 줄간격 제거 시 최소 높이(글리프 합) — 앵커 압축용
        for cp in tc.iter():
            if ln(cp.tag) == "p" and _nearest_cell(cp) is tc:
                for cl in _cell_para_lines(cp):
                    content = max(content, cl["ry"] + cl["h"])
                    compact += cl["h"]
        # 직속 중첩표 높이도 내용에 포함 — 안 하면 외곽 행이 중첩표보다
        # 짧아, 뒤 내용(푸터 등)이 위로 올라오고 중첩표가 아래로 넘친다.
        for nt in tc.iter():
            if ln(nt.tag) == "tbl" and _nearest_cell(nt) is tc:
                pp = _nearest_p(nt)
                nsegs = direct_linesegs(pp) if pp is not None else []
                nvpos = (float(nsegs[0].get("vertpos", "0")) * HU
                         if nsegs else 0.0)
                nsz = next((x.attrib for x in nt if ln(x.tag) == "sz"), {})
                nh = sane_hu(nsz.get("height", "0"))
                content = max(content, nvpos + nh)
                compact += nh
        return {
            "row": int(addr.get("rowAddr", "0")),
            "col": int(addr.get("colAddr", "0")),
            "rowSpan": int(span.get("rowSpan", "1") or "1"),
            "colSpan": int(span.get("colSpan", "1") or "1"),
            "w": w,
            "h": h,
            "ml": ml,
            "mt": mt,
            "hContent": content,
            "hCompact": min(compact, content) if compact > 0 else content,
            "bfRef": tc.attrib.get("borderFillIDRef"),
            "vAlign": sub.get("vertAlign", "TOP"),
            "tc": tc,
        }

    def walk_table(tbl, base_x, base_y, anchor_vpos=None):
        """tbl 을 (base_x, base_y) 를 좌상단으로 배치. 이 tbl 의 직속 셀만
        그리고, 셀 안 중첩표는 그 셀 내용 좌상단에서 재귀 배치한다.
        anchor_vpos: 표 다음 본문 문단의 저장 vpos(페이지 상대) — 다중페이지
        표의 실제 높이를 원본 좌표에서 역산하는 권위 앵커. 반환: 표 하단 y."""
        cells = [_cell_info(tc) for tc in tbl.iter()
                 if ln(tc.tag) == "tc" and _nearest_tbl(tc) is tbl]
        if not cells:
            return base_y
        ncol = max((c["col"] + c["colSpan"] for c in cells), default=1)
        nrow = max((c["row"] + c["rowSpan"] for c in cells), default=1)
        # 행높이는 cellSz 와 실제 내용높이(hContent+상하여백) 중 큰 값으로 —
        # cellSz 가 최소값이라 내용이 넘쳐 셀이 세로로 충돌하는 것을 막는다.
        for c in cells:
            c["hEff"] = max(c["h"], c["hContent"] + c["mt"] * 2)
        col_w = solve_axis(cells, ncol, "col", "colSpan", "w")
        row_h = solve_axis(cells, nrow, "row", "rowSpan", "hEff")
        row_h = expand_rowspan_content(cells, row_h, nrow)
        sz = next((ch.attrib for ch in tbl if ln(ch.tag) == "sz"), {})
        tw = sane_hu(sz.get("width", "0"))
        th = sane_hu(sz.get("height", "0"))
        col_w, row_h = normalize_declared(cells, col_w, row_h, tw, th, nrow)
        row_h, alpha = compress_to_anchor(
            cells, row_h, nrow, base_y, anchor_vpos, geo)
        if os.environ.get("COORD_DEBUG"):
            print(f"[DBG tbl] base=({base_x:.0f},{base_y:.0f}) "
                  f"nrow={nrow} ncol={ncol} th={th:.0f} a={alpha:.3f} "
                  f"sum={sum(row_h):.0f} row_h="
                  f"{[round(h, 1) for h in row_h]}", file=sys.stderr)
        col_x = [0.0] * (ncol + 1)
        for i in range(ncol):
            col_x[i + 1] = col_x[i] + col_w[i]
        row_abs, row_bot = paginate_rows(cells, row_h, nrow, base_y, geo)
        col_rank = col_rank_map(cells)
        table_bottom = base_y
        for c in cells:
            cid = _cell_id(tbl, c["row"], col_rank.get((c["row"], c["col"]),
                                                        c["col"]))
            cx = base_x + col_x[c["col"]]
            cy = row_abs[c["row"]]
            cw = col_x[min(c["col"] + c["colSpan"], ncol)] - col_x[c["col"]]
            _last = min(c["row"] + c["rowSpan"], nrow) - 1
            ch = row_bot[_last] - row_abs[c["row"]]
            # 이 셀 직속 문단만 (중첩표 안 문단 제외)
            cell_lines = []
            for cp in c["tc"].iter():
                if ln(cp.tag) == "p" and _nearest_cell(cp) is c["tc"]:
                    cell_lines.extend(_cell_para_lines(cp))
            # 직속 중첩표 (nvpos, 선언 높이) — voff 계산·배치에 공통 사용
            nested = []
            for nt in c["tc"].iter():
                if ln(nt.tag) == "tbl" and _nearest_cell(nt) is c["tc"]:
                    pp = _nearest_p(nt)
                    nsegs = direct_linesegs(pp) if pp is not None else []
                    nvpos = (float(nsegs[0].get("vertpos", "0")) * HU
                             if nsegs else 0.0)
                    nsz = next((x.attrib for x in nt
                                if ln(x.tag) == "sz"), {})
                    nh = sane_hu(nsz.get("height", "0"))
                    nested.append((nt, nvpos, nh))
            # α 압축 시 줄 위치 보간 — 각 줄을 [원 ry ↔ 글리프-밀착 스택]
            # 사이에서 α 만큼 이동(줄간격만 줄고 글리프는 유지 → 물림 없음).
            mt_eff = c["mt"] * (1.0 - 0.5 * alpha)
            if alpha > 0 and cell_lines:
                order = sorted(range(len(cell_lines)),
                               key=lambda i: cell_lines[i]["ry"])
                cum = 0.0
                for i in order:
                    cl = cell_lines[i]
                    cl["ryEff"] = cl["ry"] - alpha * (cl["ry"] - cum)
                    cum += cl["h"]
            else:
                for cl in cell_lines:
                    cl["ryEff"] = cl["ry"]
            # 내용 총 높이 = 본문 줄 + 중첩표 하단 중 최대
            text_h = max(
                [cl["ryEff"] + cl["h"] for cl in cell_lines]
                + [nv + nh for _, nv, nh in nested] + [0.0])
            avail = ch - mt_eff * 2
            va = c["vAlign"]
            voff = (max(0.0, (avail - text_h) / 2) if va == "CENTER"
                    else max(0.0, avail - text_h) if va == "BOTTOM"
                    else 0.0)
            for cl in cell_lines:
                line_x = cx + c["ml"] + cl["rx"]
                # 줄 폭을 셀 오른쪽 경계까지로 제한 — horzsize 가 셀보다 넓어도
                # (공백 패딩 등) 셀 밖으로 삐져나가지 않게 한다. 넘치는 부분은
                # overflow:clip 으로 셀 안에서 잘리고, 우측정렬 ')' 는 셀
                # 가장자리에 놓인다.
                cap = (cx + cw) - line_x
                wpx = min(cl["w"], cap) if cap > 2 else cl["w"]
                cline = {
                    "text": cl["text"],
                    "segments": cl.get("segments", []),
                    "x": round(line_x, 1),
                    "y": round(cy + mt_eff + voff + cl["ryEff"], 1),
                    "w": round(wpx, 1), "h": round(cl["h"], 1),
                    "baseline": round(cl.get("baseline", 0), 1),
                    "cell": True, "cellId": cid}
                if cl.get("align"):
                    cline["align"] = cl["align"]
                lines.append(cline)
            box = {"x": round(cx, 1), "y": round(cy, 1),
                   "w": round(cw, 1), "h": round(ch, 1),
                   "cellId": cid}
            bf = border_fills.get(c["bfRef"])
            if bf:
                box["border"] = border_sides_css(bf["sides"])
                if bf.get("fill"):
                    box["fill"] = bf["fill"]
            boxes.append(box)
            # 직속 중첩표 재귀 배치 — voff(세로정렬 오프셋)를 본문 줄과 동일
            # 하게 더한다. 안 그러면 vAlign=CENTER 셀에서 본문만 내려가 겹친다.
            # α 압축 시 여백 절반화 근사(다중페이지 표 안 중첩표는 코퍼스에
            # 드묾; 위치만 완만히 당긴다)
            for nt, nvpos, _ in nested:
                walk_table(nt, cx + c["ml"],
                           cy + mt_eff + voff + nvpos * (1.0 - 0.5 * alpha))
            table_bottom = max(table_bottom, cy + ch)
        st["flow_y"] = table_bottom + 4
        st["max_y"] = max(st["max_y"], table_bottom)
        # 통합 페이지 추적 — 본문(page_idx×page_h+vertpos)과 표(flow_y)가
        # 별도 좌표계라, 페이지를 넘긴 표 뒤의 본문이 stale page_idx 로 계산돼
        # 표 위에 겹치던 결함을 잡는다. 표 하단이 속한 페이지로 page_idx 를
        # 전진시켜, 표 뒤 본문(page-relative vertpos)이 올바른 페이지에 놓이게
        # 한다. 표가 한 페이지 안이면 end_pg==page_idx 라 무변화(단일페이지
        # 배치·기존 시각회귀 baseline 보존).
        if page_h:
            end_pg = int(table_bottom // page_h)
            if end_pg > st["page_idx"]:
                st["page_idx"] = end_pg
                # 새 페이지 기준 — 표 앞 본문 vertpos 와 비교해 거짓 리셋 방지
                st["prev_vpos"] = -1
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

    def _nearest_p(el):
        """el 의 가장 가까운 조상 p (없으면 None)."""
        x = parent_map.get(el)
        while x is not None:
            if ln(x.tag) == "p":
                return x
            x = parent_map.get(x)
        return None

    def _cell_para_lines(p):
        """셀 문단 → 셀 상대 라인 [{rx, ry, w, h, text, segments, align}]."""
        txt, spans = own_runs(p)
        segs = direct_linesegs(p)
        align = css_align(para_aligns.get(p.attrib.get("paraPrIDRef")))
        out = []
        for i, s in enumerate(segs):
            a = int(s.get("textpos", "0") or "0")
            b = (int(segs[i + 1].get("textpos", "0") or "0")
                 if i + 1 < len(segs) else len(txt))
            out.append({
                "rx": float(s.get("horzpos", "0")) * HU,
                "ry": float(s.get("vertpos", "0")) * HU,
                "w": float(s.get("horzsize", "0")) * HU,
                "h": float(s.get("vertsize", "1000")) * HU,
                "baseline": float(s.get("baseline", "0")) * HU,
                "text": txt[a:b],
                "align": align,
                "segments": slice_segments(txt, spans, a, b)})
        return out

    def _para_top_y(p):
        """문단 첫 lineseg 의 전역 top(px). 페이지 상태(prev_vpos/page_idx)도
        emit_para 와 동일 규칙으로 갱신한다. lineseg 없으면 None."""
        segs = direct_linesegs(p)
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
            # 원본의 명시적 페이지 나눔(hp:p @pageBreak) — 한컴이 저장한 강제
            # 페이지 구분을 권위있게 반영한다. 이 문단부터 새 페이지 최상단으로
            # (page_idx 전진 + vertpos 리셋). "0"/미지정이면 자동 흐름(무변화).
            if child.attrib.get("pageBreak", "0") not in ("0", ""):
                if page_h and st["max_y"] > st["page_idx"] * page_h + m_top:
                    st["page_idx"] += 1
                    st["prev_vpos"] = -1
                    st["flow_y"] = st["page_idx"] * page_h + m_top
            # 이 문단의 최상위 표만(중첩표는 walk_table 이 재귀 배치)
            top_tbls = [t for t in child.iter()
                        if ln(t.tag) == "tbl" and _nearest_tbl(t) is None]
            if top_tbls:
                # 표를 flow 위치(직전 내용 아래)에 순차 배치. 다중 표가 각기
                # vertpos=0(흐름) 이라 문단 top 에 두면 전부 겹친다. flow_y 로
                # 쌓고, 페이지 넘침은 렌더러가 y 로 분할한다.
                # 같은 문단에 자체 텍스트가 있으면 유실 없이 먼저 방출.
                if own_text(child).strip():
                    emit_para(child)
                else:
                    _para_top_y(child)  # 페이지 상태 갱신용
                # 다음 본문 앵커 lookahead — 표 그룹 뒤 첫 본문 문단의 저장
                # vpos(한컴 실제 배치 좌표). 다중페이지 표 높이 역산의 권위
                # 신호로 마지막 표에 전달한다.
                anchor_vpos = None
                seen = False
                for sib in el:
                    if seen and ln(sib.tag) == "p":
                        if any(ln(t.tag) == "tbl" for t in sib.iter()):
                            break        # 다음 표 그룹 — 앵커 아님
                        sgs = direct_linesegs(sib)
                        if sgs and own_text(sib).strip():
                            anchor_vpos = float(
                                sgs[0].get("vertpos", "0")) * HU
                            break
                    if sib is child:
                        seen = True
                base_y = st["flow_y"]
                for ti, t in enumerate(top_tbls):
                    walk_table(t, m_left, base_y,
                               anchor_vpos if ti == len(top_tbls) - 1
                               else None)
                    base_y = st["flow_y"]
            else:
                emit_para(child)

    walk(root)
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


def extract(path):
    """HWPX → 좌표 레이아웃. 전 섹션(sectionN.xml)을 페이지 오프셋 누적으로
    이어붙인다 — 단일 섹션이 대부분이나, 다중 섹션 문서에서 section0 외의
    내용이 사라지지 않도록(표시/편집 누락 방지) 표준 처리한다."""
    z = zipfile.ZipFile(path)
    sec_files = [n for n in z.namelist()
                 if re.search(r"section\d+\.xml$", n.lower())]
    sec_files.sort(key=lambda n: int(re.search(r"section(\d+)",
                                                n.lower()).group(1)))
    if not sec_files:
        sec_files = [n for n in z.namelist()
                     if "section0" in n.lower() and n.endswith(".xml")][:1]
    if len(sec_files) <= 1:
        return _extract_section(path, sec_files[0])

    merged_lines, merged_boxes = [], []
    page_base = 0
    first = None
    for sec in sec_files:
        r = _extract_section(path, sec)
        if first is None:
            first = r
        off = page_base * (r["pageHeightPx"] or 1)
        for line in r["lines"]:
            line["y"] = round(line["y"] + off, 1)
            merged_lines.append(line)
        for box in r["boxes"]:
            box["y"] = round(box["y"] + off, 1)
            merged_boxes.append(box)
        page_base += r["pages"]
    out = dict(first)
    out.update(pages=page_base, lines=merged_lines, boxes=merged_boxes)
    return out


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
