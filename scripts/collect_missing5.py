"""
fncLsLawPop 클릭 → 팝업 캡처 → 팝업 내 다운로드 링크 추출
"""
import time, re, zipfile, io, requests
from pathlib import Path
from playwright.sync_api import sync_playwright

H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.law.go.kr/"}
BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"

TARGETS = [
    (279455, "제32호의2서식",  "건설일반/감리원_배치",  "서식32의2_시공단계_건설사업관리계획_제출서"),
    (283727, "제22호의4서식",  "건축/허가감리",         "서식22의4_공사_감리자_지정통보서"),
    (283727, "제22호의5서식",  "건축/허가감리",         "서식22의5_허가권자_지정_감리대상_건축물_제외_신청서"),
    (282735, "제15호서식",     "소방/공사감리_배치",    "서식15_소방시설_착공및완공대장"),
    (280195, "제7호서식",      "소방/자체점검",         "서식7_소방시설_자체점검_면제연기_신청서"),
    (280195, "제8호서식",      "소방/자체점검",         "서식8_소방시설_자체점검_면제연기_신청결과_통지서"),
]

def detect_ext(data):
    if data[:4] == b"%PDF": return ".pdf"
    if data[:4] == bytes([0xd0, 0xcf, 0x11, 0xe0]): return ".hwp"
    if data[:2] == b"PK":
        try:
            ns = " ".join(zipfile.ZipFile(io.BytesIO(data)).namelist())
            return ".xlsx" if "xl/" in ns else ".hwpx"
        except: return ".zip"
    return ".bin"

saved = []
html_cache = {}

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
        accept_downloads=True,
    )
    page = ctx.new_page()

    for lsi_seq, form_no_kw, save_subdir, fname_base in TARGETS:
        print(f"\n[{form_no_kw}] lsiSeq={lsi_seq}")

        if lsi_seq not in html_cache:
            page.goto(f"https://www.law.go.kr/lsInfoP.do?lsiSeq={lsi_seq}",
                      wait_until="networkidle", timeout=30000)
            time.sleep(3)
            html_cache[lsi_seq] = page.content()
        else:
            if page.url != f"https://www.law.go.kr/lsInfoP.do?lsiSeq={lsi_seq}#0000":
                page.goto(f"https://www.law.go.kr/lsInfoP.do?lsiSeq={lsi_seq}",
                          wait_until="networkidle", timeout=30000)
                time.sleep(3)

        html = html_cache[lsi_seq]

        # 서식번호로 flSeq(popup ID) 추출
        no_m = re.search(r"제(\d+호[의\d]*)서식", form_no_kw)
        form_no_raw = no_m.group(0) if no_m else form_no_kw

        m = re.search(
            r"fncLsLawPop\s*\(['\"](\d+)['\"][^)]*\)[^>]*>[^<]*" + re.escape(form_no_raw),
            html
        )
        popup_id = m.group(1) if m else None

        if not popup_id:
            print(f"  ✗ popup_id 없음")
            continue
        print(f"  popup_id={popup_id}")

        # 팝업 URL 직접 구성 시도
        # law.go.kr 팝업은 보통 /lsBylInfoP.do?lsiSeq=...&bylSeq=... 또는
        # /lsBylContentsInfoR.do 계열
        popup_urls_to_try = [
            f"https://www.law.go.kr/lsBylInfoP.do?lsiSeq={lsi_seq}&bylSeq={popup_id}&bylClsCd=BF",
            f"https://www.law.go.kr/lsLinkLawPop.do?lsiSeq={lsi_seq}&chrClsCd={popup_id}",
            f"https://www.law.go.kr/lsBylContentsInfoR.do?lsiSeq={lsi_seq}&bylSeq={popup_id}",
        ]

        dl_url = None
        for pu in popup_urls_to_try:
            r = requests.get(pu, headers=H, timeout=15)
            # flSeq 패턴 찾기
            m_fl = re.search(r"flSeq=(\d+)", r.text)
            if m_fl:
                dl_url = f"https://www.law.go.kr/flDownload.do?flSeq={m_fl.group(1)}"
                print(f"  직접 URL에서 flSeq={m_fl.group(1)}: {pu}")
                break
            elif r.status_code == 200 and len(r.content) > 1000:
                print(f"  {pu}: {r.status_code}, {len(r.content)}bytes (flSeq없음)")

        # 팝업 Playwright 클릭으로 캡처
        if not dl_url:
            print(f"  Playwright 팝업 클릭")
            popup_pages = []
            ctx.on("page", lambda p: popup_pages.append(p))

            # 서식 링크 클릭
            for el in page.query_selector_all("a"):
                txt = el.inner_text().strip()
                if form_no_raw in txt:
                    el.click()
                    time.sleep(3)
                    break

            for pop in popup_pages:
                pop_url = pop.url
                print(f"  팝업 URL: {pop_url}")
                pop.wait_for_load_state("networkidle", timeout=15000)
                pop_html = pop.content()
                print(f"  팝업 HTML: {len(pop_html)}bytes")

                # flSeq 탐색
                m_fl2 = re.search(r"flSeq=(\d+)", pop_html)
                if m_fl2:
                    dl_url = f"https://www.law.go.kr/flDownload.do?flSeq={m_fl2.group(1)}"
                    print(f"  팝업에서 flSeq={m_fl2.group(1)}")
                    break

                # 다운로드 버튼
                dl_btn = pop.query_selector("a[href*='flDownload'], button:has-text('다운'), a:has-text('HWP'), a:has-text('다운로드')")
                if dl_btn:
                    dh = dl_btn.get_attribute("href") or ""
                    print(f"  다운 버튼: {dh}")
                    m_fl3 = re.search(r"flSeq=(\d+)", dh)
                    if m_fl3:
                        dl_url = f"https://www.law.go.kr/flDownload.do?flSeq={m_fl3.group(1)}"
                        break

        if dl_url:
            print(f"  다운로드 URL: {dl_url}")
            r = requests.get(dl_url, headers=H, timeout=25, allow_redirects=True)
            d = r.content
            print(f"  {r.status_code}, {len(d)}bytes")
            if r.status_code == 200 and len(d) > 500 and b"<!DOCTYPE" not in d[:100]:
                ext = detect_ext(d)
                out = BASE / save_subdir / (fname_base + ext)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(d)
                print(f"  SAVED: {out.name} ({len(d)//1024}KB)")
                saved.append(out.name)
        else:
            print(f"  ✗ 다운로드 URL 없음")

    browser.close()

print(f"\n완료: {len(saved)}건")
for f in saved:
    print(f"  {f}")
