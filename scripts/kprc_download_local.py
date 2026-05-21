"""
kprc.or.kr 거래가격 PDF 전체 다운로드 (로컬 실행)
저장: ~/Downloads/kprc_pdf/

페이지 구조: AJAX 동적 로딩 — callPageMove(n, '#search') 로 이동
"""

import asyncio
import re
from pathlib import Path
from playwright.async_api import async_playwright, Page

BASE_URL = "https://kprc.or.kr"
SAVE_DIR = Path.home() / "Downloads/kprc_pdf"
ID = "haehan"
PW = "0519shin**"

# board → (label, 최대페이지)  * 최대페이지는 실행 시 동적 확인
BOARDS = [
    ("주요자재별_거래가격",  "use06"),  # 108페이지
    ("거래가격동향",       "use07"),  # 32페이지
]


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", (s or "file").strip())[:120] or "file"


async def login(page: Page):
    await page.goto(f"{BASE_URL}/main.do?menuID=100000", wait_until="networkidle")
    await page.locator('a[onclick*="sGA4LinkInfo"][onclick*="openModal"]').first.click()
    await page.wait_for_timeout(1500)
    await page.fill('input[name="userID"]', ID)
    await page.fill('input[name="userPass"]', PW)
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await page.evaluate("document.getElementById('loginBtn').click()")
    await page.wait_for_timeout(3000)


async def get_max_page(page: Page) -> int:
    """페이지네이션에서 마지막 페이지 번호 추출."""
    els = await page.query_selector_all('.pagination a, .paging a')
    nums = []
    for el in els:
        onclick = await el.get_attribute("onclick") or ""
        m = re.search(r"callPageMove\((\d+)", onclick)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) if nums else 1


async def navigate_to_page(page: Page, n: int):
    await page.evaluate(f"callPageMove({n}, '#search')")
    await page.wait_for_timeout(1500)


async def extract_row_meta(page, link) -> tuple[str, str]:
    """fileDown 링크가 속한 DT에서 (날짜, 제목) 추출.
    KPRC 게시판 구조: fileDown link → P → DT → DL"""
    date_str = title = ""
    try:
        dt_text = await page.evaluate(
            "el => { var dt = el.closest('dt'); return dt ? dt.innerText : null; }",
            link,
        )
        if not dt_text:
            return date_str, title
        lines = [l.strip() for l in dt_text.splitlines() if l.strip()]
        if lines:
            title = lines[0]
        for line in lines:
            m = re.search(r"(\d{4})[./](\d{1,2})[./](\d{1,2})", line)
            if m:
                date_str = f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}"
                break
    except Exception:
        pass
    return date_str, title


async def download_filedown_links(page: Page, save_dir: Path, done: set) -> int:
    """현재 페이지의 fileDown 링크를 모두 다운로드. 완료 수 반환."""
    links = await page.query_selector_all('a[href*="fileDown"]')
    count = 0
    for link in links:
        href = (await link.get_attribute("href") or "").strip()
        if not href or href in done:
            continue
        done.add(href)

        date_str, title = await extract_row_meta(page, link)

        # 파일명: 날짜_제목 우선, 없으면 href에서 ID 추출
        if date_str or title:
            base = f"{date_str}_{safe_name(title)}" if date_str and title else (date_str or safe_name(title))
        else:
            # javascript:fileDown('TOKEN',...) 에서 토큰 추출
            m = re.search(r"fileDown\(['\"]([^'\"]{6,})['\"]", href) or \
                re.search(r"(?:seq|id|no|idx)=(\d+)", href)
            base = f"kprc_{m.group(1)[:16]}" if m else f"kprc_{abs(hash(href)) % 100000}"
        fname = base[:120] + ".pdf"
        dest = save_dir / fname

        if dest.exists():
            print(f"    [SKIP] {fname}")
            continue

        try:
            async with page.expect_download(timeout=90000) as dl_info:
                await link.click()
            dl = await dl_info.value
            await dl.save_as(str(dest))
            print(f"    [OK] {fname}  ({dest.stat().st_size // 1024} KB)")
            count += 1
        except Exception as e:
            print(f"    [FAIL] {href[:60]} — {e}")

    return count


async def scrape_board(page: Page, label: str, board_type: str, save_dir: Path, done: set):
    board_dir = save_dir / label
    board_dir.mkdir(exist_ok=True)

    print(f"\n{'='*60}")
    await page.goto(f"{BASE_URL}/boardList.do?boardType={board_type}", wait_until="networkidle")
    await page.wait_for_timeout(1000)

    # 첫 페이지에서 최대 페이지 수 확인
    max_page = await get_max_page(page)
    print(f"[{label}] 총 {max_page} 페이지")

    total = 0
    for page_no in range(1, max_page + 1):
        if page_no > 1:
            await navigate_to_page(page, page_no)

        n = await download_filedown_links(page, board_dir, done)
        total += n

        # 진행상황 (파일 없는 페이지는 간략 출력)
        if n > 0 or page_no % 10 == 0:
            print(f"  [page {page_no}/{max_page}] {n}건 (누적 {total}건)")

    print(f"  [{label}] 완료: {total}건")
    return total


async def main():
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"저장 경로: {SAVE_DIR}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        print("[1] 로그인...")
        await login(page)
        print("    완료")

        done: set = set()
        grand_total = 0
        for label, board_type in BOARDS:
            n = await scrape_board(page, label, board_type, SAVE_DIR, done)
            grand_total += n

        await browser.close()

    files = list(SAVE_DIR.rglob("*.pdf"))
    print(f"\n{'='*60}")
    print(f"전체 완료: PDF {len(files)}개 → {SAVE_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
