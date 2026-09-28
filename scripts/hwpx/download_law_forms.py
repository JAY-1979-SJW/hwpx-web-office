"""법제처 별표서식 HWP 전량 다운로드 (Phase 2) — 중복 없이, 재개 가능.

입력: law_forms_index.jsonl (harvest_law_forms.py 산출, 28,582종)
동작:
  - 각 서식의 hwpLink(/LSW/flDownload.do?flSeq=)에서 HWP 다운로드.
  - 3중 중복제거:
      ① 별표일련번호(seq) — 인덱스에서 이미 고유
      ② 콘텐츠 SHA256 — 다른 seq라도 내용 같으면 스킵
      ③ 기존 로컬 form_library manifest 해시 — 이미 가진 것 스킵
  - 재개 가능: 진행 로그(law_download_progress.jsonl) 기록, 재실행 시 이어감.
  - API 예의: 호출 간 지연(--delay), 실패 재시도.

인증 불필요(flDownload.do는 공개). Referer 헤더만 필요.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIB = PROJECT_ROOT / "data" / "drafts" / "form_library"
INDEX = LIB / "law_forms_index.jsonl"
HWP_DIR = LIB / "law_hwp"
PROGRESS = LIB / "law_download_progress.jsonl"
MANIFEST = LIB / "manifest.json"
LAW = "https://www.law.go.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.law.go.kr/",
    "Accept": "*/*",
}
HWP_OLE = bytes.fromhex("D0CF11E0A1B11AE1")  # HWP(5.x) OLE 시그니처


def _log(m):
    print(m, flush=True)


def _safe(name: str, n: int = 60) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", name or "").strip("_")
    return s[:n] or "form"


def load_existing_hashes() -> set[str]:
    """기존 로컬 form_library 해시(중복 스킵용)."""
    hashes: set[str] = set()
    if MANIFEST.exists():
        try:
            m = json.loads(MANIFEST.read_text(encoding="utf-8"))
            for r in m.get("records", []):
                if r.get("sha256"):
                    hashes.add(r["sha256"])
        except (json.JSONDecodeError, KeyError, TypeError, OSError):
            pass
    return hashes


def load_progress() -> tuple[set[str], set[str]]:
    """이미 처리한 seq / 이미 받은 콘텐츠 해시."""
    done_seq: set[str] = set()
    seen_hash: set[str] = set()
    if PROGRESS.exists():
        for line in PROGRESS.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("seq"):
                done_seq.add(str(r["seq"]))
            if r.get("sha256"):
                seen_hash.add(r["sha256"])
    return done_seq, seen_hash


def download(flseq_link: str, retries: int = 3) -> bytes | None:
    url = LAW + flseq_link if flseq_link.startswith("/") else flseq_link
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except OSError:
            time.sleep(1.5 * (attempt + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.35, help="호출 간 지연(초)")
    ap.add_argument("--limit", type=int, default=0, help="최대 다운로드 수(0=전량)")
    ap.add_argument("--ministry", default="", help="특정 부처만(부분일치)")
    args = ap.parse_args()

    HWP_DIR.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in INDEX.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.ministry:
        rows = [r for r in rows if args.ministry in (r.get("ministry") or "")]

    local_hashes = load_existing_hashes()
    done_seq, seen_hash = load_progress()
    seen_hash |= local_hashes
    _log(
        f"[start] 대상 {len(rows)}종 · 기존 로컬해시 {len(local_hashes)} · 이미처리 seq {len(done_seq)}"
    )

    t0 = time.time()
    saved = skipped_dup = skipped_done = failed = non_hwp = 0
    with PROGRESS.open("a", encoding="utf-8") as plog:
        for i, r in enumerate(rows, 1):
            seq = str(r.get("seq") or "")
            if not seq or seq in done_seq:
                skipped_done += 1
                continue
            link = r.get("hwpLink") or ""
            if not link:
                failed += 1
                plog.write(json.dumps({"seq": seq, "status": "NO_LINK"}, ensure_ascii=False) + "\n")
                continue
            data = download(link)
            if data is None:
                failed += 1
                plog.write(json.dumps({"seq": seq, "status": "FAILED"}, ensure_ascii=False) + "\n")
                time.sleep(args.delay)
                continue
            digest = hashlib.sha256(data).hexdigest()
            is_hwp = data[:8] == HWP_OLE
            is_zip = data[:2] == b"PK"  # HWPX(zip)
            if digest in seen_hash:
                skipped_dup += 1
                done_seq.add(seq)
                plog.write(
                    json.dumps({"seq": seq, "sha256": digest, "status": "DUP"}, ensure_ascii=False)
                    + "\n"
                )
                time.sleep(args.delay)
                continue
            ext = "hwpx" if is_zip else "hwp"
            fname = f"{seq}_{_safe(r.get('name', ''))}.{ext}"
            (HWP_DIR / fname).write_bytes(data)
            seen_hash.add(digest)
            done_seq.add(seq)
            saved += 1
            if not is_hwp and not is_zip:
                non_hwp += 1
            plog.write(
                json.dumps(
                    {
                        "seq": seq,
                        "sha256": digest,
                        "status": "SAVED",
                        "file": fname,
                        "ext": ext,
                        "name": r.get("name"),
                        "ministry": r.get("ministry"),
                        "lawName": r.get("lawName"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            if saved % 100 == 0:
                plog.flush()
                el = time.time() - t0
                rate = saved / el if el else 0
                rem = (len(rows) - i) / rate / 60 if rate else 0
                _log(
                    f"  … {i}/{len(rows)} · 저장 {saved} 중복 {skipped_dup} 실패 {failed} "
                    f"[{el:.0f}s, ~{rate:.1f}/s, 남은 ~{rem:.0f}분]"
                )
            if args.limit and saved >= args.limit:
                _log(f"[limit] {args.limit} 도달, 중단")
                break
            time.sleep(args.delay)

    el = time.time() - t0
    _log(
        f"[done] 저장 {saved} · 중복스킵 {skipped_dup} · 완료스킵 {skipped_done} · "
        f"실패 {failed} · 비HWP시그니처 {non_hwp} · {el / 60:.1f}분"
    )
    _log(f"[dir] {HWP_DIR}")


if __name__ == "__main__":
    main()
