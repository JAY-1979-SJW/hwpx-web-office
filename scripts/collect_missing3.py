"""
fncLsLawPop(flSeq) 패턴으로 별지서식 flSeq 추출 후 다운로드
"""
import requests, re, time, zipfile, io
from pathlib import Path

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.law.go.kr/",
}
BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"

# (lsiSeq, 서식번호, 저장경로, 파일명베이스)
TARGETS = [
    (279455, "제32호의2서식",  "건설일반/감리원_배치",   "서식32의2_시공단계_건설사업관리계획_제출서"),
    (283727, "제22호의4서식",  "건축/허가감리",          "서식22의4_공사_감리자_지정통보서"),
    (283727, "제22호의5서식",  "건축/허가감리",          "서식22의5_허가권자_지정_감리대상_건축물_제외_신청서"),
    (282735, "제15호서식",     "소방/공사감리_배치",     "서식15_소방시설_착공및완공대장"),
    (280195, "제7호서식",      "소방/자체점검",          "서식7_소방시설_자체점검_면제연기_신청서"),
    (280195, "제8호서식",      "소방/자체점검",          "서식8_소방시설_자체점검_면제연기_신청결과_통지서"),
]

def detect_ext(data):
    if data[:4] == b"%PDF": return ".pdf"
    if data[:4] == bytes([0xd0, 0xcf, 0x11, 0xe0]): return ".hwp"
    if data[:2] == b"PK":
        try:
            ns = " ".join(zipfile.ZipFile(io.BytesIO(data)).namelist())
            return ".xlsx" if "xl/" in ns else ".hwpx"
        except: return ".zip"
    return ".bin"

def get_fl_seq(lsi_seq, form_no_kw):
    """법령 HTML에서 서식번호에 해당하는 fncLsLawPop flSeq 추출"""
    r = requests.get(f"https://www.law.go.kr/lsInfoP.do?lsiSeq={lsi_seq}",
                     headers=H, timeout=25)
    html = r.text

    # fncLsLawPop('flSeq', ...) 패턴에서 텍스트와 flSeq 매핑
    # 패턴: 서식명 텍스트 뒤 또는 앞에 fncLsLawPop이 있음
    # <a ...onclick="javascript:fncLsLawPop('123456789','BF','')">별지 제N호서식</a>
    pattern1 = re.compile(
        r"fncLsLawPop\s*\(\s*['\"](\d+)['\"].*?\)\s*[^>]*>\s*([^<]{3,60})", re.DOTALL
    )
    pattern2 = re.compile(
        r"([^<]{3,60}별지[^<]{0,30}서식[^<]{0,10})\s*[^<]{0,200}fncLsLawPop\s*\(\s*['\"](\d+)['\"]",
        re.DOTALL
    )

    # 서식번호 추출: "제15호서식" → "15"
    no_m = re.search(r"제(\d+호[의\d]*)서식", form_no_kw)
    if not no_m:
        return None
    form_no_raw = no_m.group(0)  # "제15호서식"

    # 방법1: onclick에서 flSeq + 다음 텍스트
    for m in pattern1.finditer(html):
        fl, txt = m.group(1), m.group(2).strip()
        if form_no_raw in txt:
            return fl

    # 방법2: 텍스트 뒤 fncLsLawPop
    for m in pattern2.finditer(html):
        txt, fl = m.group(1).strip(), m.group(2)
        if form_no_raw in txt:
            return fl

    # 방법3: 서식번호 근처 fncLsLawPop 탐색
    idx = html.find(form_no_raw)
    while idx != -1:
        snippet = html[max(0, idx-200):idx+200]
        m3 = re.search(r"fncLsLawPop\s*\(\s*['\"](\d+)['\"]", snippet)
        if m3:
            return m3.group(1)
        idx = html.find(form_no_raw, idx+1)

    return None

saved = []

for lsi_seq, form_no_kw, save_subdir, fname_base in TARGETS:
    print(f"\n[{form_no_kw}] lsiSeq={lsi_seq}")

    fl_seq = get_fl_seq(lsi_seq, form_no_kw)
    time.sleep(0.4)

    if not fl_seq:
        print(f"  ✗ flSeq 못 찾음")
        continue

    print(f"  flSeq={fl_seq} → 다운로드")
    r = requests.get(
        f"https://www.law.go.kr/flDownload.do?flSeq={fl_seq}",
        headers=H, timeout=25, allow_redirects=True
    )
    d = r.content
    print(f"  {r.status_code}, {len(d)}bytes, CT={r.headers.get('Content-Type','')[:40]}")
    cd = r.headers.get("Content-Disposition", "")
    print(f"  CD={cd[:60]}")

    if r.status_code == 200 and len(d) > 500 and b"<!DOCTYPE" not in d[:100]:
        ext = detect_ext(d)
        out = BASE / save_subdir / (fname_base + ext)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(d)
        print(f"  SAVED: {out.name} ({len(d)//1024}KB)")
        saved.append(out.name)
    else:
        print(f"  실패: {d[:150]}")

print(f"\n완료: {len(saved)}건")
for f in saved:
    print(f"  {f}")
