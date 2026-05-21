"""KFMA 소방시설관리협회 서식 수집 - 세션 기반"""
import requests
from bs4 import BeautifulSoup
from pathlib import Path
import zipfile, io, re

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"
FIRE_DIR = BASE / "소방시설법_시행규칙"
FIRE_DIR.mkdir(parents=True, exist_ok=True)

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

s = requests.Session()
s.headers.update(H)

# 메인 방문으로 세션 초기화
print("KFMA 메인 방문...")
r0 = s.get("https://www.kfma.kr", timeout=15)
print(f"  메인: {r0.status_code}, {len(r0.content)}bytes")

# 서식자료실 방문
print("서식자료실 방문...")
r1 = s.get("https://www.kfma.kr/kfma/bbs/format",
            headers={"Referer": "https://www.kfma.kr/"}, timeout=15)
print(f"  서식자료실: {r1.status_code}, {len(r1.content)}bytes")

# 게시물 상세 방문
for ntt_id, fname_base in [(40830, "KFMA_소방자체점검결과보고서및점검표"),
                            (40827, "KFMA_소방자체점검기록표_2022개정")]:
    print(f"\nnttId={ntt_id} 상세 방문...")
    r2 = s.get(
        f"https://www.kfma.kr/kfma/bbs/format/detail?nttId={ntt_id}",
        headers={"Referer": "https://www.kfma.kr/kfma/bbs/format"},
        timeout=15
    )
    print(f"  상태: {r2.status_code}, {len(r2.content)}bytes")

    soup = BeautifulSoup(r2.text, "html.parser")
    # 제목
    title_el = soup.find(["h1", "h2", "h3", ".title", ".subject"])
    print(f"  제목: {title_el.get_text(strip=True)[:60] if title_el else '없음'}")

    # 다운로드 링크
    dl_links = soup.find_all("a", href=re.compile(r"(fileDownload|download|\.hwp|\.pdf)", re.I))
    print(f"  다운로드 링크 {len(dl_links)}개")
    for i, lnk in enumerate(dl_links):
        href = lnk.get("href", "")
        txt = lnk.get_text(strip=True)[:50]
        full = "https://www.kfma.kr" + href if href.startswith("/") else href
        print(f"    [{i}] [{txt}] {full}")

        r3 = s.get(full, headers={"Referer": f"https://www.kfma.kr/kfma/bbs/format/detail?nttId={ntt_id}"},
                   timeout=20, allow_redirects=True)
        d = r3.content
        print(f"    다운로드: {r3.status_code}, {len(d)}bytes, CT={r3.headers.get('Content-Type')}")
        print(f"    CD={r3.headers.get('Content-Disposition')}")

        if len(d) > 1000 and b"<!DOCTYPE" not in d[:100]:
            ext = detect_ext(d)
            out = FIRE_DIR / f"{fname_base}_{i}{ext}"
            out.write_bytes(d)
            print(f"    SAVED: {out.name} ({len(d)//1024}KB)")

    # 전체 HTML에서 패턴 검색
    import re as re2
    patterns = re2.findall(r'href="([^"]*(?:download|file|hwp|pdf)[^"]*)"', r2.text, re2.I)
    if patterns:
        print(f"  HTML 패턴 매치: {patterns[:5]}")
