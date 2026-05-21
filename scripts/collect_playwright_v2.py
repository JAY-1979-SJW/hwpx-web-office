"""
KFMA, KFSI 서식 Playwright 수집 v2 — 메인페이지 진입 후 세션 확보
"""
import re, time, logging, zipfile, io
from pathlib import Path
from playwright.sync_api import sync_playwright

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("/home/ubuntu/app/haehan-platform/storage/templates/inspection/collect_playwright.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger()

BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"
FIRE_DIR = BASE / "소방시설법_시행규칙"
FIRE_DIR.mkdir(parents=True, exist_ok=True)
saved = []

def detect_ext(data: bytes) -> str:
    if data[:4] == b"%PDF": return ".pdf"
    if data[:4] == bytes([0xd0, 0xcf, 0x11, 0xe0]): return ".hwp"
    if data[:2] == b"PK":
        try:
            ns = " ".join(zipfile.ZipFile(io.BytesIO(data)).namelist())
            return ".xlsx" if "xl/" in ns else ".hwpx"
        except:
            return ".zip"
    return ".bin"

def clean_name(s):
    return re.sub(r"[^\w가-힣]", "_", s)[:50]

def save_bytes(data: bytes, path: Path, label: str):
    if not data or len(data) < 200:
        return False
    if b"<!DOCTYPE" in data[:300] or b"<html" in data[:300].lower():
        log.warning(f"  SKIP [{label}] HTML 응답")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    kb = len(data) // 1024
    log.info(f"  SAVED [{label}] {path.name} ({kb}KB)")
    saved.append({"file": str(path.relative_to(BASE)), "size_kb": kb})
    return True

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        accept_downloads=True,
        viewport={"width": 1280, "height": 800},
    )

    # ── 1. KFMA ────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("[1] KFMA 소방시설관리협회")
    log.info("=" * 60)
    page = ctx.new_page()
    try:
        # 메인 진입
        page.goto("https://www.kfma.kr", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        log.info(f"  메인 타이틀: {page.title()}, HTML: {len(page.content())}bytes")

        # 서식자료실 메뉴 탐색
        fmt_link = page.query_selector("a[href*='format']")
        if fmt_link:
            fmt_link.click()
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)
            log.info(f"  서식자료실 이동: {page.url}")
        else:
            page.goto("https://www.kfma.kr/kfma/bbs/format", wait_until="networkidle", timeout=20000)
            time.sleep(2)

        log.info(f"  서식자료실 HTML: {len(page.content())}bytes, title: {page.title()}")

        # 목록에서 링크 찾기
        all_a = page.query_selector_all("a")
        kw = ["점검", "서식", "체크", "기록표", "보고서", "자체점검"]
        target_links = []
        for a in all_a:
            txt = a.inner_text().strip()
            href = a.get_attribute("href") or ""
            if any(k in txt for k in kw) and ("format" in href or "bbs" in href or "nttId" in href):
                target_links.append((txt, href))
                log.info(f"  목록 링크: [{txt}] {href}")

        if not target_links:
            # URL 패턴 직접 시도
            for ntt_id in [40830, 40827, 40826, 40825, 40824]:
                test_url = f"https://www.kfma.kr/kfma/bbs/format/detail?nttId={ntt_id}"
                page.goto(test_url, wait_until="networkidle", timeout=15000)
                time.sleep(1.5)
                title_el = page.query_selector("h2, h3, .title, .subject")
                title_txt = title_el.inner_text().strip() if title_el else ""
                html_len = len(page.content())
                log.info(f"  nttId={ntt_id}: html={html_len}bytes, title={title_txt[:50]}")

                if html_len > 5000:  # 실제 콘텐츠
                    dl_links = page.query_selector_all("a")
                    for dlnk in dl_links:
                        h = dlnk.get_attribute("href") or ""
                        t = dlnk.inner_text().strip()
                        if any(k in h.lower() for k in ["download","file","hwp","pdf"]):
                            log.info(f"    파일링크: [{t}] {h}")
                            full = "https://www.kfma.kr" + h if h.startswith("/") else h
                            import requests
                            H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.kfma.kr/"}
                            # 쿠키 포함 요청
                            cookies = {c["name"]: c["value"] for c in ctx.cookies("https://www.kfma.kr")}
                            r = requests.get(full, headers=H, cookies=cookies, timeout=20, allow_redirects=True)
                            fname = clean_name(title_txt or f"KFMA_nttId{ntt_id}")
                            save_bytes(r.content, FIRE_DIR / f"KFMA_{fname}_{ntt_id}{detect_ext(r.content) if save_bytes.__code__.co_varcount else '.bin'}", "KFMA")
                time.sleep(0.5)

    except Exception as e:
        log.error(f"  KFMA 오류: {e}")
    finally:
        page.close()

    # ── 2. KFSI ────────────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("[2] KFSI 한국소방안전원")
    log.info("=" * 60)
    page2 = ctx.new_page()
    try:
        # 메인 진입
        page2.goto("https://www.kfsi.or.kr", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        log.info(f"  메인 타이틀: {page2.title()}, HTML: {len(page2.content())}bytes")

        # 서식자료실 직접 접근
        page2.goto(
            "https://www.kfsi.or.kr/main/infocenter/InfocenterBbsList.do?boardSeqno=10045",
            wait_until="networkidle", timeout=20000
        )
        time.sleep(2)
        html_len = len(page2.content())
        log.info(f"  서식자료실 HTML: {html_len}bytes, title: {page2.title()}")

        if html_len > 5000:
            rows = page2.query_selector_all("table tbody tr, .board_list li, ul.list li")
            log.info(f"  게시물 {len(rows)}건")
            kw2 = ["점검표", "서식", "체크리스트", "감리", "기록표"]
            for row in rows[:20]:
                lnk = row.query_selector("a")
                if not lnk: continue
                txt = lnk.inner_text().strip()
                href = lnk.get_attribute("href") or ""
                if not any(k in txt for k in kw2): continue
                log.info(f"\n  게시물: [{txt}] {href}")
                full = "https://www.kfsi.or.kr" + href if href.startswith("/") else href
                page2.goto(full, wait_until="networkidle", timeout=20000)
                time.sleep(1.5)
                # 첨부파일
                file_links = page2.query_selector_all(
                    "a[href*='fileDown'], a[href*='download'], a[href*='.hwp'], a[href*='.pdf'], a[href*='Seq=']"
                )
                log.info(f"  첨부파일 {len(file_links)}개")
                import requests
                H2 = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.kfsi.or.kr/"}
                cookies2 = {c["name"]: c["value"] for c in ctx.cookies("https://www.kfsi.or.kr")}
                for j, flnk in enumerate(file_links):
                    fh = flnk.get_attribute("href") or ""
                    ft = flnk.inner_text().strip()
                    furl = "https://www.kfsi.or.kr" + fh if fh.startswith("/") else fh
                    r = requests.get(furl, headers=H2, cookies=cookies2, timeout=20, allow_redirects=True)
                    save_bytes(r.content, FIRE_DIR / f"KFSI_{clean_name(txt)}_{j}{detect_ext(r.content)}", "KFSI")
                    time.sleep(0.4)
                page2.go_back()
                time.sleep(0.5)
        else:
            # HTML이 짧으면 직접 링크 URL 추출
            log.info("  HTML 짧음 — 직접 링크 탐색")
            import requests
            H3 = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.kfsi.or.kr/",
            }
            cookies3 = {c["name"]: c["value"] for c in ctx.cookies("https://www.kfsi.or.kr")}
            log.info(f"  쿠키: {list(cookies3.keys())}")
            r = requests.get(
                "https://www.kfsi.or.kr/main/infocenter/InfocenterBbsList.do?boardSeqno=10045",
                headers=H3, cookies=cookies3, timeout=15
            )
            log.info(f"  requests 응답: status={r.status_code} size={len(r.content)} encoding={r.encoding}")
            # HTML 파싱
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            all_links = soup.find_all("a", href=True)
            log.info(f"  a 태그 {len(all_links)}개")
            for lnk in all_links[:20]:
                t = lnk.get_text(strip=True)
                h = lnk["href"]
                if t or h:
                    log.info(f"  [{t}] {h}")

    except Exception as e:
        log.error(f"  KFSI 오류: {e}")
    finally:
        page2.close()

    browser.close()

log.info("\n" + "=" * 60)
log.info(f"완료: {len(saved)}건")
for s in saved:
    log.info(f"  {s['file']} ({s['size_kb']}KB)")
