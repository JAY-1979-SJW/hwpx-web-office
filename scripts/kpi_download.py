"""
kpi.or.kr E-도서관 PDF 다운로드
- 인증: kpi.or.kr 로그인 → Session_Id → elib.kpi.or.kr SSO
- PDF 위치: https://elibfile.kpi.or.kr/Files/Pdf/{B_Code}/{B_Date}/{class}
- 과월호: B_Date=YYYYMM 직접 탐색 (2022년~현재)
- 저장: ~/Downloads/kpi_pdf/
"""

import asyncio, re, sys
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext

BASE_URL  = "https://kpi.or.kr"
ELIB_URL  = "https://elib.kpi.or.kr"
FILE_URL  = "https://elibfile.kpi.or.kr/Files/Pdf"
LOGIN_URL = f"{BASE_URL}/mmm/member/m_login.asp"
EBOOK_URL = f"{BASE_URL}/mmm/m_sub_ebook.asp"
SAVE_DIR  = Path.home() / "Downloads/kpi_pdf"
ID = "smepower"
PW = "05sh19in**"

# 탐색 범위: 2022년 1월 ~ 2026년 4월
SCAN_START = (2022, 1)
SCAN_END   = (2026, 4)

# B_Code 목록: 01=종합물가, 02=종합적산, 03=전기정보통신적산, 04=생활물가
BOOK_CODES  = ["01", "02", "03", "04"]
BOOK_NAMES  = {
    "01": "종합물가정보",
    "02": "종합적산정보",
    "03": "전기정보통신적산",
    "04": "생활물가뉴스",
}
VOLUME_NAMES = {"02": "I호", "03": "II호", "04": "III호"}

# 카테고리 이름 매핑 (class → 한글명)
CLASS_NAMES = {
    "01": "공통", "02": "토목", "03": "조경", "04": "건축",
    "05": "급배수", "06": "냉난방", "07": "기계", "08": "환경",
    "09": "전기", "10": "정보통신", "11": "소방화학", "12": "관리",
    "13": "부록", "14": "사무", "15": "녹색물품", "16": "공사비", "17": "신기술품셈", "18": "관리비",
    "21": "토목적산", "22": "건축적산", "23": "기계적산", "24": "전기적산",
}


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", (s or "file").strip())[:120] or "file"


def gen_months(start: tuple, end: tuple):
    """(year, month) 범위 생성."""
    y, m = start
    while (y, m) <= end:
        yield f"{y:04d}{m:02d}"
        m += 1
        if m > 12:
            m = 1; y += 1


async def login_and_open_elib(context: BrowserContext) -> Page | None:
    """kpi 로그인 후 elib 세션 획득, elib 홈 Page 반환."""
    page = await context.new_page()

    print("[1] kpi.or.kr 로그인...")
    await page.goto(LOGIN_URL, wait_until="networkidle")
    await page.fill('input[name="userId"]',     ID)
    await page.fill('input[name="userPasswd"]', PW)
    await page.click('a#loginBtn')
    await page.wait_for_timeout(2500)
    if "login" in page.url.lower():
        print("  [ERROR] 로그인 실패")
        return None
    print("  완료")

    print("[2] Session_Id 추출...")
    await page.goto(EBOOK_URL, wait_until="networkidle")
    await page.wait_for_timeout(1000)
    html = await page.content()
    m = re.search(r"Session_Id=(\d+)", html)
    if not m:
        print("  [ERROR] Session_Id 없음")
        return None
    session_id = m.group(1)

    elib_session = f"{ELIB_URL}/Member/Usercheck/?User_Id={ID}&Session_Id={session_id}"
    print(f"  Session_Id: {session_id}")

    print("[3] elib 접속...")
    await page.goto(elib_session, wait_until="networkidle")
    await page.wait_for_timeout(2000)
    print(f"  elib URL: {page.url}")
    return page


async def check_issue_exists(page: Page, bdate: str, bcode: str, volume: str = "02") -> list[str]:
    """뷰어 페이지 접근 → data-class 목록 반환. 없으면 빈 리스트."""
    viewer_url = f"{ELIB_URL}/elibbook/elib?B_Date={bdate}&B_Code={bcode}&Volume={volume}"
    try:
        await page.goto(viewer_url, wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(800)
    except Exception:
        return []
    html = await page.content()
    # 유효하지 않은 이슈 → 목록으로 redirect되거나 data-class 없음
    if "/Home" in page.url or "elibbook/elib" not in page.url:
        return []
    classes = re.findall(r'data-class=["\'](\d+)["\']', html)
    return list(dict.fromkeys(classes))


async def download_pdf(page: Page, pdf_url: str, dest: Path) -> bool | None:
    """PDF 다운로드. True=성공, None=스킵(존재), False=실패."""
    if dest.exists():
        return None

    # page.request.get으로 스트림 다운로드 (세션 쿠키 포함)
    try:
        resp = await page.request.get(pdf_url, timeout=120000)
        if resp.status == 200:
            ct = resp.headers.get("content-type", "")
            body = await resp.body()
            # PDF 헤더 확인
            if body[:4] == b"%PDF" or "pdf" in ct.lower():
                dest.write_bytes(body)
                return True
            # 200이지만 PDF 아님 (로그인 redirect HTML 등)
            return False
        return False
    except Exception as e:
        print(f"      [ERR] {type(e).__name__}: {e}")
        return False


async def scan_and_download(page: Page):
    """2022~현재까지 모든 bdate/bcode 조합 탐색 후 다운로드."""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    months = list(gen_months(SCAN_START, SCAN_END))
    total_months = len(months)
    print(f"\n[4] 과월호 탐색 시작: {months[0]}~{months[-1]} ({total_months}개월)")

    total_ok = total_skip = total_fail = 0
    found_issues = []

    for mi, bdate in enumerate(months, 1):
        year = bdate[:4]
        month = bdate[4:]

        for bcode in BOOK_CODES:
            book_name = BOOK_NAMES[bcode]

            # 뷰어 확인 (Volume=02 기준)
            classes = await check_issue_exists(page, bdate, bcode, "02")
            if not classes:
                continue

            issue_label = f"{year}년{month}월_{book_name}"
            print(f"\n  [{mi}/{total_months}] {issue_label} — 섹션: {classes}")
            found_issues.append((bdate, bcode, classes, issue_label))

            issue_dir = SAVE_DIR / issue_label
            issue_dir.mkdir(exist_ok=True)

            for cls in classes:
                cls_name = CLASS_NAMES.get(cls, f"sec{cls}")
                pdf_url  = f"{FILE_URL}/{bcode}/{bdate}/{cls}"
                fname    = f"{issue_label}_{cls_name}.pdf"
                dest     = issue_dir / fname

                if dest.exists():
                    print(f"      [SKIP] {fname}")
                    total_skip += 1
                    continue

                ok = await download_pdf(page, pdf_url, dest)
                if ok is True:
                    sz = dest.stat().st_size / 1024
                    print(f"      [OK] {fname}  ({sz:.0f} KB)")
                    total_ok += 1
                elif ok is None:
                    total_skip += 1
                else:
                    print(f"      [FAIL] {fname}")
                    total_fail += 1

    print(f"\n탐색 완료: {len(found_issues)}개 이슈 발견")
    return total_ok, total_skip, total_fail


async def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"저장 경로: {SAVE_DIR}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)

        page = await login_and_open_elib(context)
        if not page:
            await browser.close()
            return

        ok, skip, fail = await scan_and_download(page)
        await browser.close()

    print(f"\n완료: OK={ok} / SKIP={skip} / FAIL={fail}")
    files = list(SAVE_DIR.rglob("*.pdf"))
    print(f"저장된 PDF: {len(files)}개")


if __name__ == "__main__":
    asyncio.run(main())
