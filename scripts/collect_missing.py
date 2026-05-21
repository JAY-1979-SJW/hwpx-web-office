"""
미수집 5건 추가 수집
- 건설기술진흥법 시행규칙 별지 제32호의2서식 (lsiSeq=279455)
- 건축법 시행규칙 별지 제22호의4서식, 22호의5서식 (lsiSeq=283727)
- 소방시설공사업법 시행규칙 별지 제15호서식 (lsiSeq=282735)
- 소방시설법 시행규칙 별지 제7호서식, 제8호서식 (lsiSeq=280195)
"""
import time, re, zipfile, io
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"

TARGETS = [
    # (lsiSeq, 서식번호 키워드, 저장경로, 파일명)
    (279455, "제32호의2서식",  "건설일반/감리원_배치",   "서식32의2_시공단계_건설사업관리계획_제출서.hwp"),
    (283727, "제22호의4서식",  "건축/허가감리",          "서식22의4_공사_감리자_지정통보서.hwp"),
    (283727, "제22호의5서식",  "건축/허가감리",          "서식22의5_허가권자_지정_감리대상_건축물_제외_신청서.hwp"),
    (282735, "제15호서식",     "소방/공사감리_배치",     "서식15_소방시설_착공및완공대장.hwp"),
    (280195, "제7호서식",      "소방/자체점검",          "서식7_소방시설_자체점검_면제연기_신청서.hwp"),
    (280195, "제8호서식",      "소방/자체점검",          "서식8_소방시설_자체점검_면제연기_신청결과_통지서.hwp"),
]

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

saved = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
        accept_downloads=True,
    )
    page = ctx.new_page()

    # 네트워크 요청 캡처 (flSeq 확인용)
    captured_urls = []
    def on_request(req):
        if "flSeq" in req.url or "flDownload" in req.url:
            captured_urls.append(req.url)
    page.on("request", on_request)

    current_lsi = None

    for lsi_seq, form_no_kw, save_subdir, fname in TARGETS:
        print(f"\n[{form_no_kw}] lsiSeq={lsi_seq}")

        # 법령 페이지 진입 (lsiSeq 바뀔 때만)
        if lsi_seq != current_lsi:
            page.goto(
                f"https://www.law.go.kr/lsInfoP.do?lsiSeq={lsi_seq}",
                wait_until="networkidle", timeout=30000
            )
            time.sleep(2)
            current_lsi = lsi_seq
            print(f"  페이지 로드: {page.title()[:50]}")

        # 별지서식 탭 클릭 (탭이 있는 경우)
        try:
            tab = page.query_selector("a:has-text('별지서식'), li:has-text('별지서식') a")
            if tab:
                tab.click()
                time.sleep(1.5)
        except:
            pass

        # 해당 서식 링크 찾기
        form_link = None
        all_els = page.query_selector_all("a, button, span, td, li")
        for el in all_els:
            txt = el.inner_text().strip()
            if form_no_kw in txt:
                form_link = el
                print(f"  발견: {txt[:60]}")
                break

        if not form_link:
            print(f"  ✗ 서식 링크 없음 — flSeq 스캔으로 시도")
            continue

        # flSeq 추출 시도
        onclick = form_link.get_attribute("onclick") or ""
        href = form_link.get_attribute("href") or ""
        fl_match = re.search(r"flSeq['\",=\s]+(\d+)", onclick + href)
        fl_seq = fl_match.group(1) if fl_match else ""

        if not fl_seq:
            # HTML 전체에서 해당 서식 주변 flSeq 탐색
            html = page.content()
            # 서식명 주변 flSeq 찾기
            idx = html.find(form_no_kw)
            if idx > 0:
                snippet = html[max(0,idx-200):idx+300]
                m = re.search(r"flSeq['\",=\s]+(\d+)", snippet)
                if m:
                    fl_seq = m.group(1)
                    print(f"  HTML에서 flSeq={fl_seq} 발견")

        if fl_seq:
            print(f"  flSeq={fl_seq} → 다운로드 시도")
            import requests
            H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.law.go.kr/"}
            r = requests.get(
                f"https://www.law.go.kr/flDownload.do?flSeq={fl_seq}",
                headers=H, timeout=25, allow_redirects=True
            )
            d = r.content
            print(f"  응답: {r.status_code}, {len(d)}bytes, CT={r.headers.get('Content-Type','')[:40]}")

            if r.status_code == 200 and len(d) > 500 and b"<!DOCTYPE" not in d[:100]:
                ext = detect_ext(d)
                out_name = fname.rsplit(".", 1)[0] + ext
                out = BASE / save_subdir / out_name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(d)
                print(f"  SAVED: {out.name} ({len(d)//1024}KB)")
                saved.append({"file": str(out.relative_to(BASE)), "size_kb": len(d)//1024})
            else:
                print(f"  다운로드 실패: {d[:200]}")
        else:
            # onclick 클릭으로 다운로드 인터셉트
            print(f"  flSeq 없음 → 클릭으로 다운로드 시도")
            try:
                captured_urls.clear()
                with ctx.expect_event("response", timeout=10000) as resp_info:
                    form_link.click()
                time.sleep(2)
                # 클릭 후 캡처된 URL 확인
                for url in captured_urls:
                    m = re.search(r"flSeq=(\d+)", url)
                    if m:
                        fl_seq = m.group(1)
                        print(f"  클릭으로 flSeq={fl_seq} 획득")
                        break
                if fl_seq:
                    import requests
                    H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.law.go.kr/"}
                    r = requests.get(
                        f"https://www.law.go.kr/flDownload.do?flSeq={fl_seq}",
                        headers=H, timeout=25, allow_redirects=True
                    )
                    d = r.content
                    if r.status_code == 200 and len(d) > 500 and b"<!DOCTYPE" not in d[:100]:
                        ext = detect_ext(d)
                        out_name = fname.rsplit(".", 1)[0] + ext
                        out = BASE / save_subdir / out_name
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(d)
                        print(f"  SAVED: {out.name} ({len(d)//1024}KB)")
                        saved.append({"file": str(out.relative_to(BASE)), "size_kb": len(d)//1024})
            except Exception as e:
                print(f"  클릭 시도 실패: {e}")

        time.sleep(0.5)

    browser.close()

print(f"\n완료: {len(saved)}건 저장")
for s in saved:
    print(f"  {s['file']} ({s['size_kb']}KB)")

# 남은 미수집 항목 출력
not_saved = [(kw, fn) for _, kw, _, fn in TARGETS
             if not any(fn.rsplit(".",1)[0] in s["file"] for s in saved)]
if not_saved:
    print(f"\n미저장 {len(not_saved)}건:")
    for kw, fn in not_saved:
        print(f"  {kw} → {fn}")
