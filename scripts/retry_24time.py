import requests
from bs4 import BeautifulSoup

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.24time.kr/",
}

# 24time.kr 해당 게시물 파싱
r = requests.get("https://www.24time.kr/bbs/board.php?bo_table=cus_3&wr_id=33", headers=H, timeout=15)
print(f"Status: {r.status_code}, Size: {len(r.content)}")

soup = BeautifulSoup(r.text, "html.parser")
# 모든 다운로드 링크
dl_links = soup.find_all("a", href=True)
print(f"\n전체 링크 {len(dl_links)}개")
for lnk in dl_links:
    h = lnk.get("href", "")
    t = lnk.get_text(strip=True)
    if any(k in h.lower() for k in ["download", "file", "hwp", "pdf", "attach"]):
        print(f"  [{t[:50]}] {h}")

# 첨부파일 섹션
print("\n--- 첨부파일 섹션 HTML ---")
attach = soup.find(class_=lambda x: x and ("file" in x.lower() or "attach" in x.lower()))
if attach:
    print(attach.prettify()[:2000])
else:
    # 직접 패턴으로 찾기
    import re
    matches = re.findall(r'href="([^"]*(?:download|file|hwp)[^"]*)"', r.text, re.I)
    print(f"파일 패턴 매치: {matches[:10]}")
