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


# 인접 셀 테두리 중복 그리기(지시문 5.3) — 2차 시도(zero_rows 제외
# 가드 추가)도 "개선 확인 → 육안 승인 → baseline 재고정" 절차
# (promote_web_office_visual_baseline.py) 로 재검증한 결과 pinned
# fixture 4개 중 3개(fx_metadata_form, fx_stamp_approval_legal,
# reg_detail_form)에서 평균오차가 3~19배 악화됨을 절차 자체가 정확히
# 잡아냈다(fx_metadata_form meanAbsPx 3.05→12.2, fx_stamp_approval_legal
# 0.5→8.55, reg_detail_form 4.54→9.41 — reg_nested_valign_center 만 개선).
# 절차가 의도대로 작동해 회귀 유입을 막았다 — 되돌리고 별도 워크스트림
# (인접 억제 로직 자체의 재설계, 단순 폭 비교가 아닌 실제 렌더 검증
# 필요)으로 재시도한다.


def _extract_section(path, secname, row_scale=1.0):
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
    warnings: list[dict] = []
    st = {"page_idx": 0, "prev_vpos": -1, "flow_y": m_top, "max_y": m_top,
          "col_count": 1, "col_idx": 0}

    def _update_col_state(p):
        """다단(colPr colCount>=2) 구간 진입/이탈 반영 — 페이지 카운터용.

        colPr 은 문단 안 secPr 제어문자로 중간 삽입돼(문서 전체가 아니라
        구간별 단 수를 바꿈), vertpos 리셋이 "새 페이지"인지 "같은 페이지
        안 다음 칼럼"인지 구별하는 데 반드시 필요하다. 새 단 구간 진입 시
        칼럼 카운터를 0(첫 칼럼)으로 되돌린다 — 안 그러면 이전 구간에서
        남은 칼럼 위상이 새 구간의 페이지 판정을 어긋나게 한다.

        주의: x-오프셋(칼럼을 실제로 나란히 배치)은 아직 미구현이다 —
        시도해본 결과 이 문서의 2단 구간이 물리적으로 여러 페이지에 걸쳐
        있어(칼럼 하나가 content_h 를 넘김), 단순 "칼럼 인덱스 mod N" 만
        으로는 페이지 경계를 못 잡고 오히려 품질 게이트(bodyOverlap) 회귀
        가 발생해 되돌렸다. 페이지 카운터 이중 증가 방지(이 함수)만 유지.
        """
        col_pr = next((e for e in p.iter() if ln(e.tag) == "colPr"), None)
        if col_pr is None:
            return
        try:
            cc = int(col_pr.attrib.get("colCount", "1") or "1")
        except (TypeError, ValueError):
            return
        if cc != st["col_count"]:
            st["col_count"] = max(cc, 1)
            st["col_idx"] = 0
            if os.environ.get("COORD_DEBUG"):
                print(f"[DBG col] colCount -> {st['col_count']}", file=sys.stderr)

    def _on_vpos_reset():
        """vertpos 리셋(감소) 시 페이지 전진 여부 판정.

        단일 칼럼이면 리셋 즉시 새 페이지(기존 동작 보존). 다단(N>=2)이면
        칼럼이 N 번 채워져야(칼럼 1→2→…→N 순환 완료) 비로소 실제 새
        페이지다 — 그 전까지는 같은 페이지 안 다음 칼럼으로의 이동일 뿐.
        실사례: colCount=2 구간에서 매 리셋마다 페이지를 전진시키면 표
        앵커가 부풀려진 page_idx 기준으로 환산돼 실제보다 훨씬 아래(페이지
        바닥 91%)로 계산되는 결함이 있었다(영천경마공원 79셀 표 사례).
        """
        if st["col_count"] > 1:
            st["col_idx"] += 1
            if st["col_idx"] >= st["col_count"]:
                st["col_idx"] = 0
                st["page_idx"] += 1
        else:
            st["page_idx"] += 1
        if os.environ.get("COORD_DEBUG"):
            print(f"[DBG reset] col_count={st['col_count']} "
                  f"col_idx={st['col_idx']} page_idx={st['page_idx']}",
                  file=sys.stderr)

    def emit_para(p):
        txt, spans = own_runs(p)
        segs = direct_linesegs(p)
        align = css_align(para_aligns.get(p.attrib.get("paraPrIDRef")))
        # 인라인 개체(이미지 container 등, pos.treatAsChar=1) 앵커 lineseg
        # 검출 — 텍스트는 없지만(own_runs 는 개체를 문자로 안 셈) 한컴이
        # 그 개체 높이를 vertsize 에 그대로 기록해 둔다(실측: curSz.height
        # 73900 = 해당 lineseg vertsize 73900, 정확히 일치). "빈 줄은 흐름을
        # 안 민다"는 유령페이지 방지 규칙이 이 개체 줄까지 빈 줄로 오인해
        # 삼켜, 이미지 있는 문서에서 페이지가 통째로 결측되는 원인이었다
        # (실무 서식에 흔한 직인·로고·도면 삽입 — 안전보건계획 문서 45쪽
        # 중 5쪽 결측 실사례). 원본 무수정 원칙상 이미지는 그리지 않되,
        # 문단 안 개체들의 curSz.height 를 미리 모아 두면, 어느 lineseg
        # 든 그 높이와 근사 일치하는 빈 줄을 '개체 자리'로 인정해 흐름에
        # 반영할 수 있다(개체 자체를 렌더/편집하는 것은 아님).
        _obj_heights: set[int] = set()
        for ctrl_container in p.iter():
            if ln(ctrl_container.tag) != "container":
                continue
            sz_el = next((e for e in ctrl_container.iter()
                          if ln(e.tag) == "curSz"), None)
            if sz_el is not None:
                try:
                    _obj_heights.add(int(float(sz_el.attrib.get("height", 0))))
                except (TypeError, ValueError):
                    pass
        for i, s in enumerate(segs):
            vpos = float(s.get("vertpos", "0"))
            a = int(s.get("textpos", "0") or "0")
            b = (int(segs[i + 1].get("textpos", "0") or "0")
                 if i + 1 < len(segs) else len(txt))
            line_txt = txt[a:b]
            # 페이지 상태머신은 가시 줄만 구동 — 빈 문단(공백 줄)은 페이지를
            # 만들지 않는다. 문서 끝의 빈 문단 수백 개가 vpos 리셋을 반복해
            # 유령 페이지 6쪽+를 만들던 결함(한컴은 빈 문단으로 쪽을 늘리지
            # 않음 — 별지2: 한컴 12쪽 vs 우리 18쪽의 근본 원인).
            _obj_h = 0
            if not line_txt.strip() and _obj_heights:
                _raw_vsz = int(float(s.get("vertsize", 0) or 0))
                _obj_h = next(
                    (h for h in _obj_heights if abs(h - _raw_vsz) <= 5), 0)
            _vis = bool(line_txt.strip()) or _obj_h > 0
            if _vis:
                if st["prev_vpos"] >= 0 and vpos + 1 < st["prev_vpos"]:
                    _on_vpos_reset()  # vpos 리셋 → 새 페이지(또는 다단 다음 칼럼)
                st["prev_vpos"] = vpos
            y = (st["page_idx"] * page_h) + m_top + vpos * HU
            x = m_left + float(s.get("horzpos", "0")) * HU
            w = float(s.get("horzsize", "0")) * HU
            h = float(s.get("vertsize", "1000")) * HU
            bl = float(s.get("baseline", "0")) * HU
            # 흐름 불변식 — 문단은 선행 내용(표 하단 flow_y) 위에 올라앉을 수
            # 없다. 표가 여러 페이지를 쓰면 뒤 본문을 같은 vpos 로 다음
            # 페이지에 놓는다(한컴 배치: 각주 vpos 는 표가 끝난 페이지 기준).
            # 빈 줄은 밀지 않는다(보이지 않는 간격 문단 — 밀면 연쇄 페이지
            # 증가), 1.5줄 이상 실침범 시에만 발동.
            if i == 0 and page_h > 0 and line_txt.strip():
                _guard = 0
                while (y < st["flow_y"] - max(h * 1.5, 20.0)
                        and _guard < 6):
                    st["page_idx"] += 1
                    y = (st["page_idx"] * page_h) + m_top + vpos * HU
                    _guard += 1
            line = {"text": line_txt,
                    "segments": slice_segments(txt, spans, a, b),
                    "x": round(x, 1),
                    "y": round(y, 1), "w": round(w, 1),
                    "h": round(h, 1),
                    "baseline": round(bl, 1), "cell": False}
            if align:
                line["align"] = align
            lines.append(line)
            if _vis:
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
            # 세로쓰기(textDirection=VERTICAL/VERTICALALL) — 자리수 헤더
            # (조/천억/백억 등 좁고 긴 금액칸)에서 흔함. CSS writing-mode
            # 로 렌더러가 처리하도록 셀 단위로 전달.
            "vertical": str(sub.get("textDirection", "")).startswith(
                "VERTICAL"),
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
        # 병합 내용 불변식 재확약 — normalize 의 슬랙 축소는 단일-span
        # 하한(min_need)만 보호해 병합(rowSpan) 셀 보장을 되물릴 수 있다
        # (별표2: 병합 5~8줄 셀이 최대 57px 물림). 멱등 재호출로 재보장.
        row_h = expand_rowspan_content(cells, row_h, nrow)
        # 높이0 반복 헤더행 접기 — 한컴 '표 머리행 반복'의 저장 잔재(전 셀
        # cellSz=0, 내용도 없음)를 흐름 중간에 평행으로 그리면 페이지 꼬리
        # 문구와 겹친다. 높이 0 으로 접고 비표시(원 헤더는 r0 에 있음).
        # 회귀 수리 — 선언 높이(c["h"])만 보고 내용(hContent)은 확인하지
        # 않아, 흐름도형 표(신고서 접수→등록증발급 등, 화살표 셀)처럼
        # "높이 0 선언 + 실제 텍스트" 인 정상 행까지 통째로 숨기던 실사례
        # 결함(107셀 표 중 82셀 소실) 확인 — hContent>0(실제 내용 있음)인
        # 행은 절대 접지 않는다.
        _zero_rows = set()
        _zr = {}
        for c in cells:
            if c["rowSpan"] == 1:
                _zr.setdefault(c["row"], True)
                if c["h"] > 0 or c["hContent"] > 0:
                    _zr[c["row"]] = False
        for _r, _az in _zr.items():
            if _az and _r > 0:
                _zero_rows.add(_r)
                row_h[_r] = 0.0
        # 공장 캘리브레이션 배율 — 한컴 실제 쪽수에 맞춘 행높이 미세 배율
        # (truth 캐시의 calib.json). 축소 시엔 내용 하한(floor)을 지켜
        # 물림을 만들지 않는다. 확대는 그대로(잘림 없음).
        _calib_alpha = 0.0
        if row_scale and abs(row_scale - 1.0) > 1e-3:
            if row_scale > 1.0:
                row_h = [row_h[i] * row_scale for i in range(nrow)]
            else:
                # 축소 — 내용 하한이 아니라 글리프-컴팩트 하한(줄간격 제거)
                # 까지 허용하고, α 보간 기계로 줄 위치도 함께 압축한다
                # (글리프 크기 유지 → 물림 없음). 한컴이 조밀 문서에서
                # 실제로 쓰는 압축 방식과 동일 모델.
                _comp = [0.0] * nrow
                for c in cells:
                    if c["rowSpan"] == 1 and c["row"] not in _zero_rows:
                        _cv = c["hCompact"] + c["mt"]
                        if _cv > _comp[c["row"]]:
                            _comp[c["row"]] = _cv
                for i in range(nrow):
                    if _comp[i] > row_h[i]:
                        _comp[i] = row_h[i]
                _new = [max(_comp[i], row_h[i] * row_scale)
                        for i in range(nrow)]
                # 행별 α — 각 행의 실제 압축률(원↔컴팩트 사이 위치).
                # 표 전역 단일 α는 꽉 찬 행(압축률 1.0)과 여유 행(0.x)을
                # 평균내 꽉 찬 행의 줄이 밖으로 밀린다(물림).
                _row_alpha = [0.0] * nrow
                for i in range(nrow):
                    d = row_h[i] - _comp[i]
                    if d > 1e-6:
                        _row_alpha[i] = min(1.0, max(
                            0.0, (row_h[i] - _new[i]) / d))
                _calib_alpha = _row_alpha
                row_h = _new
        # 표 압축 폐지 — 원본 해부 결과 한컴은 다중페이지 표를 압축하지 않고
        # 페이지를 늘린다(검증: cellSz 합 2091 = p1 964+p2 1009+p3 118,
        # 각주 저장 vpos 239 = p3 표 하단 바로 아래 — 픽셀 정합). 행은
        # cellSz(한컴 저장 실높이) 그대로 두고, 표 뒤 본문은 emit_para 의
        # 흐름 불변식이 올바른 페이지로 보낸다. (α압축은 2쪽 오가정 위에서
        # 행을 글리프 밀착까지 눌러 서식이 뭉개지는 결함이었다)
        alpha = _calib_alpha   # 0.0 | 행별 α 리스트(캘리브레이션 축소 시)
        if os.environ.get("COORD_DEBUG"):
            print(f"[DBG tbl] base=({base_x:.0f},{base_y:.0f}) "
                  f"nrow={nrow} ncol={ncol} th={th:.0f} "
                  f"sum={sum(row_h):.0f} row_h="
                  f"{[round(h, 1) for h in row_h]}", file=sys.stderr)
        col_x = [0.0] * (ncol + 1)
        for i in range(ncol):
            col_x[i + 1] = col_x[i] + col_w[i]
        row_abs, row_bot = paginate_rows(cells, row_h, nrow, base_y, geo)
        col_rank = col_rank_map(cells)
        table_bottom = base_y
        for c in cells:
            if c["rowSpan"] == 1 and c["row"] in _zero_rows:
                continue   # 접힌 반복 헤더행 — 비표시
            cid = _cell_id(tbl, c["row"], col_rank.get((c["row"], c["col"]),
                                                        c["col"]))
            cx = base_x + col_x[c["col"]]
            cy = row_abs[c["row"]]
            cw = col_x[min(c["col"] + c["colSpan"], ncol)] - col_x[c["col"]]
            _last = min(c["row"] + c["rowSpan"], nrow) - 1
            # 병합 셀이 페이지 점프에 걸치면 연속 구간(조각)으로 분해 —
            # 한컴의 병합 셀 페이지 분할 재현. 조각마다 박스를 따로 그리고,
            # 셀 내용 줄은 조각을 잇는 연속 오프셋 공간에 매핑한다.
            frags = []           # [(y_top, height)] 페이지별 연속 구간
            _fs = c["row"]
            for r2 in range(c["row"], _last + 1):
                if (r2 < _last
                        and abs(row_abs[r2 + 1] - row_bot[r2]) > 0.5):
                    frags.append((row_abs[_fs], row_bot[r2] - row_abs[_fs]))
                    _fs = r2 + 1
            frags.append((row_abs[_fs], row_bot[_last] - row_abs[_fs]))
            ch = sum(f[1] for f in frags)      # 가시 높이(페이지 갭 제외)

            def _y_at(off, lh=0.0, _frags=frags):
                """셀 내용 오프셋 → 절대 y (조각 경계를 건너 연속 매핑).

                lh(줄 높이)를 주면 줄이 조각 절단면에 걸칠 때 한컴처럼 줄
                전체를 다음 조각(다음 페이지) 시작으로 넘긴다 — 글리프가
                페이지 절단면에서 반쯤 잘리는 것을 방지."""
                cum = 0.0
                for _k, (fy, fh) in enumerate(_frags):
                    if _k == len(_frags) - 1 or off + lh <= cum + fh + 1.0:
                        # 이월된 줄은 조각 상단에 클램프(음수 오프셋 방지)
                        return fy + max(0.0, off - cum)
                    cum += fh
                return _frags[-1][0] + max(0.0, off - cum)
            # 이 셀 직속 문단만 (중첩표 안 문단 제외)
            cell_lines = []
            for cp in c["tc"].iter():
                if ln(cp.tag) == "p" and _nearest_cell(cp) is c["tc"]:
                    cell_lines.extend(_cell_para_lines(cp))
            # 세로쓰기(vertical) 2글자 이상 헤더의 w/h 스왑 — 재적용 후
            # 회귀 발견(별지 제20호서식 등에서 layout_quality cellOverflow
            # 324건, 최대 15.3px) 확인돼 재차 되돌림. 코퍼스 세로쓰기 비율
            # 0.6%(142/24153건)로 극소수라, 회귀를 0으로 만드는 쪽이 이득
            # 이라는 대표님 판단에 따라 미완성 기능으로 별도 워크스트림에
            # 미룬다(1글자 헤더는 CSS writing-mode 만으로 정상 렌더돼
            # cline["vertical"] 플래그는 유지 — 그쪽은 회귀 없음).
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
            # 행별 α 배열이면 이 셀 span 의 최대 α 를 사용.
            if isinstance(alpha, list):
                _a = max((alpha[r] for r in range(
                    c["row"], min(c["row"] + c["rowSpan"], nrow))),
                    default=0.0)
            else:
                _a = alpha
            mt_eff = c["mt"] * (1.0 - 0.5 * _a)
            if _a > 0 and cell_lines:
                order = sorted(range(len(cell_lines)),
                               key=lambda i: cell_lines[i]["ry"])
                cum = 0.0
                for i in order:
                    cl = cell_lines[i]
                    cl["ryEff"] = cl["ry"] - _a * (cl["ry"] - cum)
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
                    "y": round(_y_at(mt_eff + voff + cl["ryEff"],
                                     cl["h"]), 1),
                    "w": round(wpx, 1), "h": round(cl["h"], 1),
                    "baseline": round(cl.get("baseline", 0), 1),
                    "cell": True, "cellId": cid}
                if c.get("vertical"):
                    cline["vertical"] = True
                if cl.get("align"):
                    cline["align"] = cl["align"]
                lines.append(cline)
            bf = border_fills.get(c["bfRef"])
            for _fi, (fy, fh) in enumerate(frags):
                box = {"x": round(cx, 1), "y": round(fy, 1),
                       "w": round(cw, 1), "h": round(fh, 1),
                       "cellId": cid}
                if _fi > 0:
                    box["frag"] = _fi   # 병합 셀의 다음 페이지 연속 조각
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
                           _y_at(mt_eff + voff + nvpos * (1.0 - 0.5 * _a)))
            table_bottom = max(table_bottom, row_bot[_last])
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
            _on_vpos_reset()
        st["prev_vpos"] = vpos
        return (st["page_idx"] * page_h) + m_top + vpos * HU

    def walk(el):
        for child in el:
            if ln(child.tag) != "p":
                continue
            _update_col_state(child)
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
                # 텍스트 없는 표-호스트 문단은 자체 lineseg 1개(표 배치
                # 앵커, vertpos=표가 문단 흐름 안에서 시작하는 오프셋)를
                # 갖는 경우가 흔하다 — 이 반환값을 버리면(과거 "페이지 상태
                # 갱신용"으로만 씀) 표 전체가 그 오프셋만큼 위로 밀려
                # 렌더된다(실사례: vertpos=2312HU=30.8px 누락 → 표 전체가
                # 31px 위로 어긋남). 반환된 앵커 y 를 표 시작 기준으로 사용.
                _anchor_top = None
                if own_text(child).strip():
                    emit_para(child)
                else:
                    _anchor_top = _para_top_y(child)
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
                # 안전장치 — 다중 표 문서에서 뒤쪽 표의 호스트 문단 앵커가
                # (page_idx 갱신 어긋남 등으로) 이전 표보다 앞선 y 를 내면
                # 표끼리 겹쳐 쪽수가 왜곡되는 회귀가 실사례로 확인됨(마커
                # 문서 7→5쪽). 앵커는 흐름 위치보다 뒤로 당길 수만 있고
                # (전진), 이미 채워진 flow_y 이전으로 되돌리지 않는다.
                base_y = (max(_anchor_top, st["flow_y"])
                          if _anchor_top is not None else st["flow_y"])
                if _anchor_top is not None and _anchor_top < st["flow_y"] - 0.5:
                    # 가드 발동 로그 — 무음이면 진짜 앵커 계산 버그가 가드에
                    # 가려져 diff 만 미세하게 나빠지는 원인추적 불가 상태가
                    # 된다(대표님 지적). 발동 빈도를 코퍼스 통계로 뽑아
                    # 가드가 정당한 규칙인지 임시방편인지 판별하는 근거.
                    warnings.append({
                        "code": "ANCHOR_CLAMPED",
                        "message": (f"table anchor {_anchor_top:.1f}px < "
                                    f"flow_y {st['flow_y']:.1f}px — "
                                    "anchor 무시하고 flow_y 사용"),
                        "anchorTop": round(_anchor_top, 1),
                        "flowY": round(st["flow_y"], 1)})
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
    # 페이지별 복구·출력 — 전역 y 를 페이지-로컬 좌표로 재조립한다.
    # 렌더러는 각 페이지를 독립 단위로 그리므로 전역 y 슬라이싱(경계 번짐·
    # 갭 흡수류 결함의 뿌리)이 사라진다. 잔여 걸침 박스(페이지보다 큰
    # 블록)는 여기서 페이지별 조각으로 최종 분할한다. 전역 lines/boxes 는
    # 감사·회귀 호환을 위해 병행 유지.
    pages_detail = [{"no": i + 1, "lines": [], "boxes": []}
                    for i in range(total_pages)]
    if page_h > 0:
        for l in lines:
            p = int(l["y"] // page_h)
            if 0 <= p < total_pages:
                q = dict(l)
                q["y"] = round(l["y"] - p * page_h, 1)
                pages_detail[p]["lines"].append(q)
        for b in boxes:
            top, bot = b["y"], b["y"] + b["h"]
            p0 = max(int(top // page_h), 0)
            p1 = min(int((bot - 0.1) // page_h), total_pages - 1)
            for p in range(p0, p1 + 1):
                py0 = max(top, p * page_h)
                py1 = min(bot, (p + 1) * page_h)
                if py1 - py0 < 0.5:
                    continue
                q = dict(b)
                q["y"] = round(py0 - p * page_h, 1)
                q["h"] = round(py1 - py0, 1)
                if p > p0 or b.get("frag"):
                    q["frag"] = 1
                pages_detail[p]["boxes"].append(q)
    return {
        "pageWidthPx": round(page_w, 1),
        "pageHeightPx": round(page_h, 1),
        "marginLeftPx": round(m_left, 1),
        "marginTopPx": round(m_top, 1),
        "pages": total_pages,
        "lines": lines,
        "boxes": boxes,
        "pagesDetail": pages_detail,
        "charPrDefs": char_prs,
        "warnings": warnings,
    }


def extract(path, row_scale=1.0):
    """HWPX → 좌표 레이아웃. 전 섹션(sectionN.xml)을 페이지 오프셋 누적으로
    이어붙인다 — 단일 섹션이 대부분이나, 다중 섹션 문서에서 section0 외의
    내용이 사라지지 않도록(표시/편집 누락 방지) 표준 처리한다.
    row_scale: 공장 캘리브레이션 행높이 배율(기본 1.0 = 무변화)."""
    z = zipfile.ZipFile(path)
    sec_files = [n for n in z.namelist()
                 if re.search(r"section\d+\.xml$", n.lower())]
    sec_files.sort(key=lambda n: int(re.search(r"section(\d+)",
                                                n.lower()).group(1)))
    if not sec_files:
        sec_files = [n for n in z.namelist()
                     if "section0" in n.lower() and n.endswith(".xml")][:1]
    if len(sec_files) <= 1:
        return _extract_section(path, sec_files[0], row_scale)

    merged_lines, merged_boxes, merged_pd, merged_warnings = [], [], [], []
    page_base = 0
    first = None
    for sec in sec_files:
        r = _extract_section(path, sec, row_scale)
        if first is None:
            first = r
        off = page_base * (r["pageHeightPx"] or 1)
        for line in r["lines"]:
            line["y"] = round(line["y"] + off, 1)
            merged_lines.append(line)
        for box in r["boxes"]:
            box["y"] = round(box["y"] + off, 1)
            merged_boxes.append(box)
        for pd in r.get("pagesDetail", []):
            pd = dict(pd)
            pd["no"] = page_base + pd["no"]
            merged_pd.append(pd)
        merged_warnings.extend(r.get("warnings", []))
        page_base += r["pages"]
    out = dict(first)
    out.update(pages=page_base, lines=merged_lines, boxes=merged_boxes,
               pagesDetail=merged_pd, warnings=merged_warnings)
    return out


import pathlib as _pathlib  # noqa: E402

PROJECT_ROOT = _pathlib.Path(__file__).resolve().parents[3]


def extract_layout(path):
    """공개 API 별칭 (extract 와 동일)."""
    return extract(path)


def layout_quality(layout):
    """레이아웃 자가진단 — 셀 물림·본문 겹침을 페이지-로컬 기준으로 계량.

    로드마다 서버가 계산해 응답에 실어, 품질 저하가 조용히 지나가지 않고
    뷰어 상태줄에 즉시 드러나게 한다(사용자가 매번 수동 검증할 필요 제거).
    """
    viol = 0
    max_over = 0.0
    ovl = 0
    for pd in layout.get("pagesDetail", []):
        pb = {}
        for b in pd["boxes"]:
            cid = b.get("cellId")
            if cid:
                pb.setdefault(cid, []).append(b)
        for l in pd["lines"]:
            cid = l.get("cellId")
            if cid and cid in pb:
                if not any(b["y"] - 1.5 <= l["y"]
                           and l["y"] + l["h"] <= b["y"] + b["h"] + 1.5
                           for b in pb[cid]):
                    viol += 1
                    max_over = max(max_over, min(
                        abs(l["y"] + l["h"] - (b["y"] + b["h"]))
                        for b in pb[cid]))
            elif not l.get("cell") and (l.get("text") or "").strip():
                if any(b["y"] + 3 < l["y"] < b["y"] + b["h"] - 13
                       for b in pd["boxes"]):
                    ovl += 1
    return {
        "cellOverflow": viol,
        "cellOverflowMaxPx": round(max_over, 1),
        "bodyOverlap": ovl,
        "ok": ovl == 0 and (viol == 0 or max_over <= 3.0),
    }


def _table_id_sequence(path):
    """문서 전역 등장순 표 ID 시퀀스 [(tableId, tc수)] — 섹션 파일 순.

    한컴 재저장 정규화본은 섹션을 재분할(예: 1개→2개)할 수 있어, 정규화본
    기준 tableId(t_s1_*)가 원본 파싱 문서모델(t_s0_*)과 어긋난다. 표의
    전역 등장 순서·구성(tc 수)은 재저장에도 보존되므로 위치 대응으로
    원본 네임스페이스에 번역한다.
    """
    z = zipfile.ZipFile(path)
    sec_files = sorted(
        [n for n in z.namelist() if re.search(r"section\d+\.xml$", n.lower())],
        key=lambda n: int(re.search(r"section(\d+)", n.lower()).group(1)))
    out = []
    for sec in sec_files:
        m = re.search(r"section(\d+)", sec.lower())
        si = int(m.group(1)) if m else 0
        root = ET.fromstring(z.read(sec))
        for i, t in enumerate(e for e in root.iter() if ln(e.tag) == "tbl"):
            tc = sum(1 for e in t.iter() if ln(e.tag) == "tc")
            out.append(("t_s%d_%03d" % (si, i), tc))
    return out


def _remap_cell_ids_to_source(layout, source_path, extracted_path):
    """레이아웃 cellId 를 원본 문서 표 네임스페이스로 재매핑.

    표 수·위치별 tc 수가 완전 일치할 때만 수행(보수적) — 불일치면 무변경.
    편집(문서모델)은 원본 cellId 를 쓰므로, 이 재매핑이 없으면 정규화로
    섹션이 분할된 문서에서 뒤쪽 표들의 입력칸·편집 연결이 통째로 끊긴다.
    """
    orig = _table_id_sequence(source_path)
    norm = _table_id_sequence(extracted_path)
    if len(orig) != len(norm) or any(a[1] != b[1] for a, b in zip(orig, norm)):
        return False
    remap = {b[0]: a[0] for a, b in zip(orig, norm) if a[0] != b[0]}
    if not remap:
        return False
    pat = re.compile(r"^cell_(t_s\d+_\d+)_")
    seen = set()
    colls = [layout.get("lines", []), layout.get("boxes", [])]
    for pd in layout.get("pagesDetail", []):
        colls.append(pd.get("lines", []))
        colls.append(pd.get("boxes", []))
    for coll in colls:
        for it in coll:
            if id(it) in seen:          # 동일 dict 공유 대비(이중 치환 방지)
                continue
            seen.add(id(it))
            cid = it.get("cellId")
            if not cid:
                continue
            m = pat.match(cid)
            if m and m.group(1) in remap:
                it["cellId"] = cid.replace(m.group(1), remap[m.group(1)], 1)
    return True


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
    # 한컴 좌표 정규화(가용 시) — 문서마다 제각각인 저장 좌표 신선도를
    # 한컴 재조판으로 통일해 로드 즉시 정확 렌더. 실패/미설치면 원본 추출.
    # 표시 전용: sourcePath(편집·저장 대상)는 원본 유지.
    extract_from = cand
    normalized = False
    normalization_discarded = None
    try:
        from .hancom_layout_refresh import normalize_for_layout
        norm = normalize_for_layout(cand, project_root=root)
        if norm != cand and norm.is_file():
            # 안전장치 — 한컴 재저장이 표 구조를 파괴하는 실사례 확인
            # ([별표 24] 극단 병합 rowSpan/colSpan=283 문서: 원본 tbl=3/
            # tc=46 → 정규화본 tbl=0/tc=0, 표가 통째로 문단으로 풀림).
            # 정규화본의 표 수가 원본보다 뚜렷이 적으면(소실) 정규화를
            # 버리고 원본을 그대로 쓴다 — 쪽수 정합보다 내용 무결이 우선.
            try:
                orig_tbls = _table_id_sequence(str(cand))
                norm_tbls = _table_id_sequence(str(norm))
            except Exception:
                orig_tbls, norm_tbls = [], []
            if orig_tbls and len(norm_tbls) < len(orig_tbls) * 0.5:
                # 정규화 폐기 — extract_from 은 cand 유지. 발동 로그 필수
                # (대표님 지적) — 무음이면 진짜 정규화 회귀가 조용히 쌓여
                # 원인추적 불가 상태가 된다.
                normalization_discarded = {
                    "origTables": len(orig_tbls), "normTables": len(norm_tbls)}
            else:
                extract_from = norm
                normalized = True
    except Exception:
        pass
    _rs = 1.0
    try:
        from .hancom_layout_refresh import get_row_scale
        _rs = get_row_scale(cand, project_root=root)
    except Exception:
        _rs = 1.0
    layout = extract(str(extract_from), row_scale=_rs)
    if abs(_rs - 1.0) > 1e-3:
        # 품질 게이트 — 캘리브레이션 배율이 물림/겹침을 만들면 자동 철회
        # (쪽수 정합보다 무결 표시가 우선). 철회 시 기본 배율로 재추출.
        _q = layout_quality(layout)
        if _q["ok"]:
            layout["rowScale"] = _rs
        else:
            layout = extract(str(extract_from))
            layout["rowScaleRejected"] = _rs
    if normalized:
        # 정규화본이 섹션을 재분할한 경우 cellId 를 원본 네임스페이스로 번역
        # (편집·입력칸 연결은 원본 문서모델 cellId 기준).
        try:
            layout["cellIdRemapped"] = _remap_cell_ids_to_source(
                layout, str(cand), str(extract_from))
        except Exception:
            layout["cellIdRemapped"] = False
    layout.setdefault("warnings", [])
    if normalization_discarded is not None:
        layout["warnings"].append({
            "code": "NORMALIZATION_DISCARDED",
            "message": (
                f"한컴 재저장 표 수 {normalization_discarded['normTables']} "
                f"< 원본 {normalization_discarded['origTables']}*0.5 — "
                "정규화 폐기, 원본으로 폴백"),
            **normalization_discarded})
        print(f"[COORD_WARN] NORMALIZATION_DISCARDED: {sp} "
              f"({normalization_discarded})", file=sys.stderr)
    for w in layout["warnings"]:
        if w.get("code") == "ANCHOR_CLAMPED":
            print(f"[COORD_WARN] ANCHOR_CLAMPED: {sp} "
                  f"anchor={w['anchorTop']} flow_y={w['flowY']}",
                  file=sys.stderr)
    layout["verdict"] = "PASS"
    layout["sourcePath"] = cand.relative_to(root).as_posix()
    layout["hancomNormalized"] = normalized
    layout["quality"] = layout_quality(layout)   # 로드 자가진단(상태줄 표시)
    # 실렌더 배경 정합 스냅 — truth 캐시가 있으면 편집 오버레이(셀 박스)를
    # 배경의 실제 격자선에 흡착(클릭 타깃 픽셀 정렬). 품질 계산 뒤에 수행
    # (품질은 스냅 전 자체 렌더 기준 유지).
    try:
        from .hancom_layout_refresh import snap_layout_to_truth, _truth_dir
        import hashlib as _hl
        layout["truthAligned"] = snap_layout_to_truth(
            layout, cand, project_root=root)
        # 한컴 실제 쪽수(캐시 존재 시) — 뷰어가 배경 모드 안전 여부 판단
        _dig = _hl.sha256(cand.read_bytes()).hexdigest()[:16]
        _done = _truth_dir(root) / _dig / "DONE"
        layout["hancomPages"] = (int(_done.read_text(encoding="ascii"))
                                 if _done.is_file() else None)
    except Exception:
        layout["truthAligned"] = False
        layout["hancomPages"] = None
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
