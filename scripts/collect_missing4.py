"""Playwright로 HTML 가져와서 fncLsLawPop flSeq 추출 후 다운로드"""
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

# 법령별 HTML 캐시 (중복 로드 방지)
html_cache = {}

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    )
    page = ctx.new_page()

    for lsi_seq, form_no_kw, save_subdir, fname_base in TARGETS:
        if lsi_seq not in html_cache:
            print(f"\n법령 로드: lsiSeq={lsi_seq}")
            page.goto(f"https://www.law.go.kr/lsInfoP.do?lsiSeq={lsi_seq}",
                      wait_until="networkidle", timeout=30000)
            time.sleep(3)
            html_cache[lsi_seq] = page.content()
            print(f"  HTML 크기: {len(html_cache[lsi_seq])}")

        html = html_cache[lsi_seq]
        print(f"\n[{form_no_kw}] 검색")

        # 서식번호 텍스트
        no_m = re.search(r"제(\d+호[의\d]*)서식", form_no_kw)
        form_no_raw = no_m.group(0) if no_m else form_no_kw

        fl_seq = None

        # 방법1: "별지 제N호서식" 텍스트 앞에 있는 fncLsLawPop
        # <a href="..." onclick="javascript:fncLsLawPop('1234567890','BF','')">별지 제15호서식</a>
        m1 = re.search(
            r"fncLsLawPop\s*\(['\"](\d+)['\"][^)]*\)[^>]*>[^<]*" + re.escape(form_no_raw),
            html
        )
        if m1:
            fl_seq = m1.group(1)
            print(f"  방법1: flSeq={fl_seq}")

        # 방법2: 서식번호 텍스트 앞에 onclick
        if not fl_seq:
            # 전체 HTML에서 서식번호 위치 찾기
            for idx_start in range(0, len(html)):
                idx = html.find(form_no_raw, idx_start)
                if idx == -1:
                    break
                snippet = html[max(0, idx-300):idx+50]
                m2 = re.search(r"fncLsLawPop\s*\(['\"](\d+)['\"]", snippet)
                if m2:
                    fl_seq = m2.group(1)
                    print(f"  방법2: flSeq={fl_seq} (pos={idx})")
                    break
                idx_start = idx + 1

        # 방법3: 전체 onclick 목록에서 순서로 추출
        if not fl_seq:
            # 모든 "별지 제N호서식" → flSeq 매핑 생성
            all_pairs = re.findall(
                r"fncLsLawPop\s*\(['\"](\d+)['\"][^)]*\)[^>]*>([^<]{0,80})",
                html
            )
            print(f"  전체 fncLsLawPop 쌍: {len(all_pairs)}개")
            for fl, txt in all_pairs:
                txt = txt.strip()
                if form_no_raw in txt:
                    fl_seq = fl
                    print(f"  방법3: flSeq={fl_seq} ({txt[:40]})")
                    break
            if not fl_seq and all_pairs:
                # 샘플 출력
                for fl, txt in all_pairs[:5]:
                    print(f"    sample: [{txt.strip()[:40]}] fl={fl}")

        if not fl_seq:
            print(f"  ✗ flSeq 못 찾음")
            continue

        # 다운로드
        r = requests.get(f"https://www.law.go.kr/flDownload.do?flSeq={fl_seq}",
                         headers=H, timeout=25, allow_redirects=True)
        d = r.content
        print(f"  다운로드: {r.status_code}, {len(d)}bytes")

        if r.status_code == 200 and len(d) > 500 and b"<!DOCTYPE" not in d[:100]:
            ext = detect_ext(d)
            out = BASE / save_subdir / (fname_base + ext)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(d)
            print(f"  SAVED: {out.name} ({len(d)//1024}KB)")
            saved.append(out.name)
        else:
            print(f"  실패")

    browser.close()

print(f"\n완료: {len(saved)}건")
for f in saved:
    print(f"  {f}")
