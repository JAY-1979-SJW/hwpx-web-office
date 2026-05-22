"""HWPX Pipeline — hancom_safe_gate.

hwpx_full_verify를 파이프라인에 연결하고 판정 기준을 적용한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .pipeline_contract import HancomVerifyResult

_VERIFY_PATH = Path(__file__).resolve().parents[3] / "scripts" / "local"
if str(_VERIFY_PATH) not in sys.path:
    sys.path.insert(0, str(_VERIFY_PATH))

try:
    from hwpx_full_verify import verify as _full_verify  # type: ignore
    _VERIFY_AVAILABLE = True
except ImportError:
    _VERIFY_AVAILABLE = False


def verify(output_path: Path) -> HancomVerifyResult:
    """output HWPX의 한컴 호환성을 검증한다."""
    result = HancomVerifyResult()

    if not output_path.exists():
        result.errors.append(f"output_file_not_found: {output_path}")
        result.verdict = "FAIL"
        return result

    if not _VERIFY_AVAILABLE:
        result.warnings.append("hwpx_full_verify not available; fallback to basic ZIP check")
        return _basic_check(output_path, result)

    try:
        report = _full_verify(str(output_path))
        result.errors = report.get("errors", [])
        result.warnings = report.get("warnings", [])
        result.info = report.get("info", {})
    except Exception as exc:
        result.errors.append(f"verify_exception: {exc}")
        result.verdict = "FAIL"
        return result

    if result.errors:
        result.verdict = "FAIL"
    elif result.warnings:
        result.verdict = "REVIEW_REQUIRED"
    else:
        result.verdict = "PASS"

    return result


def _basic_check(output_path: Path, result: HancomVerifyResult) -> HancomVerifyResult:
    """hwpx_full_verify 없을 때 기본 ZIP/mimetype 검사."""
    import zipfile

    try:
        with zipfile.ZipFile(output_path, "r") as zf:
            names = zf.namelist()
            infos = {i.filename: i for i in zf.infolist()}
            result.info["entry_count"] = len(names)

            if not names or names[0] != "mimetype":
                result.errors.append("mimetype is not first entry")
            mt_info = infos.get("mimetype")
            if mt_info and mt_info.compress_type != 0:
                result.errors.append(f"mimetype not ZIP_STORED: {mt_info.compress_type}")
            if "mimetype" in names:
                mt = zf.read("mimetype").decode("ascii", errors="replace").strip()
                result.info["mimetype"] = mt
                if mt not in ("application/hwp+zip", "application/owpml"):
                    result.errors.append(f"mimetype value invalid: {mt!r}")
            if "Contents/content.hpf" not in names:
                result.errors.append("content.hpf missing")
            if "META-INF/container.xml" not in names:
                result.errors.append("container.xml missing")
    except Exception as exc:
        result.errors.append(f"zip_open_fail: {exc}")

    result.verdict = "FAIL" if result.errors else ("REVIEW_REQUIRED" if result.warnings else "PASS")
    return result
