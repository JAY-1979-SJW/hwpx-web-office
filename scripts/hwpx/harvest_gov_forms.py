"""공공기관 서식 통합 수집기 — 기관별 다운로드 배관을 설정으로 꽂는다.

공공기관은 통합 서식창구가 없어 기관마다 자체 사이트에서 배포한다.
정찰로 규명한 다운로드 메커니즘(대부분 list-driven)을 기관별 collector 로 구현.
공통(다운로드·Content-Disposition 파일명·SHA256 중복제거·재개·예의지연)은 재사용.

지원 기관(정찰 CRACKED):
  nhis   국민건강보험공단  — 목록1회(articleLimit) 내 다운로드링크 직접 노출, 무인증
  nps    국민연금공단      — 상세페이지(tmpltDataSn) 순회 → fileDown.do, 무인증
  comwel 근로복지공단      — 목록 페이지네이션 → download.jsp?attach_no, 세션쿠키+Referer
  kogas  한국가스공사      — 게시판 목록 → /mgr/fileDownload.do, 세션쿠키+Referer

공개적으로 내려받도록 제공되는 빈 서식 템플릿만 대상. rate-limit 준수.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import http.cookiejar
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIB = PROJECT_ROOT / "data" / "drafts" / "form_library"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
HWP_OLE = bytes.fromhex("D0CF11E0A1B11AE1")


def _log(m): print(m, flush=True)


def _safe(name: str, n: int = 80) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣._()-]+", "_", name or "").strip("_")
    return s[:n] or "form"


def _fname_from_cd(cd: str) -> str:
    if not cd:
        return ""
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", cd, re.I)
    if not m:
        return ""
    raw = m.group(1)
    try:
        name = urllib.parse.unquote(raw)
    except Exception:
        name = raw
    # http.client 는 헤더를 latin-1 로 디코드한다. 서버가 UTF-8 파일명을
    # 퍼센트인코딩 없이 그대로 보내면 모지바케가 되므로 되돌린다.
    if not re.search(r"[가-힣]", name):
        try:
            fixed = name.encode("latin-1").decode("utf-8")
            if re.search(r"[가-힣]", fixed):
                name = fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name


def make_opener(referer: str = "") -> urllib.request.OpenerDirector:
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    hdrs = [("User-Agent", UA), ("Accept", "*/*")]
    if referer:
        hdrs.append(("Referer", referer))
    op.addheaders = hdrs
    return op


def http_get(opener, url: str, retries: int = 3):
    for attempt in range(retries):
        try:
            with opener.open(url, timeout=45) as r:
                return r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code in (404, 500, 403):
                return None, {}
            time.sleep(1.2 * (attempt + 1))
        except Exception:
            time.sleep(1.2 * (attempt + 1))
    return None, {}


# ── 기관별 링크 생성기(다운로드 URL 목록) ────────────────────────────

def links_nhis(opener) -> list[str]:
    """건보: articleLimit 큰 값 1회 → 목록 HTML 내 mode=download 링크 전량."""
    base = "https://www.nhis.or.kr/nhis/minwon/wbhaba03900m01.do"
    html, _ = http_get(opener, base + "?articleLimit=2000&article.offset=0")
    if not html:
        return []
    txt = html.decode("utf-8", "replace")
    pairs = re.findall(r"mode=download&(?:amp;)?articleNo=(\d+)&(?:amp;)?attachNo=(\d+)", txt)
    seen, urls = set(), []
    for a, b in pairs:
        k = (a, b)
        if k in seen:
            continue
        seen.add(k)
        urls.append(f"{base}?mode=download&articleNo={a}&attachNo={b}")
    return urls


def links_comwel(opener, max_pages: int = 70) -> list[str]:
    """근복공단: 서식자료 목록 페이지네이션 → download.jsp?attach_no."""
    base = "https://www.comwel.or.kr"
    listurl = base + "/comwel/info/data/papr/papr_lst.jsp"
    # 세션쿠키 확보(목록 1회 방문)
    http_get(opener, listurl)
    seen, urls = set(), []
    for pg in range(1, max_pages + 1):
        html, _ = http_get(opener, f"{listurl}?pageIndex={pg}")
        if not html:
            break
        txt = html.decode("utf-8", "replace")
        ids = re.findall(r"download\.jsp\?attach_no=(\d+)", txt)
        if not ids:
            break
        new = 0
        for i in ids:
            if i in seen:
                continue
            seen.add(i); new += 1
            urls.append(f"{base}/_custom/kcom/_common/board/download.jsp?attach_no={i}")
        if new == 0:
            break
    return urls


def links_nps(opener, max_pages: int = 40) -> list[str]:
    """국민연금: 목록 pageIndex 순회 → fncAtchFileDownload('atchFileId','atchFileSn')."""
    base = "https://www.nps.or.kr/pnsinfo/databbs/getOHAF0279M0List.do"
    dl = "https://www.nps.or.kr/fileDown.do?atchFileId={}&atchFileSn={}"
    seen, urls = set(), []
    for pg in range(1, max_pages + 1):
        html, _ = http_get(opener, f"{base}?pageIndex={pg}")
        if not html:
            break
        txt = html.decode("utf-8", "replace")
        m = re.findall(r"fncAtchFileDownload\('([^']+)',\s*'([^']+)'", txt)
        if not m:
            break
        new = 0
        for aid, sn in m:
            k = (aid, sn)
            if k in seen:
                continue
            seen.add(k); new += 1
            urls.append(dl.format(aid, sn))
        if new == 0:
            break
    return urls


def links_kogas(opener) -> list[str]:
    """한국가스: 게시판 목록(boardNo=56) → /mgr/fileDownload.do?boardIdx&fileNo (세션쿠키)."""
    base = "https://www.kogas.or.kr"
    listurl = base + "/site/koGas/goBoard.do?boardNo=56&Key=1020409000000"
    http_get(opener, listurl)   # 익명 세션쿠키 확보
    html, _ = http_get(opener, listurl)
    if not html:
        return []
    txt = html.decode("utf-8", "replace")
    pairs = re.findall(r"fileDownload\.do\?boardIdx=(\d+)&(?:amp;)?fileNo=(\d+)", txt)
    seen, urls = set(), []
    for b, f in pairs:
        k = (b, f)
        if k in seen:
            continue
        seen.add(k)
        urls.append(f"{base}/mgr/fileDownload.do?boardIdx={b}&fileNo={f}")
    return urls


def links_lh(opener) -> list[str]:
    """LH(체계A 본사 정보공개 서식): 목록 HTML 내 boardDownload.es?bid=ATT&list_no&seq."""
    base = "https://www.lh.or.kr"
    html, _ = http_get(opener, base + "/menu.es?mid=a10102040000")
    if not html:
        return []
    txt = html.decode("utf-8", "replace")
    trip = re.findall(r"boardDownload\.es\?bid=ATT&(?:amp;)?list_no=(\d+)&(?:amp;)?seq=(\d+)", txt)
    seen, urls = set(), []
    for ln, sq in trip:
        k = (ln, sq)
        if k in seen:
            continue
        seen.add(k)
        urls.append(f"{base}/boardDownload.es?bid=ATT&list_no={ln}&seq={sq}")
    return urls


def links_kodit(opener, max_pages: int = 15) -> list[str]:
    """신용보증기금: 업무서식 게시판(bbsId=264) pageIndex 순회 → nttFileDownload.do?fileKey."""
    base = "https://www.kodit.or.kr"
    listurl = base + "/kodit/na/ntt/selectNttList.do?mi=2663&bbsId=264"
    dl = base + "/common/nttFileDownload.do?fileKey={}"
    seen, urls = set(), []
    for pg in range(1, max_pages + 1):
        html, _ = http_get(opener, f"{listurl}&pageIndex={pg}")
        if not html:
            break
        txt = html.decode("utf-8", "replace")
        keys = re.findall(r"nttFileDownload\.do\?fileKey=([a-f0-9]{16,})", txt)
        if not keys:
            break
        new = 0
        for k in keys:
            if k in seen:
                continue
            seen.add(k); new += 1
            urls.append(dl.format(k))
        if new == 0:
            break
    return urls


def links_kosaf(opener, max_pages: int = 45) -> list[str]:
    """한국장학재단: 자료실 page=N 순회 → fileDown('HP.BRD.UPLOAD','seq','fileno')."""
    base = "https://www.kosaf.go.kr"
    listurl = base + "/ko/data.do"
    dl = base + "/ko/download.do?pPath=HP.BRD.UPLOAD&pSeq_No={}&pFile_No={}"
    seen, urls = set(), []
    for pg in range(1, max_pages + 1):
        html, _ = http_get(opener, f"{listurl}?page={pg}")
        if not html:
            break
        txt = html.decode("utf-8", "replace")
        m = re.findall(r"fileDown\('HP\.BRD\.UPLOAD',\s*'(\d+)',\s*'(\d+)'\)", txt)
        if not m:
            break
        new = 0
        for seq, fno in m:
            k = (seq, fno)
            if k in seen:
                continue
            seen.add(k); new += 1
            urls.append(dl.format(seq, fno))
        if new == 0:
            break
    return urls


def links_hira(opener, max_pages: int = 40) -> list[str]:
    """심평원: 공개자료서식 게시판 pageIndex 순회 → downLoadBbs('apndNo','brdBltNo','tyNo','bltNo')."""
    base = "https://www.hira.or.kr"
    pgmid = "HIRAA070001000220"
    dl = base + "/bbs/bbsCDownLoad.do?apndNo={}&apndBrdBltNo={}&apndBrdTyNo={}&apndBltNo={}"
    seen, urls = set(), []
    for pg in range(1, max_pages + 1):
        html, _ = http_get(opener, f"{base}/bbsDummy.do?pgmid={pgmid}&pageIndex={pg}")
        if not html:
            break
        txt = html.decode("utf-8", "replace")
        m = re.findall(r"downLoadBbs\('(\d+)','(\d+)','(\d+)','(\d+)'\)", txt)
        if not m:
            break
        new = 0
        for a, b, c, d in m:
            k = (a, b, c, d)
            if k in seen:
                continue
            seen.add(k); new += 1
            urls.append(dl.format(a, b, c, d))
        if new == 0:
            break
    return urls


def links_kibo(opener) -> list[str]:
    """기술보증기금: 4개 서식게시판의 file-down-btn(data-file-id/data-file-vl) → attchLocalFileDownload.do."""
    base = "https://www.kibo.or.kr"
    boards = ["/dbranch/fomt/fomt01/warrantyAppForm.do?mode=list",
              "/dbranch/fomt/fomt01/technologyEvForm.do?mode=list",
              "/dbranch/fomt/fomt01/fomt0107.do?mode=list",
              "/main/board/boardType308.do?mode=list"]
    dl = base + "/COMN0201/attchLocalFileDownload.do?attchFileDiv={}&attchFileId={}"
    seen, urls = set(), []
    for b in boards:
        html, _ = http_get(opener, base + b)
        if not html:
            continue
        txt = html.decode("utf-8", "replace")
        for tag in re.findall(r"<a[^>]*file-down-btn[^>]*>", txt):
            fid = re.search(r'data-file-id="([^"]+)"', tag)
            div = re.search(r'data-file-vl="([^"]+)"', tag)
            if not (fid and div):
                continue
            k = (fid.group(1), div.group(1))
            if k in seen:
                continue
            seen.add(k)
            urls.append(dl.format(div.group(1), fid.group(1)))
    return urls


def links_cak(opener, max_pages: int = 8) -> list[str]:
    """대한건설협회(서울회): 자료실 cpage 순회 → download.do?uuid=...hwp/hwpx (확장자 필터)."""
    base = "https://seoul.cak.or.kr"
    listurl = base + "/lay1/bbs/S340T771C1459/A/72/list.do"
    seen, urls = set(), []
    for pg in range(1, max_pages + 1):
        html, _ = http_get(opener, f"{listurl}?cpage={pg}")
        if not html:
            break
        txt = html.decode("utf-8", "replace")
        m = re.findall(r"download\.do\?uuid=([a-f0-9-]+\.(?:hwp|hwpx))", txt)
        if not m:
            break
        new = 0
        for u in m:
            if u in seen:
                continue
            seen.add(u); new += 1
            urls.append(f"{base}/download.do?uuid={u}")
        if new == 0:
            break
    return urls


def links_cu(opener) -> list[str]:
    """신협중앙회: 민원 관련서식 콘텐츠 페이지 → nttFileDownload.do?fileKey (HWP)."""
    base = "https://www.cu.co.kr"
    html, _ = http_get(opener, base + "/cu/cm/cntnts/cntntsView.do?mi=100450&cntntsId=1187")
    if not html:
        return []
    txt = html.decode("utf-8", "replace")
    seen, urls = set(), []
    for k in re.findall(r"nttFileDownload\.do\?fileKey=([a-f0-9]{16,})", txt):
        if k in seen:
            continue
        seen.add(k)
        urls.append(f"{base}/common/nttFileDownload.do?fileKey={k}")
    return urls


def links_koelsa(opener, detail_delay: float = 1.5) -> list[str]:
    """승강기안전공단(민원24): 민원서식 목록→상세 순회 → Download.do href(정확 savename/realname).
    수동식 페이싱: 상세 요청 사이 지연."""
    base = "https://minwon.koelsa.or.kr"
    lst = base + "/BoardExecute.do?pageid=BOARD00004&command=List"
    idxs: list[str] = []
    seen_idx: set[str] = set()
    for pg in (1, 2, 3):
        html, _ = http_get(opener, f"{lst}&pageIndex={pg}")
        if not html:
            break
        txt = html.decode("utf-8", "replace")
        found = re.findall(r"fn_boardView\('?(\d+)'?\)", txt)
        fresh = [i for i in dict.fromkeys(found) if i not in seen_idx]
        if not fresh:
            break
        for i in fresh:
            seen_idx.add(i); idxs.append(i)
        time.sleep(detail_delay)
    urls, seen = [], set()
    for idx in idxs:
        html, _ = http_get(opener, f"{base}/BoardExecute.do?pageid=BOARD00004&command=View&idx={idx}")
        time.sleep(detail_delay)   # 수동식: 상세 하나 열 때마다 쉼
        if not html:
            continue
        txt = html.decode("utf-8", "replace")
        for m in re.findall(r"/Download\.do\?[^\"'>]*ext=(?:hwp|hwpx)", txt):
            u = base + m.replace("&amp;", "&")
            if u in seen:
                continue
            seen.add(u); urls.append(u)
    return urls


def links_kgs(opener) -> list[str]:
    """한국가스안전공사: 민원업무서식 페이지 → 정적 경로 /asset/file/{name}.hwp."""
    base = "https://www.kgs.or.kr"
    html, _ = http_get(opener, base + "/kgs/aceb/tab.do")
    if not html:
        return []
    txt = html.decode("utf-8", "replace")
    seen, urls = set(), []
    for p in re.findall(r"/asset/file/[^\"'\s>]+\.(?:hwp|hwpx)", txt):
        if p in seen:
            continue
        seen.add(p)
        urls.append(base + urllib.parse.quote(p, safe="/"))   # 한글 경로 인코딩
    return urls


def links_kalis(opener, max_pages: int = 20) -> list[str]:
    """국토안전관리원: 기술자료실 list page 순회 → view seq → down.do (seq×file_seq)."""
    base = "https://www.kalis.or.kr"
    brd = "tech0207"
    listurl = base + "/www/brd/m_435/list.do"
    dl = base + "/www/brd/m_435/down.do?brd_id={}&seq={}&data_tp=A&file_seq={}"
    seen_seq, urls = set(), []
    for pg in range(1, max_pages + 1):
        html, _ = http_get(opener, f"{listurl}?page={pg}")
        if not html:
            break
        txt = html.decode("utf-8", "replace")
        seqs = re.findall(r"view\.do\?seq=(\d+)", txt)
        fresh = [s for s in dict.fromkeys(seqs) if s not in seen_seq]
        if not fresh:
            break
        for s in fresh:
            seen_seq.add(s)
            for fseq in (1, 2, 3):   # 게시글당 첨부 1~3
                urls.append(dl.format(brd, s, fseq))
    return urls


COLLECTORS = {
    "koelsa": {"name": "한국승강기안전공단", "dir": "koelsa_forms",
               "gen": links_koelsa, "referer": "https://minwon.koelsa.or.kr/BoardExecute.do?pageid=BOARD00004"},
    "kgs":    {"name": "한국가스안전공사", "dir": "kgs_forms",
               "gen": links_kgs, "referer": "https://www.kgs.or.kr/kgs/aceb/tab.do"},
    "kalis":  {"name": "국토안전관리원", "dir": "kalis_forms",
               "gen": links_kalis, "referer": "https://www.kalis.or.kr/www/brd/m_435/list.do"},
    "cak":    {"name": "대한건설협회", "dir": "cak_forms",
               "gen": links_cak, "referer": "https://seoul.cak.or.kr/lay1/bbs/S340T771C1459/A/72/list.do"},
    "cu":     {"name": "신협중앙회", "dir": "cu_forms",
               "gen": links_cu, "referer": "https://www.cu.co.kr/cu/cm/cntnts/cntntsView.do?mi=100450&cntntsId=1187"},
    "kibo":   {"name": "기술보증기금", "dir": "kibo_forms",
               "gen": links_kibo, "referer": "https://www.kibo.or.kr/dbranch/fomt/fomt01/warrantyAppForm.do?mode=list"},
    "hira":   {"name": "건강보험심사평가원", "dir": "hira_forms",
               "gen": links_hira, "referer": "https://www.hira.or.kr/bbsDummy.do?pgmid=HIRAA070001000220"},
    "kodit":  {"name": "신용보증기금", "dir": "kodit_forms",
               "gen": links_kodit, "referer": "https://www.kodit.or.kr/kodit/na/ntt/selectNttList.do?mi=2663&bbsId=264"},
    "kosaf":  {"name": "한국장학재단", "dir": "kosaf_forms",
               "gen": links_kosaf, "referer": "https://www.kosaf.go.kr/ko/data.do"},
    "lh":     {"name": "한국토지주택공사(LH)", "dir": "lh_forms",
               "gen": links_lh, "referer": "https://www.lh.or.kr/menu.es?mid=a10102040000"},
    "nhis":   {"name": "국민건강보험공단", "dir": "nhis_forms",
               "gen": links_nhis, "referer": "https://www.nhis.or.kr/nhis/minwon/wbhaba03900m01.do"},
    "comwel": {"name": "근로복지공단", "dir": "comwel_forms",
               "gen": links_comwel, "referer": "https://www.comwel.or.kr/comwel/info/data/papr/papr_lst.jsp"},
    "nps":    {"name": "국민연금공단", "dir": "nps_forms",
               "gen": links_nps, "referer": "https://www.nps.or.kr/pnsinfo/databbs/getOHAF0279M0List.do"},
    "kogas":  {"name": "한국가스공사", "dir": "kogas_forms",
               "gen": links_kogas, "referer": "https://www.kogas.or.kr/site/koGas/goBoard.do?boardNo=56&Key=1020409000000"},
}


def load_done_hashes(index: Path) -> set[str]:
    hs: set[str] = set()
    if index.exists():
        for line in index.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                r = json.loads(line)
                if r.get("sha256"):
                    hs.add(r["sha256"])
            except Exception:
                pass
    return hs


def harvest(key: str, delay: float) -> None:
    cfg = COLLECTORS[key]
    out_dir = LIB / cfg["dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    index = LIB / f"{cfg['dir']}_index.jsonl"
    seen_hash = load_done_hashes(index)

    opener = make_opener(cfg.get("referer", ""))
    _log(f"[{key}] {cfg['name']} — 링크 수집 중 …")
    urls = cfg["gen"](opener)
    _log(f"[{key}] 다운로드 대상 {len(urls)}건 (기존 해시 {len(seen_hash)})")

    t0 = time.time()
    saved = dup = fail = hwp = pdf = other = 0
    with index.open("a", encoding="utf-8") as idx:
        for i, url in enumerate(urls, 1):
            data, hdrs = http_get(opener, url)
            if not data or len(data) < 100:
                fail += 1
                time.sleep(delay); continue
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen_hash:
                dup += 1
                time.sleep(delay); continue
            cd = hdrs.get("Content-Disposition", "")
            name = _fname_from_cd(cd) or f"{key}_{i}"
            ext = Path(name).suffix.lower().lstrip(".") or (
                "hwp" if data[:8] == HWP_OLE else "hwpx" if data[:2] == b"PK" else
                "pdf" if data[:4] == b"%PDF" else "bin")
            if ext == "hwp": hwp += 1
            elif ext == "pdf": pdf += 1
            else: other += 1
            fname = f"{i}_{_safe(Path(name).stem)}.{ext}"
            (out_dir / fname).write_bytes(data)
            seen_hash.add(digest); saved += 1
            idx.write(json.dumps({"seq": i, "name": name, "file": fname, "ext": ext,
                                  "sizeBytes": len(data), "sha256": digest}, ensure_ascii=False) + "\n")
            idx.flush()
            if saved % 20 == 0:
                _log(f"  … {i}/{len(urls)} · 저장 {saved} (hwp {hwp} pdf {pdf}) 중복 {dup} 실패 {fail}")
            time.sleep(delay)

    el = time.time() - t0
    _log(f"[{key}] 저장 {saved} (hwp {hwp} · pdf {pdf} · 기타 {other}) · 중복 {dup} · 실패 {fail} · {el/60:.1f}분")
    _log(f"[{key}] out={out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--institution", required=True, choices=sorted(COLLECTORS.keys()))
    ap.add_argument("--delay", type=float, default=0.4)
    args = ap.parse_args()
    harvest(args.institution, args.delay)


if __name__ == "__main__":
    main()
