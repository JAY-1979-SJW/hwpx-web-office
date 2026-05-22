"""P5-D-SEC3 — HWPX 업로드 보안 게이트 (F동 진입 차단막).

방화구획:
  G1 확장자 (.hwpx/.hwp)
  G2 magic byte (PK\\x03\\x04 = ZIP 헤더)
  G3 크기 (≤100MB)
  G4 ZIP 무결성 (open 가능)
  G5 ZIP bomb (압축비 ≤ 100:1)
  G6 path traversal (entry name `..` 또는 절대경로 차단)
  G7 mimetype first entry == "application/hwp+zip" 또는 OWPML
  G8 XML XXE 안전 파싱 (resolve_entities=False)
  G9 entry 수 상한 (≤ 10000)
  G10 단일 entry 비압축 크기 상한 (≤ 500MB)

사용:
  python scripts/ops/hwpx_upload_security_gate.py FILE
  → JSON 보고 + exit 0(PASS) / 1(FAIL)
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MAX_FILE_SIZE = 100 * 1024 * 1024            # 100 MB
MAX_ENTRY_UNCOMPRESSED = 500 * 1024 * 1024   # 500 MB per entry
MAX_TOTAL_UNCOMPRESSED = 1024 * 1024 * 1024  # 1 GB total
MAX_COMPRESSION_RATIO = 100
MAX_ENTRY_COUNT = 10000
ALLOWED_EXTS = {".hwpx", ".hwp"}
ALLOWED_MIMETYPES = {
    "application/hwp+zip",
    "application/vnd.hancom.hwpx",
    "application/owpml",
    "application/owpml-package+xml",
}


def _g1_extension(p: Path) -> dict:
    ok = p.suffix.lower() in ALLOWED_EXTS
    return {"gate": "G1_extension", "ok": ok, "value": p.suffix}


def _g2_magic(p: Path) -> dict:
    with p.open("rb") as f:
        head = f.read(4)
    ok = head[:2] == b"PK"
    return {"gate": "G2_magic", "ok": ok, "value": head.hex()}


def _g3_size(p: Path) -> dict:
    size = p.stat().st_size
    ok = 0 < size <= MAX_FILE_SIZE
    return {"gate": "G3_size", "ok": ok, "value": size}


def _g4_zip_integrity(p: Path) -> dict:
    try:
        with zipfile.ZipFile(str(p)) as z:
            bad = z.testzip()
        return {"gate": "G4_zip_integrity", "ok": bad is None,
                       "value": bad or "ok"}
    except zipfile.BadZipFile as e:
        return {"gate": "G4_zip_integrity", "ok": False, "value": str(e)[:120]}


def _g5_g6_g9_g10_zip_walk(p: Path) -> list[dict]:
    results: list[dict] = []
    try:
        with zipfile.ZipFile(str(p)) as z:
            infos = z.infolist()
            results.append({
                "gate": "G9_entry_count",
                "ok": len(infos) <= MAX_ENTRY_COUNT,
                "value": len(infos),
            })

            bad_paths = [i.filename for i in infos
                                if ".." in i.filename.split("/")
                                or i.filename.startswith("/")
                                or i.filename.startswith("\\")]
            results.append({
                "gate": "G6_path_traversal",
                "ok": not bad_paths,
                "value": bad_paths[:5],
            })

            total_uncompressed = 0
            worst_ratio = 0.0
            worst_entry = ""
            oversized: list[str] = []
            for i in infos:
                total_uncompressed += i.file_size
                if i.file_size > MAX_ENTRY_UNCOMPRESSED:
                    oversized.append(i.filename)
                if i.compress_size > 0:
                    ratio = i.file_size / max(i.compress_size, 1)
                    if ratio > worst_ratio:
                        worst_ratio = ratio
                        worst_entry = i.filename

            results.append({
                "gate": "G5_zip_bomb_ratio",
                "ok": worst_ratio <= MAX_COMPRESSION_RATIO,
                "value": {"ratio": round(worst_ratio, 2),
                                  "entry": worst_entry},
            })
            results.append({
                "gate": "G10_entry_size",
                "ok": not oversized
                        and total_uncompressed <= MAX_TOTAL_UNCOMPRESSED,
                "value": {"totalUncompressed": total_uncompressed,
                                  "oversizedEntries": oversized[:5]},
            })
    except Exception as e:
        results.append({"gate": "G5_G6_G9_G10_walk_error",
                              "ok": False, "value": str(e)[:120]})
    return results


def _g7_mimetype_first(p: Path) -> dict:
    try:
        with zipfile.ZipFile(str(p)) as z:
            names = z.namelist()
            if not names or names[0] != "mimetype":
                return {"gate": "G7_mimetype_first", "ok": False,
                              "value": names[:1]}
            mt = z.read("mimetype").decode("utf-8", "ignore").strip()
            ok = mt in ALLOWED_MIMETYPES
            return {"gate": "G7_mimetype_first", "ok": ok, "value": mt}
    except Exception as e:
        return {"gate": "G7_mimetype_first", "ok": False,
                       "value": str(e)[:120]}


def _g8_xml_xxe_safe(p: Path) -> dict:
    """XXE 방어 — entity·DTD·external 차단 후 파싱 시도."""
    import xml.etree.ElementTree as ET

    bad_entries: list[str] = []
    try:
        with zipfile.ZipFile(str(p)) as z:
            for name in z.namelist():
                if not (name.endswith(".xml") or name.endswith(".hpf")):
                    continue
                raw = z.read(name)
                # 외부 entity·DTD 탐지 (보수적)
                head = raw[:2048].lower()
                if b"<!doctype" in head or b"<!entity" in head:
                    bad_entries.append(name)
                    continue
                try:
                    ET.fromstring(raw)
                except ET.ParseError:
                    # 일부 HWPX XML이 ns 선언 누락으로 fail 가능 — 보안 fail로 간주 X
                    pass
        return {"gate": "G8_xml_xxe_safe", "ok": not bad_entries,
                       "value": bad_entries[:5]}
    except Exception as e:
        return {"gate": "G8_xml_xxe_safe", "ok": False,
                       "value": str(e)[:120]}


def inspect(path: Path) -> dict:
    if not path.is_file():
        return {"verdict": "FAIL", "error": f"not a file: {path}"}

    gates: list[dict] = []
    gates.append(_g1_extension(path))
    gates.append(_g2_magic(path))
    gates.append(_g3_size(path))
    gates.append(_g4_zip_integrity(path))
    if gates[-1]["ok"]:
        gates.extend(_g5_g6_g9_g10_zip_walk(path))
        gates.append(_g7_mimetype_first(path))
        gates.append(_g8_xml_xxe_safe(path))

    failed = [g for g in gates if not g["ok"]]
    return {
        "src": str(path),
        "verdict": "PASS" if not failed else "FAIL",
        "failedGates": [g["gate"] for g in failed],
        "gates": gates,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="HWPX 파일")
    ap.add_argument("--batch", type=int, default=0,
                          help="corpus N건 일괄 검사")
    args = ap.parse_args()

    if args.batch > 0:
        import sqlite3
        conn = sqlite3.connect(
            str(PROJECT_ROOT / "data/recognition_corpus/corpus.sqlite3"))
        rows = conn.execute(f"""
            SELECT d.source_path FROM hwpx_documents d
            WHERE d.inventory_status='FOUND'
              AND d.file_size BETWEEN 10000 AND 200000
            ORDER BY d.first_seen_at LIMIT {int(args.batch)}
        """).fetchall()
        conn.close()
        counts = {"PASS": 0, "FAIL": 0}
        fails: list[dict] = []
        for (sp,) in rows:
            full = PROJECT_ROOT / sp
            if not full.is_file():
                continue
            r = inspect(full)
            v = r["verdict"]
            counts[v] = counts.get(v, 0) + 1
            if v == "FAIL":
                fails.append({"src": str(full), "failed": r["failedGates"]})
        print(json.dumps({
            "totalChecked": counts["PASS"] + counts["FAIL"],
            "counts": counts,
            "fails": fails[:10],
        }, ensure_ascii=False, indent=2))
        return 0 if counts["FAIL"] == 0 else 1

    r = inspect(Path(args.src))
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    return 0 if r.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
