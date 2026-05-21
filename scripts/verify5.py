"""
lsBylContentsInfoR.do 방식으로 별지서식 목록 조회
(이전 수집 스크립트에서 동작 확인된 endpoint)
"""
import requests, re, time, json
from pathlib import Path

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.law.go.kr/",
    "Accept": "*/*",
    "X-Requested-With": "XMLHttpRequest",
}
BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"
collected = [f.name.lower() for f in BASE.rglob("*")
             if f.is_file() and f.suffix in {".hwp", ".hwpx", ".pdf", ".xlsx"}]

# lsiSeq 조회
LSI_SEQS = {
    "건설기술진흥법_시행규칙": 279455,
    "건축법_시행규칙": 283727,
    "소방시설공사업법_시행규칙": 282735,
    "소방시설법_시행규칙": 280195,
    "전력기술관리법_시행규칙": 278995,
    "기계설비법_시행규칙": 285589,
    "정보통신공사업법_시행규칙": 272931,
}

KW_FILTER = {
    "건설기술진흥법_시행규칙": ["감리", "건설사업관리"],
    "건축법_시행규칙": ["감리"],
    "소방시설공사업법_시행규칙": ["감리", "완공", "배치"],
    "소방시설법_시행규칙": ["자체점검", "점검"],
    "전력기술관리법_시행규칙": ["감리"],
    "기계설비법_시행규칙": ["감리", "점검"],
    "정보통신공사업법_시행규칙": ["감리"],
}

def get_forms_v2(lsi_seq):
    """lsBylContentsInfoR.do 방식"""
    r = requests.get(
        "https://www.law.go.kr/lsBylContentsInfoR.do",
        params={"lsiSeq": lsi_seq, "bylClsCd": "BYL_FTXT"},
        headers=H, timeout=15
    )
    try:
        data = r.json()
        if isinstance(data, list):
            return data
        return data.get("bylContents", data.get("bylList", []))
    except:
        return []

def get_forms_v3(lsi_seq):
    """HTML에서 별지서식 목록 파싱"""
    from bs4 import BeautifulSoup
    r = requests.get(
        f"https://www.law.go.kr/lsInfoP.do?lsiSeq={lsi_seq}",
        headers=H, timeout=15
    )
    soup = BeautifulSoup(r.text, "html.parser")
    forms = []
    # 별지서식 탭
    for a in soup.find_all("a", href=re.compile(r"flSeq=\d+")):
        txt = a.get_text(strip=True)
        m = re.search(r'flSeq=(\d+)', a.get("href", ""))
        fl_seq = m.group(1) if m else ""
        if txt:
            forms.append({"bylNm": txt, "flSeq": fl_seq})
    return forms

def is_collected(title):
    no = re.search(r'제\s*(\d+[\-의\d]*)호', title)
    form_no_str = no.group(1).replace("-", "의").replace(" ", "") if no else ""
    words = [w for w in re.sub(r'[^\w가-힣]', ' ', title).split() if len(w) >= 2]
    for fname in collected:
        if form_no_str and form_no_str in fname.replace("-", "의"):
            return True
        if sum(1 for w in words[:5] if w.lower() in fname) >= 2:
            return True
    return False

all_missing = []

for law_name, lsi_seq in LSI_SEQS.items():
    print(f"\n{'='*55}")
    print(f"[{law_name}] lsiSeq={lsi_seq}")
    kw = KW_FILTER[law_name]

    # v2 시도
    forms = get_forms_v2(lsi_seq)
    time.sleep(0.3)
    if not forms:
        # v3 시도 (HTML 파싱)
        forms = get_forms_v3(lsi_seq)
        time.sleep(0.3)

    if not forms:
        print(f"  별지서식 조회 실패 → 직접 URL로 시도")
        # 직접 URL 시도
        r = requests.get(f"https://www.law.go.kr/법령/{law_name.replace('_', ' ')}",
                         headers=H, allow_redirects=True, timeout=15)
        m_fl = re.findall(r'flSeq["\s:=]+(\d+)[^"]*bylNm["\s:=]+"([^"]+)"', r.text)
        if not m_fl:
            m_fl2 = re.findall(r'"bylNm"\s*:\s*"([^"]+)"[^}]*"flSeq"\s*:\s*"?(\d+)', r.text)
            forms = [{"bylNm": t, "flSeq": s} for t, s in m_fl2]
        else:
            forms = [{"bylNm": n, "flSeq": s} for s, n in m_fl]
        if not forms:
            print(f"  별지서식 없음 (확인 필요)")
            continue

    relevant = [f for f in forms if any(k in (f.get("bylNm") or "") for k in kw)]
    print(f"  전체 {len(forms)}건 / 관련 {len(relevant)}건")

    for form in relevant:
        title = (form.get("bylNm") or "").strip()
        fl_seq = form.get("flSeq", "")
        ok = is_collected(title)
        print(f"  {'✓' if ok else '✗'} {title[:60]} (flSeq={fl_seq})")
        if not ok:
            all_missing.append({"law": law_name, "title": title,
                                 "flSeq": fl_seq, "lsiSeq": lsi_seq})

print(f"\n\n{'='*55}")
print(f"미수집 서식: {len(all_missing)}건")
for m in all_missing:
    print(f"  [{m['law'][:14]}] {m['title'][:52]}  flSeq={m['flSeq']}")
