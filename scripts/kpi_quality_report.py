#!/usr/bin/env python3
"""
KPI 파싱 결과 품질 리포트 생성기
입력: SQLite DB (kpi_prices.db) + 선택적 런타임 통계 (runtime_stats.json)
출력: 텍스트 리포트 + 옵션으로 JSON
실행: python3 kpi_quality_report.py [--year 2026] [--month 4] [--json]
"""
import sqlite3, json, sys
from pathlib import Path
from datetime import datetime
from collections import Counter

DB_DEFAULT      = Path.home() / "Downloads/kpi_pdf/result/kpi_prices.db"
RT_STATS_DEFAULT= Path.home() / "Downloads/kpi_pdf/result/runtime_stats.json"
OUT_DIR         = Path.home() / "Downloads/kpi_pdf/result"

UNIT_SET = {
    "M/T", "m", "개", "㎡", "㎥", "㎏", "본", "롤", "장", "매", "EA", "SET", "Set",
    "TON", "KG", "L", "ℓ", "개소", "식", "대", "조", "㎜", "m2", "m3", "포", "톤",
}
ILWI_EXTRA_UNITS = {"hr", "인"}
ALLOWED_UNITS    = UNIT_SET | ILWI_EXTRA_UNITS | {""}

SKIP_KWDS  = ("소계", "합계", "재료비", "노무비", "경비", "당단가")
COMBO_PATS = ["보통인부특별인부", "특별인부보통인부", "사보통인부", "비보통인부"]

KEY_CATS = ["공사비", "조경", "기계", "토목", "사무"]

# 진성 파편형 판별 기준 ─────────────────────────────────────────
# ① 단위-품목 혼동: UNIT_SET 멤버가 품목명으로 기록됨
#   (ex. "개소" — 단위가 품목명 열에 들어간 경우)
# ② 한정어형 파편: 독립 품목명으로 사용될 수 없는 수식어/색상어
#   - 한정어: 보통(보통인부), 특별(특별인부), 이하/이상(수치 비교), 일반, 저독(저독성)
#   - 색상어: 갈색, 밤색, 회색, 청색, 황색, 투명, 적색
#   근거: 위 단어들은 한국어에서 단독으로 건설자재/품목명이 될 수 없음
MODIFIER_FRAG_SET = {
    "보통", "특별", "이하", "이상", "일반", "저독",
    "갈색", "밤색", "회색", "청색", "황색", "투명", "적색",
}


def _pct(n, d):
    return round(n / d * 100, 2) if d else 0.0


def classify_fragment(item_name: str) -> str:
    """
    2글자 이하 품목명을 세 종류로 분류.
    반환: 'unit_as_item' | 'modifier_frag' | 'normal_short'
    """
    if item_name in UNIT_SET:
        return "unit_as_item"
    if item_name in MODIFIER_FRAG_SET:
        return "modifier_frag"
    return "normal_short"


def run_report(db_path: Path, year: int = None, month: int = None,
               rt_stats_path: Path = None) -> dict:
    """DB를 읽어 품질 지표 딕셔너리 반환."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    where, params = [], []
    if year:
        where.append("연도=?"); params.append(year)
    if month:
        where.append("월=?"); params.append(month)
    cond = ("WHERE " + " AND ".join(where)) if where else ""

    rows = conn.execute(f"SELECT * FROM prices {cond}", params).fetchall()
    conn.close()

    if not rows:
        return {}

    total      = len(rows)
    by_cat     = Counter(r["분류"] for r in rows)
    blank_uc   = Counter(r["분류"] for r in rows if not r["단위"])
    blank_total= sum(1 for r in rows if not r["단위"])

    # 핵심 분류 공백률
    cat_stats = {}
    for cat in KEY_CATS:
        cnt   = by_cat.get(cat, 0)
        blank = blank_uc.get(cat, 0)
        cat_stats[cat] = {"건수": cnt, "공백": blank, "공백률": _pct(blank, cnt)}

    # 미허용 단위
    unknown_units = Counter(r["단위"] for r in rows if r["단위"] not in ALLOWED_UNITS)

    # 오파싱 키워드
    oparsing = [r for r in rows if any(kw in r["품목명"] for kw in SKIP_KWDS)]
    oparsing_by_kw = Counter(
        next(kw for kw in SKIP_KWDS if kw in r["품목명"])
        for r in oparsing
    )

    # ── 파편형 3단계 분류 ─────────────────────────────────────────
    # 기존 정의(len≤2)는 하위 호환을 위해 유지
    all_frag = [r for r in rows if len(r["품목명"]) <= 2]
    all_frag_cnt = Counter(r["품목명"] for r in all_frag)

    unit_as_item  = [r for r in all_frag if classify_fragment(r["품목명"]) == "unit_as_item"]
    modifier_frag = [r for r in all_frag if classify_fragment(r["품목명"]) == "modifier_frag"]
    normal_short  = [r for r in all_frag if classify_fragment(r["품목명"]) == "normal_short"]

    true_frag_total = len(unit_as_item) + len(modifier_frag)
    unit_as_item_cnt  = Counter(r["품목명"] for r in unit_as_item)
    modifier_frag_cnt = Counter(r["품목명"] for r in modifier_frag)
    normal_short_cnt  = Counter(r["품목명"] for r in normal_short)

    # 결합형
    combo_pat  = [r for r in rows if any(p in r["품목명"] for p in COMBO_PATS)]
    combo_long = [r for r in rows if len(r["품목명"]) > 40]

    # 짧은 품목 (3~4글자)
    short_items = Counter(r["품목명"] for r in rows if 3 <= len(r["품목명"]) <= 4)

    # 저단가 (501~999원)
    low_price  = [r for r in rows if 501 <= r["가격"] <= 999]
    low_by_cat = Counter(r["분류"] for r in low_price)

    # 단위 분포
    unit_dist = Counter(r["단위"] for r in rows)

    # 연도/월 분포
    ym_dist = Counter((r["연도"], r["월"]) for r in rows)

    # 런타임 통계 로드 (옵션)
    rt_stats = {}
    rt_path = rt_stats_path or RT_STATS_DEFAULT
    if rt_path.exists():
        try:
            rt_stats = json.loads(rt_path.read_text(encoding="utf-8"))
        except Exception:
            rt_stats = {"error": "파일 읽기 실패"}

    return {
        "생성시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "필터": {"연도": year, "월": month},
        "전체건수": total,
        "분류별건수": dict(by_cat.most_common()),
        "단위공백": {
            "건수": blank_total,
            "공백률": _pct(blank_total, total),
        },
        "분류별단위공백": {
            cat: {
                "건수": s["건수"],
                "공백건수": s["공백"],
                "공백률": s["공백률"],
            }
            for cat, s in cat_stats.items()
        },
        "미허용단위": {
            "건수": sum(unknown_units.values()),
            "종류": dict(unknown_units.most_common(10)),
        },
        "오파싱키워드": {
            "건수": len(oparsing),
            "키워드별": dict(oparsing_by_kw),
        },
        # ── 파편형 (기존 + 신규 3단계) ──────────────────────────
        "파편형품목": {
            # 기존 정의 (하위 호환)
            "건수_구정의": len(all_frag),
            "상위10_구정의": dict(all_frag_cnt.most_common(10)),
            # 신규 정의
            "진성파편형건수": true_frag_total,
            "unit_as_item_건수": len(unit_as_item),
            "unit_as_item_상위": dict(unit_as_item_cnt.most_common(5)),
            "modifier_frag_건수": len(modifier_frag),
            "modifier_frag_상위": dict(modifier_frag_cnt.most_common(10)),
            "정상짧은품목_건수": len(normal_short),
            "정상짧은품목_상위10": dict(normal_short_cnt.most_common(10)),
        },
        "결합형품목": {
            "패턴매칭건수": len(combo_pat),
            "이상긴품목명건수": len(combo_long),
        },
        "저단가레코드": {
            "건수": len(low_price),
            "범위": "501~999원",
            "분류별": dict(low_by_cat.most_common()),
        },
        "짧은품목상위20": dict(short_items.most_common(20)),
        "단위분포상위20": dict(unit_dist.most_common(20)),
        "연도월분포": {f"{y}년{m:02d}월": c for (y, m), c in sorted(ym_dist.items())},
        "런타임통계": rt_stats,
    }


def format_report(d: dict) -> str:
    if not d:
        return "데이터 없음"

    total = d["전체건수"]
    lines = [
        "=" * 65,
        "  KPI 파싱 품질 리포트 v2",
        f"  생성: {d['생성시각']}",
        f"  필터: 연도={d['필터']['연도']}  월={d['필터']['월']}",
        "=" * 65,
        "",
        "[전체 수집]",
        f"  전체 건수        : {total:>10,}건",
    ]

    lines += ["", "[분류별 건수 + 단위 공백률]"]
    key_set = set(KEY_CATS)
    for cat, cnt in sorted(d["분류별건수"].items(), key=lambda x: -x[1]):
        if cat in key_set:
            s = d["분류별단위공백"][cat]
            lines.append(
                f"  {cat:<10} : {cnt:>8,}건   "
                f"단위공백 {s['공백건수']:>6,}건 ({s['공백률']:5.1f}%)"
            )
        else:
            lines.append(f"  {cat:<10} : {cnt:>8,}건")

    bu = d["단위공백"]
    lines += [
        "",
        "[단위 품질]",
        f"  전체 단위 공백   : {bu['건수']:>8,}건 ({bu['공백률']:.1f}%)",
    ]

    u = d["미허용단위"]
    lines += [
        "",
        "[미허용 단위 (UNIT_SET·ILWI_EXTRA_UNITS 외)]",
        f"  건수: {u['건수']}건",
    ]
    if u["종류"]:
        for unit, cnt in u["종류"].items():
            lines.append(f"    '{unit}': {cnt}건")
    else:
        lines.append("  없음")

    op = d["오파싱키워드"]
    lines += [
        "",
        "[오파싱 키워드 (소계/합계/경비/당단가 등)]",
        f"  건수: {op['건수']}건",
    ]
    if op["키워드별"]:
        for kw, cnt in sorted(op["키워드별"].items(), key=lambda x: -x[1]):
            lines.append(f"    '{kw}': {cnt}건")
    else:
        lines.append("  없음")

    fr = d["파편형품목"]
    old_cnt  = fr["건수_구정의"]
    true_cnt = fr["진성파편형건수"]
    norm_cnt = fr["정상짧은품목_건수"]
    lines += [
        "",
        "[파편형 품목 분류]",
        f"  ─ 기존 정의(≤2글자) : {old_cnt:>6,}건",
        f"  ─ 진성 파편형(신규) : {true_cnt:>6,}건  "
        f"({_pct(true_cnt, old_cnt):.1f}% of 기존)",
        f"    단위-품목 혼동    : {fr['unit_as_item_건수']:>6,}건  "
        f"({', '.join(f'{k}:{v}' for k, v in list(fr['unit_as_item_상위'].items())[:3])})",
        f"    한정어형 파편     : {fr['modifier_frag_건수']:>6,}건",
    ]
    for nm, cnt in fr["modifier_frag_상위"].items():
        lines.append(f"      '{nm}': {cnt}건")
    lines += [
        f"  ─ 정상 짧은 품목   : {norm_cnt:>6,}건  "
        f"(기존 파편형에서 제외됨)",
    ]
    for nm, cnt in list(fr["정상짧은품목_상위10"].items())[:5]:
        lines.append(f"      '{nm}': {cnt}건  ...")

    cb = d["결합형품목"]
    lines += [
        "",
        "[결합형 품목]",
        f"  패턴 매칭 건수   : {cb['패턴매칭건수']}건"
        f"  (보통인부특별인부 등 {len(COMBO_PATS)}패턴)",
        f"  이상 긴 품목명   : {cb['이상긴품목명건수']}건  (>40자)",
    ]

    lp = d["저단가레코드"]
    lines += [
        "",
        f"[저단가 레코드 ({lp['범위']})]",
        f"  건수: {lp['건수']}건",
    ]
    for cat, cnt in lp["분류별"].items():
        lines.append(f"    {cat}: {cnt}건")

    lines += ["", "[짧은 품목명 상위 20개 (3~4글자)]"]
    for i, (nm, cnt) in enumerate(d["짧은품목상위20"].items(), 1):
        lines.append(f"  {i:>2}. '{nm}': {cnt:,}건")

    lines += ["", "[단위 분포 상위 20개]"]
    for unit, cnt in d["단위분포상위20"].items():
        label = unit if unit else "(공백)"
        lines.append(f"  '{label}': {cnt:,}건 ({cnt/total*100:.1f}%)")

    # 런타임 통계
    rt = d.get("런타임통계", {})
    if rt and "error" not in rt:
        lines += [
            "",
            "[런타임 품질 통계 (파싱 시 기록)]",
            f"  전체 페이지       : {rt.get('total_pages', '-'):>6}",
            f"  가격 페이지       : {rt.get('price_pages', '-'):>6}",
            f"  지역헤더 경로     : {rt.get('region_header_pages', '-'):>6}페이지",
            f"  ①②③헤더 경로    : {rt.get('stage_header_pages', '-'):>6}페이지",
            f"  일위대가 경로     : {rt.get('ilwidaega_pages', '-'):>6}페이지",
            f"  헤더 미탐지       : {rt.get('no_header_pages', '-'):>6}페이지",
            f"  unit_x=None       : {rt.get('unit_x_none_pages', '-'):>6}페이지",
            f"  paren fallback    : {rt.get('paren_header_fallback', '-'):>6}회",
        ]
    elif rt:
        lines += ["", f"[런타임 통계] 로드 실패: {rt.get('error')}"]
    else:
        lines += ["", "[런타임 통계] 파일 없음 (파서 재실행 필요)"]

    lines += ["", "[연도/월 분포]"]
    for ym, cnt in d["연도월분포"].items():
        lines.append(f"  {ym}: {cnt:,}건")

    lines += ["", "=" * 65]
    return "\n".join(lines)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="KPI 파싱 품질 리포트")
    ap.add_argument("--db",    default=str(DB_DEFAULT))
    ap.add_argument("--year",  type=int, default=None)
    ap.add_argument("--month", type=int, default=None)
    ap.add_argument("--rt",    default=str(RT_STATS_DEFAULT), help="런타임 통계 JSON 경로")
    ap.add_argument("--json",  action="store_true")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB 없음: {db_path}"); sys.exit(1)

    d = run_report(db_path, year=args.year, month=args.month,
                   rt_stats_path=Path(args.rt))
    txt = format_report(d)
    print(txt)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts  = datetime.now().strftime("%Y%m%d_%H%M")
    ym  = f"_{args.year}{args.month:02d}" if args.year and args.month else ""
    tp  = OUT_DIR / f"quality_report{ym}_{ts}.txt"
    tp.write_text(txt, encoding="utf-8")
    print(f"\n리포트 저장: {tp}")

    if args.json:
        jp = OUT_DIR / f"quality_report{ym}_{ts}.json"
        jp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON 저장: {jp}")


if __name__ == "__main__":
    main()
