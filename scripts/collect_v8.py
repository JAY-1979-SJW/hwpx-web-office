"""
lsLawLinkInfo.do → lsBylInfoPLinkR.do → hanFlSeq 추출 → Playwright HWP 버튼 클릭 다운로드
허용 형식: .hwp .hwpx .pdf .xlsx 만 저장 / GIF·HTML 등 비문서 파일은 저장 안 함
"""
import sys, time, re, zipfile, io
from pathlib import Path
from playwright.sync_api import sync_playwright

# 로거 설정 (collect_logger.py 와 같은 디렉터리)
sys.path.insert(0, str(Path(__file__).parent))
try:
    from collect_logger import get_logger
    log = get_logger("collect_v8")
except ImportError:
    import logging; log = logging.getLogger("collect_v8"); logging.basicConfig(level=logging.INFO)

BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"

# 허용 문서 형식 매직 바이트
ALLOWED_SIGS = {
    bytes([0xd0, 0xcf, 0x11, 0xe0]): ".hwp",   # HWP (OLE)
    b"%PDF": ".pdf",
}
ALLOWED_PK_MARKER = "xl/"    # PK 안에 xl/ 있으면 .xlsx

TARGETS = [
    ("1030332361", "건설일반/감리원_배치",  "서식32의2_시공단계_건설사업관리계획_제출서"),
    ("1032198965", "건축/허가감리",         "서식22의4_공사_감리자_지정통보서"),
    ("1032199313", "건축/허가감리",         "서식22의5_허가권자_지정_감리대상_건축물_제외_신청서"),
    ("1031441625", "소방/공사감리_배치",    "서식15_소방시설_착공및완공대장"),
    ("1030669543", "소방/자체점검",         "서식7_소방시설_자체점검_면제연기_신청서"),
    ("1030669545", "소방/자체점검",         "서식8_소방시설_자체점검_면제연기_신청결과_통지서"),
]


def detect_doc_ext(data: bytes):
    """문서 형식이면 확장자 반환, 아니면 None"""
    if len(data) < 4:
        return None
    sig4 = data[:4]
    if sig4 == bytes([0xd0, 0xcf, 0x11, 0xe0]):
        return ".hwp"
    if sig4 == b"%PDF":
        return ".pdf"
    if data[:2] == b"PK":
        try:
            names = " ".join(zipfile.ZipFile(io.BytesIO(data)).namelist())
            if "xl/" in names:
                return ".xlsx"
            return ".hwpx"
        except:
            return None
    return None


saved = []
failed = []

log.info("수집 시작: %d건", len(TARGETS))

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
        accept_downloads=True,
    )

    for lsJoLnkSeq, save_subdir, fname_base in TARGETS:
        log.info("수집 시작: %s (lsJoLnkSeq=%s)", fname_base, lsJoLnkSeq)

        # 1단계: lsLawLinkInfo.do → lsBylInfoPLinkR.do 리다이렉트 → hanFlSeq 추출
        info_page = ctx.new_page()
        info_page.goto(
            f"https://www.law.go.kr/lsLawLinkInfo.do?lsJoLnkSeq={lsJoLnkSeq}",
            wait_until="networkidle", timeout=20000
        )
        time.sleep(2)
        html = info_page.content()
        info_page.close()

        # hanFlSeq hidden input = 실제 HWP 파일 (flSeq는 뷰어용 이미지)
        m = re.search(r'id="hanFlSeq"[^>]*value="(\d{6,10})"', html)
        if not m:
            m = re.search(r'name="hanFlSeq"[^>]*value="(\d{6,10})"', html)
        if not m:
            log.warning("hanFlSeq 없음 — %s (HTML %d bytes)", fname_base, len(html))
            failed.append(fname_base)
            continue

        fl_seq = m.group(1)
        log.debug("hanFlSeq=%s (%s)", fl_seq, fname_base)

        # 2단계: lsBylInfoPLinkR.do 페이지에서 HWP 버튼(setDownBtn('1')) 클릭 → 다운로드
        popup_page = ctx.new_page()
        popup_page.goto(
            f"https://www.law.go.kr/lsLawLinkInfo.do?lsJoLnkSeq={lsJoLnkSeq}",
            wait_until="networkidle", timeout=20000
        )
        time.sleep(2)

        dl = None
        try:
            with popup_page.expect_download(timeout=25000) as dl_info:
                btn = popup_page.query_selector("a[onclick*=\"setDownBtn('1')\"]")
                if btn:
                    btn.click()
                else:
                    log.warning("HWP 버튼 없음 — fallback LSW 경로 사용 (%s)", fname_base)
                    try:
                        popup_page.goto(
                            f"https://www.law.go.kr/LSW/flDownload.do?flSeq={fl_seq}",
                            wait_until="load", timeout=10000
                        )
                    except Exception as nav_e:
                        if "download" not in str(nav_e).lower():
                            raise
            dl = dl_info.value
        except Exception as e:
            log.error("다운로드 예외 — %s: %s", fname_base, e)

        if dl:
            out_dir = BASE / save_subdir
            out_dir.mkdir(parents=True, exist_ok=True)
            tmp = out_dir / f"_tmp_{fname_base}"
            dl.save_as(str(tmp))
            data = tmp.read_bytes()
            ext = detect_doc_ext(data)

            if ext:
                out = out_dir / (fname_base + ext)
                tmp.rename(out)
                log.info("SAVED: %s (%dKB)", out.name, len(data) // 1024)
                saved.append(out.name)
            else:
                sig = data[:4].hex() if data else "empty"
                log.warning("문서 형식이 아님 — sig=%s %d bytes, 저장 안 함 (%s)", sig, len(data), fname_base)
                tmp.unlink(missing_ok=True)
                failed.append(fname_base)
        else:
            log.error("다운로드 실패 — %s", fname_base)
            failed.append(fname_base)

        popup_page.close()

    browser.close()

log.info("=== 완료: 성공 %d건, 실패 %d건 ===", len(saved), len(failed))
for f in saved:
    log.info("  ✓ %s", f)
for f in failed:
    log.error("  ✗ %s", f)
