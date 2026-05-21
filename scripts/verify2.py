"""법령별 별지서식 수집 여부 검증 - lsiSeq 직접 조회"""
import requests, json, time
from pathlib import Path

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.law.go.kr/",
}
BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"

# 현재 수집 파일 목록
collected_files = []
for f in BASE.rglob("*"):
    if f.is_file() and f.suffix in {".hwp", ".hwpx", ".pdf", ".xlsx"}:
        collected_files.append(f.name)

print(f"현재 수집 파일 수: {len(collected_files)}")

def find_law_lsiseq(keyword):
    """법령명으로 lsiSeq 검색"""
    r = requests.get(
        "https://www.law.go.kr/DRF/lawSearch.do",
        params={"OC": "verify", "target": "law", "type": "JSON",
                "query": keyword, "display": 5, "sort": "lasc"},
        headers=H, timeout=15
    )
    data = r.json()
    laws = data.get("law", [])
    results = []
    for law in laws:
        results.append({
            "name": law.get("lawNm"),
            "lsiSeq": law.get("lsiSeq"),
            "type": law.get("lawType"),
        })
    return results

def get_bylaw_forms(lsi_seq):
    """해당 법령의 별지서식 목록 조회"""
    r = requests.post(
        "https://www.law.go.kr/lsBylInfoR.do",
        data={"lsiSeq": lsi_seq, "bylClsCd": "BYL_FTXT"},
        headers={**H, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=15
    )
    if r.status_code != 200:
        return []
    try:
        data = r.json()
        if isinstance(data, list):
            return data
        return data.get("bylList", []) or []
    except:
        return []

# 검색할 법령 목록
LAWS = [
    ("건설기술진흥법 시행규칙", ["감리", "배치", "건설사업관리"]),
    ("건축법 시행규칙", ["감리", "확인", "허가"]),
    ("소방시설공사업법 시행규칙", ["감리", "완공", "배치"]),
    ("소방시설 설치 및 관리에 관한 법률 시행규칙", ["자체점검", "점검", "관리"]),
    ("전력기술관리법 시행규칙", ["감리", "배치", "전력"]),
    ("기계설비법 시행규칙", ["점검", "감리", "기계설비"]),
    ("정보통신공사업법 시행규칙", ["감리", "배치", "정보통신"]),
]

all_missing = []

for law_name, relevant_kw in LAWS:
    print(f"\n{'='*60}")
    print(f"[{law_name}]")

    laws = find_law_lsiseq(law_name)
    time.sleep(0.3)

    if not laws:
        print(f"  검색 실패")
        continue

    # 시행규칙 찾기
    target = None
    for law in laws:
        lname = law.get("name", "")
        ltype = law.get("type", "")
        print(f"  후보: {lname} ({ltype}) lsiSeq={law.get('lsiSeq')}")
        if "시행규칙" in lname and law_name.replace(" 시행규칙", "") in lname:
            target = law
            break
    if not target and laws:
        target = laws[0]

    if not target:
        continue

    lsi_seq = target["lsiSeq"]
    print(f"  → lsiSeq={lsi_seq} 선택: {target['name']}")

    forms = get_bylaw_forms(lsi_seq)
    time.sleep(0.5)

    if not forms:
        print(f"  별지서식 없음 (또는 조회 실패)")
        continue

    print(f"  별지서식 {len(forms)}건")
    missing = []
    for form in forms:
        title = (form.get("bylNm") or form.get("title") or "").strip()
        fl_seq = form.get("flSeq", "")
        if not title:
            continue

        # 관련 키워드 포함 여부
        is_relevant = any(k in title for k in relevant_kw)
        if not is_relevant:
            continue

        # 파일명 매칭 시도
        # 서식번호 추출
        import re
        no_match = re.search(r'제\s*(\d+[\-의\d]*)\s*호', title)
        form_no = no_match.group(1) if no_match else ""

        found = False
        for fname in collected_files:
            fname_l = fname.lower()
            # 서식번호 또는 키워드로 매칭
            if form_no and form_no.replace("-", "의").replace(" ", "") in fname_l.replace("-", "의"):
                found = True
                break
            # 핵심 단어 2개 이상 매칭
            words = [w for w in title.split() if len(w) >= 2][:4]
            if sum(1 for w in words if w.lower() in fname_l) >= 2:
                found = True
                break

        status = "✓" if found else "✗"
        print(f"  {status} [{form_no or '?'}] {title[:60]} (flSeq={fl_seq})")

        if not found:
            missing.append({"law": law_name, "title": title, "flSeq": fl_seq, "lsiSeq": lsi_seq})

    if missing:
        print(f"\n  ★ 미수집 {len(missing)}건:")
        for m in missing:
            print(f"    - {m['title'][:60]} (flSeq={m['flSeq']})")
        all_missing.extend(missing)

print(f"\n\n{'='*60}")
print(f"총 미수집 후보: {len(all_missing)}건")
for m in all_missing:
    print(f"  [{m['law']}] {m['title'][:55]} flSeq={m['flSeq']}")
