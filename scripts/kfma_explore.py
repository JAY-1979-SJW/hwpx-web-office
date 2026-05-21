"""KFMA 메인 페이지에서 서식자료실 링크 탐색"""
import requests
from bs4 import BeautifulSoup
import re

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

s = requests.Session()
s.headers.update(H)

r = s.get("https://www.kfma.kr", timeout=15)
soup = BeautifulSoup(r.text, "html.parser")

print(f"Title: {soup.title.get_text(strip=True) if soup.title else ''}")

# 모든 링크 중 서식/자료 관련
kw = ["서식", "자료", "format", "bbs", "download", "자료실", "공지", "게시판"]
for a in soup.find_all("a", href=True):
    h = a.get("href", "")
    t = a.get_text(strip=True)
    if any(k in h.lower() or k in t for k in kw):
        print(f"  [{t[:40]}] {h[:80]}")

# 메뉴 구조
print("\n--- 메뉴 구조 ---")
nav = soup.find(["nav", ".gnb", ".nav", "#nav", ".menu", "#menu"])
if nav:
    for a in nav.find_all("a", href=True)[:30]:
        print(f"  [{a.get_text(strip=True)[:30]}] {a.get('href','')[:60]}")
