"""coord_xml — HWPX 좌표 추출용 순수 XML/단위 헬퍼.

coordinate_layout 에서 분리(모듈화). 상태 없음 — 전부 순수 함수.
read-only, 원본 무수정.
"""
import re

HU = 96 / 7200  # HWPUNIT -> px (96dpi)


def ln(tag):
    return tag.rsplit("}", 1)[-1]


def own_text(p):
    """문단 직속 run 의 텍스트(셀/중첩 제외)."""
    return own_runs(p)[0]


def own_runs(p):
    """문단 직속 텍스트 + run 별 charPr 구간.

    반환: (txt, spans) — spans = [{"s": start, "e": end, "cp": charPrIDRef}].
    txt 는 own_text 와 동일하게 조립되어 lineseg 의 textpos 인덱스와 정렬된다.
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


def slice_segments(txt, spans, a, b):
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


def direct_linesegs(p):
    """문단 직속 linesegarray 의 lineseg attrib 목록."""
    out = []
    for arr in p:
        if ln(arr.tag) == "linesegarray":
            out.extend(s.attrib for s in arr if ln(s.tag) == "lineseg")
    return out


def sane_hu(v):
    """HWPUNIT → px. 음수/센티널(UINT32_MAX 등 비정상 거대값)은 0(미정)
    으로 — 일부 문서가 cellSz 에 4294967295 를 저장해 좌표가 폭발한다."""
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        return 0.0
    return n * HU if 0 <= n < 1e6 else 0.0


def mm_px(v):
    """'0.12 mm' 형 두께 문자열 → px."""
    m = re.search(r"([\d.]+)\s*mm", v or "")
    return float(m.group(1)) * 3.7795 if m else 0.0
