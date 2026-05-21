"""페이지 HTML 구조 디버깅"""
import time, logging
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    )
    page = context.new_page()

    # KFMA 페이지 디버그
    log.info("=== KFMA nttId=40830 ===")
    page.goto("https://www.kfma.kr/kfma/bbs/format/detail?nttId=40830",
              wait_until="networkidle", timeout=30000)
    time.sleep(3)

    # 페이지 타이틀
    log.info(f"Title: {page.title()}")
    log.info(f"URL: {page.url}")

    # 모든 a 태그
    all_links = page.query_selector_all("a")
    log.info(f"전체 a 태그: {len(all_links)}개")
    for lnk in all_links[:30]:
        href = lnk.get_attribute("href") or ""
        text = lnk.inner_text().strip()[:50]
        if href and (any(k in href.lower() for k in ["file","down","hwp","pdf"]) or any(k in text for k in ["다운","파일","첨부","hwp","pdf"])):
            log.info(f"  [{text}] href={href}")

    # 페이지 HTML 일부 출력
    html = page.content()
    log.info(f"\nHTML 길이: {len(html)}")
    # 파일 관련 부분 찾기
    import re
    matches = re.findall(r'(?:file|down|hwp|pdf|attach)[^"\'<>]{0,100}', html.lower())
    log.info(f"\n파일 관련 패턴 {len(matches)}개:")
    for m in matches[:20]:
        log.info(f"  {m}")

    # KFSI 디버그
    log.info("\n=== KFSI 서식자료실 ===")
    page.goto("https://www.kfsi.or.kr/main/infocenter/InfocenterBbsList.do?boardSeqno=10045",
              wait_until="networkidle", timeout=30000)
    time.sleep(3)
    log.info(f"Title: {page.title()}")
    log.info(f"URL: {page.url}")

    all_links = page.query_selector_all("a")
    log.info(f"전체 a 태그: {len(all_links)}개")
    for lnk in all_links[:30]:
        href = lnk.get_attribute("href") or ""
        text = lnk.inner_text().strip()[:60]
        if text and text not in ["", "메뉴", "HOME"]:
            log.info(f"  [{text}] href={href[:80]}")

    html2 = page.content()
    log.info(f"\nHTML 길이: {len(html2)}")
    matches2 = re.findall(r'href="([^"]*(?:file|down|hwp|pdf)[^"]*)"', html2, re.I)
    log.info(f"파일링크 {len(matches2)}개: {matches2[:10]}")

    browser.close()
