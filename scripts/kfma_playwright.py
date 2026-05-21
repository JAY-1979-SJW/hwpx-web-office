"""KFMA 서식자료실 Playwright 수집"""
import time, re
from pathlib import Path
from playwright.sync_api import sync_playwright
import zipfile, io

BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"
FIRE_DIR = BASE / "소방시설법_시행규칙"
FIRE_DIR.mkdir(parents=True, exist_ok=True)
saved = []

def detect_ext(data):
    if data[:4] == b"%PDF": return ".pdf"
    if data[:4] == bytes([0xd0, 0xcf, 0x11, 0xe0]): return ".hwp"
    if data[:2] == b"PK":
        try:
            ns = " ".join(zipfile.ZipFile(io.BytesIO(data)).namelist())
            return ".xlsx" if "xl/" in ns else ".hwpx"
        except:
            return ".zip"
    return ".bin"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
        accept_downloads=True,
    )
    page = ctx.new_page()

    # 메인 방문
    page.goto("https://www.kfma.kr", wait_until="networkidle", timeout=30000)
    time.sleep(2)
    print(f"메인: {page.title()}, {len(page.content())}bytes")

    # 서식자료실
    page.goto("https://www.kfma.kr/bbs/12/list", wait_until="networkidle", timeout=30000)
    time.sleep(3)
    print(f"서식자료실: {page.title()}, {len(page.content())}bytes, URL={page.url}")

    # 게시물 목록 확인
    all_links = page.query_selector_all("a")
    print(f"링크 {len(all_links)}개")

    kw = ["자체점검", "점검기록표", "점검표", "보고서", "서식", "별지", "소방"]
    target_links = []
    for a in all_links:
        txt = a.inner_text().strip()
        href = a.get_attribute("href") or ""
        if any(k in txt for k in kw) and "/bbs/12/view/" in href:
            target_links.append((txt, href))
            print(f"  관련: [{txt}] {href}")

    # view 링크 전체
    view_links = [(a.inner_text().strip(), a.get_attribute("href") or "")
                  for a in all_links if "/bbs/12/view/" in (a.get_attribute("href") or "")]
    print(f"\n서식자료 게시물 {len(view_links)}건:")
    for t, h in view_links[:20]:
        print(f"  [{t[:50]}] {h}")

    # 자체점검 관련 파일 다운로드
    all_targets = target_links or view_links[:10]
    for title, href in all_targets:
        full = "https://www.kfma.kr" + href if href.startswith("/") else href
        print(f"\n게시물: {title}")

        detail = ctx.new_page()
        try:
            detail.goto(full, wait_until="networkidle", timeout=20000)
            time.sleep(2)

            # 파일 다운로드 링크
            dl_links = detail.query_selector_all("a[href*='download'], a[href*='file'], a[href*='.hwp'], a[href*='.pdf']")
            print(f"  첨부 {len(dl_links)}개")

            for i, lnk in enumerate(dl_links):
                fhref = lnk.get_attribute("href") or ""
                ftxt = lnk.inner_text().strip()[:50]
                if not fhref: continue
                furl = "https://www.kfma.kr" + fhref if fhref.startswith("/") else fhref
                print(f"  [{ftxt}] {furl[:80]}")

                try:
                    with detail.expect_download(timeout=15000) as dl_info:
                        lnk.click()
                    dl = dl_info.value
                    tmp = dl.path()
                    if tmp:
                        data = Path(tmp).read_bytes()
                        ext = detect_ext(data)
                        clean = re.sub(r"[^\w가-힣]", "_", title)[:50]
                        out = FIRE_DIR / f"KFMA_{clean}_{i}{ext}"
                        out.write_bytes(data)
                        print(f"    SAVED: {out.name} ({len(data)//1024}KB)")
                        saved.append(out.name)
                except Exception as e:
                    print(f"    다운로드 실패: {e}")
                time.sleep(0.5)
        except Exception as e:
            print(f"  오류: {e}")
        finally:
            detail.close()
        time.sleep(0.5)

    browser.close()

print(f"\n완료: {len(saved)}건")
for f in saved: print(f"  {f}")
