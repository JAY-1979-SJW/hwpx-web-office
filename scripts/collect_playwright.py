"""
KFMA, KFSI 서식 JavaScript 렌더링 수집
- KFMA 한국소방시설관리협회: 자체점검기록표, 자체점검결과보고서
- KFSI 한국소방안전원: 서식자료실 전체
"""
import re, time, logging
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
        import zipfile, io
        try:
            ns = " ".join(zipfile.ZipFile(io.BytesIO(data)).namelist())
            return ".xlsx" if "xl/" in ns else ".hwpx"
        except:
            return ".zip"
    return ".bin"

def save_bytes(data: bytes, path: Path, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    kb = len(data) // 1024
    log.info(f"  SAVED [{label}] {path.name} ({kb}KB)")
    saved.append({"file": str(path.relative_to(BASE)), "size_kb": kb})
    return True

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        accept_downloads=True,
    )
    page = context.new_page()

    # ── 1. KFMA 소방시설관리협회 서식자료실 ───────────────────────────
    log.info("=" * 60)
    log.info("[1] KFMA 소방시설관리협회 서식자료실")
    log.info("=" * 60)

    KFMA_PAGES = [
        ("https://www.kfma.kr/kfma/bbs/format/detail?nttId=40830", "소방자체점검결과보고서및점검표"),
        ("https://www.kfma.kr/kfma/bbs/format/detail?nttId=40827", "소방자체점검기록표_2022개정"),
    ]

    for url, fname_base in KFMA_PAGES:
        try:
            log.info(f"\n  페이지: {url}")
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(2)

            # 다운로드 링크 탐색
            links = page.query_selector_all("a[href*='fileDownload'], a[href*='Download'], a[href*='.hwp'], a[href*='.pdf']")
            log.info(f"  다운로드 링크 {len(links)}개")

            for i, lnk in enumerate(links):
                href = lnk.get_attribute("href") or ""
                text = lnk.inner_text().strip()
                if not href:
                    continue
                full = "https://www.kfma.kr" + href if href.startswith("/") else href
                log.info(f"  [{i}] {text} → {full[:80]}")

                # 다운로드 인터셉트
                with context.expect_event("response") as resp_info:
                    with context.expect_event("response", timeout=15000):
                        try:
                            with page.expect_download(timeout=15000) as dl_info:
                                lnk.click()
                            dl = dl_info.value
                            tmp = dl.path()
                            if tmp:
                                data = Path(tmp).read_bytes()
                                ext = detect_ext(data)
                                clean = re.sub(r"[^\w가-힣]", "_", text or fname_base)[:50]
                                save_bytes(data, FIRE_DIR / f"KFMA_{fname_base}_{i}{ext}", "KFMA")
                        except Exception:
                            # click으로 다운로드가 안 되면 requests로 직접
                            import requests
                            H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.kfma.kr/"}
                            r = requests.get(full, headers=H, timeout=20, allow_redirects=True)
                            d = r.content
                            if r.status_code == 200 and len(d) > 200 and b"<!DOCTYPE" not in d[:200]:
                                ext = detect_ext(d)
                                clean = re.sub(r"[^\w가-힣]", "_", text or fname_base)[:50]
                                save_bytes(d, FIRE_DIR / f"KFMA_{fname_base}_{i}{ext}", "KFMA_direct")
                time.sleep(0.5)
        except Exception as e:
            log.error(f"  KFMA 오류: {e}")
        time.sleep(1)

    # ── 2. KFSI 한국소방안전원 서식자료실 ─────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("[2] KFSI 한국소방안전원 서식자료실")
    log.info("=" * 60)

    try:
        page.goto(
            "https://www.kfsi.or.kr/main/infocenter/InfocenterBbsList.do?boardSeqno=10045",
            wait_until="networkidle", timeout=30000
        )
        time.sleep(2)

        # 게시물 목록
        rows = page.query_selector_all("table tbody tr, .board_list li")
        log.info(f"  게시물 {len(rows)}건")

        FIRE_KW = ["점검표", "서식", "체크리스트", "감리", "검사표", "확인표"]

        for row in rows[:20]:
            link = row.query_selector("a")
            if not link:
                continue
            title = link.inner_text().strip()
            if not any(k in title for k in FIRE_KW):
                continue
            href = link.get_attribute("href") or ""
            full = "https://www.kfsi.or.kr" + href if href.startswith("/") else href
            log.info(f"\n  게시물: {title}")

            detail_page = context.new_page()
            try:
                detail_page.goto(full, wait_until="networkidle", timeout=20000)
                time.sleep(1.5)

                # 첨부파일 링크
                dl_links = detail_page.query_selector_all(
                    "a[href*='fileDown'], a[href*='download'], a[href*='Seq='], a[href*='.hwp'], a[href*='.pdf']"
                )
                log.info(f"  첨부파일 {len(dl_links)}개")

                for j, dlnk in enumerate(dl_links):
                    fhref = dlnk.get_attribute("href") or ""
                    ftxt = dlnk.inner_text().strip()
                    if not fhref:
                        continue
                    furl = "https://www.kfsi.or.kr" + fhref if fhref.startswith("/") else fhref

                    import requests
                    H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.kfsi.or.kr/"}
                    r = requests.get(furl, headers=H, timeout=20, allow_redirects=True)
                    d = r.content
                    if r.status_code == 200 and len(d) > 200 and b"<!DOCTYPE" not in d[:200]:
                        ext = detect_ext(d)
                        clean = re.sub(r"[^\w가-힣]", "_", title)[:50]
                        save_bytes(d, FIRE_DIR / f"KFSI_{clean}_{j}{ext}", "KFSI")
                    time.sleep(0.4)
            except Exception as e:
                log.error(f"  KFSI 게시물 오류: {e}")
            finally:
                detail_page.close()
            time.sleep(0.5)

    except Exception as e:
        log.error(f"  KFSI 자료실 오류: {e}")

    browser.close()

log.info("\n" + "=" * 60)
log.info(f"Playwright 수집 완료: {len(saved)}건")
for s in saved:
    log.info(f"  {s['file']} ({s['size_kb']}KB)")
