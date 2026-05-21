"""KFMA 서식자료실 /bbs/12/list 에서 자체점검 서식 수집"""
import requests
from bs4 import BeautifulSoup
from pathlib import Path
import zipfile, io, re, time

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
BASE_URL = "https://www.kfma.kr"
BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"
FIRE_DIR = BASE / "소방시설법_시행규칙"
FIRE_DIR.mkdir(parents=True, exist_ok=True)

saved = []

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
s.get(BASE_URL, timeout=15)  # 세션 초기화

# 서식자료실 목록 가져오기
r = s.get(f"{BASE_URL}/bbs/12/list", headers={"Referer": BASE_URL}, timeout=15)
print(f"서식자료실: {r.status_code}, {len(r.content)}bytes")
soup = BeautifulSoup(r.text, "html.parser")

# 게시물 링크 찾기
kw = ["자체점검", "점검기록표", "점검표", "보고서", "서식", "별지"]
posts = []
for a in soup.find_all("a", href=re.compile(r"/bbs/12/view/")):
    title = a.get_text(strip=True)
    href = a.get("href", "")
    if any(k in title for k in kw):
        posts.append((title, href))
        print(f"  관련 게시물: [{title}] {href}")

# 전체 게시물도 출력 (확인용)
print(f"\n전체 게시물 목록:")
for a in soup.find_all("a", href=re.compile(r"/bbs/12/view/"))[:20]:
    print(f"  [{a.get_text(strip=True)[:60]}] {a.get('href','')}")

# 관련 게시물에서 파일 다운로드
for title, href in posts:
    full_url = BASE_URL + href if href.startswith("/") else href
    print(f"\n게시물 접근: {title}")
    r2 = s.get(full_url, headers={"Referer": f"{BASE_URL}/bbs/12/list"}, timeout=15)
    soup2 = BeautifulSoup(r2.text, "html.parser")

    # 첨부파일 링크
    dl_links = soup2.find_all("a", href=re.compile(r"(download|file|hwp|pdf)", re.I))
    print(f"  첨부파일 {len(dl_links)}개")
    for i, lnk in enumerate(dl_links):
        fhref = lnk.get("href", "")
        ftxt = lnk.get_text(strip=True)[:50]
        if not fhref: continue
        furl = BASE_URL + fhref if fhref.startswith("/") else fhref
        print(f"  [{i}] [{ftxt}] {furl[:80]}")
        r3 = s.get(furl, headers={"Referer": full_url}, timeout=20, allow_redirects=True)
        d = r3.content
        print(f"    → {r3.status_code}, {len(d)}bytes, CT={r3.headers.get('Content-Type','')[:40]}")
        if len(d) > 1000 and b"<!DOCTYPE" not in d[:100] and b"<html" not in d[:50].lower():
            ext = detect_ext(d)
            clean = re.sub(r"[^\w가-힣]", "_", title)[:50]
            out = FIRE_DIR / f"KFMA_{clean}_{i}{ext}"
            out.write_bytes(d)
            print(f"    SAVED: {out.name} ({len(d)//1024}KB)")
            saved.append(out.name)
        time.sleep(0.3)
    time.sleep(0.5)

print(f"\n완료: {len(saved)}건 저장")
for f in saved:
    print(f"  {f}")
