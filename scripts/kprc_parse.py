"""
kprc.or.kr 주요자재 가격 PDF 파싱 (Claude Code CLI OCR)
- 대상: 주요자재별_거래가격 3년치 (2024~2026)
- 모델: claude-haiku-4-5-20251001 (claude CLI, API 키 불필요)
- 출력: ~/Downloads/kprc_pdf/result/주요자재_가격_3년_YYYYMMDD.json
"""

import json, re, fitz, subprocess
from pathlib import Path
from datetime import datetime

PDF_DIR  = Path.home() / "Downloads/kprc_pdf/주요자재별_거래가격"
OUT_DIR  = Path.home() / "Downloads/kprc_pdf/result"
TMP_DIR  = Path.home() / "Downloads/kprc_pdf/tmp_pages"
MODEL    = "claude-haiku-4-5-20251001"
YEAR_MIN = 2024


# ── 이미지 렌더링 ────────────────────────────────────────────────────────────

def render_page_to_file(pdf_path: Path, page_idx: int, scale: float) -> Path | None:
    """PDF 페이지 한 장을 PNG 파일로 저장 후 경로 반환."""
    doc = fitz.open(str(pdf_path))
    if page_idx >= doc.page_count:
        doc.close()
        return None
    mat = fitz.Matrix(scale, scale)
    pix = doc[page_idx].get_pixmap(matrix=mat)
    out = TMP_DIR / f"page_{page_idx:03d}.png"
    pix.save(str(out))
    doc.close()
    return out


# ── Claude Code CLI OCR ──────────────────────────────────────────────────────

PROMPT_TABLE = """아래 이미지는 한국 건설자재 월별 가격표다.
표에서 데이터를 추출해 JSON만 반환하라 (설명 없이):

{
  "items": [
    {
      "품목명": "고장력철근",
      "규격": "SD400, 10mm",
      "단위": "톤",
      "가격": [
        {"연도": 2024, "월": 1, "가격": 950000},
        {"연도": 2024, "월": 2, "가격": 960000}
      ]
    }
  ]
}

규칙:
- 2024년 이후 데이터만 추출
- 가격 없는 셀은 null (행에서 제외)
- 숫자는 쉼표 제거한 정수
- 품목명·규격·단위는 표에 있는 그대로"""

PROMPT_CHART = """아래 이미지는 건설자재 가격 차트와 그 아래 표다.
표에서 2024년 이후 데이터만 추출해 JSON만 반환하라:

{
  "items": [
    {
      "품목명": "고장력철근",
      "규격": "SD400, KSD3504",
      "단위": "톤",
      "가격": [
        {"연도": 2024, "월": 1, "가격": 950000}
      ]
    }
  ]
}

규칙:
- 페이지 당 여러 품목 가능
- 표 하단의 연도/월 열 확인
- 숫자 쉼표 제거"""


def ocr_page(img_path: Path, prompt: str) -> list[dict]:
    """Claude Code CLI로 이미지 OCR → 품목 리스트 반환."""
    full_prompt = f"{prompt}\n\n이미지 파일 경로: {img_path}"
    try:
        result = subprocess.run(
            [
                "claude", "-p", full_prompt,
                "--tools", "Read",
                "--model", MODEL,
                "--dangerously-skip-permissions",
                "--output-format", "text",
            ],
            capture_output=True, text=True, timeout=120,
        )
        text = result.stdout.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group()).get("items", [])
        if result.returncode != 0:
            print(f"    [CLI ERR] {result.stderr[:200]}")
    except Exception as e:
        print(f"    [OCR ERROR] {e}")
    return []


# ── PDF 1개 파싱 ─────────────────────────────────────────────────────────────

def parse_pdf(pdf_path: Path) -> list[dict]:
    """PDF 전체 파싱 → [{품목명, 규격, 단위, 연도, 월, 가격, 출처}] 반환."""
    rows = []
    doc  = fitz.open(str(pdf_path))
    n    = doc.page_count
    doc.close()
    print(f"  페이지 수: {n}")

    def _collect(page_idx: int, scale: float, prompt: str, label: str) -> list[dict]:
        img = render_page_to_file(pdf_path, page_idx, scale)
        if not img:
            return []
        items = ocr_page(img, prompt)
        img.unlink(missing_ok=True)
        return items

    # p1~p4: 차트 페이지
    for i in range(min(4, n)):
        items = _collect(i, 2.0, PROMPT_CHART, f"chart p{i+1}")
        for item in items:
            for p in item.get("가격", []):
                if p.get("연도", 0) >= YEAR_MIN and p.get("가격") is not None:
                    rows.append({
                        "품목명": item.get("품목명", ""),
                        "규격":   item.get("규격", ""),
                        "단위":   item.get("단위", ""),
                        "연도":   p["연도"], "월": p["월"], "가격": p["가격"],
                        "출처":   "차트페이지",
                    })
        print(f"    chart p{i+1}: {len(items)}품목")

    # p5~: 종합 가격표 페이지
    for i in range(4, n):
        items = _collect(i, 2.5, PROMPT_TABLE, f"table p{i+1}")
        for item in items:
            for p in item.get("가격", []):
                if p.get("연도", 0) >= YEAR_MIN and p.get("가격") is not None:
                    rows.append({
                        "품목명": item.get("품목명", ""),
                        "규격":   item.get("규격", ""),
                        "단위":   item.get("단위", ""),
                        "연도":   p["연도"], "월": p["월"], "가격": p["가격"],
                        "출처":   "종합표",
                    })
        print(f"    table p{i+1}: {len(items)}품목")

    return rows


# ── JSON 저장 ────────────────────────────────────────────────────────────────

def save_json(all_rows: list[dict], out_path: Path):
    pivot: dict = {}
    for r in all_rows:
        key = f"{r['품목명']}|{r['규격']}"
        if key not in pivot:
            pivot[key] = {"품목명": r["품목명"], "규격": r["규격"], "단위": r["단위"], "가격": []}
        pivot[key]["가격"].append({"연도": r["연도"], "월": r["월"], "가격": r["가격"]})

    out_path.write_text(json.dumps({
        "생성일시": datetime.now().isoformat(timespec="seconds"),
        "총행수":   len(all_rows),
        "품목수":   len(pivot),
        "rows":     all_rows,
        "pivot":    list(pivot.values()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON 저장: {out_path}")


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(PDF_DIR.glob("*.pdf"), reverse=True)
    print(f"대상 PDF: {len(pdfs)}개")
    for p in pdfs:
        print(f"  {p.name}")

    all_rows: list[dict] = []
    for i, pdf in enumerate(pdfs, 1):
        print(f"\n[{i}/{len(pdfs)}] {pdf.name}")
        rows = parse_pdf(pdf)
        all_rows.extend(rows)
        print(f"  → {len(rows)}행 추출 (누적 {len(all_rows)}행)")

    if not all_rows:
        print("추출된 데이터 없음")
        return

    seen: set = set()
    deduped: list[dict] = []
    for r in all_rows:
        k = (r["품목명"], r["규격"], r["연도"], r["월"])
        if k not in seen:
            seen.add(k)
            deduped.append(r)

    print(f"\n중복 제거 후: {len(deduped)}행")
    stamp = datetime.now().strftime("%Y%m%d")
    save_json(deduped, OUT_DIR / f"주요자재_가격_3년_{stamp}.json")


if __name__ == "__main__":
    main()
