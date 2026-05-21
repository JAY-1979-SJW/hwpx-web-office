"""Image insertion mode policy for HWPX compose jobs.

The direct writer has two image-placement families:

- visible_* modes clone an existing picture object from the template and are
  preferred when a template picture placeholder exists.
- synthetic modes generate picture XML directly and remain an explicit
  fallback for templates without a cloneable picture object.
"""

from __future__ import annotations

from hwpx_schema_rules import SUPPORTED_IMAGE_MODES, SYNTHETIC_IMAGE_MODES, VISIBLE_IMAGE_MODES


def is_visible_image_mode(mode: str) -> bool:
    return mode in VISIBLE_IMAGE_MODES


def is_synthetic_image_mode(mode: str) -> bool:
    return mode in SYNTHETIC_IMAGE_MODES


def image_step_name(mode: str) -> str:
    if is_visible_image_mode(mode):
        return "visible_image_insert"
    if mode == "chart_png":
        return "chart_png_insert"
    return "png_insert"


def normalize_image_mode(mode: str | None, *, prefer_visible: bool = False, chart: bool = False) -> str:
    if mode:
        return str(mode)
    if chart:
        return "visible_chart_png" if prefer_visible else "chart_png"
    return "visible_png_insert" if prefer_visible else "png_insert"


def visible_template_missing_warning(result: dict) -> list[dict]:
    if result.get("status") != "VISIBLE_PICTURE_TEMPLATE_NOT_FOUND":
        return []
    return [
        {
            "type": "VISIBLE_PICTURE_TEMPLATE_NOT_FOUND",
            "message": "visible image modes require a template that already contains a visible picture object",
            "result": result,
        }
    ]


__all__ = [
    "SUPPORTED_IMAGE_MODES",
    "SYNTHETIC_IMAGE_MODES",
    "VISIBLE_IMAGE_MODES",
    "image_step_name",
    "is_synthetic_image_mode",
    "is_visible_image_mode",
    "normalize_image_mode",
    "visible_template_missing_warning",
]
