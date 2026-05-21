"""Example compose jobs for HWPX direct writer users.

The examples are deliberately generated from code so schema documentation and
smoke validation can share the same source of truth.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hwpx_package import write_json


STABLE_EXAMPLE_PROFILES = (
    "paragraph_list",
    "styled_table",
    "page_layout_numbering",
)

EXPERIMENTAL_EXAMPLE_PROFILES = (
    "complex_section_table_chart",
)


def _all_example_jobs(template: str, output_dir: str) -> dict[str, dict[str, Any]]:
    """Return small, independently composable job examples."""
    out = Path(output_dir)
    return {
        "paragraph_list": {
            "template": template,
            "output": str(out / "paragraph_list.hwpx"),
            "style_definitions": {
                "char_styles": {
                    "emphasis": {
                        "height": 1200,
                        "text_color": "#1F4E79",
                        "bold": True,
                    }
                },
                "para_styles": {
                    "centered": {
                        "align": "CENTER",
                        "line_spacing": 160,
                    }
                },
                "list_styles": {
                    "legal_outline": {
                        "preset": "mixed_legal",
                        "restart": True,
                        "start_number": 1,
                    }
                },
            },
            "paragraphs": [
                {
                    "text": "P27 문단 스타일 예시",
                    "style": {
                        "char_style": "emphasis",
                        "para_style": "centered",
                    },
                },
                {
                    "text": "P27 목록 1단계",
                    "style": {
                        "list_style": "legal_outline",
                        "list_level": 1,
                    },
                },
                {
                    "text": "P27 목록 2단계",
                    "style": {
                        "list_style": "legal_outline",
                        "list_level": 2,
                    },
                },
            ],
            "expected_values": ["P27 문단 스타일 예시", "P27 목록 1단계", "P27 목록 2단계"],
            "validate": True,
        },
        "styled_table": {
            "template": template,
            "output": str(out / "styled_table.hwpx"),
            "style_definitions": {
                "border_fills": {
                    "header_fill": {
                        "fill_color": "#D9EAF7",
                    },
                    "body_fill": {
                        "fill_color": "#FFFFFF",
                    },
                }
            },
            "tables": [
                {
                    "rows": [
                        ["항목", "값", "비고"],
                        ["공사명", "P27 표 예시", "자동 생성"],
                        ["상태", "PASS", "검증"],
                    ],
                    "style": {
                        "width": 36000,
                        "column_widths": [12000, 14000, 10000],
                        "row_heights": [2600, 2400, 2400],
                        "header_border_fill_style": "header_fill",
                        "body_border_fill_style": "body_fill",
                        "cell_vertical_align": "CENTER",
                        "cell_line_wrap": "BREAK",
                        "cell_margin": {"left": 400, "right": 400, "top": 200, "bottom": 200},
                    },
                }
            ],
            "expected_values": ["항목", "P27 표 예시", "PASS"],
            "validate": True,
        },
        "page_layout_numbering": {
            "template": template,
            "output": str(out / "page_layout_numbering.hwpx"),
            "page_layout": {
                "orientation": "portrait",
                "width": 59528,
                "height": 84188,
                "margins": {
                    "left": 8500,
                    "right": 8500,
                    "top": 7000,
                    "bottom": 7000,
                    "header": 4250,
                    "footer": 4250,
                    "gutter": 0,
                },
            },
            "page_numbering": {
                "start_page": 3,
                "page_starts_on": "BOTH",
                "hide_header": False,
                "hide_footer": False,
                "visible_header": True,
                "header_text": "Generated Header",
                "header_align": "CENTER",
                "visible_footer": True,
                "footer_text": "Page {page}",
                "footer_align": "CENTER",
            },
            "paragraphs": [{"text": "P27 page layout and numbering example"}],
            "expected_values": ["P27 page layout and numbering example", "Generated Header", "Page 3"],
            "validate": True,
        },
        "complex_section_table_chart": {
            "template": template,
            "output": str(out / "complex_section_table_chart.hwpx"),
            "sections": {"count": 3, "clear_body": True},
            "document_metadata": {
                "title": "Complex Section Table Chart Example",
                "creator": "office-analysis-engine",
                "subject": "HWPX direct writer complex example",
                "keywords": ["example", "section", "table", "chart"],
                "date": "2026-05-10",
            },
            "page_layouts": [
                {"section_index": 0, "orientation": "portrait", "width": 59528, "height": 84188},
                {"section_index": 1, "orientation": "landscape", "width": 84188, "height": 59528},
                {"section_index": 2, "orientation": "portrait", "width": 59528, "height": 84188},
            ],
            "page_numberings": [
                {
                    "section_index": 0,
                    "start_page": 1,
                    "visible_header": True,
                    "header_text": "Example Section 0 Header",
                    "visible_footer": True,
                    "footer_text": "Example Footer {page}",
                },
                {
                    "section_index": 1,
                    "start_page": 10,
                    "visible_header": True,
                    "header_text": "Example Section 1 Header",
                    "visible_footer": True,
                    "footer_text": "Example Footer {page}",
                },
                {
                    "section_index": 2,
                    "start_page": 20,
                    "visible_header": True,
                    "header_text": "Example Section 2 Header",
                    "visible_footer": True,
                    "footer_text": "Example Footer {page}",
                },
            ],
            "paragraphs": [
                {"text": "Example section zero body", "section_index": 0},
                {"text": "Example section one table body", "section_index": 1},
                {"text": "Example section two chart body", "section_index": 2},
            ],
            "tables": [
                {
                    "section_index": 1,
                    "rows": [
                        ["Field", "Value"],
                        ["section", "1"],
                        ["table", "PASS"],
                    ],
                }
            ],
            "images": [
                {
                    "mode": "chart_png",
                    "section_index": 2,
                    "chart_output": str(out / "example_section_chart.png"),
                    "image_entry": "BinData/example_section_chart.png",
                    "width": 17000,
                    "height": 11000,
                    "chart": {
                        "title": "Example Section Chart",
                        "series": [
                            {"label": "section", "value": 45},
                            {"label": "table", "value": 30},
                            {"label": "image", "value": 25},
                        ],
                    },
                }
            ],
            "preview_text": {"enabled": True, "include_metadata": True},
            "package_manifest": {"enabled": True},
            "expected_values": [
                "Complex Section Table Chart Example",
                "Example Section 0 Header",
                "Example Section 1 Header",
                "Example Section 2 Header",
                "Example Footer 1",
                "Example Footer 10",
                "Example Footer 20",
                "Example section one table body",
                "Example section two chart body",
                "table",
                "PASS",
            ],
            "validate": True,
        },
    }


def example_jobs(template: str, output_dir: str, include_experimental: bool = False) -> dict[str, dict[str, Any]]:
    """Return stable examples by default, with synthetic fallback examples opt-in."""
    jobs = _all_example_jobs(template, output_dir)
    paragraph_list = jobs.get("paragraph_list")
    if paragraph_list:
        paragraph_list.pop("style_definitions", None)
        paragraph_list["paragraphs"] = [{"text": str(value)} for value in paragraph_list.get("expected_values", [])]
    selected = set(STABLE_EXAMPLE_PROFILES)
    if include_experimental:
        selected.update(EXPERIMENTAL_EXAMPLE_PROFILES)
    return {name: job for name, job in jobs.items() if name in selected}


def write_example_jobs(out_dir: Path, template: str, include_experimental: bool = False) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = example_jobs(template, str(out_dir), include_experimental=include_experimental)
    files: dict[str, str] = {}
    for name, job in jobs.items():
        path = out_dir / f"{name}.json"
        write_json(path, job)
        files[name] = str(path)
    index = {
        "status": "PASS",
        "template": template,
        "out_dir": str(out_dir),
        "count": len(files),
        "stable_profiles": list(STABLE_EXAMPLE_PROFILES),
        "experimental_profiles": list(EXPERIMENTAL_EXAMPLE_PROFILES),
        "include_experimental": bool(include_experimental),
        "excluded_experimental_profiles": [] if include_experimental else list(EXPERIMENTAL_EXAMPLE_PROFILES),
        "files": files,
    }
    write_json(out_dir / "index.json", index)
    return index


__all__ = [
    "EXPERIMENTAL_EXAMPLE_PROFILES",
    "STABLE_EXAMPLE_PROFILES",
    "example_jobs",
    "write_example_jobs",
]
