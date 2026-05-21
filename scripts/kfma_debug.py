"""KFMA 서식자료실 HTML 구조 확인"""
import requests
from bs4 import BeautifulSoup
import re

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
BASE_URL = "https://www.kfma.kr"

s = requests.Session()
s.headers.update(H)
s.get(BASE_URL, timeout=15)

r = s.get(f"{BASE_URL}/bbs/12/list", headers={"Referer": BASE_URL}, timeout=15)
html = r.text

# 모든 링크
soup = BeautifulSoup(html, "html.parser")
print(f"전체 a 태그: {len(soup.find_all('a'))}개")

# bbs 관련 링크
for a in soup.find_all("a", href=re.compile(r"/bbs/")):
    print(f"  [{a.get_text(strip=True)[:40]}] {a.get('href','')}")

# API endpoint 패턴
print("\n--- JSON/API 패턴 ---")
api_matches = re.findall(r'(?:fetch|ajax|url|href)[^\'"]*[\'"]([^\'"]*api[^\'"]*)[\'"]', html, re.I)
for m in api_matches[:10]:
    print(f"  {m}")

# 게시물 데이터
print("\n--- boardSeq / nttId 패턴 ---")
seq_matches = re.findall(r'(?:nttId|boardSeq|seq|no)\s*[=:]\s*[\'"]*(\d+)', html, re.I)
print(f"  {seq_matches[:20]}")

# HTML 일부
print("\n--- HTML 일부 (3000~5000) ---")
print(html[3000:5000])
