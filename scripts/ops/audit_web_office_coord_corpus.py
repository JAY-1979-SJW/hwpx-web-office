"""WEB-OFFICE-COORD-CORPUS-AUDIT — 로컬 HWPX 전수 좌표 렌더 감사.

저장소 내(또는 --root 로 지정한) 모든 .hwpx 를 coordinate_layout 으로
추출해 뷰어 불변식을 검사하고, 한컴 내장 PrvText(자체 텍스트 추출본)와
대조해 텍스트 충실도를 채점한다. 실패/경고 랭킹이 곧 뷰어 완성 작업목록.

read-only — 원본 무수정. 보고는 stdout(JSON). 파일 저장은 --json 지정 시만.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/hwpx"))

from scripts.hwpx.web_office.coordinate_layout import extract  # noqa: E402

DEFAULT_ROOTS = ["samples", "tests/fixtures/hwpx", "data/drafts"]

PASS_VERDICT = "PASS_WEB_OFFICE_COORD_CORPUS_AUDIT"
FAIL_VERDICT = "FAIL_WEB_OFFICE_COORD_CORPUS_AUDIT"


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and v == v and abs(v) < 1e7


def _read_prv_text(path: Path) -> str:
    """HWPX 내장 Preview/PrvText.txt (한컴 자체 텍스트) — 충실도 정답지."""
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.endswith("PrvText.txt")]
            if not names:
                return ""
            raw = z.read(names[0])
        # BOM 이 있으면 utf-16 확정. 없으면 utf-8 먼저 — utf-8 은 엄격한
        # 검증기라 오검출이 없지만, utf-16 은 아무 짝수 바이트열이나
        # "성공"해 mojibake 를 만든다(순서 바꾸면 0점 오탐 대량 발생).
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            try:
                return raw.decode("utf-16")
            except (UnicodeDecodeError, UnicodeError):
                pass
        try:
            t = raw.decode("utf-8")
            if "\x00" not in t:   # ASCII-계열 utf-16 오검출 방지
                return t
        except UnicodeDecodeError:
            pass
        for enc in ("utf-16", "cp949"):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
    except Exception:
        pass
    return ""


def _char_coverage(ours: str, truth: str) -> float:
    """PrvText 문자(공백 제외)가 우리 추출본에 얼마나 있는지 [0..1].

    multiset 교집합 — 순서 무관 문자 단위라 낙관적이지만, 통째로 빠진
    블록(누락 셀/문단)을 안정적으로 잡아낸다. '<' '>' 는 PrvText 의 셀
    구분 마크업이라 채점에서 제외(실텍스트와 구분 불가한 형식 문자).
    """
    skip = "<>"
    t = Counter(c for c in truth if not c.isspace() and c not in skip)
    if not t:
        return 1.0
    o = Counter(c for c in ours if not c.isspace() and c not in skip)
    hit = sum(min(n, o.get(c, 0)) for c, n in t.items())
    return hit / sum(t.values())


def _cellid_summary(results: list[dict]) -> dict:
    vals = [r["cellIdMatch"] for r in results
            if r.get("cellIdMatch") is not None]
    if not vals:
        return {"docs": 0}
    return {
        "docs": len(vals),
        "mean": round(sum(vals) / len(vals), 3),
        "min": round(min(vals), 3),
        "under98": sum(1 for v in vals if v < 0.98),
    }


def audit_one(path: Path, project_root: Path) -> dict:
    rel = str(path.relative_to(project_root)) if path.is_relative_to(
        project_root) else str(path)
    rec: dict = {"path": rel, "verdict": "OK", "warnings": []}
    t0 = time.time()
    try:
        lay = extract(str(path))
    except Exception as e:
        rec["verdict"] = "ERROR"
        rec["error"] = f"{type(e).__name__}: {e}"[:160]
        return rec
    rec["seconds"] = round(time.time() - t0, 2)
    rec["pages"] = lay.get("pages", 0)
    rec["lines"] = len(lay.get("lines", []))
    rec["boxes"] = len(lay.get("boxes", []))

    pw, ph = lay.get("pageWidthPx", 0), lay.get("pageHeightPx", 0)
    if not (pw > 50 and ph > 50):
        rec["warnings"].append("PAGE_GEOMETRY_BAD")

    bad_coord = bad_span = off_page = 0
    for ln in lay.get("lines", []):
        if not all(_finite(ln.get(k)) for k in ("x", "y", "w", "h")):
            bad_coord += 1
            continue
        if ln.get("segments"):
            joined = "".join(s.get("text", "") for s in ln["segments"])
            if joined != ln.get("text", ""):
                bad_span += 1
        if pw and (ln["x"] < -2 or ln["x"] > pw + 2):
            off_page += 1
    if bad_coord:
        rec["warnings"].append(f"NONFINITE_COORDS:{bad_coord}")
    if bad_span:
        rec["warnings"].append(f"SEGMENT_TEXT_MISMATCH:{bad_span}")
    if off_page:
        rec["warnings"].append(f"LINE_OFF_PAGE_X:{off_page}")

    neg_box = sum(1 for b in lay.get("boxes", [])
                  if not (b.get("w", 0) > 0 and b.get("h", 0) > 0))
    if neg_box:
        rec["warnings"].append(f"BOX_NONPOSITIVE:{neg_box}")

    # 편집 연결성 — 좌표 박스 cellId 가 문서모델 셀 ID 와 일치하는지(편집
    # 파이프라인 연결). 불일치 셀은 클릭 편집이 안 된다.
    box_ids = {b["cellId"] for b in lay.get("boxes", []) if b.get("cellId")}
    if box_ids:
        try:
            from scripts.hwpx.web_office.ro_view_importer import (
                import_hwpx_as_ro_view)
            doc = import_hwpx_as_ro_view(path)
            model_ids = {c.cellId for c in doc.cells}
            matched = box_ids & model_ids
            rec["cellIdMatch"] = round(len(matched) / len(box_ids), 3)
            rec["inputCells"] = sum(
                1 for c in doc.cells if not (c.text or "").strip())
            if rec["cellIdMatch"] < 0.98:
                rec["warnings"].append(
                    f"CELLID_MISMATCH:{rec['cellIdMatch']:.2f}")
        except Exception as e:
            rec["warnings"].append(f"CELLID_CHECK_FAIL:{type(e).__name__}")

    # 페이지 인플레이션 휴리스틱: 내용 대비 페이지 과다(빈 페이지 남발)
    if rec["pages"] > 3 and rec["lines"] / max(1, rec["pages"]) < 6:
        rec["warnings"].append("PAGE_INFLATION_SUSPECT")

    # 텍스트 충실도 (한컴 PrvText 대조)
    truth = _read_prv_text(path)
    if truth.strip():
        ours = "\n".join(ln.get("text", "") for ln in lay.get("lines", []))
        cov = _char_coverage(ours, truth)
        rec["textCoverage"] = round(cov, 3)
        if cov < 0.85:
            rec["warnings"].append(f"TEXT_COVERAGE_LOW:{cov:.2f}")
    else:
        rec["textCoverage"] = None

    if rec["warnings"]:
        rec["verdict"] = "WARN"
    return rec


def discover(roots: list[str], project_root: Path, limit: int = 0) -> list[Path]:
    seen: list[Path] = []
    for r in roots:
        base = (project_root / r) if not Path(r).is_absolute() else Path(r)
        if not base.exists():
            continue
        seen.extend(sorted(base.rglob("*.hwpx")))
    if limit:
        step = max(1, len(seen) // limit)
        seen = seen[::step][:limit]
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", action="append", default=None,
                    help="검색 루트(반복 지정 가능). 기본: 저장소 표준 위치")
    ap.add_argument("--limit", type=int, default=0,
                    help="균등 샘플링 상한(0=전수)")
    ap.add_argument("--json", default=None, help="상세 결과 JSON 저장 경로")
    ap.add_argument("--worst", type=int, default=15,
                    help="요약에 표시할 최악 문서 수")
    args = ap.parse_args()

    roots = args.root or DEFAULT_ROOTS
    files = discover(roots, ROOT, args.limit)
    results = [audit_one(p, ROOT) for p in files]

    by = Counter(r["verdict"] for r in results)
    warn_modes: Counter = Counter()
    for r in results:
        for w in r["warnings"]:
            warn_modes[w.split(":")[0]] += 1

    covs = [r["textCoverage"] for r in results
            if r.get("textCoverage") is not None]
    ranked = sorted(
        (r for r in results if r["verdict"] != "OK"),
        key=lambda r: (r["verdict"] != "ERROR",
                       r.get("textCoverage") if r.get("textCoverage")
                       is not None else 1.0))

    summary = {
        "schemaVersion": "web_office_coord_corpus_audit_v1",
        "verdict": PASS_VERDICT if not by.get("ERROR") else FAIL_VERDICT,
        "scanned": len(results),
        "ok": by.get("OK", 0),
        "warn": by.get("WARN", 0),
        "error": by.get("ERROR", 0),
        "textCoverage": {
            "docs": len(covs),
            "mean": round(sum(covs) / len(covs), 3) if covs else None,
            "min": round(min(covs), 3) if covs else None,
            "under85": sum(1 for c in covs if c < 0.85),
        },
        "cellIdMatch": _cellid_summary(results),
        "warningModes": dict(warn_modes.most_common()),
        "worst": [
            {"path": r["path"], "verdict": r["verdict"],
             "textCoverage": r.get("textCoverage"),
             "warnings": r["warnings"][:4],
             "error": r.get("error")}
            for r in ranked[: args.worst]
        ],
    }
    if args.json:
        Path(args.json).write_text(
            json.dumps({"summary": summary, "results": results},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if summary["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
