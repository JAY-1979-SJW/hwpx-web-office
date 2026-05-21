"""Playwright로 law.go.kr 법령 별지서식 목록 확인"""
import time, re
from playwright.sync_api import sync_playwright
from pathlib import Path

BASE = Path.home() / "app/haehan-platform/storage/templates/inspection"
collected = [f.name.lower() for f in BASE.rglob("*")
             if f.is_file() and f.suffix in {".hwp", ".hwpx", ".pdf", ".xlsx"}]

# (법령명, lsiSeq, 감리관련 키워드)
LAWS = [
    ("건설기술진흥법 시행규칙",  279455, ["감리", "건설사업관리"]),
    ("건축법 시행규칙",           283727, ["감리"]),
    ("소방시설공사업법 시행규칙", 282735, ["감리", "완공"]),
    ("소방시설법 시행규칙",       280195, ["자체점검", "점검"]),
    ("전력기술관리법 시행규칙",   278995, ["감리"]),
    ("기계설비법 시행규칙",       285589, ["감리", "점검"]),
    ("정보통신공사업법 시행규칙", 272931, ["감리"]),
]

def is_collected(title):
    no = re.search(r"제\s*(\d+[\-의\d]*)호", title)
    form_no = no.group(1).replace("-","의").replace(" ","") if no else ""
    words = [w for w in re.sub(r"[^\w가-힣]", " ", title).split() if len(w) >= 2]
    for fname in collected:
        if form_no and form_no in fname.replace("-","의"):
            return True
        if sum(1 for w in words[:5] if w.lower() in fname) >= 2:
            return True
    return False

all_missing = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    )
    page = ctx.new_page()

    for law_name, lsi_seq, kw_filter in LAWS:
        print(f"\n[{law_name}] lsiSeq={lsi_seq}")

        # 법령 상세 페이지 접근
        page.goto(
            f"https://www.law.go.kr/lsInfoP.do?lsiSeq={lsi_seq}",
            wait_until="networkidle", timeout=30000
        )
        time.sleep(2)

        # 별지서식 탭 클릭
        try:
            byls_tab = page.query_selector(
                "a[href*='BYL_FTXT'], li:has-text('별지서식'), button:has-text('별지서식')"
            )
            if byls_tab:
                byls_tab.click()
                time.sleep(2)
        except:
            pass

        # 별지서식 목록 텍스트 추출
        html = page.content()
        form_names = re.findall(r"[\[〔]별지\s*제?\s*[\d]+[\-\d의]+호서식?[\]〕][^<]{0,60}", html)
        fl_seqs = re.findall(r"flSeq['\",=\s]+(\d+)", html)

        # onclick 패턴에서 서식명
        onclick_forms = re.findall(r"bylNm['\",=\s]+([^'\"<>]{3,50}서식[^'\"<>]{0,30})", html)
        if not onclick_forms:
            onclick_forms = re.findall(r"bylNm['\",=\s]+([^'\"<>]{3,60})", html)

        # JavaScript 변수에서 추출
        js_forms = re.findall(r'"bylNm"\s*:\s*"([^"]+)"', html)
        js_fl = re.findall(r'"flSeq"\s*:\s*"?(\d+)"?', html)

        print(f"  form_names={len(form_names)}, fl_seqs={len(fl_seqs)}")
        print(f"  js_forms={len(js_forms)}, onclick_forms={len(onclick_forms)}")

        # 별지서식 텍스트 링크
        form_links = page.query_selector_all("a, button, span")
        form_items = []
        for el in form_links:
            txt = el.inner_text().strip()
            if len(txt) >= 4 and any(k in txt for k in ["별지", "서식", "별표"]):
                onclick = el.get_attribute("onclick") or ""
                m_fl = re.search(r"flSeq['\",=\s]+(\d+)", onclick)
                fl = m_fl.group(1) if m_fl else ""
                form_items.append((txt[:60], fl))

        print(f"  element 텍스트 {len(form_items)}건")

        # 감리 관련 필터링
        relevant = [(t, fl) for t, fl in form_items
                    if any(k in t for k in kw_filter)]
        if js_forms:
            for nm, fl in zip(js_forms, js_fl or [""]*len(js_forms)):
                if any(k in nm for k in kw_filter):
                    relevant.append((nm, fl))

        print(f"  관련 {len(relevant)}건")
        for txt, fl in relevant[:30]:
            ok = is_collected(txt)
            print(f"  {'✓' if ok else '✗'} {txt[:60]} (flSeq={fl})")
            if not ok and fl:
                all_missing.append({"law": law_name, "title": txt, "flSeq": fl})

    browser.close()

print(f"\n미수집: {len(all_missing)}건")
for m in all_missing:
    print(f"  [{m['law'][:16]}] {m['title'][:55]}  flSeq={m['flSeq']}")
