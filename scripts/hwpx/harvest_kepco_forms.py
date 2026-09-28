"""한전(KEPCO) 한전ON 서식자료실 전량 수집기 — ID 열거 방식.

한전ON(online.kepco.co.kr)의 서식 다운로드 엔드포인트:
    GET /form/file/down/{id}
      - 유효 ID → 200 + Content-Disposition(파일명, URL인코딩) + 파일 바이트
      - 무효 ID → 500(text/html)

ID를 1..MAX 로 열거해 전량(서식 HWP/HWPX + 약관·규정 PDF)을 확보한다.
- 파일명은 Content-Disposition 에서 디코드.
- 콘텐츠 SHA256 중복제거(동일 바이트만 스킵; hwp+pdf 쌍은 다른 콘텐츠라 각각 보존).
- 재개 가능: 인덱스(kepco_forms_index.jsonl)에 기록된 ID 스킵.
- 예의: 호출 간 지연(--delay), 무효 연속 시에도 갭 고려해 MAX 까지 스캔.

법제처와 달리 공식 OpenAPI가 없어 공개 다운로드 엔드포인트를 열거하는 방식.
공개적으로 내려받도록 제공되는 고객 서식·약관 문서만 대상으로 한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIB = PROJECT_ROOT / "data" / "drafts" / "form_library"
OUT_DIR = LIB / "kepco_forms"
INDEX = LIB / "kepco_forms_index.jsonl"
BASE = "https://online.kepco.co.kr/form/file/down/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://online.kepco.co.kr/",
    "Accept": "*/*",
}
HWP_OLE = bytes.fromhex("D0CF11E0A1B11AE1")


def _log(m):
    print(m, flush=True)


def _safe(name: str, n: int = 70) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", name or "").strip("_")
    return s[:n] or "form"


def _filename_from_cd(cd: str) -> str:
    if not cd:
        return ""
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", cd, re.I)
    if not m:
        return ""
    raw = m.group(1)
    try:
        name = urllib.parse.unquote(raw)
    except (ValueError, UnicodeDecodeError):
        name = raw
    # http.client 는 헤더를 latin-1 로 디코드한다. 서버가 UTF-8 파일명을
    # 퍼센트인코딩 없이 그대로 보내면 모지바케가 되므로 되돌린다.
    if not re.search(r"[가-힣]", name):
        try:
            fixed = name.encode("latin-1").decode("utf-8")
            if re.search(r"[가-힣]", fixed):
                name = fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name


def load_done() -> set[int]:
    done: set[int] = set()
    if INDEX.exists():
        for line in INDEX.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if "id" in r:
                    done.add(int(r["id"]))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return done


def fetch(fid: int, retries: int = 3):
    url = BASE + str(fid)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read()
                cd = r.headers.get("Content-Disposition", "")
                ct = r.headers.get("Content-Type", "")
                return data, cd, ct
        except urllib.error.HTTPError as e:
            if e.code in (404, 500):
                return None, "", ""  # 무효 ID
            time.sleep(1.2 * (attempt + 1))
        except OSError:
            time.sleep(1.2 * (attempt + 1))
    return None, "", ""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-id", type=int, default=1000)
    ap.add_argument("--delay", type=float, default=0.3)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    done = load_done()
    seen_hash: set[str] = set()
    # 기존 인덱스의 해시도 로드(중복제거)
    if INDEX.exists():
        for line in INDEX.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                r = json.loads(line)
                if r.get("sha256"):
                    seen_hash.add(r["sha256"])
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    _log(f"[start] ID 1..{args.max_id} 스캔 · 이미처리 {len(done)}")
    t0 = time.time()
    saved = dup = miss = hwp = hwpx = pdf = other = 0
    with INDEX.open("a", encoding="utf-8") as idx:
        for fid in range(1, args.max_id + 1):
            if fid in done:
                continue
            data, cd, ct = fetch(fid)
            if data is None or len(data) < 100:
                miss += 1
                time.sleep(args.delay)
                continue
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen_hash:
                dup += 1
                idx.write(
                    json.dumps({"id": fid, "sha256": digest, "status": "DUP"}, ensure_ascii=False)
                    + "\n"
                )
                time.sleep(args.delay)
                continue
            name = _filename_from_cd(cd) or f"kepco_{fid}"
            ext = Path(name).suffix.lower().lstrip(".") or (
                "hwp" if data[:8] == HWP_OLE else "hwpx" if data[:2] == b"PK" else "bin"
            )
            if ext == "hwp":
                hwp += 1
            elif ext == "hwpx":
                hwpx += 1
            elif ext == "pdf":
                pdf += 1
            else:
                other += 1
            stem = _safe(Path(name).stem)
            fname = f"{fid}_{stem}.{ext}"
            (OUT_DIR / fname).write_bytes(data)
            seen_hash.add(digest)
            saved += 1
            idx.write(
                json.dumps(
                    {
                        "id": fid,
                        "name": name,
                        "file": fname,
                        "ext": ext,
                        "sizeBytes": len(data),
                        "sha256": digest,
                        "status": "SAVED",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            idx.flush()
            if saved % 20 == 0:
                _log(
                    f"  … id{fid} · 저장 {saved} (hwp {hwp} hwpx {hwpx} pdf {pdf}) 중복 {dup} 무효 {miss}"
                )
            time.sleep(args.delay)

    el = time.time() - t0
    _log(
        f"[done] 저장 {saved} (hwp {hwp} · hwpx {hwpx} · pdf {pdf} · 기타 {other}) · "
        f"중복 {dup} · 무효 {miss} · {el / 60:.1f}분"
    )
    _log(f"[out] {OUT_DIR}")
    _log(f"[index] {INDEX}")


if __name__ == "__main__":
    main()
