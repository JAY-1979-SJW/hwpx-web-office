"""
law.go.kr 웹 파싱으로 각 법령 별지서식 목록 조회 후 수집 여부 대조
"""
import requests, re, time, json
from bs4 import BeautifulSoup
from pathlib import Path

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.law.go.kr/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"

# 수집된 파일명 (소문자)
collected = [f.name.lower() for f in BASE.rglob("*")
             if f.is_file() and f.suffix in {".hwp", ".hwpx", ".pdf", ".xlsx"}]

def get_lsiseq(law_name):
    """법령명으로 lsiSeq 획득"""
    url = f"https://www.law.go.kr/법령/{requests.utils.quote(law_name)}"
    r = requests.get(url, headers=H, allow_redirects=True, timeout=15)
    m = re.search(r'lsiSeq["\s:=]+(\d+)', r.text)
    if m:
        return m.group(1)
    # URL redirect 확인
    m2 = re.search(r'lsiSeq=(\d+)', r.url)
    return m2.group(1) if m2 else None

def get_forms(lsi_seq):
    """별지서식 목록 (lsBylInfoR.do)"""
    r = requests.post(
        "https://www.law.go.kr/lsBylInfoR.do",
        data={"lsiSeq": lsi_seq, "bylClsCd": "BYL_FTXT"},
        headers={**H, "Content-Type": "application/x-www-form-urlencoded",
                 "X-Requested-With": "XMLHttpRequest"},
        timeout=15
    )
    try:
        data = r.json()
        return data if isinstance(data, list) else data.get("bylList", [])
    except:
        return []

def is_collected(title):
    """파일명에서 키워드 매칭"""
    # 서식번호 추출
    no = re.search(r'제\s*(\d+[\-의\d]*)호', title)
    form_no_str = no.group(1).replace("-", "의").replace(" ", "") if no else ""
    # 핵심 단어들
    words = [w for w in re.sub(r'[^\w가-힣]', ' ', title).split() if len(w) >= 2]

    for fname in collected:
        if form_no_str and form_no_str in fname.replace("-", "의"):
            return True
        match_count = sum(1 for w in words[:5] if w.lower() in fname)
        if match_count >= 2:
            return True
    return False

# 대상 법령 - (법령명, 감리관련 키워드)
TARGET_LAWS = [
    ("건설기술진흥법 시행규칙",      ["감리", "건설사업관리", "감리원"]),
    ("건축법 시행규칙",               ["감리", "공사감리"]),
    ("소방시설공사업법 시행규칙",     ["감리", "배치", "완공"]),
    ("소방시설 설치 및 관리에 관한 법률 시행규칙", ["자체점검", "점검"]),
    ("전력기술관리법 시행규칙",       ["감리"]),
    ("기계설비법 시행규칙",           ["감리", "점검", "기계설비"]),
    ("정보통신공사업법 시행규칙",     ["감리"]),
]

all_missing = []

for law_name, kw_filter in TARGET_LAWS:
    print(f"\n{'='*60}")
    print(f"[{law_name}]")

    lsi_seq = get_lsiseq(law_name)
    time.sleep(0.4)

    if not lsi_seq:
        print(f"  lsiSeq 획득 실패")
        continue
    print(f"  lsiSeq={lsi_seq}")

    forms = get_forms(lsi_seq)
    time.sleep(0.4)

    if not forms:
        print(f"  별지서식 없음")
        continue

    # 감리 관련 서식만 필터
    relevant = [f for f in forms
                if any(k in (f.get("bylNm") or "") for k in kw_filter)]
    print(f"  전체 {len(forms)}건 중 관련 {len(relevant)}건")

    for form in relevant:
        title = (form.get("bylNm") or "").strip()
        fl_seq = form.get("flSeq", "")
        ok = is_collected(title)
        mark = "✓" if ok else "✗"
        print(f"  {mark} {title[:62]} (flSeq={fl_seq})")
        if not ok:
            all_missing.append({"law": law_name, "title": title,
                                 "flSeq": fl_seq, "lsiSeq": lsi_seq})

print(f"\n\n{'='*60}")
print(f"총 미수집 서식: {len(all_missing)}건")
for m in all_missing:
    print(f"  [{m['law'][:12]}] {m['title'][:55]}  flSeq={m['flSeq']}")

# JSON 저장
out = BASE / "collect_verify.json"
out.write_text(json.dumps({
    "missing": all_missing,
    "collected_count": len(collected),
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n결과 저장: {out}")
