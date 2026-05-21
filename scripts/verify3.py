"""law.go.kr 법령 검색 - 짧은 키워드, 다양한 target"""
import requests, json, time

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.law.go.kr/",
}

# 짧은 키워드로 재시도
for kw in ["건설기술진흥", "기계설비법", "정보통신공사업", "전력기술관리", "소방시설공사업"]:
    for target in ["law", "bylChk"]:
        r = requests.get(
            "https://www.law.go.kr/DRF/lawSearch.do",
            params={"OC": "verify01", "target": target, "type": "JSON",
                    "query": kw, "display": 3},
            headers=H, timeout=15
        )
        data = r.json()
        items = data.get("law", data.get("bylChk", []))
        if items:
            print(f"[{kw}] target={target}: {len(items)}건")
            for it in items[:2]:
                print(f"  {it.get('lawNm') or it}")
        else:
            print(f"[{kw}] target={target}: 없음 / totalCnt={data.get('totalCnt')}")
        time.sleep(0.2)
