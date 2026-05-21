"""KFMA API 엔드포인트 탐색"""
import requests
from bs4 import BeautifulSoup
import re, json

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

# script 태그 내 API URL
print("--- script 태그 분석 ---")
soup = BeautifulSoup(html, "html.parser")
for script in soup.find_all("script"):
    src = script.get("src", "")
    txt = script.get_text()
    if any(k in txt for k in ["fetch(", "ajax", "axios", "/api/", "bbs"]):
        print(f"\n[script src={src[:50]}]")
        print(txt[:500])

# HTML 마지막 2000자
print("\n--- HTML 후반부 ---")
print(html[-2000:])

# /bbs/12/list JSON 형태 요청
print("\n--- JSON API 시도 ---")
r2 = s.get(f"{BASE_URL}/bbs/12/list",
           headers={"Referer": BASE_URL, "Accept": "application/json, text/javascript, */*"},
           timeout=15)
print(f"Content-Type: {r2.headers.get('Content-Type')}")
# JSON 시도
try:
    data = r2.json()
    print(json.dumps(data, ensure_ascii=False, indent=2)[:1000])
except:
    print("JSON 아님")

# API 직접 탐색
for path in ["/api/bbs/12/list", "/bbs/12/posts", "/bbs/api/12/list"]:
    r3 = s.get(BASE_URL + path, timeout=10)
    print(f"\n{path}: {r3.status_code}, {len(r3.content)}bytes")
    if r3.status_code == 200 and len(r3.content) > 100:
        try:
            d = r3.json()
            print(json.dumps(d, ensure_ascii=False, indent=2)[:500])
        except:
            print(r3.text[:200])
