"""
kpi.or.kr 종합물가정보 PDF 파서
- 대상: 종합물가정보 (지역별 가격 테이블)
- 출력: ~/Downloads/kpi_pdf/result/kpi_prices.db (SQLite) + kpi_prices.csv
- 방식: PyMuPDF dict(span) 기반 좌표 매핑 테이블 파싱
"""

import csv
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

import fitz

PDF_DIR = Path.home() / "Downloads/kpi_pdf"
OUT_DIR = Path.home() / "Downloads/kpi_pdf/result"
DB_PATH = OUT_DIR / "kpi_prices.db"
CSV_PATH = OUT_DIR / "kpi_prices.csv"

REGIONS = {"서울", "인천", "수원", "부산", "대구", "대전", "광주", "전주", "강원", "제주"}
PRICE_PAT = re.compile(r"^\d[\d,]+$")
FILE_PAT = re.compile(r"(\d{4})년(\d{2})월_(.+?)_(.+?)\.pdf$")
DITTO = {"〃", "″", "//"}
UNIT_SET = {
    "M/T",
    "m",
    "개",
    "㎡",
    "㎥",
    "㎏",
    "본",
    "롤",
    "장",
    "매",
    "EA",
    "SET",
    "Set",
    "TON",
    "KG",
    "L",
    "ℓ",
    "개소",
    "식",
    "대",
    "조",
    "㎜",
    "m2",
    "m3",
    "포",
    "톤",
}
# 공사비(일위대가) 전용 단위 — 단위 컬럼 위치(±20px)에서만 판정
ILWI_EXTRA_UNITS = {"hr", "인"}
KOREAN_RE = re.compile(r"[가-힣]{2,}")
KOREAN_FIRST_RE = re.compile(r"^[가-힣]")
# 규격·치수 전용 한글 접두어 (품목명으로 쓰지 않음)
SPEC_PREFIXES = (
    "외경",
    "내경",
    "두께",
    "직경",
    "관경",
    "파경",
    "호칭경",
    "규격",
    "길이",
    "폭",
    "높이",
    "두께",
    "반경",
    "반지름",
)


# ── 텍스트 정규화 ─────────────────────────────────────────────────────────────


def norm(s: str) -> str:
    s = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", s)  # 제어문자 제거
    s = re.sub(r"\s+", " ", s).strip()  # 공백 통합
    return s


def norm_region(s: str) -> str:
    """'서       울' → '서울'"""
    return re.sub(r"\s+", "", s)


def parse_price(s: str):
    v = int(s.replace(",", ""))
    return v if 500 < v < 5_000_000_000 else None


def has_korean(s: str) -> bool:
    return bool(KOREAN_RE.search(s))


def is_number_only(s: str) -> bool:
    return bool(re.match(r"^[\d.,×xX/㎜㎡㎥㎏%~@#ØΦ()\-]+$", s))


# ── span → 행 그룹 ───────────────────────────────────────────────────────────


def page_spans(page):
    """→ [(y, x, text)]"""
    out = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            y = round(line["bbox"][1])
            for span in line["spans"]:
                t = norm(span["text"])
                if t:
                    out.append((y, span["origin"][0], t))
    return out


def group_rows(spans, tol=5):
    rows: dict = defaultdict(list)
    for y, x, t in spans:
        rows[round(y / tol) * tol].append((x, t))
    return {k: sorted(v) for k, v in rows.items()}


# ── 컬럼 맵 탐지 ─────────────────────────────────────────────────────────────


def _find_stage_xs(y, sorted_rows) -> dict:
    """헤더 아래 35px에서 ①②③ 행 탐색."""
    stage_xs = {}
    for y2, row2 in sorted_rows:
        if not (y < y2 <= y + 40):
            continue
        for x2, t2 in row2:
            if t2 in ("①", "②", "③"):
                stage_xs[x2] = t2
    return stage_xs


def _assign_stage_to_region(stage_xs: dict, region_xs: dict) -> dict:
    """stage_x → 가장 가까운 지역 (±40px)."""
    sorted_rg = sorted(region_xs.items())
    rg_count: dict = defaultdict(int)
    col_map: dict = {}

    for sx in sorted(stage_xs):
        candidates = [(abs(rx - sx), rx, rn) for rx, rn in sorted_rg if abs(rx - sx) < 60]
        if not candidates:
            continue
        _, _, rn = min(candidates)
        cnt = rg_count[rn]
        if cnt == 0:
            label = rn
        else:
            # 이미 할당된 항목을 ①로 소급
            label = f"{rn}②"
            for old_sx in list(col_map):
                if col_map[old_sx] == rn:
                    col_map[old_sx] = f"{rn}①"
        col_map[sx] = label
        rg_count[rn] += 1

    return col_map


def detect_region_header(sorted_rows):
    """
    지역명 헤더 행 탐색.
    → (header_y, col_map {stage_x: 지역명}) or None
    """
    for y, row in sorted_rows:
        region_xs = {}
        for x, t in row:
            r = norm_region(t)
            if r in REGIONS:
                region_xs[x] = r
        if len(region_xs) < 3:
            continue

        stage_xs = _find_stage_xs(y, sorted_rows)

        if not stage_xs:
            # stage 없으면 지역 X 직접 사용
            return y, dict(region_xs)

        return y, _assign_stage_to_region(stage_xs, region_xs)

    return None


def nearest_col(x, col_map, tol=30):
    if not col_map:
        return None
    bx = min(col_map, key=lambda cx: abs(cx - x))
    return col_map[bx] if abs(bx - x) <= tol else None


# ── 단위 헤더 x 좌표 탐지 ────────────────────────────────────────────────────


def _find_wi_matching_dan(sorted_rows, around_y, dan_xs):
    """'단' 바로 아래 행(+20px 이내)에 '위'가 같은 x에 있으면 그 x 반환."""
    for y, row in sorted_rows:
        if not (around_y - 30 <= y <= around_y + 90):
            continue
        for x, t in row:
            if t.replace(" ", "") == "위":
                for dx, dy in dan_xs.items():
                    if abs(dx - x) <= 10 and 0 < y - dy <= 20:
                        return dx
    return None


def find_unit_col_x(sorted_rows, around_y):
    """헤더 행 근방에서 '단위' 텍스트의 x 좌표 반환. 없으면 None.
    '단'과 '위'가 인접 두 행에 분리된 경우도 인식한다.
    """
    dan_xs = {}  # x -> y, '단' 글자 위치 수집
    for y, row in sorted_rows:
        if not (around_y - 30 <= y <= around_y + 70):
            continue
        for x, t in row:
            tn = t.replace(" ", "")
            if tn == "단위":
                return x
            if tn == "단":
                dan_xs[x] = y
    return _find_wi_matching_dan(sorted_rows, around_y, dan_xs)


# ── (단위 : XXX) 괄호 헤더에서 단위 추출 ─────────────────────────────────────

_UNIT_PAREN_RE = re.compile(r"[（(]\s*단\s*위\s*[：:]\s*([^)）]+)[)）]")


def find_unit_from_paren_header(sorted_rows, around_y):
    """'(단위 : 대)' 형태 헤더에서 단위 추출. unit_x=None인 경우 보조 사용."""
    for y, row in sorted_rows:
        if not (around_y - 60 <= y <= around_y + 20):
            continue
        for _x, t in row:
            m = _UNIT_PAREN_RE.search(t)
            if m:
                for u in re.split(r"[,，\s]+", m.group(1).strip()):
                    u = u.strip()
                    if u in UNIT_SET:
                        return u
    return None


# ── price_x_min 보정: 단위 열이 경계 우측으로 밀리는 것 방지 ─────────────────


def calc_price_x_min(col_map_min_x, unit_col_x):
    """
    col_map 최솟값 기반 기본 경계를 계산하되,
    단위 헤더가 경계 안쪽에 있으면 단위 열 포함되도록 경계를 우측으로 이동.
    단위 헤더가 col_map 최솟값보다 우측이면 다른 컬럼의 헤더로 보고 무시한다.
    """
    base = col_map_min_x - 40
    if (
        unit_col_x is not None
        and unit_col_x < col_map_min_x  # 가격 컬럼 왼쪽에 있어야 유효
        and unit_col_x + 20 > base
    ):
        return unit_col_x + 20
    return base


# ── 일위대가형 헤더 탐지 ──────────────────────────────────────────────────────


def detect_ilwidaega_header(sorted_rows):
    """
    일위대가형 테이블 탐지: '단가' + '단위' 헤더가 같은 행에 존재하고
    지역 헤더(서울/부산 등)가 없는 경우.
    → (header_y, danwon_x, unit_x) or None
    """
    for y, row in sorted_rows:
        texts = {t.replace(" ", "") for _, t in row}
        if "단가" not in texts and "단  가" not in " ".join(t for _, t in row).replace("  ", ""):
            continue
        if "단위" not in texts:
            continue
        # 지역명이 같은 행에 있으면 제외
        if any(t.replace(" ", "") in REGIONS for _, t in row):
            continue
        danwon_x = next((x for x, t in row if "단가" in t.replace(" ", "")), None)
        unit_x = next((x for x, t in row if t.replace(" ", "") == "단위"), None)
        if danwon_x is not None and unit_x is not None:
            return y, danwon_x, unit_x
    return None


# ── 품목명 추출 ───────────────────────────────────────────────────────────────


def _detect_unit(tokens, prev_unit):
    """단위 탐지: UNIT_SET 정확 매칭 우선, 〃/ditto는 prev_unit 유지 신호."""
    for t in reversed(tokens):
        tn = norm_region(t)  # 공백 제거
        if tn in DITTO:
            # 〃가 단위 위치에 있으면 prev_unit 상속
            break
        if tn in UNIT_SET:
            return tn
    return prev_unit


def _is_item_name_candidate(t: str) -> bool:
    if t in DITTO:
        return False
    if "," in t and any(c.isdigit() for c in t):
        return False  # 가격 문자열
    if is_number_only(t):
        return False
    if t.startswith("("):
        return False  # 괄호형 주석/규격 상세
    if not KOREAN_FIRST_RE.match(t):
        return False  # 한글 시작이 아니면 제외 (숫자·영문·특수문자 시작)
    if not has_korean(t):
        return False
    if len(norm_region(t)) < 2:
        return False  # 한 글자 잔재
    # 규격 전용 접두어로 시작하는 경우 품목명 아님
    return not t.startswith(SPEC_PREFIXES)


def extract_item(tokens, prev_item, prev_unit):
    """
    왼쪽 컬럼 토큰에서 (품목명, 단위) 추출.
    의미 있는 한글 토큰이 없으면 이전 값 유지.
    """
    unit = _detect_unit(tokens, prev_unit)

    # 품목명 후보: 한글로 시작, 2자 이상, 가격/규격 토큰 제외
    candidates = [t for t in tokens if _is_item_name_candidate(t)]

    if not candidates:
        return prev_item, unit

    # 짧은 연속 토큰들은 합치기 (예: "고장력" + "철근" → "고장력철근")
    parts = [candidates[0]]
    for c in candidates[1:]:
        if len(c) <= 6 and not c.startswith("("):
            parts.append(c)
        else:
            break
    item = "".join(parts)[:60]
    return item, unit


# ── 세로 분산 품목명 사전 스캔 ───────────────────────────────────────────────


def scan_vertical_names(sorted_rows) -> list[tuple]:
    """
    왼쪽 여백(x<82)에 한 글자씩 세로로 배치된 품목명 클러스터를 탐지.
    → [(start_y, end_y, name), ...]
    """
    # 단일 한글 글자가 x<82에 있는 행 수집
    char_rows = []  # [(y, chars_joined)]
    for y, row in sorted_rows:
        chars = [t for x, t in row if x < 82 and len(t) == 1 and "가" <= t <= "힣"]
        if chars:
            char_rows.append((y, "".join(chars)))

    if not char_rows:
        return []

    # 연속 행(15px 이내) 클러스터링
    clusters = []
    cur_start, cur_name, cur_last_y = char_rows[0][0], char_rows[0][1], char_rows[0][0]
    for y, chars in char_rows[1:]:
        if y - cur_last_y <= 20:
            cur_name += chars
            cur_last_y = y
        else:
            if len(cur_name) >= 2:
                clusters.append((cur_start, cur_last_y + 15, cur_name))
            cur_start, cur_name, cur_last_y = y, chars, y
    if len(cur_name) >= 2:
        clusters.append((cur_start, cur_last_y + 15, cur_name))

    return clusters


def lookup_vertical_name(y: float, clusters: list[tuple]) -> str:
    """price row Y에 해당하는 수직 품목명 반환."""
    for start_y, end_y, name in clusters:
        if start_y - 5 <= y <= end_y + 60:  # 아래로 여유 60px
            return name
    return ""


# ── 페이지 파싱 ──────────────────────────────────────────────────────────────


def parse_page(page, meta, stats=None):
    spans = page_spans(page)
    if stats is not None:
        stats["total_pages"] += 1
    if not spans:
        return []

    raw_rows = group_rows(spans, tol=5)
    sorted_rows = sorted(raw_rows.items())

    # 가격 페이지 빠른 체크 (6자리 이상 숫자 3개 이상)
    all_texts = [t for row in raw_rows.values() for _, t in row]
    if sum(1 for t in all_texts if PRICE_PAT.match(t) and len(t) > 5) < 3:
        return []

    if stats is not None:
        stats["price_pages"] += 1

    res = detect_region_header(sorted_rows)
    rows_out = []

    # 수직 분산 품목명 사전 스캔
    vert_clusters = scan_vertical_names(sorted_rows)

    if res:
        if stats is not None:
            stats["region_header_pages"] += 1
        header_y, col_map = res
        # price_x_min: 단위 헤더 x 기준으로 경계 보정 (단위 열이 경계 우측으로 밀리는 것 방지)
        unit_col_x = find_unit_col_x(sorted_rows, header_y)
        price_x_min = calc_price_x_min(min(col_map), unit_col_x)

        prev_item = prev_unit = ""
        for y, row in sorted_rows:
            if y <= header_y + 15:
                continue

            left = [(x, t) for x, t in row if x < price_x_min]
            right = [(x, t) for x, t in row if x >= price_x_min]
            # 가격/규격 혼입 차단: 규격 열 좌표(x<160)의 짧은 숫자는 가격 후보 제외
            prices = [
                (x, t)
                for x, t in right
                if PRICE_PAT.match(t)
                and len(t) > 4
                and not (x < 160 and len(t.replace(",", "")) <= 5)
            ]
            if not prices:
                continue

            left_toks = [t for _, t in left]
            explicit_item, new_unit = extract_item(left_toks, prev_item, prev_unit)
            # 수직 품목명 클러스터 우선 사용
            vert = lookup_vertical_name(y, vert_clusters)
            if vert and len(vert) >= 2:
                prev_item = vert
            elif explicit_item:
                prev_item = explicit_item
            if new_unit:
                prev_unit = new_unit
            if not prev_item:
                continue

            for px, pt in prices:
                label = nearest_col(px, col_map)
                if not label:
                    continue
                try:
                    pv = parse_price(pt)
                except (ValueError, AttributeError):
                    continue
                if pv:
                    rows_out.append({
                        **meta,
                        "품목명": prev_item,
                        "단위": prev_unit,
                        "지역": label,
                        "가격": pv,
                    })

    else:
        # 비-지역 테이블: ①②③ 기반 우선, 없으면 일위대가 분기
        stage_y = None
        col_map = {}
        for y, row in sorted_rows:
            for x, t in row:
                if t in ("①", "②", "③"):
                    if stage_y is None:  # 첫 번째 ①②③만 사용 — 다중 섹션 덮어쓰기 방지
                        col_map[x] = t
                        stage_y = y
                    elif y == stage_y:  # 같은 행의 다른 ①②③은 포함
                        col_map[x] = t

        # 일위대가형 분기: ①②③가 없거나 있어도 지역 헤더가 없으면 시도
        ilwi = detect_ilwidaega_header(sorted_rows)
        if ilwi and not col_map:
            if stats is not None:
                stats["ilwidaega_pages"] += 1
            # ──── 일위대가 전용 파서 ────
            header_y, danwon_x, unit_x = ilwi
            price_x_min = unit_x + 15
            prev_item = prev_unit = ""

            for y, row in sorted_rows:
                if y <= header_y + 10:
                    continue

                left = [(x, t) for x, t in row if x < price_x_min]
                right = [(x, t) for x, t in row if x >= price_x_min]
                # 단가 열 값만 가격 후보: danwon_x 기준 ±45px 이내 정수
                prices = [
                    (x, t)
                    for x, t in right
                    if PRICE_PAT.match(t) and len(t) > 4 and abs(x - danwon_x) <= 45
                ]
                if not prices:
                    continue

                left_toks = [t for _, t in left]
                # 구분 열 경계: unit_x 왼쪽 10px (단위 토큰 제외)
                item_boundary = unit_x - 10

                # 구분 열 경계 이전 단글자 한글 수집 — x>=40 으로 좌측 구분기호 제외
                # 연속된 첫 클러스터만 사용: 간격 >50px이면 다음 품목 시작으로 판단
                _cpairs = sorted(
                    (x, t)
                    for x, t in row
                    if x >= 40 and x < item_boundary and len(t) == 1 and "가" <= t <= "힣"
                )
                if _cpairs:
                    _cluster = [_cpairs[0]]
                    for _ci in range(1, len(_cpairs)):
                        if _cpairs[_ci][0] - _cpairs[_ci - 1][0] > 120:
                            break
                        _cluster.append(_cpairs[_ci])
                    item_chars = [t for _, t in _cluster]
                else:
                    item_chars = []
                joined_chars = "".join(item_chars)

                # 소계/합계/재료비/노무비/경비 행 제외
                # — 단글자 조합(joined_chars) + 단일 스팬 토큰(left_toks) 동시 검사
                SKIP_KWDS = ("소계", "합계", "재료비", "노무비", "경비", "당단가")
                skip_text = joined_chars + " ".join(left_toks)
                if any(kw in skip_text for kw in SKIP_KWDS):
                    continue
                if any(kw in t for _, t in row for kw in ("합  계", "소  계")):
                    continue

                # 품목명: 구분 열 가로 배치 단글자 우선, 없으면 extract_item 폴백
                if len(item_chars) >= 2:
                    prev_item = joined_chars
                else:
                    explicit_item, new_unit = extract_item(left_toks, prev_item, prev_unit)
                    if explicit_item:
                        prev_item = explicit_item
                    if new_unit:
                        prev_unit = new_unit

                if not prev_item:
                    continue

                # 단위 열 직접 탐색 (unit_x 기준 ±20px)
                for x, t in sorted(row):
                    tn = t.replace(" ", "")
                    if abs(x - unit_x) <= 20:
                        if tn in UNIT_SET or tn in ILWI_EXTRA_UNITS:
                            prev_unit = tn
                        elif tn in DITTO:
                            pass  # prev_unit 유지
                        break

                for _px, pt in prices:
                    try:
                        pv = parse_price(pt)
                    except (ValueError, AttributeError):
                        continue
                    if pv:
                        rows_out.append({
                            **meta,
                            "품목명": prev_item,
                            "단위": prev_unit,
                            "지역": "단가",
                            "가격": pv,
                        })

            return rows_out

        if not col_map:
            if stats is not None:
                stats["no_header_pages"] += 1
            return []

        if stats is not None:
            stats["stage_header_pages"] += 1
        unit_col_x = find_unit_col_x(sorted_rows, stage_y) if stage_y else None
        price_x_min = calc_price_x_min(min(col_map), unit_col_x)
        # unit_col_x가 없으면 (단위 : XXX) 괄호 헤더에서 초기 단위 추출
        paren_unit = None
        if unit_col_x is None and stage_y:
            if stats is not None:
                stats["unit_x_none_pages"] += 1
            paren_unit = find_unit_from_paren_header(sorted_rows, stage_y)
            if paren_unit and stats is not None:
                stats["paren_header_fallback"] += 1
        # ①② → 기준①, 기준② 로 재매핑
        col_map = {x: f"기준{v}" if v in ("①", "②", "③") else v for x, v in col_map.items()}
        prev_item = prev_unit = ""
        if paren_unit:
            prev_unit = paren_unit

        for y, row in sorted_rows:
            if y <= stage_y:
                continue
            left = [(x, t) for x, t in row if x < price_x_min]
            right = [(x, t) for x, t in row if x >= price_x_min]
            # 가격/규격 혼입 차단
            prices = [
                (x, t)
                for x, t in right
                if PRICE_PAT.match(t)
                and len(t) > 4
                and not (x < 160 and len(t.replace(",", "")) <= 5)
            ]
            if not prices:
                continue

            left_toks = [t for _, t in left]
            # 소계/합계 행 제외 (일위대가 내부 집계 행 오파싱 방지)
            _skip_check = " ".join(left_toks)
            if any(kw in _skip_check for kw in ("소계", "합계", "재료비", "노무비", "경비")):
                continue
            prev_item, prev_unit = extract_item(left_toks, prev_item, prev_unit)
            if not prev_item:
                continue

            for px, pt in prices:
                label = nearest_col(px, col_map, tol=35) or "기준가"
                try:
                    pv = parse_price(pt)
                except (ValueError, AttributeError):
                    continue
                if pv:
                    rows_out.append({
                        **meta,
                        "품목명": prev_item,
                        "단위": prev_unit,
                        "지역": label,
                        "가격": pv,
                    })

    return rows_out


# ── PDF 파싱 ─────────────────────────────────────────────────────────────────

SKIP_BOOKS = {"생활물가뉴스", "종합적산정보"}

RT_STATS_SCHEMA = {
    "total_pages": 0,
    "price_pages": 0,
    "region_header_pages": 0,
    "stage_header_pages": 0,
    "ilwidaega_pages": 0,
    "no_header_pages": 0,
    "unit_x_none_pages": 0,
    "paren_header_fallback": 0,
}


def parse_pdf(pdf_path: Path, stats=None):
    m = FILE_PAT.match(pdf_path.name)
    if not m:
        return []
    year, month, book, section = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    if book in SKIP_BOOKS:
        return []

    meta = {"연도": year, "월": month, "책명": book, "분류": section}
    doc = fitz.open(str(pdf_path))
    rows = []
    for pi in range(doc.page_count):
        try:
            rows.extend(parse_page(doc[pi], meta, stats=stats))
        except Exception:  # ruff: ignore[blind-except] — 이 페이지만 건너뛰고 나머지 페이지 계속 파싱
            if stats is not None:
                stats["parse_crash_pages"] = stats.get("parse_crash_pages", 0) + 1
    doc.close()
    return rows


# ── DB / CSV ─────────────────────────────────────────────────────────────────


def init_db(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS prices (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        연도    INTEGER,
        월      INTEGER,
        책명    TEXT,
        분류    TEXT,
        품목명  TEXT,
        단위    TEXT,
        지역    TEXT,
        가격    INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_item ON prices(품목명, 지역, 연도, 월);
    """)
    conn.commit()


def save_db(conn, rows):
    conn.executemany(
        "INSERT INTO prices(연도,월,책명,분류,품목명,단위,지역,가격) "
        "VALUES(:연도,:월,:책명,:분류,:품목명,:단위,:지역,:가격)",
        rows,
    )
    conn.commit()


def save_csv(rows, path):
    if not rows:
        return
    fields = ["연도", "월", "책명", "분류", "품목명", "단위", "지역", "가격"]
    with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


# ── 메인 ─────────────────────────────────────────────────────────────────────


def _process_all_pdfs(pdfs: list[Path], conn, rt_stats: dict) -> list:
    all_rows = []
    for i, pdf in enumerate(pdfs, 1):
        rows = parse_pdf(pdf, stats=rt_stats)
        if rows:
            save_db(conn, rows)
            all_rows.extend(rows)
            print(f"[{i}/{len(pdfs)}] {pdf.name}: {len(rows)}행")
        else:
            print(f"[{i}/{len(pdfs)}] {pdf.name}: 스킵")
    return all_rows


def main():
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(PDF_DIR.rglob("*.pdf"))
    print(f"대상 PDF: {len(pdfs)}개")

    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)
    conn.execute("DELETE FROM prices")
    conn.commit()

    rt_stats = dict(RT_STATS_SCHEMA)
    all_rows = _process_all_pdfs(pdfs, conn, rt_stats)

    conn.close()
    save_csv(all_rows, CSV_PATH)

    # 런타임 품질 통계 저장
    rt_stats_path = OUT_DIR / "runtime_stats.json"
    import json as _json

    rt_stats_path.write_text(_json.dumps(rt_stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"런타임 통계 저장: {rt_stats_path}")

    # ── 결과 리포트 ────────────────────────────────────────────────────────
    from collections import Counter
    from datetime import datetime

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(all_rows)
    items = {r["품목명"] for r in all_rows}
    regions = {r["지역"] for r in all_rows}
    books = Counter(r["책명"] for r in all_rows)
    cats = Counter(r["분류"] for r in all_rows)
    years = sorted({r["연도"] for r in all_rows})

    skipped = [
        pdf.name for pdf in sorted(PDF_DIR.rglob("*.pdf")) if any(b in pdf.name for b in SKIP_BOOKS)
    ]

    lines = [
        "=" * 60,
        "  KPI 물가정보 PDF 파싱 결과 리포트",
        f"  생성: {now}",
        "=" * 60,
        "",
        "[수집 범위]",
        f"  대상 PDF    : {len(pdfs)}개",
        f"  스킵 PDF    : {len(skipped)}개  ({', '.join(sorted({n.split('_')[2] for n in skipped})[:5])} ...)",
        f"  파싱 연도   : {years[0]}년 ~ {years[-1]}년",
        "",
        "[추출 결과]",
        f"  총 행 수    : {total:,}행",
        f"  고유 품목   : {len(items):,}개",
        f"  지역 종류   : {len(regions)}개  {sorted(regions)}",
        "",
        "[책명별 행 수]",
    ]
    for book, cnt in books.most_common():
        lines.append(f"  {book:<20} : {cnt:>10,}행")

    lines += [
        "",
        "[분류(섹션)별 행 수 TOP 15]",
    ]
    for cat, cnt in cats.most_common(15):
        lines.append(f"  {cat:<20} : {cnt:>10,}행")

    lines += [
        "",
        "[주요 품목 가격 샘플 - 서울 2026년 4월]",
    ]
    sample_targets = [
        "고장력철근",
        "이형철근",
        "시멘트",
        "레미콘",
        "H형강",
        "형강",
        "강관",
        "합판",
        "전기동",
        "아스팔트",
    ]
    april26 = [r for r in all_rows if r["연도"] == 2026 and r["월"] == 4 and "서울" in r["지역"]]
    for tgt in sample_targets:
        hits = [r for r in april26 if tgt in r["품목명"]]
        if hits:
            r = hits[0]
            lines.append(
                f"  {r['품목명'][:25]:<25} | {r['지역']:<8} | {r['가격']:>12,}원 | {r['단위']}"
            )

    lines += [
        "",
        "[출력 파일]",
        f"  DB  : {DB_PATH}",
        f"  CSV : {CSV_PATH}",
        "=" * 60,
    ]

    report = "\n".join(lines)
    print(report)

    # 리포트 파일 저장
    report_path = OUT_DIR / f"parse_report_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n리포트 저장: {report_path}")


if __name__ == "__main__":
    main()
