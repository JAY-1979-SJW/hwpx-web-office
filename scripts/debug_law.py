"""law.go.kr 별지서식 클릭 동작 디버깅"""
import time, re
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
        accept_downloads=True,
    )

    # 모든 요청/응답 로깅
    all_urls = []
    def log_req(req):
        all_urls.append(f"REQ {req.method} {req.url}")
    def log_resp(resp):
        ct = resp.headers.get("content-type", "")
        if resp.status != 200 or any(k in resp.url for k in ["flSeq", "bly", "Byl", "download", "Download"]):
            all_urls.append(f"RESP {resp.status} [{ct[:30]}] {resp.url}")

    page = ctx.new_page()
    page.on("request", log_req)
    page.on("response", log_resp)

    # 소방시설공사업법 시행규칙 (lsiSeq=282735) - 별지 제15호서식 찾기
    page.goto("https://www.law.go.kr/lsInfoP.do?lsiSeq=282735",
              wait_until="networkidle", timeout=30000)
    time.sleep(3)

    print(f"Title: {page.title()}")
    print(f"URL: {page.url}")

    # 별지서식 관련 요소 확인
    html = page.content()
    print(f"\nHTML 크기: {len(html)}")

    # flSeq 후보 추출
    fl_seqs = re.findall(r"flSeq['\",=:\s]+(\d+)", html)
    print(f"flSeq 후보: {fl_seqs[:20]}")

    # 별지서식 iframe 확인
    frames = page.frames
    print(f"\n프레임 수: {len(frames)}")
    for f in frames:
        print(f"  Frame: {f.url[:80]}")

    # 별지서식 탭 찾기
    print("\n--- 별지 관련 요소 ---")
    for el in page.query_selector_all("a, button, li, span"):
        txt = el.inner_text().strip()
        if "별지서식" in txt or "별지" in txt[:10]:
            onclick = el.get_attribute("onclick") or ""
            href = el.get_attribute("href") or ""
            print(f"  [{txt[:40]}] onclick={onclick[:60]} href={href[:60]}")

    # '별지서식' 탭 클릭
    print("\n--- 별지서식 탭 클릭 시도 ---")
    all_urls.clear()
    byls_tabs = page.query_selector_all("a, li, span, button")
    byls_tab = None
    for el in byls_tabs:
        if "별지서식" in el.inner_text():
            byls_tab = el
            break

    if byls_tab:
        print(f"탭 발견: {byls_tab.inner_text()[:40]}")
        byls_tab.click()
        time.sleep(3)
        for url in all_urls[-20:]:
            print(f"  {url}")

        # 클릭 후 HTML 재분석
        html2 = page.content()
        fl_seqs2 = re.findall(r"flSeq['\",=:\s]+(\d+)", html2)
        print(f"\n클릭 후 flSeq 후보: {fl_seqs2[:20]}")

        # 15호서식 찾기
        idx = html2.find("제15호서식")
        if idx > 0:
            snippet = html2[max(0,idx-300):idx+300]
            print(f"\n15호서식 주변:\n{snippet}")

    # 새 팝업 감지
    print("\n--- 팝업 페이지 감지 ---")
    popup_detected = []
    ctx.on("page", lambda p: popup_detected.append(p))

    # 15호서식 직접 클릭
    all_urls.clear()
    for el in page.query_selector_all("a, span, td, li, button"):
        if "제15호서식" in el.inner_text():
            print(f"클릭: {el.inner_text()[:40]}")
            el.click()
            time.sleep(3)
            break

    print(f"팝업: {len(popup_detected)}개")
    for p in popup_detected:
        print(f"  팝업 URL: {p.url}")
        print(f"  팝업 HTML:\n{p.content()[:500]}")

    print(f"\n클릭 후 네트워크:")
    for url in all_urls:
        print(f"  {url}")

    # 현재 페이지 iframe 재확인
    for f in page.frames:
        if f.url and "law.go.kr" in f.url:
            print(f"\nFrame {f.url[:80]}:")
            f_html = f.content()
            print(f"  크기: {len(f_html)}")
            fl = re.findall(r"flSeq['\",=:\s]+(\d+)", f_html)
            print(f"  flSeq: {fl[:10]}")

    browser.close()
