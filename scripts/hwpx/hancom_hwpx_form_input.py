#!/usr/bin/env python3
"""Mark input-required cells in known HWPX form templates."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from hwpx_package import HwpxPackage, HwpxValidator
from hwpx_table_ops import (
    estimate_text_fit,
    get_table_cell_matrix,
    set_table_visual_cell_text,
    set_table_visual_cell_vertical_align,
    shrink_table_visual_cell_text_to_fit,
)


# Coordinates are HWPX visual grid coordinates from hp:cellAddr, not physical
# tc order. This matches the Java parse API response row/col values.
INPUT_REQUIRED_UPDATES = [
    {"table": 0, "row": 0, "col": 0, "value": "문서번호 : [입력필요: 문서번호] 호"},
    {"table": 0, "row": 2, "col": 0, "value": "시행일자 : [입력필요: 시행일자]"},
    {"table": 0, "row": 4, "col": 2, "value": "[입력필요: 접수일시]"},
    {"table": 0, "row": 4, "col": 4, "value": "[입력필요: 접수번호]"},
    {"table": 1, "row": 2, "col": 2, "value": "[입력필요: 감리자 상호]"},
    {"table": 1, "row": 2, "col": 7, "value": "제 [입력필요: 활동주체 신고번호]"},
    {"table": 1, "row": 3, "col": 7, "value": "[입력필요: 감리자 전화번호]"},
    {"table": 1, "row": 4, "col": 2, "value": "[입력필요: 감리자 주소]"},
    {"table": 1, "row": 6, "col": 2, "value": "[입력필요: 시공사 상호]"},
    {"table": 1, "row": 6, "col": 7, "value": "제 [입력필요: 정보통신공사업 등록번호]"},
    {"table": 1, "row": 7, "col": 2, "value": "[입력필요: 시공사 대표자]"},
    {"table": 1, "row": 7, "col": 7, "value": "[입력필요: 시공사 전화번호]"},
    {"table": 1, "row": 8, "col": 2, "value": "[입력필요: 시공사 주소]"},
    {"table": 1, "row": 10, "col": 2, "value": "[입력필요: 현장명]"},
    {"table": 1, "row": 11, "col": 2, "value": "[입력필요: 현장주소]"},
    {"table": 1, "row": 12, "col": 2, "value": "[입력필요: 공사의 종류]"},
    {"table": 1, "row": 13, "col": 2, "value": "[입력필요: 구내통신선로설비 등 구분]"},
    {"table": 1, "row": 14, "col": 2, "value": "[입력필요: 건축면적] ㎡"},
    {"table": 1, "row": 14, "col": 6, "value": "[입력필요: 연면적] ㎡"},
    {"table": 1, "row": 15, "col": 2, "value": "[입력필요: 착공일]"},
    {"table": 1, "row": 15, "col": 6, "value": "[입력필요: 완공일]"},
    {"table": 2, "row": 2, "col": 2, "value": "[입력필요: 착공일]"},
    {"table": 2, "row": 2, "col": 4, "value": "[입력필요: 완공일]"},
    {"table": 2, "row": 3, "col": 2, "value": "[입력필요: 감리자 상호]"},
    {"table": 2, "row": 3, "col": 4, "value": "제 [입력필요: 활동주체 신고번호]"},
    {"table": 2, "row": 4, "col": 4, "value": "[입력필요: 감리자 전화번호]"},
    {"table": 3, "row": 2, "col": 4, "value": "[입력필요: 착공일]"},
    {"table": 3, "row": 2, "col": 11, "value": "[입력필요: 완공일]"},
    {"table": 3, "row": 3, "col": 4, "value": "[입력필요: 감리자 상호]"},
    {"table": 3, "row": 3, "col": 11, "value": "제 [입력필요: 활동주체 신고번호]"},
    {"table": 3, "row": 4, "col": 11, "value": "[입력필요: 감리자 전화번호]"},
    {"table": 3, "row": 8, "col": 1, "value": "[입력필요: 품명]"},
    {"table": 3, "row": 8, "col": 3, "value": "[입력필요: 규격]"},
    {"table": 3, "row": 8, "col": 5, "value": "[입력필요: 단위]"},
    {"table": 3, "row": 8, "col": 6, "value": "[입력필요: 설계량]"},
    {"table": 3, "row": 8, "col": 7, "value": "[입력필요: 반입량]"},
    {"table": 3, "row": 8, "col": 8, "value": "[입력필요: 반입일]"},
    {"table": 3, "row": 8, "col": 9, "value": "[입력필요: 합격량]"},
    {"table": 3, "row": 8, "col": 10, "value": "[입력필요: 불합격량]"},
    {"table": 3, "row": 8, "col": 12, "value": "[입력필요: 불합격 사유]"},
    {"table": 3, "row": 8, "col": 13, "value": "[입력필요: 검수자]"},
    {"table": 4, "row": 2, "col": 3, "value": "[입력필요: 시공사 상호]"},
    {"table": 4, "row": 2, "col": 7, "value": "[입력필요: 시공사 전화번호]"},
    {"table": 4, "row": 3, "col": 3, "value": "[입력필요: 시공사 대표자]"},
    {"table": 4, "row": 3, "col": 7, "value": "제 [입력필요: 정보통신공사업 등록번호]"},
    {"table": 4, "row": 4, "col": 3, "value": "[입력필요: 시공사 주소]"},
    {"table": 4, "row": 7, "col": 0, "value": "[입력필요: 기술자 성명]"},
    {"table": 4, "row": 7, "col": 2, "value": "[입력필요: 자격등급]"},
    {"table": 4, "row": 7, "col": 4, "value": "[입력필요: 자격발급번호]"},
    {"table": 4, "row": 7, "col": 6, "value": "[입력필요: 업무 배치 구분]"},
]


def table_text_at(matrix: dict[str, Any], row: int, col: int) -> str:
    cell = table_cell_at(matrix, row, col)
    return str(cell.get("text", "")) if cell else ""


def table_cell_at(matrix: dict[str, Any], row: int, col: int) -> dict[str, Any] | None:
    for row_info in matrix.get("rows", []):
        for cell in row_info.get("cells", []):
            if cell.get("visual_row") == row and cell.get("visual_col") == col:
                return cell
    return None


def field_label(marker_value: str) -> str:
    match = re.search(r"\[입력필요:\s*([^\]]+)\]", marker_value)
    return match.group(1).strip() if match else marker_value.strip()


def normalize_key(value: str) -> str:
    return re.sub(r"[\s:_\-\[\]()]+", "", value).lower()


def validate_supplied_field(label: str, value: str) -> list[dict[str, Any]]:
    normalized_label = normalize_key(label)
    text = value.strip()
    warnings: list[dict[str, Any]] = []
    if not text:
        return warnings
    if any(token in normalized_label for token in ("일자", "착공일", "완공일", "반입일")):
        if not re.fullmatch(r"(?:20)?\d{2}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?", text):
            warnings.append({"type": "DATE_FORMAT_WARN", "label": label, "value": value, "expected": "YYYY.MM.DD or YYYY년 MM월 DD일"})
    if "전화번호" in normalized_label:
        if not re.fullmatch(r"0\d{1,2}-?\d{3,4}-?\d{4}", text):
            warnings.append({"type": "PHONE_FORMAT_WARN", "label": label, "value": value, "expected": "02-0000-0000 or 010-0000-0000"})
    if any(token in normalized_label for token in ("면적", "설계량", "반입량", "합격량", "불합격량")):
        number_text = text.replace(",", "").replace("㎡", "").replace("m2", "").strip()
        if number_text and not re.fullmatch(r"\d+(?:\.\d+)?", number_text):
            warnings.append({"type": "NUMBER_FORMAT_WARN", "label": label, "value": value, "expected": "numeric value"})
    if any(token in normalized_label for token in ("등록번호", "신고번호", "자격발급번호", "문서번호", "접수번호")):
        if len(re.sub(r"\s+", "", text)) < 3:
            warnings.append({"type": "IDENTIFIER_TOO_SHORT_WARN", "label": label, "value": value})
    return warnings


def compact_supplied_value_candidates(label: str, value: str) -> list[str]:
    normalized_label = normalize_key(label)
    text = value.strip()
    candidates = [text]
    date_match = re.search(r"(20\d{2})\D+(\d{1,2})\D+(\d{1,2})", text)
    if date_match and any(token in normalized_label for token in ("일시", "일자", "착공일", "완공일", "반입일")):
        year, month, day = date_match.groups()
        candidates.extend(
            [
                f"{year}.{int(month):02d}.{int(day):02d}",
                f"{int(month):02d}.{int(day):02d}",
                f"{int(month)}.{int(day)}",
            ]
        )
    if any(token in normalized_label for token in ("등록번호", "신고번호")) and "-" in text:
        parts = [part for part in text.split("-") if part]
        if len(parts) >= 2:
            candidates.append("-".join(parts[-2:]))
        candidates.append(parts[-1])
    if "접수번호" in normalized_label and "-" in text:
        parts = [part for part in text.split("-") if part]
        candidates.append(parts[-1])
    if "품명" in normalized_label:
        candidates.append(re.sub(r"\s+", "", text))
    unique = []
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def choose_output_value_for_cell(marker_value: str, label: str, supplied: str, before_cell: dict[str, Any]) -> dict[str, Any]:
    attempts = []
    for candidate in compact_supplied_value_candidates(label, supplied):
        output_value = format_supplied_value(marker_value, candidate)
        fit_check = estimate_text_fit(output_value, before_cell) if before_cell else {"status": "CELL_STYLE_NOT_FOUND"}
        attempts.append({"supplied": candidate, "output": output_value, "fit_check": fit_check})
        if fit_check.get("status") == "PASS":
            return {
                "output_value": output_value,
                "supplied_value_used": candidate,
                "layout_compaction": {
                    "status": "APPLIED" if candidate != supplied.strip() else "NOT_NEEDED",
                    "original_value": supplied,
                    "used_value": candidate,
                    "attempts": attempts,
                },
                "fit_check": fit_check,
            }
    best = min(attempts, key=lambda item: item["fit_check"].get("text_length", 999999)) if attempts else None
    return {
        "output_value": best["output"] if best else format_supplied_value(marker_value, supplied),
        "supplied_value_used": best["supplied"] if best else supplied.strip(),
        "layout_compaction": {
            "status": "UNRESOLVED" if best and best["supplied"] != supplied.strip() else "NOT_APPLIED",
            "original_value": supplied,
            "used_value": best["supplied"] if best else supplied.strip(),
            "attempts": attempts,
        },
        "fit_check": best["fit_check"] if best else {"status": "CELL_STYLE_NOT_FOUND"},
    }


def load_input_data(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("data-json must be a JSON object")
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            normalized[normalize_key(str(key))] = text
    return normalized


def is_placeholder_or_label(text: str, label: str) -> bool:
    normalized = re.sub(r"\s+", "", text or "")
    if not normalized:
        return True
    if "입력필요" in normalized:
        return True
    if normalized in {"제", "호", "㎡", ".", "..", "..."}:
        return True
    if set(normalized) <= {".", "년", "월", "일"}:
        return True
    if "0000-000" in normalized:
        return True
    if normalized.startswith("시행일자:20") and "월" in normalized and "일" in normalized:
        return True
    if normalize_key(normalized) == normalize_key(label):
        return True
    return False


def format_missing_marker(marker_value: str) -> str:
    value = marker_value.strip()
    if value.startswith("제 ") and not value.endswith("호"):
        return f"{value} 호"
    return value


def format_supplied_value(marker_value: str, supplied: str) -> str:
    value = supplied.strip()
    if marker_value.startswith("문서번호"):
        return f"문서번호 : {value} 호"
    if marker_value.startswith("시행일자"):
        return f"시행일자 : {value}"
    if marker_value.startswith("제 "):
        return f"제 {value} 호"
    if marker_value.endswith("㎡"):
        return f"{value} ㎡"
    return value


def missing_request_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# HWPX 입력 필요 자료 요청",
        "",
        "아래 값은 원본 문서에서 확인되지 않아 사용자 입력이 필요합니다.",
        "",
    ]
    lines.extend(f"- {item['label']} (table={item['table']}, row={item['row']}, col={item['col']})" for item in report.get("missing_user_inputs", []))
    lines.append("")
    lines.append("JSON으로 제공할 경우 예:")
    lines.append("")
    lines.append("```json")
    example = {item["label"]: "" for item in report.get("missing_user_inputs", [])}
    lines.append(json.dumps(example, ensure_ascii=False, indent=2))
    lines.append("```")
    return "\n".join(lines)


def apply_final_layout_adjustments(package: HwpxPackage, results: list[dict[str, Any]]) -> dict[str, Any]:
    font_adjustments = []
    vertical_alignments = []
    layout_warnings = []
    for result in results:
        if result.get("status") != "PASS":
            continue
        table = int(result.get("table_index", -1))
        row = int(result.get("visual_row", -1))
        col = int(result.get("visual_col", -1))
        value = str(result.get("field", ""))
        align_result = set_table_visual_cell_vertical_align(package, table, row, col, "CENTER")
        result["vertical_alignment"] = align_result
        if align_result.get("status") == "VERTICAL_ALIGN_PASS" and align_result.get("before") != align_result.get("after"):
            vertical_alignments.append(
                {
                    "label": result.get("label", ""),
                    "table": table,
                    "row": row,
                    "col": col,
                    "before": align_result.get("before"),
                    "after": align_result.get("after"),
                }
            )

        matrix = get_table_cell_matrix(package, table)
        after_cell = table_cell_at(matrix, row, col) or {}
        fit_check = estimate_text_fit(value, after_cell) if after_cell else {"status": "CELL_STYLE_NOT_FOUND"}
        if str(fit_check.get("status", "")).startswith("WARN") and result.get("source") == "supplied_data":
            font_adjustment = shrink_table_visual_cell_text_to_fit(package, table, row, col, value)
            result["font_adjustment"] = font_adjustment
            if font_adjustment.get("status") == "FONT_SHRINK_PASS":
                font_adjustments.append(
                    {
                        "label": result.get("label", ""),
                        "table": table,
                        "row": row,
                        "col": col,
                        "source_charPrIDRef": font_adjustment.get("source_charPrIDRef"),
                        "new_charPrIDRef": font_adjustment.get("new_charPrIDRef"),
                        "original_height": font_adjustment.get("original_height"),
                        "target_height": font_adjustment.get("target_height"),
                        "before_fit": font_adjustment.get("before_fit"),
                        "after_fit": font_adjustment.get("after_fit"),
                    }
                )
                fit_check = font_adjustment.get("after_fit", fit_check)
        result["fit_check"] = fit_check
        if str(fit_check.get("status", "")).startswith("WARN"):
            layout_warnings.append(
                {
                    "label": result.get("label", ""),
                    "table": table,
                    "row": row,
                    "col": col,
                    "status": fit_check["status"],
                    "text_length": fit_check["text_length"],
                    "estimated_max_chars_single_line": fit_check["estimated_max_chars_single_line"],
                    "line_wrap": fit_check["line_wrap"],
                }
            )
    return {
        "font_adjustments": font_adjustments,
        "vertical_alignments": vertical_alignments,
        "layout_warnings": layout_warnings,
    }


def mark_input_required(input_path: Path, output_path: Path, data_json: Path | None = None) -> dict[str, Any]:
    package = HwpxPackage(input_path)
    supplied_data = load_input_data(data_json)
    before_matrices = {i: get_table_cell_matrix(package, i) for i in range(5)}
    results = []
    missing_user_inputs = []
    preserved_existing_values = []
    supplied_values = []
    layout_warnings = []
    layout_compactions = []
    font_adjustments = []
    vertical_alignments = []
    value_warnings = []
    for update in INPUT_REQUIRED_UPDATES:
        matrix = before_matrices.get(update["table"], {})
        before_cell = table_cell_at(matrix, update["row"], update["col"]) or {}
        before_text = str(before_cell.get("text", ""))
        label = field_label(update["value"])
        data_value = supplied_data.get(normalize_key(label))
        if data_value:
            choice = choose_output_value_for_cell(update["value"], label, data_value, before_cell)
            output_value = choice["output_value"]
            source = "supplied_data"
            supplied_values.append(
                {
                    "label": label,
                    "value": data_value,
                    "used_value": choice["supplied_value_used"],
                    "table": update["table"],
                    "row": update["row"],
                    "col": update["col"],
                }
            )
            if choice["layout_compaction"]["status"] in {"APPLIED", "UNRESOLVED"}:
                layout_compactions.append(
                    {
                        "label": label,
                        "table": update["table"],
                        "row": update["row"],
                        "col": update["col"],
                        **choice["layout_compaction"],
                    }
                )
            for warning in validate_supplied_field(label, data_value):
                warning.update({"table": update["table"], "row": update["row"], "col": update["col"]})
                value_warnings.append(warning)
        elif not is_placeholder_or_label(before_text, label):
            output_value = before_text
            source = "existing_document"
            preserved_existing_values.append({"label": label, "value": before_text, "table": update["table"], "row": update["row"], "col": update["col"]})
        else:
            output_value = format_missing_marker(update["value"])
            source = "missing_user_input"
            missing_user_inputs.append(
                {
                    "label": label,
                    "table": update["table"],
                    "row": update["row"],
                    "col": update["col"],
                    "current_text": before_text,
                    "prompt": f"{label} 자료를 제공해 주세요.",
                }
            )
        result = set_table_visual_cell_text(
            package,
            update["table"],
            update["row"],
            update["col"],
            output_value,
            clear_remaining=True,
        )
        result["expected_before_text"] = before_text
        result["field"] = output_value
        result["label"] = label
        result["source"] = source
        result["pre_adjust_fit_check"] = estimate_text_fit(output_value, before_cell) if before_cell else {"status": "CELL_STYLE_NOT_FOUND"}
        results.append(result)
    final_adjustments = apply_final_layout_adjustments(package, results)
    font_adjustments = final_adjustments["font_adjustments"]
    vertical_alignments = final_adjustments["vertical_alignments"]
    layout_warnings = final_adjustments["layout_warnings"]
    package.write_package(output_path)
    validation = HwpxValidator.validate_hwpx(output_path)
    return {
        "status": "PASS" if all(result.get("status") == "PASS" for result in results) and validation.get("xml_ok") else "FAIL",
        "input": str(input_path),
        "output": str(output_path),
        "validation": validation,
        "updated_cells": sum(1 for result in results if result.get("status") == "PASS"),
        "supplied_values": supplied_values,
        "preserved_existing_values": preserved_existing_values,
        "missing_user_inputs": missing_user_inputs,
        "missing_user_input_count": len(missing_user_inputs),
        "layout_warnings": layout_warnings,
        "layout_warning_count": len(layout_warnings),
        "layout_compactions": layout_compactions,
        "layout_compaction_count": len(layout_compactions),
        "font_adjustments": font_adjustments,
        "font_adjustment_count": len(font_adjustments),
        "vertical_alignments": vertical_alignments,
        "vertical_alignment_count": len(vertical_alignments),
        "value_warnings": value_warnings,
        "value_warning_count": len(value_warnings),
        "updates": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--data-json", type=Path, help="Optional JSON object with field labels and values to insert")
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--request-md", type=Path, help="Optional markdown file listing missing user input fields")
    args = parser.parse_args()
    report = mark_input_required(args.input, args.output, args.data_json)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.request_md:
        args.request_md.parent.mkdir(parents=True, exist_ok=True)
        args.request_md.write_text(missing_request_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
