"""법령별 별지서식 목록 파싱 - HTML 방식"""
import requests, re, time
from bs4 import BeautifulSoup
from pathlib import Path

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.law.go.kr/",
    "Content-Type": "application/x-www-form-urlencoded",
}
BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"
collected = [f.name.lower() for f in BASE.rglob("*")
             if f.is_file() and f.suffix in {".hwp", ".hwpx", ".pdf", ".xlsx"}]

LAWS = {
    "건설기술진흥법_시행규칙": (279455, ["감리", "건설사업관리"]),
    "건축법_시행규칙":          (283727, ["감리"]),
    "소방시설공사업법_시행규칙": (282735, ["감리", "완공", "배치"]),
    "소방시설법_시행규칙":       (280195, ["자체점검", "점검"]),
    "전력기술관리법_시행규칙":   (278995, ["감리"]),
    "기계설비법_시행규칙":       (285589, ["감리", "점검"]),
    "정보통신공사업법_시행규칙": (272931, ["감리"]),
}

def get_forms(seq):
    r = requests.post(
        "https://www.law.go.kr/lsBylInfoR.do",
        data={"lsiSeq": str(seq), "bylClsCd": "BYL_FTXT"},
        headers=H, timeout=15
    )
    soup = BeautifulSoup(r.text, "html.parser")
    forms = []
    # 모든 flSeq 링크
    for a in soup.find_all("a"):
        href = a.get("href", "")
        txt = a.get_text(strip=True)
        m = re.search(r"flSeq[=,\s]+(\d+)", href)
        if not m:
            m = re.search(r"flSeq['\"\s:=]+(\d+)", str(a))
        if m and txt:
            forms.append({"bylNm": txt, "flSeq": m.group(1)})
    # onclick에서 flSeq
    for el in soup.find_all(attrs={"onclick": True}):
        onclick = el.get("onclick", "")
        m = re.search(r"flSeq['\"\s,=]+(\d+)", onclick)
        if m:
            txt = el.get_text(strip=True)
            if txt and not any(f["flSeq"] == m.group(1) for f in forms):
                forms.append({"bylNm": txt, "flSeq": m.group(1)})
    # span/li 안의 텍스트에서도 추출
    fl_seqs = re.findall(r"'(\d{9,11})'", r.text)
    # bylNm 패턴
    nm_pats = re.findall(r"bylNm['\",\s:=]+([^'\"<>]{3,60})", r.text)
    if fl_seqs and nm_pats and not forms:
        for i, (fs, nm) in enumerate(zip(fl_seqs, nm_pats)):
            forms.append({"bylNm": nm.strip(), "flSeq": fs})
    return forms

def is_collected(title):
    no = re.search(r"제\s*(\d+[\-의\d]*)호", title)
    form_no = no.group(1).replace("-", "의").replace(" ", "") if no else ""
    words = [w for w in re.sub(r"[^\w가-힣]", " ", title).split() if len(w) >= 2]
    for fname in collected:
        if form_no and form_no in fname.replace("-", "의"):
            return True
        if sum(1 for w in words[:5] if w.lower() in fname) >= 2:
            return True
    return False

all_missing = []

for law_name, (seq, kw_filter) in LAWS.items():
    print(f"\n[{law_name}] lsiSeq={seq}")
    forms = get_forms(seq)
    time.sleep(0.4)
    print(f"  전체 별지서식 {len(forms)}건")

    relevant = [f for f in forms if any(k in f["bylNm"] for k in kw_filter)]
    print(f"  감리 관련 {len(relevant)}건")

    for form in relevant:
        title = form["bylNm"]
        fl_seq = form["flSeq"]
        ok = is_collected(title)
        print(f"  {'✓' if ok else '✗'} {title[:62]} (flSeq={fl_seq})")
        if not ok:
            all_missing.append({"law": law_name, "title": title, "flSeq": fl_seq})

print(f"\n\n미수집: {len(all_missing)}건")
for m in all_missing:
    print(f"  [{m['law'][:16]}] {m['title'][:55]}  flSeq={m['flSeq']}")
