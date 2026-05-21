import requests, json

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*",
    "Referer": "https://www.law.go.kr/",
}

# 전력시설물 공사감리업무수행지침 행정규칙 검색
r = requests.get(
    "https://www.law.go.kr/DRF/lawSearch.do",
    params={"OC": "skyjw", "target": "admrul", "type": "JSON", "query": "전력시설물 공사감리업무수행지침", "display": 10},
    headers=H, timeout=15
)
data = r.json()
total = data.get("totalCnt", 0)
print(f"행정규칙 검색 결과: {total}건")
for item in data.get("admrul", [])[:5]:
    print(f"  MST={item.get('admRulMst')} 제목={item.get('admRulNm')} 부처={item.get('mnstNm')}")

# 법령체계도 조회
if data.get("admrul"):
    mst = data["admrul"][0]["admRulMst"]
    r2 = requests.get(
        "https://www.law.go.kr/DRF/lawService.do",
        params={"OC": "skyjw", "target": "admrul", "type": "JSON", "MST": mst},
        headers=H, timeout=15
    )
    d2 = r2.json()
    print(f"\n법령 상세:")
    print(json.dumps(d2, ensure_ascii=False, indent=2)[:2000])
