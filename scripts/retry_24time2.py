import requests
from pathlib import Path
import zipfile, io

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.24time.kr/bbs/board.php?bo_table=cus_3&wr_id=33",
}

BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"

# 세션으로 메인 먼저 방문
s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
})
# 메인 방문
s.get("https://www.24time.kr", timeout=10)
# 게시물 방문
s.get("https://www.24time.kr/bbs/board.php?bo_table=cus_3&wr_id=33",
      headers={"Referer": "https://www.24time.kr/"}, timeout=10)
# 다운로드
r = s.get(
    "https://www.24time.kr/bbs/download.php?bo_table=cus_3&wr_id=33&no=0",
    headers={"Referer": "https://www.24time.kr/bbs/board.php?bo_table=cus_3&wr_id=33"},
    timeout=25, allow_redirects=True
)

d = r.content
print(f"Status: {r.status_code}")
print(f"Size: {len(d)} bytes")
print(f"Content-Type: {r.headers.get('Content-Type')}")
print(f"Content-Disposition: {r.headers.get('Content-Disposition')}")
print(f"첫 16바이트: {d[:16].hex()}")
print(f"HTML 여부: {b'<!DOCTYPE' in d[:100] or b'<html' in d[:100].lower()}")

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

if len(d) > 10000:
    ext = detect_ext(d)
    out = BASE / "전력기술관리법_시행규칙" / f"전력시설물_공사감리업무수행지침_별지서식모음{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(d)
    print(f"SAVED: {out.name} ({len(d)//1024}KB)")
else:
    print(f"내용: {d[:500]}")
