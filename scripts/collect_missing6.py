"""
law.go.kr 별지서식 수집 - Playwright 세션 + 네트워크 요청 캡처 방식
fncLsLawPop 클릭 → lsBylInfoPLinkR.do URL 캡처 → flSeq 추출 → Playwright로 직접 다운로드
"""
import time, re, zipfile, io
from pathlib import Path
from playwright.sync_api import sync_playwright

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

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
        accept_downloads=True,
    )

    # 법령 HTML 캐시
    html_cache = {}
    # 팝업 URL 캐시 (클릭 후 캡처된 lsBylInfoPLinkR.do URL)
    link_url_cache = {}  # (lsi_seq, form_no_raw) -> url

    page = ctx.new_page()

    # 네트워크 요청 리스너: lsBylInfoPLinkR.do 요청 캡처
    captured_requests = {}  # popup_id -> url
    def on_request(req):
        if "lsBylInfoPLinkR" in req.url or "flSeq" in req.url or "flDownload" in req.url:
            print(f"  [NET] {req.url[:120]}")
    page.on("request", on_request)

    for lsi_seq, form_no_kw, save_subdir, fname_base in TARGETS:
        print(f"\n[{form_no_kw}] lsiSeq={lsi_seq}")

        # 서식번호 파싱
        no_m = re.search(r"제(\d+호[의\d]*)서식", form_no_kw)
        form_no_raw = no_m.group(0) if no_m else form_no_kw

        # 법령 페이지 로드 (캐시)
        if lsi_seq not in html_cache:
            page.goto(f"https://www.law.go.kr/lsInfoP.do?lsiSeq={lsi_seq}",
                      wait_until="networkidle", timeout=30000)
            time.sleep(2)
            html_cache[lsi_seq] = True
            print(f"  법령 페이지 로드 완료")
        else:
            # 같은 lsi_seq면 이미 있는 페이지에서 진행 (다른 lsi_seq면 재이동)
            if lsi_seq not in [t[0] for t in TARGETS if t[1] != form_no_kw]:
                pass  # 이미 같은 페이지
            current_url = page.url
            if str(lsi_seq) not in current_url:
                page.goto(f"https://www.law.go.kr/lsInfoP.do?lsiSeq={lsi_seq}",
                          wait_until="networkidle", timeout=30000)
                time.sleep(2)

        # 별지서식 탭 클릭 (아직 안 한 경우)
        tab_key = f"tab_{lsi_seq}"
        if tab_key not in html_cache:
            for el in page.query_selector_all("a, li, span, button"):
                try:
                    txt = el.inner_text().strip()
                    if "별지서식" in txt and len(txt) < 20:
                        el.click()
                        time.sleep(2)
                        print(f"  별지서식 탭 클릭")
                        html_cache[tab_key] = True
                        break
                except:
                    pass

        # form_no_raw 링크 찾아서 클릭 + 팝업/응답 캡처
        fl_seq = None

        # 팝업 페이지 캡처
        popup_pages = []
        ctx.on("page", lambda p: popup_pages.append(p))

        # lsBylInfoPLinkR.do 캡처용 요청 리스너
        captured_link_urls = []
        def on_req_capture(req):
            if "lsBylInfoPLinkR" in req.url:
                captured_link_urls.append(req.url)
                print(f"  [CAPTURE] {req.url[:120]}")
        page.on("request", on_req_capture)

        # 서식 링크 클릭
        clicked = False
        for el in page.query_selector_all("a"):
            try:
                txt = el.inner_text().strip()
                if form_no_raw in txt:
                    print(f"  클릭: [{txt[:50]}]")
                    el.click()
                    time.sleep(4)
                    clicked = True
                    break
            except:
                pass

        if not clicked:
            print(f"  ✗ 링크 못 찾음")
            page.remove_listener("request", on_req_capture)
            continue

        # 캡처된 lsBylInfoPLinkR.do URL에서 flSeq 추출
        for link_url in captured_link_urls:
            # 직접 fetch해서 flSeq 찾기
            # Playwright로 새 탭에서 열기
            p2 = ctx.new_page()
            p2.goto(link_url, wait_until="networkidle", timeout=20000)
            time.sleep(2)
            p2_html = p2.content()
            m_fl = re.search(r"flSeq[='\",:\s]+(\d{7,10})", p2_html)
            if m_fl:
                fl_seq = m_fl.group(1)
                print(f"  lsBylInfoPLinkR에서 flSeq={fl_seq}")
            p2.close()
            if fl_seq:
                break

        # 팝업에서도 시도
        if not fl_seq:
            for pop in popup_pages:
                try:
                    pop.wait_for_load_state("networkidle", timeout=10000)
                    pop_html = pop.content()
                    m_fl = re.search(r"flSeq[='\",:\s]+(\d{7,10})", pop_html)
                    if m_fl:
                        fl_seq = m_fl.group(1)
                        print(f"  팝업에서 flSeq={fl_seq}")
                        break
                except Exception as e:
                    print(f"  팝업 오류: {e}")

        page.remove_listener("request", on_req_capture)

        if not fl_seq:
            print(f"  ✗ flSeq 못 찾음")
            continue

        # Playwright로 직접 다운로드
        print(f"  flSeq={fl_seq} 다운로드 시도")
        dl_page = ctx.new_page()
        try:
            with dl_page.expect_download(timeout=30000) as dl_info:
                dl_page.goto(f"https://www.law.go.kr/flDownload.do?flSeq={fl_seq}")
            dl = dl_info.value
            out_dir = BASE / save_subdir
            out_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = out_dir / ("_tmp_" + fname_base)
            dl.save_as(str(tmp_path))
            d = tmp_path.read_bytes()
            ext = detect_ext(d)
            out = out_dir / (fname_base + ext)
            tmp_path.rename(out)
            print(f"  SAVED: {out.name} ({len(d)//1024}KB)")
            saved.append(out.name)
        except Exception as e:
            print(f"  다운로드 예외: {e}")
            # fallback: page content 방식
            try:
                dl_page.goto(f"https://www.law.go.kr/flDownload.do?flSeq={fl_seq}",
                             wait_until="networkidle", timeout=20000)
                # body 내용 직접 확인
                content = dl_page.content()
                print(f"  응답 HTML 크기: {len(content)}")
                m_fl2 = re.search(r"flSeq[='\",:\s]+(\d{7,10})", content)
                if m_fl2:
                    print(f"  페이지 내 다른 flSeq: {m_fl2.group(1)}")
            except Exception as e2:
                print(f"  fallback 오류: {e2}")
        finally:
            dl_page.close()

    browser.close()

# 기존에 저장된 잘못된 .bin 파일 정리
print("\n--- .bin 파일 정리 ---")
for subdir in BASE.rglob("*.bin"):
    d = subdir.read_bytes()
    if d[:4] == bytes([0x47, 0x49, 0x46, 0x38]):  # GIF
        print(f"  GIF 오류 파일 삭제: {subdir}")
        subdir.unlink()
    else:
        ext = detect_ext(d)
        if ext != ".bin":
            new_path = subdir.with_suffix(ext)
            subdir.rename(new_path)
            print(f"  확장자 수정: {subdir.name} → {new_path.name}")

print(f"\n완료: {len(saved)}건")
for f in saved:
    print(f"  {f}")
