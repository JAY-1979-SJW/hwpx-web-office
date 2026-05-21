import requests, json

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*",
    "Referer": "https://www.law.go.kr/",
}

queries = [
    "전력시설물 공사감리",
    "전력시설물 감리업무",
    "전력시설물 공사감리업무",
]

for q in queries:
    r = requests.get(
        "https://www.law.go.kr/DRF/lawSearch.do",
        params={"OC": "skyjw", "target": "admrul", "type": "JSON", "query": q, "display": 10},
        headers=H, timeout=15
    )
    data = r.json()
    total = data.get("totalCnt", 0)
    print(f"[{q}] 행정규칙 {total}건")
    for item in data.get("admrul", [])[:3]:
        print(f"  MST={item.get('admRulMst')} 제목={item.get('admRulNm')}")

# 고시 검색도 시도
print("\n--- 훈령/예규/고시 검색 ---")
for q in ["전력시설물 공사감리", "전력시설물 감리"]:
    r = requests.get(
        "https://www.law.go.kr/DRF/lawSearch.do",
        params={"OC": "skyjw", "target": "admrul", "type": "JSON", "query": q, "display": 5, "org": "1430000"},
        headers=H, timeout=15
    )
    data = r.json()
    total = data.get("totalCnt", 0)
    print(f"[{q}] (산업부) {total}건")
    for item in data.get("admrul", [])[:3]:
        print(f"  MST={item.get('admRulMst')} 제목={item.get('admRulNm')}")
