"""KFMA page.json API로 서식 수집"""
import requests, re, json, time, zipfile, io
from pathlib import Path

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.kfma.kr/bbs/12/list",
}
BASE_URL = "https://www.kfma.kr"
BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"
FIRE_DIR = BASE / "소방시설법_시행규칙"
FIRE_DIR.mkdir(parents=True, exist_ok=True)
saved = []

def detect_ext(data):
    if data[:4] == b"%PDF": return ".pdf"
    if data[:4] == bytes([0xd0, 0xcf, 0x11, 0xe0]): return ".hwp"
    if data[:2] == b"PK":
        try:
            ns = " ".join(zipfile.ZipFile(io.BytesIO(data)).namelist())
            return ".xlsx" if "xl/" in ns else ".hwpx"
        except:
            return ".zip"
    return ".bin"

s = requests.Session()
s.headers.update(H)
# 세션 초기화
s.get(BASE_URL, timeout=15)
s.get(f"{BASE_URL}/bbs/12/list", timeout=15)

# 게시물 목록 가져오기
r = s.get(
    f"{BASE_URL}/bbs/12/page.json",
    params={"bbsCd": 12, "size": 30, "searchKey": 1000, "searchVal": "", "pageNumber": 1},
    headers={**H, "Accept": "application/json"},
    timeout=15
)
print(f"page.json: {r.status_code}, {len(r.content)}bytes")
data = r.json()
posts = data.get("data", {}).get("list", [])
print(f"게시물 {len(posts)}건")

# 소방 자체점검 관련 키워드
kw = ["자체점검", "점검기록표", "점검표", "보고서", "서식", "별지", "외관점검"]

for post in posts:
    seq = post.get("bbsSeq")
    title = post.get("pstTtl", "")
    date = post.get("regDt", "")[:10]
    print(f"\n  [{seq}] {title} ({date})")

    if not any(k in title for k in kw):
        print(f"    → 키워드 없음, 건너뜀")
        continue

    # 게시물 상세 조회
    r2 = s.get(
        f"{BASE_URL}/bbs/12/view.json",
        params={"bbsSeq": seq, "bbsCd": 12},
        headers={**H, "Accept": "application/json"},
        timeout=15
    )
    if r2.status_code != 200:
        # HTML 상세 페이지 시도
        r2 = s.get(
            f"{BASE_URL}/bbs/12/view/{seq}",
            headers=H, timeout=15
        )
    print(f"    상세: {r2.status_code}, {len(r2.content)}bytes, CT={r2.headers.get('Content-Type','')[:30]}")

    # 첨부파일 정보 찾기
    try:
        d2 = r2.json()
        files = d2.get("data", {}).get("fileList", []) or d2.get("data", {}).get("files", [])
        print(f"    첨부 {len(files)}개 (JSON)")
    except:
        # HTML 파싱
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r2.text, "html.parser")
        # 파일 링크
        file_links = soup.find_all("a", href=re.compile(r"(download|file|hwp|pdf)", re.I))
        print(f"    첨부 {len(file_links)}개 (HTML)")
        for lnk in file_links:
            fhref = lnk.get("href", "")
            ftxt = lnk.get_text(strip=True)[:50]
            furl = BASE_URL + fhref if fhref.startswith("/") else fhref
            print(f"      [{ftxt}] {furl}")
            r3 = s.get(furl, headers={**H, "Referer": f"{BASE_URL}/bbs/12/view/{seq}"},
                      timeout=20, allow_redirects=True)
            d3 = r3.content
            print(f"      → {r3.status_code}, {len(d3)}bytes")
            if len(d3) > 1000 and b"<!DOCTYPE" not in d3[:100]:
                ext = detect_ext(d3)
                clean = re.sub(r"[^\w가-힣]", "_", title)[:50]
                out = FIRE_DIR / f"KFMA_{clean}{ext}"
                out.write_bytes(d3)
                print(f"      SAVED: {out.name} ({len(d3)//1024}KB)")
                saved.append(out.name)
            time.sleep(0.3)

        # onclick 패턴에서 파일 시퀀스 추출
        onclick_pats = re.findall(r"fileDownload\((\d+)", r2.text)
        pstFileSeq_pats = re.findall(r"pstFileSeq['\"\s:=]+(\d+)", r2.text)
        print(f"    onclick fileDownload: {onclick_pats}")
        print(f"    pstFileSeq: {pstFileSeq_pats}")

        for fseq in onclick_pats + pstFileSeq_pats:
            for dl_path in [f"/bbs/download/{fseq}", f"/file/download/{fseq}",
                             f"/bbs/12/download/{fseq}"]:
                r3 = s.get(BASE_URL + dl_path, headers={**H, "Referer": f"{BASE_URL}/bbs/12/view/{seq}"},
                          timeout=15, allow_redirects=True)
                d3 = r3.content
                if r3.status_code == 200 and len(d3) > 1000 and b"<!DOCTYPE" not in d3[:100]:
                    ext = detect_ext(d3)
                    clean = re.sub(r"[^\w가-힣]", "_", title)[:50]
                    out = FIRE_DIR / f"KFMA_{clean}_{fseq}{ext}"
                    out.write_bytes(d3)
                    print(f"      SAVED: {out.name} ({len(d3)//1024}KB)")
                    saved.append(out.name)
                    break
                print(f"      {dl_path}: {r3.status_code}, {len(d3)}bytes")

    time.sleep(0.5)

print(f"\n완료: {len(saved)}건")
for f in saved:
    print(f"  {f}")
