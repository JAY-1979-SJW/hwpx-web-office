"""coord_table — 표 레이아웃 순수 계산(축 해석·정규화·앵커 압축·페이지네이션).

coordinate_layout.walk_table 에서 분리(모듈화). 전부 명시 인자 순수 함수 —
클로저·전역 상태 없음. geo = {"page_h", "m_top", "content_h"} (px).
read-only, 원본 무수정.
"""


def solve_axis(cells, n, key_start, key_span, key_size):
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


def expand_rowspan_content(cells, row_h, nrow):
    """rowSpan 정밀화 — 병합 셀 '내용'이 배정 행높이 합보다 크면 부족분을
    span 행들에 균등 가산. 모든 행이 단일-span 셀로 이미 확정된 경우
    solve_axis 2)가 병합 셀 요구를 무시해 줄이 셀 밖으로 밀리던 결함.
    (cellSz 가 아닌 내용 기준 — 예약 높이로 표가 부풀지 않게)"""
    for c in cells:
        if c["rowSpan"] <= 1:
            continue
        idxs = [i for i in range(c["row"], c["row"] + c["rowSpan"])
                if 0 <= i < nrow]
        if not idxs:
            continue
        # 내용 수용 하드 불변식 — 셀은 자기 내용(본문 줄)을 반드시 담는다.
        # 이전의 cellSz 상한은 병합 셀 내용이 선언높이보다 클 때 줄이 셀
        # 밖으로 밀리는 물림(문자·테두리 겹침)을 남겼다. 겹침은 페이지 수
        # 오차보다 치명적이므로 상한 없이 내용만큼 확장한다. 단 중첩표
        # 추정치(과대 가능)는 실측 줄 기반 하한(hCompact)과 병행 판단.
        need = c["hContent"] + c["mt"] * 2
        alloc = sum(row_h[i] for i in idxs)
        if need > alloc + 0.5:
            add = (need - alloc) / len(idxs)
            for i in idxs:
                row_h[i] += add
    return row_h


def normalize_declared(cells, col_w, row_h, tw, th, nrow):
    """한컴 선언 표 폭(sz)에 열 정규화(가로 드리프트 방지). 행높이는 내용
    기반이므로 선언 높이보다 작을 때만 위로 채우고, 클 때는 유지(넘침 방지).
    행은 위로 늘리지 않는다 — 한컴은 각 행을 cellSz/내용 높이 그대로
    렌더하고, 합이 선언 tbl height 보다 작으면 표가 그만큼 짧아질 뿐이다."""
    sw = sum(col_w)
    if tw > 0 and sw > 0:
        col_w = [w * tw / sw for w in col_w]
    sh = sum(row_h)
    # 선언 표높이(th)가 행합의 2/3에도 못 미치면 stale(구버전 잔존값) —
    # 무시한다. cellSz(행별 저장 실높이)가 한컴 실배치와 일치함이 다중
    # 문서 픽셀 감사로 검증됨. stale th 로 축소하면 행이 내용 밀착까지
    # 눌려 서식이 뭉개진다. th-정규화는 근소 인플레이션(≤1.5x)만 보정.
    if th > 0 and sh > 0 and sh <= th * 1.5:
        if sh > th * 1.02:
            # 과대(인플레이션) — 각 행의 "내용 최소높이"는 보장하고
            # 여유분만 비례 축소해 선언 표높이(th)로 수렴. rowSpan 분배
            # 근사가 행을 부풀려 페이지가 배로 늘던 결함의 근본 보정.
            min_need = [0.0] * nrow
            for c in cells:
                if c["rowSpan"] == 1:
                    need = min(c["hContent"] + c["mt"] * 2, c["hEff"])
                    if need > min_need[c["row"]]:
                        min_need[c["row"]] = need
            slack = [max(0.0, row_h[i] - min_need[i])
                     for i in range(nrow)]
            tslack = sum(slack)
            if tslack > 1e-6:
                k = min(1.0, (sh - th) / tslack)
                row_h = [row_h[i] - slack[i] * k for i in range(nrow)]
    return col_w, row_h


def sim_bottom(row_h, base_y, geo):
    """블록 미고려 단순 행 페이지네이션 시뮬레이션 → 표 하단 y."""
    page_h = geo["page_h"]
    m_top = geo["m_top"]
    content_h = geo["content_h"]
    cur = base_y
    for hrow in row_h:
        _pg = int(cur // page_h)
        _cbot = _pg * page_h + m_top + content_h
        if cur + hrow > _cbot + 1.0 and hrow <= content_h + 1.0:
            cur = (_pg + 1) * page_h + m_top
        cur += hrow
    return cur


def compress_to_anchor(cells, row_h, nrow, base_y, anchor_vpos, geo):
    """앵커 역산 — HWPX 는 자동흐름 페이지 나눔을 저장하지 않지만, 표 다음
    본문 문단의 vpos(페이지 상대)는 한컴이 실제 배치한 좌표다. 표가
    페이지를 넘을 때 이 앵커에서 표의 실제 총높이를 역산한다.
    압축 방식은 균일 축소가 아니라 한컴 모델(실측 일치: 줄간격 제거 +
    셀 상하여백 절반)로 — 각 행을 [원높이 ↔ 컴팩트높이(글리프 합+여백/2)]
    사이에서 α 보간한다. 글리프 크기는 유지되므로 줄이 셀 경계를 물지
    않는다. 단일페이지 표는 건드리지 않는다. 반환: (row_h, alpha)."""
    page_h = geo["page_h"]
    m_top = geo["m_top"]
    content_h = geo["content_h"]
    alpha = 0.0
    if anchor_vpos is None or page_h <= 0:
        return row_h, alpha
    sh_now = sum(row_h)
    start_pg = int(base_y // page_h)
    end_pg = int(sim_bottom(row_h, base_y, geo) // page_h)
    if not (end_pg > start_pg and sh_now > 0):   # 페이지 넘는 표만
        return row_h, alpha
    comp = [0.0] * nrow                # 행별 컴팩트 하한
    for c in cells:
        if c["rowSpan"] == 1:
            v = c["hCompact"] + c["mt"]   # 여백 2mt → mt(절반)
            if v > comp[c["row"]]:
                comp[c["row"]] = v
    for i in range(nrow):
        if comp[i] <= 0 or comp[i] > row_h[i]:
            comp[i] = row_h[i]
    sh_comp = sum(comp)
    for p_end in range(start_pg, end_pg + 1):
        anchor_abs = p_end * page_h + m_top + anchor_vpos
        if anchor_abs <= base_y + 1:
            continue
        tgt = 0.0                  # 목표높이 = 페이지별 가용합
        for pg in range(start_pg, p_end + 1):
            top = base_y if pg == start_pg else pg * page_h + m_top
            bot = (anchor_abs - 2 if pg == p_end
                   else pg * page_h + m_top + content_h)
            if bot > top:
                tgt += bot - top
        if tgt < sh_comp * 0.96:
            continue    # 컴팩트로도 안 들어감 → 다음 페이지 후보
        if tgt >= sh_now:
            break       # 압축 불필요(이미 앵커 안)
        denom = sh_now - sh_comp
        a = (sh_now - tgt) / denom if denom > 1e-6 else 1.0
        a = min(1.0, max(0.0, a))
        # 행이 페이지 경계를 통째로 넘으며 생기는 슬랙 보정 —
        # 재시뮬레이션으로 하단이 앵커 안에 들 때까지 α 미세 상향.
        for _ in range(4):
            rh = [row_h[i] - a * (row_h[i] - comp[i])
                  for i in range(nrow)]
            excess = sim_bottom(rh, base_y, geo) - (anchor_abs - 2)
            if excess <= 1.0 or a >= 1.0:
                break
            a = min(1.0, a + excess / max(denom, 1e-6))
        row_h = [row_h[i] - a * (row_h[i] - comp[i])
                 for i in range(nrow)]
        alpha = a
        # 컴팩트 하한(α=1)로도 수 px 초과하면 잔여를 행당 절대
        # 상한 2.5px(렌더러 clip-margin 3px 이내 = 시각 무해)로
        # 균등 분배해 깎는다. 비례 축소는 대형(다줄) 행에서 더
        # 많이 깎아 줄이 셀 밖으로 밀리므로 쓰지 않는다.
        if a >= 1.0:
            removed = [0.0] * nrow
            for _ in range(4):
                excess = sim_bottom(row_h, base_y, geo) - (anchor_abs - 2)
                if excess <= 1.0:
                    break
                budget = [max(0.0, 2.5 - removed[i])
                          for i in range(nrow)]
                tot_b = sum(budget)
                if tot_b <= 0.5:
                    break   # 상한 소진 — 잔여는 수용(과깎기 금지)
                kk = min(1.0, excess / tot_b)
                for i in range(nrow):
                    cut = budget[i] * kk
                    row_h[i] -= cut
                    removed[i] += cut
        break
    return row_h, alpha


def paginate_rows(cells, row_h, nrow, base_y, geo):
    """규격 기반 행 페이지네이션 → (row_abs, row_bot).

    - 행이 콘텐츠 영역(m_top ~ m_top+content_h)을 넘고 한 페이지에 들어가면
      통째로 다음 페이지 콘텐츠 상단으로 이동(한컴: 행은 페이지에 걸쳐
      쪼개지지 않는다). 행 단위로만 점프한다 — 병합(rowSpan) 셀이 점프에
      걸치면 방출부가 박스를 페이지별 조각으로 분할해 그린다(한컴의 병합 셀
      페이지 분할 재현; 블록 통째 이월은 페이지 낭비 슬랙으로 표 하단이
      앵커를 넘는 결함이 있어 폐기).
    - keep-with-table: 표 머리 몇 행(누적 12% 미만)만 남기고 본체가 점프하면
      표 전체를 다음 페이지 상단으로(서식 마커·제목 행이 표와 분리 방지).
    - row_bot 은 페이지 갭 미포함 행 하단 — 셀 박스 높이가 점프 갭을
      흡수하면 안 된다(앞 행 박스가 페이지 하단까지 늘어나는 결함 방지).
    """
    page_h = geo["page_h"]
    m_top = geo["m_top"]
    content_h = geo["content_h"]
    def _paginate(start_y):
        ra = [start_y] * (nrow + 1)
        cur = start_y
        first_jump_at = None
        placed = 0.0
        for i in range(nrow):
            if page_h > 0:
                _pg = int(cur // page_h)
                _cbot = _pg * page_h + m_top + content_h
                if (cur + row_h[i] > _cbot + 1.0
                        and row_h[i] <= content_h + 1.0):
                    if first_jump_at is None:
                        first_jump_at = placed
                    cur = (_pg + 1) * page_h + m_top
            ra[i] = cur
            cur += row_h[i]
            placed += row_h[i]
        ra[nrow] = cur
        return ra, first_jump_at

    row_abs, _fj = _paginate(base_y)
    if (_fj is not None and page_h > 0
            and _fj < content_h * 0.12
            and _fj > 0):
        _next_top = (int(base_y // page_h) + 1) * page_h + m_top
        if _next_top > base_y:
            row_abs, _ = _paginate(_next_top)
    row_bot = [row_abs[i] + row_h[i] for i in range(nrow)]
    return row_abs, row_bot


def col_rank_map(cells):
    """행별 colAddr → 순차 col 인덱스 — 문서모델(ro_view)은 col 을 행 내
    순차 번호(0,1,2…)로 매기므로 raw colAddr 갭(병합)을 압축해 맞춘다."""
    col_rank = {}
    row_cols = {}
    for c in cells:
        row_cols.setdefault(c["row"], set()).add(c["col"])
    for r, cs in row_cols.items():
        for rank, ca in enumerate(sorted(cs)):
            col_rank[(r, ca)] = rank
    return col_rank
