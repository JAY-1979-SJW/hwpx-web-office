"""법제처 HWP 코퍼스 → HWPX 선(先)변환 배치 — 지속 인스턴스, 재개 가능, 불량격리.

- data/drafts/form_library/law_hwp/*.hwp 를 지속배치(한컴 1회 기동)로 청크 처리.
- 지속 인스턴스라 파일당 ~0.2초(냉시동 300시간 → 지속 1~2시간).
- 청크별 32bit PowerShell 서브프로세스 타임아웃 → 불량 파일이 라인 전체를 막지 않게 격리.
  타임아웃 시: 그 청크에서 이미 산출된 것은 유지, 순서상 첫 미산출 파일 = 행(hang) 용의자
  → 영구 SKIP 표시, 나머지는 다음 회차 재시도.
- 재개: 출력 HWPX(zip 유효) 존재 시 스킵 + 진행로그(law_hwpx_convert_progress.jsonl).
- 산출: data/drafts/form_library/law_hwpx/{stem}.hwpx

한컴 COM은 자동화 서버가 단일이라 병렬 다중 인스턴스는 불안정 → 단일 인스턴스 지속 처리.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "hwpx"))
from hancom_hwp_to_hwpx_batch import current_hwp_pids, stop_pids  # noqa: E402

LIB = PROJECT_ROOT / "data" / "drafts" / "form_library"
IN_DIR = LIB / "law_hwp"
OUT_DIR = LIB / "law_hwpx"
PROGRESS = LIB / "law_hwpx_convert_progress.jsonl"
DIAG_DIR = PROJECT_ROOT / "tmp" / "law_convert_diag"
WORK_DIR = PROJECT_ROOT / "tmp" / "law_convert_work"
BATCH_PS1 = PROJECT_ROOT / "scripts" / "hwp-worker" / "Convert-HwpToHwpx-PersistentBatch.ps1"
PS32 = Path("C:/Windows/SysWOW64/WindowsPowerShell/v1.0/powershell.exe")

MAX_ATTEMPTS = 2   # 이 횟수 이후 미산출이면 SKIP_BAD


def _log(m: str) -> None:
    print(m, flush=True)


def _is_valid_hwpx(p: Path) -> bool:
    if not p.is_file() or p.stat().st_size < 200:
        return False
    try:
        with p.open("rb") as f:
            return f.read(2) == b"PK"
    except OSError:
        return False


def _load_progress() -> tuple[set[str], dict[str, int]]:
    """(영구 SKIP_BAD stem 집합, stem→시도횟수)."""
    bad: set[str] = set()
    attempts: dict[str, int] = {}
    if PROGRESS.exists():
        for line in PROGRESS.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            stem = r.get("stem")
            if not stem:
                continue
            if r.get("status") == "SKIP_BAD":
                bad.add(stem)
            if "attempt" in r:
                attempts[stem] = max(attempts.get(stem, 0), int(r["attempt"]))
    return bad, attempts


def _append(records: list[dict]) -> None:
    with PROGRESS.open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _run_chunk(chunk: list[Path], timeout_sec: int, strategy: str) -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    DIAG_DIR.mkdir(parents=True, exist_ok=True)
    items = [{"itemId": p.stem, "inputPath": str(p),
              "outputPath": str(OUT_DIR / f"{p.stem}.hwpx")} for p in chunk]
    mani = WORK_DIR / "chunk_manifest.json"
    res = WORK_DIR / "chunk_result.jsonl"
    mani.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    res.unlink(missing_ok=True)

    pre_pids = current_hwp_pids()
    try:
        subprocess.run(
            [str(PS32), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BATCH_PS1),
             "-ManifestPath", str(mani), "-ResultPath", str(res),
             "-DiagDir", str(DIAG_DIR), "-SaveStrategy", strategy],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        # 행(hang) — 이 청크에서 새로 뜬 한컴만 종료
        killed = stop_pids(current_hwp_pids() - pre_pids)
        _log(f"    ⏱ 청크 타임아웃 — 한컴 {len(killed)}개 종료")
    # 종료 후 잔여 한컴 정리(누수 방지)
    stop_pids(current_hwp_pids() - pre_pids)


def convert(chunk_size: int, limit: int, strategy: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bad, attempts = _load_progress()

    all_hwp = sorted(IN_DIR.glob("*.hwp"))
    todo = [p for p in all_hwp
            if p.stem not in bad
            and not _is_valid_hwpx(OUT_DIR / f"{p.stem}.hwpx")]
    already = len(all_hwp) - len(todo) - len([p for p in all_hwp if p.stem in bad])
    if limit:
        todo = todo[:limit]

    _log(f"[start] HWP 총 {len(all_hwp)} · 기변환 {already} · 불량스킵 {len(bad)} · "
         f"이번대상 {len(todo)} (청크 {chunk_size}, 전략 {strategy})")
    if not todo:
        _log("[done] 변환할 파일 없음 — 전량 완료 상태")
        return

    t0 = time.time()
    converted = skipped_bad = 0
    per_file = 3.0   # 파일당 타임아웃 예산(초) — 지속모드 실측 0.2s의 넉넉한 여유
    for ci in range(0, len(todo), chunk_size):
        chunk = todo[ci:ci + chunk_size]
        timeout_sec = int(40 + len(chunk) * per_file)
        _run_chunk(chunk, timeout_sec, strategy)

        # 산출 확인 → 성공/실패 판정, 순서상 첫 미산출 = 행 용의자
        records = []
        first_missing_marked = False
        for p in chunk:
            out = OUT_DIR / f"{p.stem}.hwpx"
            if _is_valid_hwpx(out):
                converted += 1
                records.append({"stem": p.stem, "status": "OK", "size": out.stat().st_size})
            else:
                att = attempts.get(p.stem, 0) + 1
                attempts[p.stem] = att
                if not first_missing_marked:
                    # 이 청크에서 한컴이 멈춘 지점 → 즉시 영구 격리
                    first_missing_marked = True
                    bad.add(p.stem); skipped_bad += 1
                    records.append({"stem": p.stem, "status": "SKIP_BAD",
                                    "attempt": att, "reason": "chunk_hang_suspect"})
                elif att >= MAX_ATTEMPTS:
                    bad.add(p.stem); skipped_bad += 1
                    records.append({"stem": p.stem, "status": "SKIP_BAD",
                                    "attempt": att, "reason": "max_attempts"})
                else:
                    records.append({"stem": p.stem, "status": "RETRY", "attempt": att})
        _append(records)

        done = ci + len(chunk)
        el = time.time() - t0
        rate = converted / el if el else 0
        rem = (len(todo) - done) / rate / 60 if rate else 0
        _log(f"  … {done}/{len(todo)} · 변환 {converted} · 불량 {skipped_bad} "
             f"[{el:.0f}s, ~{rate:.1f}/s, 남은 ~{rem:.0f}분]")

    el = time.time() - t0
    _log(f"[done] 변환 {converted} · 불량스킵 {skipped_bad} · {el/60:.1f}분")
    _log(f"[out] {OUT_DIR}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chunk-size", type=int, default=150)
    ap.add_argument("--limit", type=int, default=0, help="이번 실행 최대 변환수(0=전량)")
    ap.add_argument("--strategy", choices=["direct", "haction"], default="direct")
    ap.add_argument("--in-dir", default="", help="HWP 입력 폴더(기본 law_hwp)")
    ap.add_argument("--out-dir", default="", help="HWPX 출력 폴더(기본 law_hwpx)")
    ap.add_argument("--progress", default="", help="진행로그 경로(기본 law_hwpx_convert_progress.jsonl)")
    args = ap.parse_args()
    if not PS32.exists():
        raise SystemExit(f"32bit PowerShell 없음: {PS32}")
    global IN_DIR, OUT_DIR, PROGRESS
    if args.in_dir:
        IN_DIR = Path(args.in_dir) if Path(args.in_dir).is_absolute() else PROJECT_ROOT / args.in_dir
    if args.out_dir:
        OUT_DIR = Path(args.out_dir) if Path(args.out_dir).is_absolute() else PROJECT_ROOT / args.out_dir
    if args.progress:
        PROGRESS = Path(args.progress) if Path(args.progress).is_absolute() else PROJECT_ROOT / args.progress
    elif args.out_dir:
        PROGRESS = OUT_DIR.parent / (OUT_DIR.name + "_convert_progress.jsonl")
    convert(args.chunk_size, args.limit, args.strategy)


if __name__ == "__main__":
    main()
