"""KFMA 서식자료실 네트워크 요청 인터셉트"""
import time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

api_calls = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    )
    page = ctx.new_page()

    # 네트워크 요청 로깅
    def on_request(req):
        if any(k in req.url for k in ["api", "bbs", "list", "json", "ajax"]):
            print(f"REQ: {req.method} {req.url}")

    def on_response(resp):
        if any(k in resp.url for k in ["api", "bbs/12", "json", "ajax"]):
            ct = resp.headers.get("content-type", "")
            size = 0
            try:
                body = resp.body()
                size = len(body)
                if "json" in ct and size > 100:
                    print(f"RESP JSON: {resp.url}\n  {body[:500]}")
                    api_calls.append({"url": resp.url, "size": size, "body": body[:500].decode("utf-8", errors="replace")})
            except:
                pass
            if size > 100 and ("json" in ct or size > 5000):
                print(f"RESP: {resp.status} {resp.url} [{ct}] {size}bytes")

    page.on("request", on_request)
    page.on("response", on_response)

    # 메인 방문
    page.goto("https://www.kfma.kr", wait_until="networkidle", timeout=30000)
    time.sleep(1)

    # 서식자료실 방문
    print("\n=== 서식자료실 방문 ===")
    page.goto("https://www.kfma.kr/bbs/12/list", wait_until="networkidle", timeout=30000)
    time.sleep(5)  # JS 실행 충분히 대기

    print(f"\nHTML 크기: {len(page.content())}")

    # 게시물 링크 재확인
    view_links = page.query_selector_all("a[href*='/bbs/12/view/']")
    print(f"view 링크: {len(view_links)}개")
    for a in view_links[:10]:
        print(f"  [{a.inner_text().strip()[:40]}] {a.get_attribute('href')}")

    # repeater 컨테이너 확인
    rpt = page.query_selector("#repeater, [id*='repeater'], [class*='repeater']")
    if rpt:
        print(f"\nrepeater 내용:\n{rpt.inner_html()[:1000]}")

    # tbody 확인
    tbody = page.query_selector("table tbody")
    if tbody:
        print(f"\ntbody 내용:\n{tbody.inner_html()[:1000]}")

    browser.close()

print(f"\n캡처된 API 호출: {len(api_calls)}건")
for call in api_calls:
    print(f"  {call['url']}")
    print(f"  {call['body'][:200]}")
