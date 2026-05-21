"""
수집 대상 법령별 별지서식 목록 조회 → 수집 여부 대조
대상 법령:
  1. 건설기술진흥법 시행규칙
  2. 건축법 시행규칙
  3. 소방시설공사업법 시행규칙
  4. 소방시설 설치 및 관리에 관한 법률 시행규칙
  5. 전력기술관리법 시행규칙
  6. 기계설비법 시행규칙
  7. 정보통신공사업법 시행규칙
"""
import requests, json, time
from pathlib import Path

H = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.law.go.kr/",
}
BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"

def search_law(query):
    r = requests.get(
        "https://www.law.go.kr/DRF/lawSearch.do",
        params={"OC": "verify", "target": "law", "type": "JSON",
                "query": query, "display": 5},
        headers=H, timeout=15
    )
    data = r.json()
    laws = data.get("law", [])
    return laws

def get_bylaws(lsi_seq):
    """별지서식 목록 조회"""
    r = requests.post(
        "https://www.law.go.kr/lsBylInfoR.do",
        data={"lsiSeq": lsi_seq, "bylClsCd": "BYL_FTXT"},
        headers={**H, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=15
    )
    return r.json() if r.status_code == 200 else {}

def get_bylaw_list(lsi_seq):
    """별지서식 전체 목록 (서식번호, 제목)"""
    r = requests.get(
        "https://www.law.go.kr/lsBylContentsInfoR.do",
        params={"lsiSeq": lsi_seq, "bylClsCd": "BYL_FTXT"},
        headers=H, timeout=15
    )
    return r.json() if r.status_code == 200 else {}

# 현재 수집된 파일 목록
collected = set()
for f in BASE.rglob("*"):
    if f.is_file() and f.suffix in {".hwp", ".hwpx", ".pdf", ".xlsx"}:
        collected.add(f.name.lower())

print(f"현재 수집 파일 수: {len(collected)}")
print()

# 법령별 별지서식 목록 조회
TARGET_LAWS = [
    ("건설기술진흥법 시행규칙", ["건설사업관리", "감리", "감리원", "배치"]),
    ("건축법 시행규칙", ["건축공사감리", "감리", "허가감리"]),
    ("소방시설공사업법 시행규칙", ["소방", "감리", "완공검사"]),
    ("소방시설 설치 및 관리에 관한 법률 시행규칙", ["자체점검", "소방시설"]),
    ("전력기술관리법 시행규칙", ["전기", "감리"]),
    ("기계설비법 시행규칙", ["기계설비", "점검", "감리"]),
    ("정보통신공사업법 시행규칙", ["정보통신", "감리"]),
]

all_results = {}

for law_name, keywords in TARGET_LAWS:
    print(f"\n{'='*60}")
    print(f"[{law_name}]")

    laws = search_law(law_name)
    if not laws:
        print(f"  검색 결과 없음")
        continue

    law = laws[0]
    lsi_seq = law.get("lsiSeq")
    print(f"  lsiSeq={lsi_seq} / {law.get('lawNm')}")

    # 별지서식 목록
    r = requests.get(
        "https://www.law.go.kr/DRF/lawService.do",
        params={"OC": "verify", "target": "bylChk", "type": "JSON", "MST": lsi_seq},
        headers=H, timeout=15
    )
    time.sleep(0.5)

    # 별지서식 직접 조회
    r2 = requests.post(
        "https://www.law.go.kr/lsBylInfoR.do",
        data={"lsiSeq": lsi_seq, "bylClsCd": "BYL_FTXT"},
        headers={**H, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=15
    )

    try:
        bylaw_data = r2.json()
        items = bylaw_data if isinstance(bylaw_data, list) else bylaw_data.get("bylList", [])
        print(f"  별지서식 {len(items)}건")

        law_results = []
        for item in items:
            title = item.get("bylNm", "") or item.get("title", "") or str(item)
            fl_seq = item.get("flSeq", "")

            # 감리 관련 키워드 필터
            relevant = any(k in title for k in keywords + ["서식", "별지", "별표"])

            # 수집 여부 확인 (파일명에 서식번호나 키워드 포함 여부로 판단)
            status = "?"
            for fname in collected:
                if any(k.lower() in fname for k in title.split()[:3] if len(k) > 1):
                    status = "OK"
                    break

            if relevant:
                print(f"  {'✓' if status=='OK' else '✗'} {title[:60]} (flSeq={fl_seq})")
            law_results.append({"title": title, "flSeq": fl_seq, "collected": status=="OK"})

        all_results[law_name] = law_results
    except Exception as e:
        print(f"  파싱 오류: {e}")
        print(f"  응답: {r2.text[:300]}")

    time.sleep(0.5)

print(f"\n\n{'='*60}")
print("조회 완료")
