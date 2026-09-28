"""Java HwpxParser roundtrip gate for generated HWPX files."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from hwpx_package import read_json, write_csv, write_json


def _gradlew_path() -> Path:
    return Path("gradlew.bat") if Path("gradlew.bat").exists() else Path("./gradlew")


def _roundtrip_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault(
        "GRADLE_USER_HOME", str(Path(tempfile.gettempdir()) / "office-analysis-gradle-home")
    )
    return env


def _expected_found(
    response: dict[str, Any], expected_values: list[str]
) -> tuple[list[str], list[str]]:
    full_text = str(response.get("fullText", ""))
    found = [value for value in expected_values if value in full_text]
    missing = [value for value in expected_values if value not in full_text]
    return found, missing


def _list_strings(values: Any) -> list[str]:
    if not values:
        return []
    if not isinstance(values, list):
        values = [values]
    return [str(value) for value in values if str(value)]


def run_java_roundtrip(  # ruff: ignore[too-many-arguments] -- 테스트 커버리지 없어 시그니처 재구성 보류, 전부 keyword-only 라 가독성 문제는 적음
    hwpx_path: Path,
    *,
    expected_values: list[str] | None = None,
    parser_text_expected_values: list[str] | None = None,
    package_expected_values: list[str] | None = None,
    metadata_expected_values: list[str] | None = None,
    out_json: Path | None = None,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    """Run the Java parser CLI for one HWPX file and summarize the result."""
    expected = _list_strings(expected_values)
    parser_text_expected = _list_strings(
        parser_text_expected_values if parser_text_expected_values is not None else expected
    )
    package_expected = _list_strings(package_expected_values)
    metadata_expected = _list_strings(metadata_expected_values)
    output_json = out_json or hwpx_path.with_suffix(".java_roundtrip.json")
    gradlew = _gradlew_path()
    cmd = [
        str(gradlew),
        "parseHwpxCli",
        "-PskipGitHooks=true",
        f"-Pinput={hwpx_path!s}",
        f"-Poutput={output_json!s}",
    ]
    report: dict[str, Any] = {
        "status": "FAIL",
        "input": str(hwpx_path),
        "output_json": str(output_json),
        "command": cmd,
        "expected_values": expected,
        "parser_text_expected_values": parser_text_expected,
        "package_expected_values": package_expected,
        "metadata_expected_values": metadata_expected,
    }
    if not hwpx_path.exists():
        report["error"] = "INPUT_NOT_FOUND"
        return report
    try:
        proc = subprocess.run(
            cmd,
            cwd=Path.cwd(),
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_roundtrip_env(),
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        report.update({
            "status": "FAIL",
            "error": "JAVA_ROUNDTRIP_TIMEOUT",
            "timeout_sec": timeout_sec,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        })
        return report

    report["returncode"] = proc.returncode
    report["stdout_tail"] = (proc.stdout or "")[-4000:]
    report["stderr_tail"] = (proc.stderr or "")[-4000:]
    if not output_json.exists():
        report["error"] = "JAVA_ROUNDTRIP_OUTPUT_NOT_FOUND"
        return report

    response = read_json(output_json)
    found, missing = _expected_found(response, parser_text_expected)
    diagnostics = response.get("diagnostics") or {}
    ok = bool(response.get("ok")) and proc.returncode == 0
    report.update({
        "status": "PASS" if ok and not missing else "WARN" if ok else "FAIL",
        "parse_ok": bool(response.get("ok")),
        "paragraph_count": len(response.get("paragraphs") or []),
        "table_count": len(response.get("tables") or []),
        "semantic_sections_count": len(response.get("semanticSections") or []),
        "extracted_fields_count": len(response.get("extractedFields") or []),
        "diagnostics_exists": bool(diagnostics),
        "quality_score": diagnostics.get("qualityScore") if isinstance(diagnostics, dict) else None,
        "expected_values_found": found,
        "missing_expected_values": missing,
        "parser_text_expected_count": len(parser_text_expected),
        "package_expected_count": len(package_expected),
        "metadata_expected_count": len(metadata_expected),
        "error_count": response.get("errorCount"),
        "warning_count": response.get("warningCount"),
    })
    return report


def run_many_java_roundtrips(
    items: list[dict[str, Any]],
    out_dir: Path,
    *,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    """Run Java parser roundtrip for several generated HWPX files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, item in enumerate(items, start=1):
        input_path = Path(str(item["input"]))
        output_json = out_dir / f"{input_path.stem}_{index:03d}_java_roundtrip.json"
        result = run_java_roundtrip(
            input_path,
            expected_values=_list_strings(item.get("expected_values", [])),
            parser_text_expected_values=_list_strings(
                item.get("parser_text_expected_values", item.get("text_expected_values", []))
            )
            or None,
            package_expected_values=_list_strings(item.get("package_expected_values", [])),
            metadata_expected_values=_list_strings(item.get("metadata_expected_values", [])),
            out_json=output_json,
            timeout_sec=timeout_sec,
        )
        result["name"] = item.get("name", input_path.stem)
        results.append(result)
    summary = {
        "status": "PASS"
        if results and all(item.get("status") == "PASS" for item in results)
        else "WARN"
        if results and all(item.get("status") in {"PASS", "WARN"} for item in results)
        else "FAIL",
        "count": len(results),
        "pass_count": sum(1 for item in results if item.get("status") == "PASS"),
        "warn_count": sum(1 for item in results if item.get("status") == "WARN"),
        "fail_count": sum(1 for item in results if item.get("status") == "FAIL"),
        "results": results,
    }
    return summary


def _items_from_json(path: Path) -> list[dict[str, Any]]:
    data = read_json(path)
    if isinstance(data, dict):
        items = data.get("items", [])
    else:
        items = data
    if not isinstance(items, list):
        raise ValueError("items JSON must be a list or an object with items[]")
    return [dict(item) for item in items]


def csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": item.get("name"),
            "status": item.get("status"),
            "input": item.get("input"),
            "paragraph_count": item.get("paragraph_count"),
            "table_count": item.get("table_count"),
            "semantic_sections_count": item.get("semantic_sections_count"),
            "extracted_fields_count": item.get("extracted_fields_count"),
            "quality_score": item.get("quality_score"),
            "parser_text_expected_count": item.get("parser_text_expected_count"),
            "package_expected_count": item.get("package_expected_count"),
            "metadata_expected_count": item.get("metadata_expected_count"),
            "missing_expected_values": "|".join(item.get("missing_expected_values", [])),
        }
        for item in report.get("results", [])
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Java HwpxParser roundtrip for generated HWPX files"
    )
    parser.add_argument("--items-json", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--report-json")
    parser.add_argument("--report-csv")
    parser.add_argument("--timeout-sec", type=int, default=120)
    args = parser.parse_args()

    report = run_many_java_roundtrips(
        _items_from_json(Path(args.items_json)), Path(args.out_dir), timeout_sec=args.timeout_sec
    )
    if args.report_json:
        write_json(Path(args.report_json), report)
    if args.report_csv:
        write_csv(Path(args.report_csv), csv_rows(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
