"""서식 준비 — 온디맨드로 편집 가능한 HWPX를 프로젝트 내 경로에 마련한다.

흐름:
    카탈로그/라이브러리의 원본(HWP 또는 HWPX)
    → HWP면 한컴 COM 변환, HWPX면 복사
    → tmp/web_office_forms/ (project-relative)
    → 편집기가 load 할 sourcePath 반환.

한컴 변환은 실제 한컴 한글 프로그램을 COM으로 구동(§ hwp-worker).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = PROJECT_ROOT / "tmp" / "web_office_forms"
DIAG_DIR = PROJECT_ROOT / "tmp" / "web_office_convert_diag"


def _rel(p: Path) -> str:
    return p.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def prepare_form(source_path: str, *, timeout_sec: int = 120) -> dict[str, Any]:
    """원본(HWP/HWPX)을 편집 가능한 project-relative HWPX로 준비.

    Returns:
        {ok, sourcePath, converted, provider?, error?}
    """
    src = Path(source_path)
    if not src.is_absolute():
        src = (PROJECT_ROOT / source_path)
    if not src.is_file():
        return {"ok": False, "error": "SOURCE_NOT_FOUND", "path": str(src)}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower()

    if ext == ".hwpx":
        dst = OUT_DIR / f"{src.stem}_{int(src.stat().st_size)}.hwpx"
        if not dst.exists():
            shutil.copy2(src, dst)
        return {"ok": True, "sourcePath": _rel(dst), "converted": False}

    if ext == ".hwp":
        # 한컴 COM 변환 (실제 한컴 한글 구동)
        sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "hwpx"))
        try:
            from hancom_hwp_to_hwpx_batch import convert_one_with_strategy
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "WORKER_IMPORT_FAIL", "detail": str(e)[:200]}
        DIAG_DIR.mkdir(parents=True, exist_ok=True)
        result = convert_one_with_strategy(
            src, OUT_DIR, timeout_sec, "convert", DIAG_DIR, "auto")
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error_code", "CONVERT_FAILED"),
                    "detail": result.get("error_message", ""),
                    "provider": result.get("provider")}
        out = Path(result.get("output", ""))
        if not out.is_file():
            return {"ok": False, "error": "OUTPUT_MISSING"}
        return {"ok": True, "sourcePath": _rel(out), "converted": True,
                "provider": result.get("provider")}

    return {"ok": False, "error": f"UNSUPPORTED_EXT:{ext}"}
