"""
kprc.or.kr 물가자료 PDF 다운로드 스크립트
- 로그인 후 자료실에서 최신순으로 PDF를 모두 다운로드
- 저장 경로: ~/app/haehan-platform/storage/price_data/kprc/
"""

import asyncio
import os
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright, Page, Download

BASE_URL = "https://kprc.or.kr"
LOGIN_URL = f"{BASE_URL}/main.do?menuID=100000"
SAVE_DIR = Path.home() / "app/haehan-platform/storage/price_data/kprc"

ID = "smepower"
PW = "05sh19in**"


async def login(page: Page):
    await page.goto(LOGIN_URL, wait_until="networkidle")

    # 로그인 폼 탐색
    # id/pw 필드 찾기 (name, id, placeholder 기준)
    id_selectors = [
        'input[name="userId"]', 'input[name="id"]', 'input[name="loginId"]',
        'input[id="userId"]', 'input[id="id"]', 'input[type="text"][name*="id" i]',
        'input[placeholder*="아이디" i]', 'input[placeholder*="ID" i]',
    ]
    pw_selectors = [
        'input[name="password"]', 'input[name="passwd"]', 'input[name="pwd"]',
        'input[id="password"]', 'input[type="password"]',
    ]

    id_field = None
    for sel in id_selectors:
        el = page.locator(sel).first
        if await el.count() > 0:
            id_field = el
            print(f"[login] id field: {sel}")
            break

    pw_field = None
    for sel in pw_selectors:
        el = page.locator(sel).first
        if await el.count() > 0:
            pw_field = el
            print(f"[login] pw field: {sel}")
            break

    if not id_field or not pw_field:
        # 팝업 로그인 링크 클릭 시도
        login_btns = page.locator('a:has-text("로그인"), button:has-text("로그인")')
        if await login_btns.count() > 0:
            await login_btns.first.click()
            await page.wait_for_timeout(1500)
            for sel in id_selectors:
                el = page.locator(sel).first
                if await el.count() > 0:
                    id_field = el
                    break
            for sel in pw_selectors:
                el = page.locator(sel).first
                if await el.count() > 0:
                    pw_field = el
                    break

    if not id_field or not pw_field:
        raise RuntimeError("로그인 폼을 찾을 수 없습니다.")

    await id_field.fill(ID)
    await pw_field.fill(PW)

    # 로그인 버튼
    login_btn_sel = [
        'button[type="submit"]', 'input[type="submit"]',
        'a:has-text("로그인")', 'button:has-text("로그인")',
        '.login-btn', '#loginBtn',
    ]
    for sel in login_btn_sel:
        el = page.locator(sel).first
        if await el.count() > 0:
            await el.click()
            print(f"[login] submit: {sel}")
            break

    await page.wait_for_timeout(2000)
    print(f"[login] 현재 URL: {page.url}")


async def find_pdf_section(page: Page) -> list[str]:
    """PDF 목록 페이지 URL 후보를 찾는다."""
    # 자료실, 간행물, 월간물가, ebook 등 링크 탐색
    keywords = ["자료", "간행물", "월간", "ebook", "e-book", "발간", "pdf", "다운"]
    links = await page.query_selector_all("a")
    candidates = []
    for link in links:
        text = (await link.text_content() or "").strip()
        href = await link.get_attribute("href") or ""
        for kw in keywords:
            if kw.lower() in text.lower() or kw.lower() in href.lower():
                full = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
                if full not in candidates:
                    candidates.append(full)
                break
    return candidates


async def collect_pdf_links_from_page(page: Page) -> list[dict]:
    """현재 페이지에서 PDF 다운로드 링크를 수집."""
    results = []

    # 다운로드 버튼/링크 찾기
    selectors = [
        'a[href$=".pdf"]',
        'a[href*="download"]',
        'a[href*="fileDown"]',
        'a[href*="attach"]',
        'button[onclick*="download"]',
        'a[onclick*="download"]',
        'a[onclick*="fileDown"]',
        'a:has-text("다운로드")',
        'a:has-text("PDF")',
        'a:has-text("자료")',
    ]

    seen = set()
    for sel in selectors:
        els = await page.query_selector_all(sel)
        for el in els:
            href = await el.get_attribute("href") or ""
            onclick = await el.get_attribute("onclick") or ""
            text = (await el.text_content() or "").strip()

            key = href or onclick
            if key in seen or not key:
                continue
            seen.add(key)

            url = ""
            if href.endswith(".pdf") or "download" in href.lower() or "fileDown" in href.lower() or "attach" in href.lower():
                url = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
            elif onclick:
                # onclick에서 URL 추출 시도
                m = re.search(r"['\"]([^'\"]*(?:download|fileDown|attach)[^'\"]*)['\"]", onclick)
                if m:
                    url = m.group(1)
                    if not url.startswith("http"):
                        url = BASE_URL + "/" + url.lstrip("/")

            if url:
                results.append({"url": url, "text": text, "onclick": onclick})

    return results


async def download_file(page: Page, url: str, save_dir: Path, filename: str | None = None) -> bool:
    """단일 파일 다운로드. 성공 여부 반환."""
    try:
        async with page.expect_download(timeout=60000) as dl_info:
            await page.goto(url)
        download: Download = await dl_info.value
        fname = filename or download.suggested_filename or url.split("/")[-1]
        dest = save_dir / fname
        await download.save_as(str(dest))
        print(f"  [OK] {fname}")
        return True
    except Exception as e:
        print(f"  [FAIL] {url} — {e}")
        return False


async def get_total_pages(page: Page) -> int:
    """페이지네이션에서 총 페이지 수 추출."""
    # 일반적인 패턴들
    selectors = [
        '.pagination a', '.paging a', '.page-nav a',
        'a[href*="page="]', 'a[href*="pageNo="]', 'a[href*="pageNum="]',
    ]
    max_page = 1
    for sel in selectors:
        els = await page.query_selector_all(sel)
        for el in els:
            text = (await el.text_content() or "").strip()
            if text.isdigit():
                max_page = max(max_page, int(text))
    return max_page


async def scrape_list_page(page: Page, url: str, save_dir: Path, visited_urls: set):
    """목록 페이지에서 PDF 링크를 수집하고 다운로드."""
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(1000)

    total = await get_total_pages(page)
    print(f"[list] 총 {total} 페이지 — {url}")

    # 최신순 정렬 확인/변경 시도
    sort_btns = page.locator('a:has-text("최신"), a:has-text("등록일"), select[name*="sort"], select[name*="order"]')
    if await sort_btns.count() > 0:
        await sort_btns.first.click()
        await page.wait_for_timeout(800)

    for page_no in range(1, total + 1):
        if page_no > 1:
            # 페이지 이동
            page_link = page.locator(
                f'a[href*="page={page_no}"], a[href*="pageNo={page_no}"], '
                f'a[href*="pageNum={page_no}"], .pagination a:has-text("{page_no}")'
            ).first
            if await page_link.count() > 0:
                await page_link.click()
                await page.wait_for_timeout(1000)
            else:
                break

        pdf_links = await collect_pdf_links_from_page(page)
        new_links = [l for l in pdf_links if l["url"] not in visited_urls]

        for link in new_links:
            visited_urls.add(link["url"])
            fname = link["text"] or link["url"].split("/")[-1]
            if not fname.endswith(".pdf"):
                fname += ".pdf"
            # 파일명 정제
            fname = re.sub(r'[\\/:*?"<>|]', "_", fname)
            await download_file(page, link["url"], save_dir, fname)

        print(f"  [page {page_no}/{total}] {len(new_links)}건 수집")


async def main():
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[start] 저장 경로: {SAVE_DIR}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            accept_downloads=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        # 1. 로그인
        print("[1] 로그인 중...")
        await login(page)

        # 2. PDF 섹션 탐색
        print("[2] PDF 자료실 탐색 중...")
        candidates = await find_pdf_section(page)
        print(f"  후보 링크: {len(candidates)}건")
        for c in candidates[:10]:
            print(f"    {c}")

        visited_urls: set = set()

        if not candidates:
            # 현재 페이지에서 직접 시도
            print("[2b] 현재 페이지에서 PDF 직접 탐색...")
            pdf_links = await collect_pdf_links_from_page(page)
            for link in pdf_links:
                visited_urls.add(link["url"])
                await download_file(page, link["url"], SAVE_DIR)
        else:
            for url in candidates[:5]:  # 상위 5개 섹션
                print(f"\n[3] 섹션 스크래핑: {url}")
                try:
                    await scrape_list_page(page, url, SAVE_DIR, visited_urls)
                except Exception as e:
                    print(f"  [ERROR] {e}")

        await browser.close()

    files = list(SAVE_DIR.glob("*.pdf"))
    print(f"\n[완료] 총 {len(files)}개 PDF 저장 완료 → {SAVE_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
