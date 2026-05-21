"""
law.go.kr 별지서식 flSeq 추출 - 클릭 후 모든 네트워크 요청 캡처
"""
import time, re, zipfile, io
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"

TARGETS = [
    (279455, "제32호의2서식",  "건설일반/감리원_배치",   "서식32의2_시공단계_건설사업관리계획_제출서"),
    (283727, "제22호의4서식",  "건축/허가감리",          "서식22의4_공사_감리자_지정통보서"),
    (283727, "제22호의5서식",  "건축/허가감리",          "서식22의5_허가권자_지정_감리대상_건축물_제외_신청서"),
    (282735, "제15호서식",     "소방/공사감리_배치",     "서식15_소방시설_착공및완공대장"),
    (280195, "제7호서식",      "소방/자체점검",          "서식7_소방시설_자체점검_면제연기_신청서"),
    (280195, "제8호서식",      "소방/자체점검",          "서식8_소방시설_자체점검_면제연기_신청결과_통지서"),
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
fl_seq_map = {}  # form_no_kw → flSeq

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
        accept_downloads=True,
    )

    # 모든 네트워크 요청 캡처
    all_requests = []
    def on_request(req):
        all_requests.append(req.url)

    page = ctx.new_page()
    page.on("request", on_request)

    current_lsi = None

    for lsi_seq, form_no_kw, save_subdir, fname_base in TARGETS:
        print(f"\n[{form_no_kw}] lsiSeq={lsi_seq}")
        all_requests.clear()

        if lsi_seq != current_lsi:
            page.goto(
                f"https://www.law.go.kr/lsInfoP.do?lsiSeq={lsi_seq}",
                wait_until="networkidle", timeout=30000
            )
            time.sleep(3)
            current_lsi = lsi_seq

        # HTML 전체에서 flSeq 추출 시도
        html = page.content()

        # 방법1: 서식명 근처에서 flSeq 찾기
        form_no_digits = re.search(r"제(\d+호[의\d]*)서식", form_no_kw)
        if form_no_digits:
            num_str = form_no_digits.group(1)
            # 해당 번호가 포함된 JavaScript 함수 호출 찾기
            patterns = [
                rf"제{re.escape(num_str)}서식[^<]{{0,200}}flSeq\s*['\",=]+\s*(\d+)",
                rf"flSeq\s*['\",=]+\s*(\d+)[^<]{{0,200}}제{re.escape(num_str)}서식",
            ]
            for pat in patterns:
                m = re.search(pat, html)
                if m:
                    fl_seq_map[form_no_kw] = m.group(1)
                    print(f"  방법1 flSeq={m.group(1)}")
                    break

        # 방법2: 모든 flSeq 후보를 추출 후 인접 텍스트로 매핑
        if form_no_kw not in fl_seq_map:
            # JavaScript 배열/객체에서 bylNm + flSeq 쌍 추출
            pairs = re.findall(
                r"bylNm['\",:\s]+([^'\"<>]{3,60})['\",;\s)]+.*?flSeq['\",:\s]+(\d+)",
                html, re.DOTALL
            )
            if not pairs:
                pairs = re.findall(
                    r"flSeq['\",:\s]+(\d+)['\",;\s)]+.*?bylNm['\",:\s]+([^'\"<>]{3,60})",
                    html, re.DOTALL
                )
                pairs = [(n, s) for s, n in pairs]

            for nm, fl in pairs:
                for kw, _, _, _ in TARGETS:
                    no_m = re.search(r"제(\d+호[의\d]*)서식", kw)
                    if no_m and no_m.group(0) in nm:
                        fl_seq_map[kw] = fl
                        print(f"  방법2 [{kw}] flSeq={fl} from '{nm[:40]}'")

        # 방법3: 클릭 후 lsBylContentsInfoR.do 요청 캡처
        if form_no_kw not in fl_seq_map:
            print(f"  방법3: 클릭으로 요청 캡처")
            all_requests.clear()
            form_link = None
            for el in page.query_selector_all("a, span, td, li, button"):
                txt = el.inner_text().strip()
                if form_no_kw in txt:
                    form_link = el
                    break

            if form_link:
                try:
                    form_link.click()
                    time.sleep(3)
                    # 캡처된 요청에서 flSeq 찾기
                    for url in all_requests:
                        m = re.search(r"flSeq=(\d+)", url)
                        if m:
                            fl_seq_map[form_no_kw] = m.group(1)
                            print(f"  방법3 캡처 flSeq={m.group(1)} from {url[:80]}")
                            break
                    if form_no_kw not in fl_seq_map:
                        print(f"  캡처된 요청들:")
                        for url in all_requests[-10:]:
                            print(f"    {url[:100]}")
                except Exception as e:
                    print(f"  클릭 오류: {e}")

    browser.close()

print(f"\n--- flSeq 수집 결과 ---")
for kw, fl in fl_seq_map.items():
    print(f"  {kw}: {fl}")

# flSeq로 다운로드
import requests as req_lib
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.law.go.kr/"}

for lsi_seq, form_no_kw, save_subdir, fname_base in TARGETS:
    fl_seq = fl_seq_map.get(form_no_kw)
    if not fl_seq:
        print(f"\n✗ [{form_no_kw}] flSeq 없음, 건너뜀")
        continue

    print(f"\n[{form_no_kw}] flSeq={fl_seq} 다운로드")
    r = req_lib.get(
        f"https://www.law.go.kr/flDownload.do?flSeq={fl_seq}",
        headers=H, timeout=25, allow_redirects=True
    )
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
        print(f"  실패: {d[:200]}")

print(f"\n완료: {len(saved)}건")
for f in saved:
    print(f"  {f}")
