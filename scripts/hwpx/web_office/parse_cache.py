"""HWPX 파싱 결과 캐시 — 같은 문서를 두 번 깎지 않는다 (read-only).

왜 있는가
---------
파생 산출물(입력 스키마·행정 요건·라벨 색인)은 전부 같은 파싱 결과에서
나온다. 그런데 라벨 규칙 하나만 바꿔도 HWPX 35,791건을 처음부터 다시
연다. 2026-07-23 하루에만 전량 파싱을 두 번 했고, 그때마다 작업 PC 를
1~2시간 점유했다.

이 모듈은 `load_hwpx_for_editor` 의 결과를 그대로 저장해두고, 다음부터는
파싱 대신 읽어온다. 실측(표본 12건, 크기 스펙트럼 표집):

    JSON 무압축   원본의 45.6배   ← 그냥 저장하면 안 된다
    gzip 압축     원본의  1.8배   → 전량 약 3.76 GB
    캐시 쓰기     0.048 초/건
    캐시 읽기     0.041 초/건     ← 파싱을 이것으로 대체한다

즉 파서를 고칠 때만 1회 재생성하고, 라벨·역할·subject 규칙 변경은 캐시
읽기만으로 끝난다.

가장 큰 위험은 "파서가 바뀌었는데 캐시가 옛 결과를 계속 돌려주는 것"이다.
두 겹으로 막는다:

  ① 파서 버전 태그 — 파싱 결과에 영향을 주는 소스 파일들의 내용 해시로
     버전을 만든다. 파서가 바뀌면 버전이 바뀌고 캐시가 통째로 빗나가
     자동으로 재생성된다. 저장 경로에 버전이 들어간다.
  ② `verify` — 표본을 실제로 재파싱해 캐시와 대조한다. ①의 파일 목록에
     빠진 모듈이 있으면 여기서 잡힌다(목록 누락이 유일한 구멍이다).

**PARSER_SOURCES 에 파서 모듈을 추가하는 것을 잊으면 캐시가 조용히 낡는다.**
파싱 경로에 새 모듈을 넣었다면 반드시 여기에도 넣을 것.

캐시는 `data/` 아래라 git 추적 대상이 아니다. 원본은 읽기만 한다.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CACHE_ROOT = PROJECT_ROOT / "data" / "drafts" / "form_library" / "parse_cache"

# 파싱 결과에 영향을 주는 소스. 하나라도 바뀌면 캐시 버전이 바뀐다.
# ★ 파싱 경로에 모듈을 추가하면 여기에도 반드시 추가할 것 ★
PARSER_SOURCES = [
    "scripts/hwpx/web_office/__init__.py",
    "scripts/hwpx/web_office/editor_file_bridge.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    "scripts/hwpx/web_office/render_payload.py",
    "scripts/hwpx/web_office/document_model.py",
    "scripts/hwpx/web_office/coordinate_layout.py",
    "scripts/hwpx/parser/parser_engine.py",
    "scripts/hwpx/parser/table_parser.py",
    "scripts/hwpx/parser/style_parser.py",
    "scripts/hwpx/parser/parser_contract.py",
    "scripts/hwpx/parser/input_slot_detector.py",
    "scripts/hwpx/hwpx_package.py",
    "scripts/hwpx/hwpx_paragraph_ops.py",
    "scripts/hwpx/hwpx_table_ops.py",
    "scripts/hwpx/hwpx_header_field_detector.py",
]

# 호출마다 새로 발급되는 필드 — 파싱 결과의 일부가 아니다.
# 캐시에서 꺼낼 때 새로 채우고, 대조할 때는 빼고 본다.
VOLATILE_FIELDS = [("documentModel", "requestId")]

_parser_version: str | None = None


def _refresh_volatile(payload: dict[str, Any]) -> dict[str, Any]:
    """캐시본에 요청 단위 식별자를 새로 발급한다.

    안 하면 캐시를 읽은 모든 호출이 같은 requestId 를 달고 나가 추적이
    엉킨다(원래는 호출마다 유일해야 하는 값이다).
    """
    dm = payload.get("documentModel")
    if isinstance(dm, dict) and "requestId" in dm:
        dm["requestId"] = str(uuid.uuid4())
    return payload


def _without_volatile(payload: dict[str, Any]) -> dict[str, Any]:
    """대조용 사본 — 호출마다 달라지는 필드를 뺀다."""
    out = dict(payload)
    for parent, key in VOLATILE_FIELDS:
        node = out.get(parent)
        if isinstance(node, dict) and key in node:
            node = dict(node)
            node.pop(key, None)
            out[parent] = node
    return out


def parser_version(refresh: bool = False) -> str:
    """파싱 결과를 좌우하는 소스들의 내용 해시 (12자).

    파일이 없으면 그 사실 자체를 해시에 넣는다 — 이름이 바뀌면 버전이
    달라져 캐시가 무효화되므로 안전한 방향으로 실패한다.
    """
    global _parser_version
    if _parser_version is not None and not refresh:
        return _parser_version
    h = hashlib.sha256()
    for rel in PARSER_SOURCES:
        p = PROJECT_ROOT / rel
        h.update(rel.encode("utf-8"))
        if p.is_file():
            h.update(p.read_bytes())
        else:
            h.update(b"__MISSING__")
    _parser_version = h.hexdigest()[:12]
    return _parser_version


def source_digest(path: Path) -> str:
    """원본 HWPX 내용 해시 — 경로가 아니라 내용으로 캐시를 건다.

    같은 문서가 여러 경로에 있어도 한 번만 파싱하면 되고, 파일이 바뀌면
    자동으로 다른 항목이 된다.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def entry_path(digest: str, version: str | None = None) -> Path:
    ver = version or parser_version()
    # 앞 2자로 디렉터리를 갈라 한 폴더에 3만 개가 쌓이지 않게 한다
    return CACHE_ROOT / ver / digest[:2] / f"{digest}.json.gz"


def read_entry(digest: str, version: str | None = None) -> dict[str, Any] | None:
    p = entry_path(digest, version)
    if not p.is_file():
        return None
    try:
        with gzip.open(p, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except (OSError, EOFError, json.JSONDecodeError):
        # 손상된 항목은 없는 것으로 친다 — 다시 파싱해 덮어쓴다
        return None


def write_entry(digest: str, payload: dict[str, Any], version: str | None = None) -> int:
    p = entry_path(digest, version)
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    # 임시 파일에 쓰고 교체 — 도중에 끊겨도 반쪽 파일이 남지 않는다
    tmp = p.with_suffix(p.suffix + f".tmp{id(payload) & 0xFFFF:04x}")
    with gzip.open(tmp, "wb", compresslevel=6) as f:
        f.write(raw)
    tmp.replace(p)
    return p.stat().st_size


def load_hwpx_cached(
    source_rel: str,
    *,
    project_root: Path = PROJECT_ROOT,
    use_cache: bool = True,
    store: bool = True,
) -> tuple[dict[str, Any], bool]:
    """`load_hwpx_for_editor` 자리에 그대로 끼운다.

    Returns (결과, 캐시적중여부). 캐시에 없으면 파싱하고 저장한다.
    PASS 가 아닌 결과는 저장하지 않는다 — 실패를 굳혀두면 나중에 원인이
    고쳐져도 계속 실패로 보인다.
    """
    from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor

    src = project_root / source_rel
    digest: str | None = None
    if use_cache and src.is_file():
        digest = source_digest(src)
        hit = read_entry(digest)
        if hit is not None:
            return _refresh_volatile(hit), True

    res = load_hwpx_for_editor(
        {"operation": "HWPX_EDITOR_LOAD", "sourcePath": source_rel}, project_root=project_root
    )
    if store and digest is not None and res.get("verdict") == "PASS":
        try:
            write_entry(digest, res)
        except OSError:
            pass  # 캐시 저장 실패가 본 작업을 막지는 않는다
    return res, False


# ── 운영 ────────────────────────────────────────────────────────────


def stats() -> dict[str, Any]:
    ver = parser_version()
    root = CACHE_ROOT / ver
    n = size = 0
    if root.is_dir():
        for p in root.rglob("*.json.gz"):
            n += 1
            size += p.stat().st_size
    others = []
    if CACHE_ROOT.is_dir():
        others = [d.name for d in CACHE_ROOT.iterdir() if d.is_dir() and d.name != ver]
    return {
        "parserVersion": ver,
        "entries": n,
        "sizeMB": round(size / 1024 / 1024, 1),
        "staleVersions": others,
    }


def verify(sample: int = 25, seed: int = 0) -> dict[str, Any]:
    """캐시가 지금 파서의 결과와 정말 같은지 표본으로 확인한다.

    PARSER_SOURCES 목록에서 빠진 모듈이 있으면 버전이 안 바뀌어 캐시가
    조용히 낡는다 — 그 구멍을 잡는 유일한 장치다.
    """
    from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor

    ver = parser_version()
    root = CACHE_ROOT / ver
    if not root.is_dir():
        return {"checked": 0, "mismatch": 0, "note": "캐시 없음"}
    entries = list(root.rglob("*.json.gz"))
    random.Random(seed).shuffle(entries)
    checked = mismatch = missing_src = 0
    bad: list[str] = []
    for p in entries:
        if checked >= sample:
            break
        cached = read_entry(p.stem.replace(".json", ""))
        if cached is None:
            continue
        rel = cached.get("sourcePath")
        if not rel or not (PROJECT_ROOT / rel).is_file():
            missing_src += 1
            continue
        fresh = load_hwpx_for_editor(
            {"operation": "HWPX_EDITOR_LOAD", "sourcePath": rel}, project_root=PROJECT_ROOT
        )
        checked += 1
        a = json.dumps(_without_volatile(cached), sort_keys=True, ensure_ascii=False)
        b = json.dumps(_without_volatile(fresh), sort_keys=True, ensure_ascii=False)
        if a != b:
            mismatch += 1
            if len(bad) < 5:
                bad.append(rel)
    return {
        "parserVersion": ver,
        "checked": checked,
        "mismatch": mismatch,
        "sourceMissing": missing_src,
        "mismatchSamples": bad,
        "verdict": "PASS" if mismatch == 0 and checked else ("FAIL" if mismatch else "EMPTY"),
    }


def prune() -> dict[str, Any]:
    """현재 파서 버전이 아닌 캐시를 지운다."""
    import shutil

    ver = parser_version()
    removed = []
    freed = 0
    if CACHE_ROOT.is_dir():
        for d in CACHE_ROOT.iterdir():
            if d.is_dir() and d.name != ver:
                freed += sum(p.stat().st_size for p in d.rglob("*") if p.is_file())
                shutil.rmtree(d, ignore_errors=True)
                removed.append(d.name)
    return {"removed": removed, "freedMB": round(freed / 1024 / 1024, 1)}


def _select_targets(rows: list, shard: int, shards: int, cap: float) -> list[str]:
    targets: list[str] = []
    for fid, rel in rows:
        if shards > 1 and (fid % shards) != shard:
            continue
        if rel.startswith(("/", "\\")) or Path(rel).is_absolute():
            continue
        p = PROJECT_ROOT / rel
        if p.is_file() and p.stat().st_size < cap:
            targets.append(rel)
    return targets


def build(shard: int = 0, shards: int = 1, limit: int = 0, size_cap_mb: float = 1.5) -> None:
    """카탈로그의 서식을 훑어 캐시를 채운다.

    항목마다 별도 파일이라 샤드끼리 경합이 없다(DB 잠금 문제 없음).
    """
    import sqlite3

    catalog = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"
    con = sqlite3.connect(f"file:{catalog}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT form_id, source_path FROM forms "
        "WHERE status='OK' AND source_path IS NOT NULL "
        "ORDER BY form_id"
    ).fetchall()
    con.close()

    cap = size_cap_mb * 1024 * 1024
    targets = _select_targets(rows, shard, shards, cap)
    if limit:
        targets = targets[:limit]

    tag = f"[shard {shard}/{shards}] " if shards > 1 else ""
    print(f"{tag}[start] 캐시 대상 {len(targets):,}건 · 파서버전 {parser_version()}", flush=True)
    t0 = time.time()
    hit = made = fail = 0
    written = 0
    for i, rel in enumerate(targets, 1):
        try:
            res, cached = load_hwpx_cached(rel)
            if cached:
                hit += 1
            elif res.get("verdict") == "PASS":
                made += 1
                src = PROJECT_ROOT / rel
                written += entry_path(source_digest(src)).stat().st_size
            else:
                fail += 1
        except Exception:  # ruff: ignore[blind-except]
            fail += 1
        if i % 500 == 0:
            el = time.time() - t0
            rate = i / el if el else 0
            eta = (len(targets) - i) / rate / 60 if rate else 0
            print(
                f"{tag}  … {i:,}/{len(targets):,} 적중 {hit:,} 생성 {made:,} "
                f"실패 {fail} [{el:.0f}s ~{rate:.1f}/s 남은 {eta:.0f}분] "
                f"{written / 1024 / 1024:.0f}MB",
                flush=True,
            )
    el = time.time() - t0
    print(
        f"{tag}[done] 적중 {hit:,} · 생성 {made:,} · 실패 {fail} · "
        f"{el / 60:.1f}분 · {written / 1024 / 1024:.0f}MB",
        flush=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="캐시 채우기")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--verify", action="store_true", help="표본 재파싱해 캐시와 대조 (낡음 검출)")
    ap.add_argument("--prune", action="store_true", help="옛 파서 버전 캐시 삭제")
    ap.add_argument("--sample", type=int, default=25)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    if args.stats:
        print(json.dumps(stats(), ensure_ascii=False, indent=2))
    elif args.verify:
        print(json.dumps(verify(args.sample), ensure_ascii=False, indent=2))
    elif args.prune:
        print(json.dumps(prune(), ensure_ascii=False, indent=2))
    elif args.build:
        build(args.shard, args.shards, args.limit)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
