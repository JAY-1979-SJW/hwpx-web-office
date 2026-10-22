"""법정 별지 대량 시험 — 인식 → 가짜값 입력 → 다시 읽기 (요청 121).

기존 도구(parse_hwpx_v2 · recognize_form · plan_builder · hwpx_edit_tool · run_pipeline)를 그대로 돌려
'인식한 칸마다 칸 주소 문자열을 넣고 → 저장 → 다시 읽어 같은지' 를 서식 300종에 대해 잰다.
규칙을 고치기 전(기준선)과 고친 뒤를 같은 표본·같은 방식으로 재서 비교한다.

사용:
  python mass_fill_readback.py run   --out <폴더> [--n 300] [--seed 121]   (1프로세스·서식마다 이어쓰기·재시작 시 건너뜀)
  python mass_fill_readback.py compare --before <results.json> --after <results.json>

원본은 건드리지 않는다(복사본만 편집). 9222·유료 AI 를 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
import tempfile
import traceback
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2]
for _p in (str(_SCRIPTS.parent), str(_SCRIPTS), str(_SCRIPTS / "hwpx")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_LIBRARY = Path(r"C:/work/02. hwpx-web-office/data/drafts/form_library")
SEED = 121
PER_FORM_TIMEOUT = 120

_STATUTORY = re.compile(r"\[별지_제")
_EXCLUDE = re.compile(r"__filled|__A\.hwpx$|모범|삭제")
# 서명·(인) 칸 판정 — 값을 넣으면 안 되는 칸
_SIGN_RE = re.compile(r"\(인\)|\(서명|서명\s*또는\s*인|날인|직인|인감|\(인$|^인$")
_PIPELINE_VALUES = {"projectName": "시험공사", "contractorName": "시험건설", "reportDate": "2026-10-23"}


def select_forms(library: Path, n: int, seed: int) -> list[Path]:
    names = sorted(p.name for p in library.iterdir() if p.suffix == ".hwpx")
    pool = [x for x in names if _STATUTORY.search(x) and not _EXCLUDE.search(x)]
    rng = random.Random(seed)
    pick = rng.sample(pool, min(n, len(pool)))
    return [library / x for x in sorted(pick)]


def _is_sign_target(slot, cell_by_pos: dict, row_cells: dict) -> bool:
    if _SIGN_RE.search(getattr(slot, "labelText", "") or ""):
        return True
    for c in row_cells.get((slot.tableId, slot.visualRow), []):
        if _SIGN_RE.search(c.normalizedText or "") and abs(c.visualCol - slot.visualCol) <= 1:
            return True
    return False


def run_one(path_str: str, work_dir_str: str) -> dict:
    """서식 1개 — 순수 함수(프로세스 풀에서 실행)."""
    from hwpx_edit_tool import apply_edit_plan

    from hwpx.parser import parse_hwpx_v2
    from hwpx.parser.slot_modes import choice_options
    from hwpx.pipeline.form_recognizer import recognize_form
    from hwpx.pipeline.plan_builder import _build_slot_item
    from hwpx.pipeline.recognition_pipeline import run_pipeline

    src = Path(path_str)
    work = Path(work_dir_str) / src.stem[:40]
    work.mkdir(parents=True, exist_ok=True)
    copy = work / "in.hwpx"
    shutil.copy2(src, copy)  # 원본 보호 — 이후 모든 작업은 복사본
    res: dict = {"name": src.name, "failures": []}

    try:
        before = parse_hwpx_v2(copy)
    except Exception as exc:  # noqa: BLE001 -- 서식별 실패를 지표로 기록하고 다음 서식으로 진행
        res.update(parse_ok=False, slots=0, failures=[f"PARSE_ERROR:{type(exc).__name__}"])
        return res
    if getattr(before, "errors", []):
        res.update(parse_ok=False, slots=0, failures=["PARSE_ERROR:parser_errors"])
        return res
    res["parse_ok"] = True

    fr = recognize_form(before)
    slots = list(fr.enhancedSlots)
    res["slots"] = len(slots)
    res["tables"] = len(before.tables)
    if not slots:
        res["failures"].append("ZERO_SLOTS")

    cell_by_pos = {(t.tableId, c.visualRow, c.visualCol): c for t in before.tables for c in t.cells}
    row_cells: dict = {}
    for (tid, r, _c), c in cell_by_pos.items():
        row_cells.setdefault((tid, r), []).append(c)

    # ── 가짜값 입력(기존 plan_builder 가 만드는 항목 그대로) ──────────────
    items, targets, sign_targets = [], [], 0
    for i, s in enumerate(slots):
        mode = getattr(s, "writeMode", "set")
        options = choice_options(getattr(s, "cellText", "")) if mode == "choice" else []
        val = options[0] if options else f"@{i:03d}"
        item, dest = _build_slot_item(s, "mass", val, 0.95, {"mass": 1})
        if item is None or dest != "visual":
            res["failures"].append("PLAN_NO_ITEM")
            continue
        items.append(item)
        # (위치, 칸에 들어가야 할 최종 글자, 원래 글자를 덮어써도 되는 방식인지)
        targets.append(((s.tableId, s.visualRow, s.visualCol), item["value"], mode == "set"))
        if _is_sign_target(s, cell_by_pos, row_cells):
            sign_targets += 1
    res["planned"] = len(items)
    res["sign_writes"] = sign_targets

    matched = mismatch = stray = overwrote = 0
    if items:
        out = work / "out.hwpx"
        try:
            rep = apply_edit_plan(copy, out, {"set_visual_cells": items})
            if rep.get("status") == "FAIL" or rep.get("errors"):
                res["failures"].append("EDIT_FAIL")
            after = parse_hwpx_v2(out)
            after_pos = {(t.tableId, c.visualRow, c.visualCol): c for t in after.tables for c in t.cells}
            for pos, val, replaces in targets:
                written = after_pos.get(pos)
                if written is None:
                    mismatch += 1
                    res["failures"].append("CELL_NOT_FOUND")
                elif (written.normalizedText or "") == val:
                    matched += 1
                else:
                    mismatch += 1
                    res["failures"].append("TEXT_MISMATCH")
                b = cell_by_pos.get(pos)
                if replaces and b is not None and (b.normalizedText or ""):
                    overwrote += 1
                    res["failures"].append("LABEL_OVERWRITE")
            tpos = {t[0] for t in targets}
            for pos, c in after_pos.items():
                b = cell_by_pos.get(pos)
                if pos not in tpos and b is not None and (b.normalizedText or "") != (c.normalizedText or ""):
                    stray += 1
            if stray:
                res["failures"].append("STRAY_WRITE")
        except Exception as exc:  # noqa: BLE001 -- 서식별 실패를 지표로 기록하고 다음 서식으로 진행
            res["failures"].append(f"EDIT_ERROR:{type(exc).__name__}")
            mismatch = len(items)
    res.update(matched=matched, mismatch=mismatch, stray=stray, overwrote=overwrote)
    if sign_targets:
        res["failures"].append("SIGN_WRITE")

    # ── 기존 end-to-end 경로(run_pipeline)의 판정 ────────────────────────
    try:
        pr = run_pipeline(copy, work / "pipe.hwpx", dict(_PIPELINE_VALUES))
        res["pipeline"] = pr.finalDecision
        res["hancom"] = getattr(pr.hancomVerify, "verdict", "")
        res["compare"] = getattr(pr.verification, "decision", "")
        if not slots and pr.finalDecision == "PASS":
            res["failures"].append("ZERO_SLOT_PASS")
        if res["hancom"] == "PASS" and pr.finalDecision not in ("PASS",):
            res["hancom_pass_not_final_pass"] = True
    except Exception as exc:  # noqa: BLE001 -- 서식별 실패를 지표로 기록하고 다음 서식으로 진행
        res["pipeline"] = f"ERROR:{type(exc).__name__}"
    shutil.rmtree(work, ignore_errors=True)
    return res


def _safe_run(path_str: str, work_dir_str: str) -> dict:
    try:
        return run_one(path_str, work_dir_str)
    except Exception:  # noqa: BLE001 -- 서식별 실패를 지표로 기록하고 다음 서식으로 진행
        return {"name": Path(path_str).name, "parse_ok": False, "slots": 0,
                "failures": ["HARNESS_ERROR"], "trace": traceback.format_exc()[-400:]}


def summarize(results: list[dict]) -> dict:
    n = len(results)
    ok = [r for r in results if r.get("parse_ok")]
    planned = sum(r.get("planned", 0) for r in results)
    matched = sum(r.get("matched", 0) for r in results)
    ftypes: Counter = Counter()
    examples: dict[str, str] = {}
    for r in results:
        for f in set(r.get("failures", [])):
            ftypes[f] += 1
            examples.setdefault(f, r["name"])
    return {
        "forms": n,
        "analysis_success": len(ok),
        "zero_value_forms": sum(1 for r in ok if r.get("slots", 0) == 0),
        "slots_total": sum(r.get("slots", 0) for r in results),
        "planned": planned,
        "matched": matched,
        "readback_match_rate": round(matched / planned, 4) if planned else 0.0,
        "forms_with_any_mismatch": sum(1 for r in ok if r.get("mismatch", 0) > 0),
        "sign_writes": sum(r.get("sign_writes", 0) for r in results),
        "label_overwrites": sum(r.get("overwrote", 0) for r in results),
        "stray_write_forms": sum(1 for r in ok if r.get("stray", 0) > 0),
        "zero_slot_pass": sum(1 for r in results if "ZERO_SLOT_PASS" in r.get("failures", [])),
        "hancom_pass_not_final_pass": sum(1 for r in results if r.get("hancom_pass_not_final_pass")),
        "top_failures": [{"type": t, "forms": c, "example": examples[t]} for t, c in ftypes.most_common(10)],
    }


def _child(path_str: str, work_str: str, q) -> None:
    q.put(_safe_run(path_str, work_str))


def run_isolated(path: Path, work: Path, timeout: int) -> dict:
    """서식 1개를 별도 프로세스로 돌린다 — 시간 초과면 죽이고, 메모리는 서식마다 반환된다."""
    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    proc = ctx.Process(target=_child, args=(str(path), str(work), q))
    proc.start()
    try:
        return q.get(timeout=timeout)
    except Exception:  # noqa: BLE001 -- 서식별 실패를 지표로 기록하고 다음 서식으로 진행
        return {"name": path.name, "parse_ok": False, "slots": 0, "failures": ["TIMEOUT"]}
    finally:
        if proc.is_alive():
            proc.kill()
        proc.join(5)


def cmd_run(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    forms = select_forms(Path(args.library), args.n, args.seed)
    (out / "sample.txt").write_text(chr(10).join(p.name for p in forms), encoding="utf-8")
    log = out / "results.jsonl"  # 서식마다 이어 쓴다 — 중간에 멈춰도 이어서 재개
    done: dict[str, dict] = {}
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["name"]] = r
    work = Path(tempfile.mkdtemp(prefix="massfill_", dir=str(out)))
    with log.open("a", encoding="utf-8") as fh:
        for p in forms:
            if p.name in done:
                continue
            r = run_isolated(p, work, PER_FORM_TIMEOUT)
            done[r["name"]] = r
            fh.write(json.dumps(r, ensure_ascii=False) + chr(10))
            fh.flush()
    shutil.rmtree(work, ignore_errors=True)
    results = [done[p.name] for p in forms if p.name in done]
    summary = summarize(results)
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


def cmd_compare(args) -> int:
    a = json.loads(Path(args.before).read_text(encoding="utf-8"))
    b = json.loads(Path(args.after).read_text(encoding="utf-8"))
    sa, sb = summarize(a), summarize(b)
    keys = ["analysis_success", "zero_value_forms", "slots_total", "readback_match_rate",
            "forms_with_any_mismatch", "sign_writes", "label_overwrites", "stray_write_forms",
            "zero_slot_pass", "hancom_pass_not_final_pass"]
    print("| 지표 | 전 | 후 |\n|---|---|---|")
    for k in keys:
        print(f"| {k} | {sa[k]} | {sb[k]} |")
    by_a = {r["name"]: r for r in a}
    worse = []
    for r in b:
        o = by_a.get(r["name"])
        if not o:
            continue
        if (r.get("slots", 0) < o.get("slots", 0) or r.get("mismatch", 0) > o.get("mismatch", 0)
                or r.get("sign_writes", 0) > o.get("sign_writes", 0) or (o.get("parse_ok") and not r.get("parse_ok"))):
            worse.append(r["name"])
    print(f"\n나빠진 서식: {len(worse)}")
    for x in worse[:20]:
        print(" -", x)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--library", default=str(DEFAULT_LIBRARY))
    r.add_argument("--n", type=int, default=300)
    r.add_argument("--seed", type=int, default=SEED)
    c = sub.add_parser("compare")
    c.add_argument("--before", required=True)
    c.add_argument("--after", required=True)
    args = ap.parse_args(argv)
    return cmd_run(args) if args.cmd == "run" else cmd_compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
