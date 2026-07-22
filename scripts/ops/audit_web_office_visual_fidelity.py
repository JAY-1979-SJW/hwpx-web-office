"""WEB-OFFICE-VISUAL-FIDELITY-AUDIT — 한컴 원본 렌더(PrvImage) 픽셀 대조.

각 HWPX 에 한컴이 저장한 1페이지 원본 렌더(Preview/PrvImage.png)를 정답지로,
우리 좌표 렌더러의 헤드리스 Chrome 스크린샷을 정합(shift 탐색) 후 대조한다.

주 지표는 폰트와 무관한 **표 격자선 위치 오차**(mean|Δ|px, 2px이내 비율).
표 없는 문서는 행 잉크 프로파일 상관계수로 대체. read-only, 원본 무수정.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/hwpx"))

from scripts.hwpx.web_office.coordinate_layout import extract  # noqa: E402
from scripts.ops.audit_web_office_coord_corpus import (  # noqa: E402
    _read_prv_text, _char_coverage)

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
DEFAULT_ROOTS = ["samples", "tests/fixtures/hwpx", "data/drafts"]
INK = 165          # 잉크 임계(그레이스케일)
GRID_FRAC = 0.45   # 가로줄로 인정할 행 잉크 비율
SHIFT = 40         # 정합 탐색 범위(px)


def _chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        if Path(c).is_file():
            return c
    return None


def _renderer_js() -> str:
    base = ROOT / "frontend/web_office_viewer/weboffice"
    sres = (base / "style_resolver.mjs").read_text(encoding="utf-8")
    rend = (base / "coordinate_renderer.mjs").read_text(encoding="utf-8")
    sres = sres.replace("export function", "function").replace(
        "export const", "const")
    rend = rend.replace(
        'import { charPrToCss } from "./style_resolver.mjs";', "").replace(
        "export function", "function")
    return sres + "\n" + rend


def _prv_image(path: Path) -> bytes | None:
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.endswith("PrvImage.png")]
            return z.read(names[0]) if names else None
    except Exception:
        return None


def _profiles(img):
    """(rowInkCounts, colInkCounts) — 순수 PIL, numpy 무의존."""
    w, h = img.size
    px = img.load()
    rows = [0] * h
    cols = [0] * w
    for y in range(h):
        r = 0
        for x in range(w):
            if px[x, y] < INK:
                r += 1
                cols[x] += 1
        rows[y] = r
    return rows, cols


def _corr(a, b):
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def _best_shift(a, b, rng=SHIFT):
    """corr 최대 shift s — b(우리) 위치 p 는 a(정답) 위치 p+s 에 대응."""
    best = (0, -9.0)
    for s in range(-rng, rng + 1):
        if s >= 0:
            c = _corr(a[s:], b[: len(a) - s] if s else b)
        else:
            c = _corr(a[:s], b[-s:])
        if c > best[1]:
            best = (s, c)
    return best


def _resample(prof, factor):
    """1-D 프로파일 선형 리샘플 — 이미지 재렌더 없이 배율 탐색용."""
    n2 = max(2, int(round(len(prof) * factor)))
    out = [0.0] * n2
    last = len(prof) - 1
    for i in range(n2):
        srcf = i / factor
        j = int(srcf)
        t = srcf - j
        if j >= last:
            out[i] = prof[last]
        else:
            out[i] = prof[j] * (1 - t) + prof[j + 1] * t
    return out


def _best_scale_shift(truth_prof, our_prof):
    """(배율, shift, corr) — 썸네일 배율 오차(±4%)까지 흡수해 정합."""
    best = (1.0, 0, -9.0)
    for k in range(-10, 11):
        sv = 1 + k * 0.004
        s, c = _best_shift(truth_prof, _resample(our_prof, sv))
        if c > best[2]:
            best = (sv, s, c)
    return best


def _gridlines(rows, width):
    """행 잉크 프로파일 → 가로 격자선 중심 y 목록(연속 픽셀 군집화)."""
    hits = [i for i, v in enumerate(rows) if v > GRID_FRAC * width]
    out: list[float] = []
    grp: list[int] = []
    for i in hits:
        if grp and i - grp[-1] > 2:
            out.append(sum(grp) / len(grp))
            grp = []
        grp.append(i)
    if grp:
        out.append(sum(grp) / len(grp))
    return out


def compare_one(path: Path, chrome: str, workdir: Path,
                renderer_js: str, project_root: Path) -> dict:
    rel = str(path.relative_to(project_root)) if path.is_relative_to(
        project_root) else str(path)
    rec: dict = {"path": rel, "verdict": "OK", "warnings": []}
    truth_bytes = _prv_image(path)
    if not truth_bytes:
        rec["verdict"] = "SKIP"
        rec["warnings"].append("NO_PRVIMAGE")
        return rec
    try:
        lay = extract(str(path))
        if not lay.get("lines") and not lay.get("boxes"):
            # 한컴 미저장 파일(프로그램 생성 등) — lineseg 없음. 좌표 렌더
            # 대상 아님 → 흐름 렌더러 폴백 부류로 분류.
            rec["verdict"] = "WARN"
            rec["warnings"].append("NO_LINESEG_DATA")
            return rec
        # 정답지 신선도 — 문서 텍스트가 PrvText 에 없으면 XML 이 프리뷰
        # 저장 이후 수정된 것(예: 자동 fill). 실효 정답지와의 픽셀 비교는
        # 뷰어 결함이 아니므로 STALE_TRUTH 로 분리 집계한다.
        truth_txt = _read_prv_text(path)
        if truth_txt.strip():
            ours_txt = "\n".join(
                ln.get("text", "") for ln in lay.get("lines", []))
            if _char_coverage(truth_txt, ours_txt) < 0.9:
                rec["verdict"] = "STALE"
                rec["warnings"].append("PREVIEW_OLDER_THAN_XML")
                return rec
        W = int(round(lay["pageWidthPx"])) or 794
        H = int(round(lay["pageHeightPx"])) or 1123
        html = (
            '<!doctype html><meta charset="utf-8"><style>'
            "html,body{margin:0;background:#fff;}"
            'body{font-family:"함초롬바탕","바탕","Malgun Gothic",serif;}'
            ".co-page{position:relative;background:#fff;"
            f"width:{W}px;height:{H}px;}}"
            ".co-line{position:absolute;white-space:pre;overflow:clip;"
            "overflow-clip-margin:3px;}.co-box{position:absolute;}"
            '</style><div id="s"></div><script type="module">\n'
            + renderer_js
            + '\nconst r=document.getElementById("s");'
            + "r.innerHTML=renderCoordinateLayout("
            + json.dumps(lay, ensure_ascii=False)
            + ");autoFitLines(r);</script>"
        )
        hf = workdir / "page.html"
        sf = workdir / "shot.png"
        hf.write_text(html, encoding="utf-8")
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=1", f"--window-size={W},{H + 1}",
             f"--screenshot={sf}", "--default-background-color=FFFFFFFF",
             hf.as_uri()],
            capture_output=True, timeout=45, check=False)
        if not sf.is_file():
            raise RuntimeError("SCREENSHOT_FAILED")

        from PIL import Image
        import io
        truth = Image.open(io.BytesIO(truth_bytes)).convert("L")
        ours = Image.open(sf).convert("L").resize(truth.size)
        sf.unlink(missing_ok=True)
        tw, th = truth.size
        rowsT, colsT = _profiles(truth)
        rowsO, colsO = _profiles(ours)
        sv, sy, rc = _best_scale_shift(rowsT, rowsO)
        sh, sx, cc = _best_scale_shift(colsT, colsO)
        rec["rowCorr"] = round(rc, 3)
        rec["colCorr"] = round(cc, 3)
        rec["scaleY"] = round(sv, 3)

        glT = _gridlines(rowsT, tw)
        # 배율·shift 정합 반영: 정답 좌표 = 우리 좌표*sv + sy
        glO = [g * sv + sy for g in _gridlines(rowsO, tw)]
        rec["gridlinesTruth"] = len(glT)
        if len(glT) >= 3 and glO:
            offs = [min((abs(g - t), g - t) for g in glO)[1] for t in glT]
            aoffs = sorted(abs(o) for o in offs)
            rec["gridMeanAbsPx"] = round(sum(aoffs) / len(aoffs), 2)
            rec["gridMedianAbsPx"] = round(aoffs[len(aoffs) // 2], 2)
            rec["gridWithin2px"] = round(
                sum(1 for o in aoffs if o <= 2) / len(aoffs), 3)
            # 판정은 median(중앙값 오차) 주도 — 시각 정확도의 핵심 지표.
            # within2px 는 하위픽셀 정밀도라 median<1.5px 인 near-perfect
            # 문서도 임계 근처 격자선 소수 때문에 0.75 아래로 떨어져 오탐한다.
            # → median>3px(육안 인지 가능) 이거나, within2px 가 매우 낮고
            #   (<0.4) median 도 1.5px 초과일 때만 WARN.
            if (rec["gridMedianAbsPx"] > 3.0
                    or (rec["gridWithin2px"] < 0.40
                        and rec["gridMedianAbsPx"] > 1.5)):
                rec["verdict"] = "WARN"
                rec["warnings"].append(
                    f"GRID_MISALIGN:med{rec['gridMedianAbsPx']}px")
        else:
            # 표 없는 문서 — 행 프로파일 상관으로 판정 (폰트 영향 있음: 완화)
            if rc < 0.55:
                rec["verdict"] = "WARN"
                rec["warnings"].append(f"ROW_PROFILE_LOW:{rc:.2f}")
    except Exception as e:
        rec["verdict"] = "ERROR"
        rec["error"] = f"{type(e).__name__}: {e}"[:140]
    return rec


def discover(roots, project_root: Path, limit: int) -> list[Path]:
    seen: list[Path] = []
    for r in roots:
        base = (project_root / r) if not Path(r).is_absolute() else Path(r)
        if base.exists():
            seen.extend(sorted(base.rglob("*.hwpx")))
    if limit and len(seen) > limit:
        step = max(1, len(seen) // limit)
        seen = seen[::step][:limit]
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", action="append", default=None)
    ap.add_argument("--limit", type=int, default=0,
                    help="균등 샘플 상한(0=전수). 문서당 ~2-3초 소요")
    ap.add_argument("--json", default=None)
    ap.add_argument("--worst", type=int, default=15)
    args = ap.parse_args()

    chrome = _chrome()
    if not chrome:
        print(json.dumps({"verdict": "SKIP", "reason": "NO_CHROME"}))
        return 0
    files = discover(args.root or DEFAULT_ROOTS, ROOT, args.limit)
    rjs = _renderer_js()
    results = []
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        for p in files:
            results.append(compare_one(p, chrome, wd, rjs, ROOT))

    from collections import Counter
    by = Counter(r["verdict"] for r in results)
    graded = [r for r in results if r.get("gridWithin2px") is not None]
    ranked = sorted(
        (r for r in results if r["verdict"] in ("WARN", "ERROR")),
        key=lambda r: (r["verdict"] != "ERROR",
                       r.get("gridWithin2px", 0.0)))
    summary = {
        "schemaVersion": "web_office_visual_fidelity_audit_v1",
        "verdict": ("PASS_WEB_OFFICE_VISUAL_FIDELITY_AUDIT"
                    if not by.get("ERROR") else
                    "FAIL_WEB_OFFICE_VISUAL_FIDELITY_AUDIT"),
        "compared": len(results),
        "ok": by.get("OK", 0), "warn": by.get("WARN", 0),
        "error": by.get("ERROR", 0), "skip": by.get("SKIP", 0),
        "staleTruth": by.get("STALE", 0),
        "grid": {
            "docs": len(graded),
            "meanAbsPx": round(sum(r["gridMeanAbsPx"] for r in graded)
                               / len(graded), 2) if graded else None,
            "within2pxMean": round(sum(r["gridWithin2px"] for r in graded)
                                   / len(graded), 3) if graded else None,
        },
        "worst": [
            {k: r.get(k) for k in ("path", "verdict", "gridMeanAbsPx",
                                   "gridWithin2px", "rowCorr",
                                   "warnings", "error")}
            for r in ranked[: args.worst]
        ],
    }
    if args.json:
        Path(args.json).write_text(
            json.dumps({"summary": summary, "results": results},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
