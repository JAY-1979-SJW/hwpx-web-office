import requests, re, time, logging, json
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("/home/ubuntu/app/haehan-platform/storage/templates/inspection/collect_additional.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger()

BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"
results = []

def detect_ext(data):
    if not data or len(data) < 4: return None
    if data[:4] == b"%PDF": return ".pdf"
    if data[:4] == bytes([0xd0, 0xcf, 0x11, 0xe0]): return ".hwp"
    if data[:2] == b"PK":
        import zipfile, io
        try:
            ns = " ".join(zipfile.ZipFile(io.BytesIO(data)).namelist())
            return ".xlsx" if "xl/" in ns else ".hwpx"
        except:
            return ".zip"
    return None

def save(data, path, source, doc_type):
    if not data: return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    kb = len(data) // 1024
    log.info(f"  SAVED [{doc_type}] {path.name} ({kb}KB)")
    results.append({"file": str(path.relative_to(BASE)), "doc_type": doc_type,
                    "source": source, "size_kb": kb, "saved_at": datetime.now().isoformat()})
    return True

def dl(url, headers, label="", timeout=25):
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        d = r.content
        if r.status_code != 200 or len(d) < 200:
            log.warning(f"  MISS [{label}] status={r.status_code} size={len(d)}")
            return None
        if b"<!DOCTYPE" in d[:300] or b"<html" in d[:300].lower():
            log.warning(f"  MISS [{label}] HTML 응답")
            return None
        return d
    except Exception as e:
        log.error(f"  ERR [{label}] {e}")
        return None

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

log.info("=" * 60)
log.info("추가 감리서식 수집 시작")
log.info("=" * 60)

# ── 1. KICA 정보통신공사 감리업무수행기준 ──────────────────────────
log.info("\n[1] KICA 정보통신공사 감리")
kica_dir = BASE / "정보통신_감리"
H_KICA = {**H, "Referer": "https://ictis.kica.or.kr/"}

d = dl("https://ictis.kica.or.kr/file/download/e20336d7-50f2-42b9-8854-6098fe1b7a88",
       H_KICA, "KICA_감리업무수행기준")
if d:
    ext = detect_ext(d) or ".pdf"
    save(d, kica_dir / ("KICA_정보통신공사감리업무수행기준" + ext), "한국정보통신공사협회", "감리업무수행기준")
time.sleep(1)

# KICA 서식자료실 크롤링
try:
    r = requests.get("https://ictis.kica.or.kr/bbs/1/list", headers=H_KICA, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    links = soup.find_all("a", href=re.compile(r"/bbs/1/view/"))
    kw = ["감리", "체크리스트", "점검표", "검측", "서식", "양식"]
    log.info(f"  KICA 게시물 {len(links)}건 중 관련 탐색")
    for lnk in links[:40]:
        title = lnk.get_text(strip=True)
        if not any(k in title for k in kw):
            continue
        rv = requests.get("https://ictis.kica.or.kr" + lnk["href"], headers=H_KICA, timeout=15)
        sv = BeautifulSoup(rv.text, "html.parser")
        for dlnk in sv.find_all("a", href=re.compile(r"/file/download/")):
            d2 = dl("https://ictis.kica.or.kr" + dlnk["href"], H_KICA, title[:20])
            if d2:
                ext = detect_ext(d2) or ".bin"
                clean = re.sub(r"[^\w가-힣]", "_", title)[:50]
                save(d2, kica_dir / ("KICA_" + clean + ext), "한국정보통신공사협회", "정보통신감리서식")
            time.sleep(0.3)
        time.sleep(0.3)
except Exception as e:
    log.error(f"  KICA 자료실: {e}")

# ── 2. KFMA 소방시설관리협회 서식 ──────────────────────────────────
log.info("\n[2] KFMA 소방시설관리협회 서식")
fire_dir = BASE / "소방시설법_시행규칙"
H_KFMA = {**H, "Referer": "https://www.kfma.kr/"}

for ntt_id, fname_base in [
    (40830, "소방자체점검결과보고서및점검표"),
    (40827, "소방자체점검기록표_2022개정"),
]:
    try:
        r2 = requests.get(
            f"https://www.kfma.kr/kfma/bbs/format/detail?nttId={ntt_id}",
            headers=H_KFMA, timeout=15)
        soup = BeautifulSoup(r2.text, "html.parser")
        dl_links = soup.find_all("a", href=re.compile(r"fileDownload|Download|\.hwp|\.pdf", re.I))
        log.info(f"  nttId={ntt_id}: 링크 {len(dl_links)}개")
        for i, dlnk in enumerate(dl_links):
            href = dlnk.get("href", "")
            if not href:
                continue
            full = "https://www.kfma.kr" + href if href.startswith("/") else href
            d2 = dl(full, H_KFMA, f"KFMA_{ntt_id}_{i}")
            if d2:
                ext = detect_ext(d2) or ".bin"
                save(d2, fire_dir / (fname_base + f"_{i}" + ext), "한국소방시설관리협회", "소방자체점검서식")
            time.sleep(0.5)
    except Exception as e:
        log.error(f"  KFMA nttId={ntt_id}: {e}")
    time.sleep(0.5)

# KFSI 소방안전원 서식자료실
log.info("\n  KFSI 소방안전원 서식")
H_KFSI = {**H, "Referer": "https://www.kfsi.or.kr/"}
try:
    r = requests.get(
        "https://www.kfsi.or.kr/main/infocenter/InfocenterBbsList.do?boardSeqno=10045",
        headers=H_KFSI, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("table tbody tr") or []
    log.info(f"  KFSI 목록 {len(rows)}건")
    for row in rows[:15]:
        link = row.find("a")
        if not link:
            continue
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not href or "javascript" in href:
            continue
        full = "https://www.kfsi.or.kr" + href if href.startswith("/") else href
        rv = requests.get(full, headers=H_KFSI, timeout=15)
        sv = BeautifulSoup(rv.text, "html.parser")
        for flnk in sv.find_all("a", href=re.compile(r"(fileDown|download|Seq=)", re.I)):
            fhref = flnk.get("href", "")
            if not fhref:
                continue
            furl = "https://www.kfsi.or.kr" + fhref if fhref.startswith("/") else fhref
            d2 = dl(furl, H_KFSI, title[:20])
            if d2:
                ext = detect_ext(d2) or ".bin"
                clean = re.sub(r"[^\w가-힣]", "_", title)[:50]
                save(d2, fire_dir / ("KFSI_" + clean + ext), "한국소방안전원", "소방점검서식")
            time.sleep(0.3)
        time.sleep(0.3)
except Exception as e:
    log.error(f"  KFSI: {e}")

# ── 3. NCS 전기설비감리 서식 ───────────────────────────────────────
log.info("\n[3] NCS 전기설비감리 서식")
elec_dir = BASE / "전력기술관리법_시행규칙"
H_NCS = {**H, "Referer": "https://www.ncs.go.kr/"}
ncs_url = (
    "https://www.ncs.go.kr/common/file/downloadFile.do?sysDstinCd=03"
    "&fileMstky=20160211095231579&filedetlSeq=20160211095231584"
    "&ncsLclasCd=19&ncsMclasCd=01&ncsSclasCd=06&ncsSubdCd=02"
    "&ncsCompeUnitCd=04&ncsDegr=7&downlDstinCd=02"
)
d = dl(ncs_url, H_NCS, "NCS_전기설비감리")
if d:
    ext = detect_ext(d) or ".pdf"
    save(d, elec_dir / ("NCS_전기설비감리시공관리" + ext), "NCS(국가직무능력표준)", "전기감리서식")

# ── 4. 결과 분류 및 저장 ─────────────────────────────────────────
log.info("\n" + "=" * 60)
log.info(f"수집 완료: 총 {len(results)}건")

TYPE_MAP = {
    "소방": ["소방", "KFMA", "KFSI"],
    "전기/전력": ["전기", "전력", "NCS"],
    "정보통신": ["정보통신", "KICA"],
    "건축/건설": ["건축", "건설", "LH", "국토"],
    "기계설비": ["기계설비"],
}
by_type = {}
for item in results:
    assigned = "기타"
    for dtype, kws in TYPE_MAP.items():
        if any(k in item["file"] or k in item["source"] for k in kws):
            assigned = dtype
            break
    by_type.setdefault(assigned, []).append(item)

for dtype, items in sorted(by_type.items()):
    log.info(f"\n  [{dtype}] {len(items)}건")
    for it in items:
        log.info(f"    - {it['file']} ({it['size_kb']}KB)")

(BASE / "collect_additional_log.json").write_text(
    json.dumps({
        "collected_at": datetime.now().isoformat(),
        "total": len(results),
        "by_type": {k: len(v) for k, v in by_type.items()},
        "files": results
    }, ensure_ascii=False, indent=2),
    encoding="utf-8"
)
log.info("\n결과 저장 완료")
