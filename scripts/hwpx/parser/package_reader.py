"""HWPX Parser V2 — package reader (read-only).

HWPX ZIP 패키지 구조를 읽는다. 원본 수정 없음.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .errors import ErrCode, WarnCode
from .parser_contract import PackageInfo, ParserWarning

NS_HH = "http://www.hancom.co.kr/hwpml/2011/head"
NS_OPF = "http://www.idpf.org/2007/opf/"


def read_package_info(path: Path) -> tuple[PackageInfo, list[ParserWarning]]:
    """HWPX ZIP 패키지 기본 정보를 읽어 PackageInfo로 반환."""
    warnings: list[ParserWarning] = []

    if not zipfile.is_zipfile(path):
        return PackageInfo(), [ParserWarning(ErrCode.ZIP_OPEN_FAIL, str(path))]

    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()

            has_mimetype = "mimetype" in names
            mt_value = ""
            mt_compress = -1
            if has_mimetype:
                try:
                    mt_value = zf.read("mimetype").decode("ascii", errors="replace").strip()
                    mt_compress = zf.getinfo("mimetype").compress_type
                except Exception as exc:  # noqa: BLE001 — 원인 무관하게 warning 기록 후 계속
                    warnings.append(
                        ParserWarning(
                            WarnCode.PACKAGE_STRUCTURE_WARN, f"mimetype read error: {exc}"
                        )
                    )

            has_content_hpf = "Contents/content.hpf" in names
            has_container = "META-INF/container.xml" in names
            has_header = "Contents/header.xml" in names
            section_files = [n for n in names if re.match(r"Contents/section\d+\.xml$", n)]

            xml_decode_ok = True
            pkg_warnings: list[str] = []

            if has_header:
                try:
                    header_raw = zf.read("Contents/header.xml")
                    ET.fromstring(header_raw)
                except Exception as exc:  # noqa: BLE001 — 원인 무관하게 warning 기록 후 계속
                    pkg_warnings.append(f"header.xml parse failed: {exc}")
                    xml_decode_ok = False

            for n in names:
                if n.endswith((".xml", ".hpf")):
                    try:
                        zf.read(n).decode("utf-8")
                    except UnicodeDecodeError:
                        pkg_warnings.append(f"non-utf8: {n}")
                        xml_decode_ok = False

            if has_mimetype and mt_compress != 0:
                pkg_warnings.append(f"mimetype not ZIP_STORED (compress_type={mt_compress})")
            if mt_value and mt_value not in ("application/hwp+zip", "application/owpml"):
                pkg_warnings.append(f"unexpected mimetype: {mt_value!r}")

            info = PackageInfo(
                entryCount=len(names),
                hasMimetype=has_mimetype,
                mimetypeValue=mt_value,
                mimetypeCompressType=mt_compress,
                hasContentHpf=has_content_hpf,
                hasContainerXml=has_container,
                hasHeaderXml=has_header,
                sectionFileCount=len(section_files),
                xmlDecodeOk=xml_decode_ok,
                packageWarnings=pkg_warnings,
            )
            return info, warnings

    except Exception as exc:  # noqa: BLE001 — 원인 무관하게 ZIP_OPEN_FAIL 로 기록 후 폴백
        return PackageInfo(), [ParserWarning(ErrCode.ZIP_OPEN_FAIL, str(exc))]


_ZIP_READ_ERRORS = (KeyError, zipfile.BadZipFile, OSError, RuntimeError)


def list_section_files(path: Path) -> list[str]:
    """section XML 파일 목록을 반환."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            return sorted(n for n in zf.namelist() if re.match(r"Contents/section\d+\.xml$", n))
    except _ZIP_READ_ERRORS:
        return []


def read_xml_entry(path: Path, entry_name: str) -> bytes:
    """ZIP 엔트리 raw bytes 반환. 읽기 전용."""
    with zipfile.ZipFile(path, "r") as zf:
        return zf.read(entry_name)


def read_header_xml(path: Path) -> bytes | None:
    """header.xml 내용 반환."""
    try:
        return read_xml_entry(path, "Contents/header.xml")
    except _ZIP_READ_ERRORS:
        return None


def read_section_xmls(path: Path) -> dict[str, bytes]:
    """section XML 파일들을 {entry_name: bytes} 로 반환."""
    result = {}
    for entry in list_section_files(path):
        try:
            result[entry] = read_xml_entry(path, entry)
        except _ZIP_READ_ERRORS:
            pass
    return result
