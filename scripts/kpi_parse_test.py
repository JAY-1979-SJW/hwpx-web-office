"""
kpi_parse.py 회귀 검증 스크립트
검증 항목:
  1) 단위 〃 상속
  2) 일위대가형 공사비 파싱
  3) 규격→가격 혼입 차단
  4) price_x_min 경계 (단위 헤더 우측 컬럼 오참조 방지)
"""

import importlib.util
import os
import sqlite3
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import fitz

# CLI로 직접 실행하는 회귀 검증 스크립트(main() 참고) — test_* 함수들이
# 인자 m(파서 모듈)을 필수로 받아 pytest가 그대로 수집하면 전부 fixture
# 오류로 깨진다(scripts/hwpx/test_hwpx_security.py 와 같은 이유·같은 처리).
__test__ = False


def load_parser(path="/home/ubuntu/kpi_parse.py"):
    spec = importlib.util.spec_from_file_location("kpi_parse", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_quality_report(path="/home/ubuntu/kpi_quality_report.py"):
    spec = importlib.util.spec_from_file_location("kpi_quality_report", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def make_temp_db(rows):
    """rows: list of dict with prices 테이블 컬럼. 임시 SQLite 파일 경로 반환."""
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(tmp)
    conn.executescript("""
    CREATE TABLE prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        연도 INTEGER, 월 INTEGER, 책명 TEXT, 분류 TEXT,
        품목명 TEXT, 단위 TEXT, 지역 TEXT, 가격 INTEGER
    );
    """)
    conn.executemany(
        "INSERT INTO prices(연도,월,책명,분류,품목명,단위,지역,가격) "
        "VALUES(:연도,:월,:책명,:분류,:품목명,:단위,:지역,:가격)",
        rows,
    )
    conn.commit()
    conn.close()
    return Path(tmp)


def run_page(m, pdf_path, page_idx, meta):
    doc = fitz.open(str(pdf_path))
    rows = m.parse_page(doc[page_idx], meta)
    doc.close()
    return rows


PDF_BASE = Path("/home/ubuntu/Downloads/kpi_pdf/2026년04월_종합물가정보")
META_토목 = {"연도": 2026, "월": 4, "책명": "종합물가정보", "분류": "토목"}
META_공사비 = {"연도": 2026, "월": 4, "책명": "종합물가정보", "분류": "공사비"}
META_사무 = {"연도": 2026, "월": 4, "책명": "종합물가정보", "분류": "사무"}


def test_ditto_unit_inheritance(m):
    """
    〃 기호가 단위 위치에 있을 때 이전 단위를 상속해야 한다.
    토목 PDF에서 동일 품목 다음 행에 〃가 있을 때 단위가 유지되는지 확인.
    """
    pdf = fitz.open(str(PDF_BASE / "2026년04월_종합물가정보_토목.pdf"))
    rows_all = []
    for pi in range(pdf.page_count):
        rows_all.extend(m.parse_page(pdf[pi], META_토목))
    pdf.close()

    # 지표 1: 단위 공백률
    blank_rate = sum(1 for r in rows_all if not r["단위"]) / len(rows_all) * 100

    # 지표 2: 과도한 단위 불일관성 (3종 이상 단위 = 오파싱 강하게 의심)
    #   2종 이하 불일관은 정상 판매 단위 혼재(㎡/개 등)로 허용
    by_item = defaultdict(set)
    for r in rows_all:
        if r["단위"]:
            by_item[r["품목명"]].add(r["단위"])

    multi3_items = sum(1 for units in by_item.values() if len(units) >= 3)
    multi3_rate = multi3_items / len(by_item) * 100 if by_item else 0

    result = "PASS" if blank_rate < 35 and multi3_rate < 5 else "WARN"
    print("[TEST 1] 단위 공백률 / 과도한 단위 불일관")
    print(f"  단위 공백률: {blank_rate:.1f}%  (기준 <35%)")
    print(f"  3종 이상 단위 품목: {multi3_rate:.1f}%  (기준 <5%, 오파싱 지표)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_ilwidaega_parsing(m):
    """
    일위대가형 공사비 PDF가 단가 열을 파싱해 131건 이상 수집되어야 한다.
    """
    pdf = fitz.open(str(PDF_BASE / "2026년04월_종합물가정보_공사비.pdf"))
    rows = []
    for pi in range(pdf.page_count):
        rows.extend(m.parse_page(pdf[pi], META_공사비))
    pdf.close()

    SKIP_KWDS = ("소계", "합계", "재료비", "노무비", "경비")
    count = len(rows)
    danwon_rows = [r for r in rows if r["지역"] == "단가"]
    has_valid_price = sum(1 for r in danwon_rows if r["가격"] > 1000)
    blank_item = sum(1 for r in rows if not r["품목명"])
    # 소계/합계 행이 품목명으로 잘못 저장되지 않아야 함
    leaked_summary = sum(1 for r in rows if any(kw in r["품목명"] for kw in SKIP_KWDS))

    result = "PASS" if count > 500 and has_valid_price > 100 and leaked_summary == 0 else "WARN"
    print("\n[TEST 2] 일위대가형 공사비 파싱")
    print(f"  수집 건수: {count}  (기준 >500, 수정 전 131)")
    print(f"  단가 열 유효 가격: {has_valid_price}건  (기준 >100)")
    print(f"  품목명 공백: {blank_item}건")
    print(f"  소계/합계 오파싱: {leaked_summary}건  (기준 0)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_spec_price_isolation(m):
    """
    규격 열(x<160) 수치가 가격으로 혼입되지 않아야 한다.
    토목 PDF에서 가격 컬럼이 160px 이상 위치에 있는지 확인.
    """
    import re

    PRICE_PAT = re.compile(r"^\d[\d,]+$")
    REGIONS = {"서울", "인천", "수원", "부산", "대구", "대전", "광주", "전주", "강원", "제주"}

    pdf = fitz.open(str(PDF_BASE / "2026년04월_종합물가정보_토목.pdf"))
    suspicious = 0
    total_prices = 0

    for pi in range(pdf.page_count):
        spans = []
        for block in pdf[pi].get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                y = round(line["bbox"][1])
                for span in line["spans"]:
                    t = span["text"].strip()
                    if t:
                        spans.append((y, round(span["origin"][0]), t))

        region_xs = [x for y, x, t in spans if t.replace(" ", "") in REGIONS]
        if not region_xs:
            continue
        price_x_min = min(region_xs) - 40

        for _y, x, t in spans:
            if PRICE_PAT.match(t) and len(t) > 4 and x >= price_x_min:
                total_prices += 1
                if x < 160:
                    suspicious += 1

    pdf.close()
    rate = suspicious / total_prices * 100 if total_prices else 0
    result = "PASS" if rate < 1.0 else "WARN"
    print("\n[TEST 3] 규격→가격 혼입 차단")
    print(f"  전체 가격 후보: {total_prices}")
    print(f"  x<160 혼입 의심: {suspicious}건 ({rate:.2f}%)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_unit_col_boundary(m):
    """
    단위 헤더가 가격 컬럼보다 우측에 있을 때 price_x_min을 오염시키지 않아야 한다.
    토목 8페이지(기준①) 사례: unit_x=501 > col_map_min=280 → base=240 유지.
    """
    # calc_price_x_min 직접 테스트
    result_ok = m.calc_price_x_min(280, 501) == 240  # unit_x > col_map_min → ignore
    result_ok &= m.calc_price_x_min(248, 199) == 219  # unit_x < col_map_min, 199+20=219 > 208
    result_ok &= m.calc_price_x_min(279, 242) == 262  # 사무 케이스: 242+20=262 > 239

    result = "PASS" if result_ok else "FAIL"
    print("\n[TEST 4] price_x_min 경계 보정 로직")
    print(f"  calc_price_x_min(280, 501) = {m.calc_price_x_min(280, 501)}  (expect 240)")
    print(f"  calc_price_x_min(248, 199) = {m.calc_price_x_min(248, 199)}  (expect 219)")
    print(f"  calc_price_x_min(279, 242) = {m.calc_price_x_min(279, 242)}  (expect 262)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_ilwidaega_unit_recognition(m):
    """
    공사비 단위 인식 보강 검증:
    1) hr 인식: 크레인/굴삭기 등 장비 품목에 hr 단위 부여
    2) 인 인식: 보통인부/배관공 등 인력 품목에 인 단위 부여
    3) 오탐 방지: ILWI_EXTRA_UNITS가 공통 UNIT_SET을 오염시키지 않아야 함
    """
    # 케이스 3: UNIT_SET 오염 없는지 확인
    assert "hr" not in m.UNIT_SET, "hr이 공통 UNIT_SET에 들어가면 안 됨"
    assert "인" not in m.UNIT_SET, "인이 공통 UNIT_SET에 들어가면 안 됨"
    assert hasattr(m, "ILWI_EXTRA_UNITS"), "ILWI_EXTRA_UNITS 미정의"
    assert "hr" in m.ILWI_EXTRA_UNITS, "hr이 ILWI_EXTRA_UNITS에 있어야 함"
    assert "인" in m.ILWI_EXTRA_UNITS, "인이 ILWI_EXTRA_UNITS에 있어야 함"

    # 케이스 1 & 2: 실제 공사비 PDF 파싱 후 hr / 인 단위 등장 여부 확인
    PDF = PDF_BASE / "2026년04월_종합물가정보_공사비.pdf"
    if not PDF.exists():
        print("\n[TEST 5] ilwidaega 단위 인식 — PDF 없음, 구조 검증만 수행")
        print("  UNIT_SET 오염 없음: PASS")
        print("  ILWI_EXTRA_UNITS 정의: PASS")
        print("  결과: PASS")
        return True

    pdf = fitz.open(str(PDF))
    rows = []
    for pi in range(pdf.page_count):
        rows.extend(m.parse_page(pdf[pi], META_공사비))
    pdf.close()

    danwon = [r for r in rows if r["지역"] == "단가"]
    hr_rows = [r for r in danwon if r["단위"] == "hr"]
    in_rows = [r for r in danwon if r["단위"] == "인"]
    blank_danwon = [r for r in danwon if not r["단위"]]
    blank_rate = len(blank_danwon) / len(danwon) * 100 if danwon else 100

    result = "PASS" if hr_rows and in_rows and blank_rate < 35 else "WARN"
    print("\n[TEST 5] ilwidaega 단위 인식 (hr / 인 / 오탐 방지)")
    print(f"  hr 단위 품목: {len(hr_rows)}건  (기준 >0)")
    print(f"  인 단위 품목: {len(in_rows)}건  (기준 >0)")
    print(f"  단가 분기 단위 공백률: {blank_rate:.1f}%  (기준 <35%)")
    print(f"  UNIT_SET 오염 없음: {'PASS' if 'hr' not in m.UNIT_SET else 'FAIL'}")
    print(f"  결과: {result}")
    return result == "PASS"


def test_ilwidaega_item_fragment(m):
    """
    공사비 품목명 파편/결합 오파싱 방지 검증:
    1) 보통인부 파편 방지: '보통인부특별인부' 결합이 나타나지 않아야 함
    2) 특별인부 파편 방지: '사보통인부', '비보통인부' 등 좌측 구분기호 결합 없어야 함
    3) 정상 짧은 품목 유지: 목재, 트럭, 석공, 크레인 등이 유지돼야 함
    """
    PDF = PDF_BASE / "2026년04월_종합물가정보_공사비.pdf"
    if not PDF.exists():
        print("\n[TEST 6] ilwidaega 품목명 파편/결합 방지 — PDF 없음, SKIP")
        return True

    pdf = fitz.open(str(PDF))
    rows = []
    for pi in range(pdf.page_count):
        rows.extend(m.parse_page(pdf[pi], META_공사비))
    pdf.close()

    from collections import Counter

    item_cnt = Counter(r["품목명"] for r in rows)

    # 케이스 1: 결합형 오파싱 없어야 함
    combo_bad = item_cnt.get("보통인부특별인부", 0) + item_cnt.get("특별인부보통인부", 0)
    # 케이스 2: 좌측 구분기호 결합 없어야 함
    prefix_bad = item_cnt.get("사보통인부", 0) + item_cnt.get("비보통인부", 0)
    # 케이스 3: 정상 짧은 품목 유지
    short_normals = {"목재": 1, "트럭": 1, "석공": 1, "크레인": 1, "굴삭기": 1, "보통인부": 50}
    short_ok = all(item_cnt.get(nm, 0) >= min_cnt for nm, min_cnt in short_normals.items())

    result = "PASS" if combo_bad == 0 and prefix_bad == 0 and short_ok else "FAIL"
    print("\n[TEST 6] ilwidaega 품목명 파편/결합 방지")
    print(f"  결합형 오파싱 (보통인부특별인부 등): {combo_bad}건  (기준 0)")
    print(f"  구분기호 결합 (사보통인부 등): {prefix_bad}건  (기준 0)")
    print(f"  정상 짧은 품목 유지: {'OK' if short_ok else 'FAIL'}")
    for nm, min_cnt in short_normals.items():
        print(f"    {nm}: {item_cnt.get(nm, 0)}건  (기준 >={min_cnt})")
    print(f"  결과: {result}")
    return result == "PASS"


def test_jyogyeong_unit_rate(m):
    """
    조경 분류 단위 공백률이 35% 미만이어야 한다.
    Set·톤 추가 + 단위헤더 분리 인식 후 기준.
    """
    PDF = PDF_BASE / "2026년04월_종합물가정보_조경.pdf"
    if not PDF.exists():
        print("\n[TEST 7] 조경 단위 공백률 — PDF 없음, SKIP")
        return True

    pdf = fitz.open(str(PDF))
    META = {"연도": 2026, "월": 4, "책명": "종합물가정보", "분류": "조경"}
    rows = []
    for pi in range(pdf.page_count):
        rows.extend(m.parse_page(pdf[pi], META))
    pdf.close()

    total = len(rows)
    blank = sum(1 for r in rows if not r["단위"])
    rate = blank / total * 100 if total else 100
    set_cnt = sum(1 for r in rows if r["단위"] == "Set")
    ton_cnt = sum(1 for r in rows if r["단위"] == "톤")

    result = "PASS" if rate < 35 and set_cnt > 0 else "WARN"
    print("\n[TEST 7] 조경 단위 공백률")
    print(f"  전체: {total}건  단위공백: {blank}건 ({rate:.1f}%)  (기준 <35%)")
    print(f"  Set 단위: {set_cnt}건  톤 단위: {ton_cnt}건  (기준 >0)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_giyye_multi_section(m):
    """
    기계 분류 단위 공백률이 45% 미만이어야 한다.
    stage_y 첫 번째 고정으로 다중 섹션 커버리지 증가 확인.
    """
    PDF = PDF_BASE / "2026년04월_종합물가정보_기계.pdf"
    if not PDF.exists():
        print("\n[TEST 8] 기계 단위 공백률 — PDF 없음, SKIP")
        return True

    pdf = fitz.open(str(PDF))
    META = {"연도": 2026, "월": 4, "책명": "종합물가정보", "분류": "기계"}
    rows = []
    for pi in range(pdf.page_count):
        rows.extend(m.parse_page(pdf[pi], META))
    pdf.close()

    total = len(rows)
    blank = sum(1 for r in rows if not r["단위"])
    rate = blank / total * 100 if total else 100
    desktop_cnt = sum(1 for r in rows if "데스크탑" in r["품목명"] or "PC" in r["품목명"])

    result = "PASS" if rate < 45 and desktop_cnt > 0 else "WARN"
    print("\n[TEST 8] 기계 단위 공백률 / 다중 섹션 커버리지")
    print(f"  전체: {total}건  단위공백: {blank}건 ({rate:.1f}%)  (기준 <45%)")
    print(f"  데스크탑/PC 품목: {desktop_cnt}건  (기준 >0, stage_y 수정 지표)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_unit_set_no_contamination(m):
    """
    Set·톤이 공통 UNIT_SET에 추가됐을 때 공사비 단위 오탐 없는지 확인.
    공사비 파싱 결과에서 단위 공백률이 5% 미만이어야 한다.
    """
    assert "Set" in m.UNIT_SET, "Set이 UNIT_SET에 있어야 함"
    assert "톤" in m.UNIT_SET, "톤이 UNIT_SET에 있어야 함"
    assert "hr" not in m.UNIT_SET, "hr이 공통 UNIT_SET에 들어가면 안 됨"

    PDF = PDF_BASE / "2026년04월_종합물가정보_공사비.pdf"
    if not PDF.exists():
        print("\n[TEST 9] Set·톤 오탐 방지 — PDF 없음, 구조 검증만")
        print("  UNIT_SET 포함: PASS")
        print("  결과: PASS")
        return True

    pdf = fitz.open(str(PDF))
    rows = []
    for pi in range(pdf.page_count):
        rows.extend(m.parse_page(pdf[pi], META_공사비))
    pdf.close()

    total = len(rows)
    blank = sum(1 for r in rows if not r["단위"])
    rate = blank / total * 100 if total else 100
    ton_danwon = sum(1 for r in rows if r["지역"] == "단가" and r["단위"] == "톤")
    # Set은 공사비 댐퍼류에서 정상 사용됨 — 단위공백률과 톤 오탐만 검사
    result = "PASS" if rate < 5 and ton_danwon == 0 else "WARN"
    print("\n[TEST 9] Set·톤 공사비 오탐 방지")
    print(f"  공사비 단위공백률: {rate:.1f}%  (기준 <5%)")
    print(f"  공사비 톤 단위(일위대가): {ton_danwon}건  (기준 0)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_paren_header_func(m):
    """
    find_unit_from_paren_header 함수 직접 단위 테스트.
    (단위 : 대) / (단위 : 개, 대) / (단위 : 개, m) 패턴에서 정확히 추출하는지 확인.
    텍스트 없을 때 None 반환 확인.
    """
    if not hasattr(m, "find_unit_from_paren_header"):
        print("\n[TEST 10] paren header 함수 단위 테스트 — 함수 미존재, FAIL")
        return False

    def make_rows(y, text):
        return [(y, [(10.0, text)])]

    # 케이스 1: (단위 : 대)
    r1 = m.find_unit_from_paren_header(make_rows(100, "(단위 : 대)"), 100)
    # 케이스 2: (단위 : 개, 대) → 첫 UNIT_SET 멤버인 개
    r2 = m.find_unit_from_paren_header(make_rows(100, "(단위 : 개, 대)"), 100)
    # 케이스 3: (단위 : 개, m)
    r3 = m.find_unit_from_paren_header(make_rows(100, "(단위 : 개, m)"), 100)
    # 케이스 4: 텍스트 없음 → None
    r4 = m.find_unit_from_paren_header(make_rows(100, "합계"), 100)
    # 케이스 5: y 범위 밖 → None
    r5 = m.find_unit_from_paren_header(make_rows(300, "(단위 : 대)"), 100)

    ok = r1 == "대" and r2 == "개" and r3 == "개" and r4 is None and r5 is None
    result = "PASS" if ok else "FAIL"
    print("\n[TEST 10] find_unit_from_paren_header 직접 단위 테스트")
    print(f"  (단위 : 대)       → '{r1}'  (expect '대')")
    print(f"  (단위 : 개, 대)   → '{r2}'  (expect '개')")
    print(f"  (단위 : 개, m)    → '{r3}'  (expect '개')")
    print(f"  '합계' 텍스트     → {r4}    (expect None)")
    print(f"  y 범위 밖         → {r5}    (expect None)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_giyye_paren_unit_effect(m):
    """
    기계 unit_x=None 페이지 paren_unit 효과 검증.
    전체 단위 공백률 <5% (unit_x=None 6페이지 846건이 채워진 후 기준: 1.2%).
    개/대 단위 각각 >0 확인.
    """
    PDF = PDF_BASE / "2026년04월_종합물가정보_기계.pdf"
    if not PDF.exists():
        print("\n[TEST 11] 기계 paren_unit 효과 — PDF 없음, SKIP")
        return True

    pdf = fitz.open(str(PDF))
    META = {"연도": 2026, "월": 4, "책명": "종합물가정보", "분류": "기계"}
    rows = []
    for pi in range(pdf.page_count):
        rows.extend(m.parse_page(pdf[pi], META))
    pdf.close()

    total = len(rows)
    blank = sum(1 for r in rows if not r["단위"])
    rate = blank / total * 100 if total else 100
    gae_cnt = sum(1 for r in rows if r["단위"] == "개")
    dae_cnt = sum(1 for r in rows if r["단위"] == "대")

    result = "PASS" if rate < 5 and gae_cnt > 0 and dae_cnt > 0 else "WARN"
    print("\n[TEST 11] 기계 paren_unit 효과 (unit_x=None 6페이지)")
    print(f"  전체: {total}건  단위공백: {blank}건 ({rate:.1f}%)  (기준 <5%)")
    print(f"  개 단위: {gae_cnt}건  대 단위: {dae_cnt}건  (기준 각 >0)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_paren_unit_no_side_effect(m):
    """
    paren_unit 추가로 인해 조경·공사비 분류에 오탐이 생기지 않아야 한다.
    조경 단위 공백률 <20% (14.9% 달성 후 기준).
    공사비 단위 항목에 UNIT_SET 외 이상 값이 없어야 함.
    """
    ok_jyogyeong = True
    ok_gongsa = True

    # 조경 확인
    PDF_J = PDF_BASE / "2026년04월_종합물가정보_조경.pdf"
    if PDF_J.exists():
        pdf = fitz.open(str(PDF_J))
        META = {"연도": 2026, "월": 4, "책명": "종합물가정보", "분류": "조경"}
        rows = []
        for pi in range(pdf.page_count):
            rows.extend(m.parse_page(pdf[pi], META))
        pdf.close()
        total = len(rows)
        blank = sum(1 for r in rows if not r["단위"])
        rate = blank / total * 100 if total else 100
        ok_jyogyeong = rate < 20
        print("\n[TEST 12] paren_unit 부작용 없음 — 조경/공사비")
        print(f"  조경 단위공백률: {rate:.1f}%  (기준 <20%)")
    else:
        print("\n[TEST 12] paren_unit 부작용 없음 — 조경 PDF 없음")

    # 공사비 확인: paren_unit으로 인한 이상 단위 없는지
    PDF_G = PDF_BASE / "2026년04월_종합물가정보_공사비.pdf"
    if PDF_G.exists():
        pdf = fitz.open(str(PDF_G))
        rows = []
        for pi in range(pdf.page_count):
            rows.extend(m.parse_page(pdf[pi], META_공사비))
        pdf.close()
        all_units = set(r["단위"] for r in rows if r["단위"])
        # UNIT_SET + ILWI_EXTRA_UNITS 외 단위는 오탐
        allowed = m.UNIT_SET | getattr(m, "ILWI_EXTRA_UNITS", set())
        unknown = all_units - allowed
        ok_gongsa = len(unknown) == 0
        print(f"  공사비 미허용 단위: {sorted(unknown) if unknown else '없음'}  (기준 0종)")
    else:
        print("  공사비 PDF 없음 — 건너뜀")

    result = "PASS" if ok_jyogyeong and ok_gongsa else "WARN"
    print(f"  결과: {result}")
    return result == "PASS"


def test_report_structure(m_report):
    """
    run_report가 실제 DB에서 필수 키를 가진 딕셔너리를 반환하는지 확인.
    기존 파싱 테스트 수치(기계 1.2%, 조경 14.9%, 공사비 2.4%)와 일치하는지 검증.
    """
    DB = Path.home() / "Downloads/kpi_pdf/result/kpi_prices.db"
    if not DB.exists():
        print("\n[TEST 13] 리포트 구조 검증 — DB 없음, SKIP")
        return True

    d = m_report.run_report(DB, year=2026, month=4)

    required_keys = [
        "전체건수",
        "분류별건수",
        "단위공백",
        "분류별단위공백",
        "미허용단위",
        "오파싱키워드",
        "파편형품목",
        "결합형품목",
        "저단가레코드",
        "짧은품목상위20",
    ]
    missing = [k for k in required_keys if k not in d]

    cat_blank = d.get("분류별단위공백", {})
    giyye_rate = cat_blank.get("기계", {}).get("공백률", 999)
    jyo_rate = cat_blank.get("조경", {}).get("공백률", 999)
    gongsa_rate = cat_blank.get("공사비", {}).get("공백률", 999)

    ok = (
        not missing
        and d["전체건수"] > 100_000
        and giyye_rate < 5
        and jyo_rate < 20
        and gongsa_rate < 5
    )

    result = "PASS" if ok else "FAIL"
    print("\n[TEST 13] 리포트 구조 + 기존 수치 일치")
    print(f"  누락 키: {missing if missing else '없음'}")
    print(f"  전체 건수: {d['전체건수']:,}건  (기준 >100,000)")
    print(f"  기계 공백률: {giyye_rate:.1f}%  (기준 <5%,  이전 보고 1.2%)")
    print(f"  조경 공백률: {jyo_rate:.1f}%  (기준 <20%, 이전 보고 14.9%)")
    print(f"  공사비 공백률: {gongsa_rate:.1f}%  (기준 <5%,  이전 보고 2.4%)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_report_aggregate_accuracy(m_report):
    """
    Synthetic DB로 파편형/결합형/오파싱/미허용 단위 집계 정확성 검증.
    알려진 행 삽입 후 run_report 결과와 대조.
    """
    BASE = {"연도": 2026, "월": 4, "책명": "TEST", "지역": "서울", "가격": 10000}
    rows = [
        {**BASE, "분류": "토목", "품목명": "이형철근", "단위": "M/T"},  # 정상
        {**BASE, "분류": "토목", "품목명": "시멘트", "단위": "포"},  # 정상
        {**BASE, "분류": "토목", "품목명": "레미콘", "단위": "㎥"},  # 정상
        {**BASE, "분류": "토목", "품목명": "이형", "단위": "M/T"},  # 파편형 (2글자)
        {**BASE, "분류": "공사비", "품목명": "보통인부", "단위": "인"},  # 정상
        {**BASE, "분류": "공사비", "품목명": "소계합계이상", "단위": "인"},  # 오파싱 (소계 포함)
        {**BASE, "분류": "조경", "품목명": "잔디초원", "단위": ""},  # 단위 공백
        {**BASE, "분류": "기계", "품목명": "데스크탑", "단위": "대"},  # 정상
        {**BASE, "분류": "기계", "품목명": "보통인부특별인부", "단위": "인"},  # 결합형 패턴
        {**BASE, "분류": "토목", "품목명": "정상품목", "단위": "XX미허용"},  # 미허용 단위
    ]

    tmp = make_temp_db(rows)
    try:
        d = m_report.run_report(tmp)
    finally:
        Path(tmp).unlink()

    fr = d["파편형품목"]
    frag = fr["건수_구정의"]  # expect 1 ("이형")
    combo = d["결합형품목"]["패턴매칭건수"]  # expect 1 ("보통인부특별인부")
    oprs = d["오파싱키워드"]["건수"]  # expect 1 ("소계합계이상")
    unk = d["미허용단위"]["건수"]  # expect 1 ("XX미허용")
    blank = d["단위공백"]["건수"]  # expect 1 ("잔디초원")
    jyo_blank = d["분류별단위공백"]["조경"]["공백건수"]  # expect 1

    ok = frag == 1 and combo == 1 and oprs == 1 and unk == 1 and blank == 1 and jyo_blank == 1
    result = "PASS" if ok else "FAIL"
    print("\n[TEST 14] 집계 정확성 (synthetic DB)")
    print(f"  파편형 건수(구정의): {frag}  (expect 1)")
    print(f"  결합형 건수: {combo}  (expect 1)")
    print(f"  오파싱 건수: {oprs}  (expect 1)")
    print(f"  미허용 단위: {unk}  (expect 1)")
    print(f"  단위 공백  : {blank}  (expect 1)")
    print(f"  조경 공백건수: {jyo_blank}  (expect 1)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_format_report_sections(m_report):
    """
    format_report 출력에 필수 섹션이 모두 포함되는지 확인.
    기존 파싱 테스트는 변경 없이 통과하는지 smoke 확인.
    """
    BASE = {"연도": 2026, "월": 4, "책명": "T", "지역": "서울", "가격": 50000}
    rows = [
        {**BASE, "분류": "토목", "품목명": "철근", "단위": "M/T"},
        {**BASE, "분류": "공사비", "품목명": "보통인부", "단위": "인"},
        {**BASE, "분류": "조경", "품목명": "잔디", "단위": "㎡"},
        {**BASE, "분류": "기계", "품목명": "데스크탑", "단위": "대"},
    ]
    tmp = make_temp_db(rows)
    try:
        d = m_report.run_report(tmp)
        txt = m_report.format_report(d)
    finally:
        Path(tmp).unlink()

    required_sections = [
        "[전체 수집]",
        "[분류별 건수",
        "[단위 품질]",
        "[미허용 단위",
        "[오파싱 키워드",
        "[파편형 품목 분류]",
        "[결합형 품목]",
        "[저단가 레코드",
        "[짧은 품목명",
    ]
    missing = [s for s in required_sections if s not in txt]

    ok = not missing and len(txt) > 200
    result = "PASS" if ok else "FAIL"
    print("\n[TEST 15] format_report 섹션 구조")
    print(f"  누락 섹션: {missing if missing else '없음'}")
    print(f"  출력 길이: {len(txt)}자  (기준 >200)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_fragment_classification(m_report):
    """
    파편형 3단계 분류 정확성 검증.
    - unit_as_item: UNIT_SET 멤버 → 단위-품목 혼동으로 분류
    - modifier_frag: 한정어/색상어 → 한정어형 파편으로 분류
    - normal_short: 업계 약어 → 정상 짧은 용어로 분류
    """
    cf = m_report.classify_fragment

    # unit_as_item 확인
    assert cf("개소") == "unit_as_item", "개소는 UNIT_SET 멤버 → unit_as_item"
    assert cf("대") == "unit_as_item", "대는 UNIT_SET 멤버 → unit_as_item"

    # modifier_frag 확인
    assert cf("보통") == "modifier_frag", "보통(보통인부 파편) → modifier_frag"
    assert cf("이하") == "modifier_frag", "이하(수치 한정어) → modifier_frag"
    assert cf("갈색") == "modifier_frag", "갈색(색상어) → modifier_frag"
    assert cf("회색") == "modifier_frag", "회색(색상어) → modifier_frag"

    # normal_short 확인 (업계 정상 약어)
    assert cf("경간") == "normal_short", "경간(교량 스팬) → normal_short"
    assert cf("용접") == "normal_short", "용접(공정 용어) → normal_short"
    assert cf("강판") == "normal_short", "강판(자재) → normal_short"

    result = "PASS"
    print("\n[TEST 16] 파편형 3단계 분류 정확성")
    print("  unit_as_item: 개소, 대 ✓")
    print("  modifier_frag: 보통, 이하, 갈색, 회색 ✓")
    print("  normal_short: 경간, 용접, 강판 ✓")
    print(f"  결과: {result}")
    return True


def test_runtime_stats_param(m):
    """
    parse_page에 stats=None 파라미터 추가 후 동작 검증.
    1) stats=None (기본값) 으로 호출해도 정상 동작
    2) stats dict 전달 시 total_pages 카운터 증가
    """
    # 케이스 1: stats=None, 기존 인터페이스 유지
    PDF = PDF_BASE / "2026년04월_종합물가정보_토목.pdf"
    if not PDF.exists():
        print("\n[TEST 17] 런타임 stats 파라미터 — PDF 없음, SKIP")
        return True

    import inspect

    sig = inspect.signature(m.parse_page)
    has_stats_param = "stats" in sig.parameters
    stats_default_none = sig.parameters.get("stats") and sig.parameters["stats"].default is None

    # 케이스 2: stats dict 전달
    test_stats = dict.fromkeys(m.RT_STATS_SCHEMA, 0)
    pdf = fitz.open(str(PDF))
    m.parse_page(pdf[0], META_토목, stats=test_stats)
    m.parse_page(pdf[1], META_토목, stats=test_stats)
    pdf.close()

    ok = (
        has_stats_param
        and stats_default_none
        and test_stats["total_pages"] == 2
        and test_stats["price_pages"] >= 0
    )  # 가격 페이지 0 이상
    result = "PASS" if ok else "FAIL"
    print("\n[TEST 17] parse_page stats 파라미터")
    print(f"  stats 파라미터 존재: {has_stats_param}  (기준 True)")
    print(f"  기본값=None: {stats_default_none}  (기준 True)")
    print(f"  total_pages 카운터 (2페이지): {test_stats['total_pages']}  (기준 2)")
    print(f"  price_pages 카운터: {test_stats['price_pages']}")
    print(f"  결과: {result}")
    return result == "PASS"


def test_report_runtime_integration(m_report):
    """
    품질 리포트가 runtime_stats.json을 읽어 런타임통계 키를 반영하는지 확인.
    임시 JSON 파일로 테스트.
    """
    import json
    import tempfile

    # 임시 runtime_stats.json 생성
    fake_stats = {
        "total_pages": 500,
        "price_pages": 400,
        "region_header_pages": 300,
        "stage_header_pages": 80,
        "ilwidaega_pages": 20,
        "no_header_pages": 100,
        "unit_x_none_pages": 6,
        "paren_header_fallback": 6,
    }
    fd, tmp_rt = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        Path(tmp_rt).write_text(json.dumps(fake_stats), encoding="utf-8")

        BASE = {"연도": 2026, "월": 4, "책명": "T", "지역": "서울", "가격": 50000}
        rows = [{**BASE, "분류": "토목", "품목명": "철근", "단위": "M/T"}]
        tmp_db = make_temp_db(rows)
        try:
            d = m_report.run_report(tmp_db, rt_stats_path=Path(tmp_rt))
        finally:
            Path(tmp_db).unlink()
    finally:
        Path(tmp_rt).unlink()

    rt = d.get("런타임통계", {})
    ok = (
        rt.get("total_pages") == 500
        and rt.get("unit_x_none_pages") == 6
        and rt.get("paren_header_fallback") == 6
    )
    result = "PASS" if ok else "FAIL"
    print("\n[TEST 18] 리포트 런타임 로그 연계")
    print(f"  total_pages 반영: {rt.get('total_pages')}  (expect 500)")
    print(f"  unit_x_none_pages: {rt.get('unit_x_none_pages')}  (expect 6)")
    print(f"  paren_header_fallback: {rt.get('paren_header_fallback')}  (expect 6)")
    print(f"  결과: {result}")
    return result == "PASS"


def test_normal_short_excluded(m_report):
    """
    정상 짧은 품목("경간", "용접" 등)이 진성 파편형에서 제외되고
    확실한 파편형("보통", "개소")은 진성 파편형에 포함되는지 확인.
    Synthetic DB로 검증.
    """
    BASE = {"연도": 2026, "월": 4, "책명": "T", "지역": "서울", "가격": 50000}
    rows = [
        {**BASE, "분류": "토목", "품목명": "경간", "단위": "m"},  # normal_short
        {**BASE, "분류": "토목", "품목명": "용접", "단위": "개"},  # normal_short
        {**BASE, "분류": "공통", "품목명": "개소", "단위": "조"},  # unit_as_item
        {**BASE, "분류": "공통", "품목명": "보통", "단위": ""},  # modifier_frag
        {**BASE, "분류": "공통", "품목명": "이하", "단위": "개"},  # modifier_frag
    ]
    tmp = make_temp_db(rows)
    try:
        d = m_report.run_report(tmp)
    finally:
        Path(tmp).unlink()

    fr = d["파편형품목"]
    old_total = fr["건수_구정의"]  # 5 (전부 ≤2글자)
    true_total = fr["진성파편형건수"]  # 3 (개소+보통+이하)
    norm_total = fr["정상짧은품목_건수"]  # 2 (경간+용접)
    unit_cnt = fr["unit_as_item_건수"]  # 1 (개소)
    mod_cnt = fr["modifier_frag_건수"]  # 2 (보통+이하)

    ok = old_total == 5 and true_total == 3 and norm_total == 2 and unit_cnt == 1 and mod_cnt == 2
    result = "PASS" if ok else "FAIL"
    print("\n[TEST 19] 정상 짧은 품목 제외 / 파편형 분류")
    print(f"  구정의 전체(≤2글자): {old_total}  (expect 5)")
    print(f"  진성 파편형        : {true_total}  (expect 3)")
    print(f"  정상 짧은 품목     : {norm_total}  (expect 2,  경간·용접)")
    print(f"  unit_as_item       : {unit_cnt}  (expect 1,  개소)")
    print(f"  modifier_frag      : {mod_cnt}  (expect 2,  보통·이하)")
    print(f"  결과: {result}")
    return result == "PASS"


def main():
    parser_path = sys.argv[1] if len(sys.argv) > 1 else "/home/ubuntu/kpi_parse.py"
    m = load_parser(parser_path)
    print(f"파서 경로: {parser_path}")
    print("=" * 60)

    results = []
    results.append(test_unit_col_boundary(m))
    results.append(test_ditto_unit_inheritance(m))
    results.append(test_ilwidaega_parsing(m))
    results.append(test_spec_price_isolation(m))
    results.append(test_ilwidaega_unit_recognition(m))
    results.append(test_ilwidaega_item_fragment(m))
    results.append(test_jyogyeong_unit_rate(m))
    results.append(test_giyye_multi_section(m))
    results.append(test_unit_set_no_contamination(m))
    results.append(test_paren_header_func(m))
    results.append(test_giyye_paren_unit_effect(m))
    results.append(test_paren_unit_no_side_effect(m))

    # 품질 리포트 테스트 (TEST 13~15, 16~19)
    qr_path = sys.argv[2] if len(sys.argv) > 2 else "/home/ubuntu/kpi_quality_report.py"
    if Path(qr_path).exists():
        mr = load_quality_report(qr_path)
        results.append(test_report_structure(mr))
        results.append(test_report_aggregate_accuracy(mr))
        results.append(test_format_report_sections(mr))
        results.append(test_fragment_classification(mr))
        results.append(test_runtime_stats_param(m))
        results.append(test_report_runtime_integration(mr))
        results.append(test_normal_short_excluded(mr))
    else:
        print(f"\n[TEST 13~15] 품질 리포트 모듈 없음 ({qr_path}), SKIP")

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"최종: {passed}/{total} PASS")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
