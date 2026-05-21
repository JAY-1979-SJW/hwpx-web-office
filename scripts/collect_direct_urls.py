"""
확인된 직접 다운로드 URL로 서식 수집
- KEEA 한국전기기술인협회 감리 서식
- KFMA 소방시설관리협회 자체점검 서식
- 강원소방서 자체점검 서식
- 전력시설물 공사감리업무수행지침
"""
import requests, re, time, logging, zipfile, io
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("/home/ubuntu/app/haehan-platform/storage/templates/inspection/collect_direct.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger()

BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"
saved = []

def detect_ext(data: bytes) -> str:
    if not data: return ".bin"
    if data[:4] == b"%PDF": return ".pdf"
    if data[:4] == bytes([0xd0, 0xcf, 0x11, 0xe0]): return ".hwp"
    if data[:2] == b"PK":
        try:
            ns = " ".join(zipfile.ZipFile(io.BytesIO(data)).namelist())
            return ".xlsx" if "xl/" in ns else ".hwpx"
        except:
            return ".zip"
    return ".bin"

def dl_save(url, headers, save_dir, fname_base, doc_type, source):
    try:
        r = requests.get(url, headers=headers, timeout=25, allow_redirects=True)
        d = r.content
        if r.status_code != 200:
            log.warning(f"  MISS [{fname_base}] HTTP {r.status_code}")
            return False
        if len(d) < 200:
            log.warning(f"  MISS [{fname_base}] 빈 응답 ({len(d)}bytes)")
            return False
        if b"<!DOCTYPE" in d[:300] or b"<html" in d[:300].lower():
            log.warning(f"  MISS [{fname_base}] HTML 응답")
            return False
        ext = detect_ext(d)
        out = Path(save_dir) / (fname_base + ext)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(d)
        kb = len(d) // 1024
        log.info(f"  OK  [{doc_type}] {out.name} ({kb}KB)")
        saved.append({"file": str(out.relative_to(BASE)), "doc_type": doc_type,
                      "source": source, "size_kb": kb,
                      "saved_at": datetime.now().isoformat()})
        return True
    except Exception as e:
        log.error(f"  ERR [{fname_base}] {e}")
        return False

H_BASE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

log.info("=" * 60)
log.info("직접 URL 서식 수집")
log.info("=" * 60)

# ── 1. KEEA 한국전기기술인협회 감리 서식 ────────────────────────────
log.info("\n[1] KEEA 한국전기기술인협회 감리 서식")
ELEC_DIR = BASE / "전력기술관리법_시행규칙"
H_KEEA = {**H_BASE, "Referer": "https://www.keea.or.kr/"}

KEEA_FILES = [
    ("mon_person_put_plan.hwp",           "KEEA_감리원배치계획서"),
    ("mon_person_put_info_27th.hwp",      "KEEA_감리원배치정보_별지27호"),
    ("const_mon_finish_27-3th.hwp",       "KEEA_공사감리완료보고_별지27-3호"),
    ("const_mon_finish_reson.hwp",        "KEEA_감리완료보고사유서"),
    ("will_const_all_form.hwp",           "KEEA_공사감리전체서식모음"),
    ("union_gamri_form.hwp",              "KEEA_공동감리서식"),
    ("design_mon_apply_18th.hwp",         "KEEA_설계감리원신청서_별지18호"),
    ("design_mon_regi_29th.hwp",          "KEEA_설계감리원등록_별지29호"),
    ("house_mon_select_info_35-5th.hwp",  "KEEA_주택감리원선정정보_별지35-5호"),
    ("safety_work_guide_form.hwp",        "KEEA_안전작업지침서"),
]
for o_file, fname in KEEA_FILES:
    url = f"https://www.keea.or.kr/head/fileDownload.do?path=/pds/&O_FILE={o_file}"
    dl_save(url, H_KEEA, ELEC_DIR, fname, "전기감리서식", "한국전기기술인협회(KEEA)")
    time.sleep(0.5)

# ── 2. KFMA 소방시설관리협회 자체점검 서식 ────────────────────────
log.info("\n[2] KFMA 소방시설관리협회 자체점검 서식")
FIRE_DIR = BASE / "소방시설법_시행규칙"
H_KFMA = {**H_BASE, "Referer": "https://www.kfma.kr/"}

KFMA_FILES = [
    ("[첨부]_소방시설등+자체점검기록표+양식+A4+사이즈.hwp",
     "20221202011341_[첨부]_소방시설등+자체점검기록표+양식+A4+사이즈.hwp",
     "KFMA_소방시설자체점검기록표_2022개정"),
    ("소방시설+외관점검표(세대+점검용)[별지+제36호서식].hwp",
     "20221201093227_소방시설+외관점검표(세대+점검용)[별지+제36호서식].hwp",
     "KFMA_소방시설외관점검표_세대점검용_별지36호"),
]
for org_name, file_name, fname in KFMA_FILES:
    url = (f"https://www.kfma.kr/kfma/fileDownload"
           f"?orgFileName={org_name}"
           f"&fileName={file_name}"
           f"&fileDir=G:/files/file&mode=file")
    dl_save(url, H_KFMA, FIRE_DIR, fname, "소방자체점검서식", "한국소방시설관리협회(KFMA)")
    time.sleep(0.8)

# ── 3. 강원소방서(속초) 자체점검 서식 ────────────────────────────
log.info("\n[3] 강원소방서 자체점검 서식")
H_FIRE = {**H_BASE, "Referer": "https://fire.gwd.go.kr/"}

GWD_FILES = [
    (1211601, "강원소방_자체점검실시결과보고서_별지9호"),
    (1211602, "강원소방_자체점검결과이행계획서_별지10호"),
    (1212147, "강원소방_자체점검기록표_게시용"),
]
for file_seq, fname in GWD_FILES:
    url = f"https://fire.gwd.go.kr/egf/bp/board/article/download?fileSeq={file_seq}"
    dl_save(url, H_FIRE, FIRE_DIR, fname, "소방자체점검서식", "강원도소방본부")
    time.sleep(0.5)

# ── 4. 전력시설물 공사감리업무수행지침 HWP ────────────────────────
log.info("\n[4] 전력시설물 공사감리업무수행지침")
H_24 = {**H_BASE, "Referer": "https://www.24time.kr/"}
dl_save(
    "https://www.24time.kr/bbs/download.php?bo_table=cus_3&wr_id=33&no=0",
    H_24, BASE / "전력기술관리법_시행규칙",
    "전력시설물_공사감리업무수행지침_별지서식모음",
    "전기감리업무수행지침", "24time.kr (산업부 고시 반영)"
)

# ── 5. 결과 분류 요약 ────────────────────────────────────────────
log.info("\n" + "=" * 60)
log.info(f"수집 완료: 총 {len(saved)}건")

by_type = {}
for item in saved:
    t = item["doc_type"]
    by_type.setdefault(t, []).append(item)

for dtype, items in sorted(by_type.items()):
    log.info(f"\n  [{dtype}] {len(items)}건")
    for it in items:
        log.info(f"    {it['file']} ({it['size_kb']}KB)")
