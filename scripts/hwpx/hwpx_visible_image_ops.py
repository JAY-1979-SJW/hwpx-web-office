"""Visible image insertion orchestration for HWPX templates.

This module intentionally uses a template-first strategy. It does not invent a
new picture/control XML structure from scratch. Instead it adds/replaces a
BinData image entry and clones an existing visible picture object from the
template, rebinding the clone to the new image entry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hwpx_image_ops import add_bindata_image_data
from hwpx_element_factory import append_generated_picture
from hwpx_package import HwpxPackage
from hwpx_picture_ops import clone_picture_object, picture_inventory


def insert_visible_image_from_template(
    package: HwpxPackage,
    image_path: Path,
    picture_index: int = 0,
    image_entry: str = "BinData/visible_image001.png",
    manifest_id: str | None = None,
) -> dict[str, Any]:
    """Add an image entry and clone a visible picture object to reference it."""
    image_path = Path(image_path)
    before_inventory = picture_inventory(package)
    if before_inventory.get("status") != "PASS":
        return {
            "status": "VISIBLE_PICTURE_TEMPLATE_NOT_FOUND",
            "picture_index": picture_index,
            "image": str(image_path),
            "image_entry": image_entry,
            "picture_inventory_before": before_inventory,
            "warnings": [
                {
                    "type": "VISIBLE_PICTURE_TEMPLATE_REQUIRED",
                    "message": "A template with an existing visible picture/control object is required.",
                }
            ],
        }

    add_result = add_bindata_image_data(package.entries, image_path, image_entry)
    if add_result.get("status") != "IMAGE_BINDATA_ADD_PASS":
        return {
            "status": add_result.get("status", "IMAGE_BINDATA_ADD_FAIL"),
            "picture_index": picture_index,
            "image": str(image_path),
            "image_entry": image_entry,
            "picture_inventory_before": before_inventory,
            "add_result": add_result,
            "warnings": [],
        }

    clone_result = clone_picture_object(package, picture_index, image_entry, manifest_id)
    if clone_result.get("status") != "PICTURE_CLONE_REBIND_PASS":
        return {
            "status": clone_result.get("status", "PICTURE_CLONE_REBIND_FAIL"),
            "picture_index": picture_index,
            "image": str(image_path),
            "image_entry": image_entry,
            "picture_inventory_before": before_inventory,
            "add_result": add_result,
            "clone_result": clone_result,
            "warnings": [],
        }

    return {
        "status": "VISIBLE_IMAGE_INSERT_PASS",
        "picture_index": picture_index,
        "image": str(image_path),
        "image_entry": image_entry,
        "manifest_id": manifest_id,
        "picture_inventory_before": before_inventory,
        "add_result": add_result,
        "clone_result": clone_result,
        "picture_inventory_after": picture_inventory(package),
        "warnings": [],
    }


def insert_generated_png_picture(
    package: HwpxPackage,
    image_path: Path,
    image_entry: str = "BinData/generated_picture001.png",
    section_index: int = 0,
    width: int = 12000,
    height: int = 9000,
    manifest_id: str | None = None,
) -> dict[str, Any]:
    result = append_generated_picture(
        package,
        image_path,
        image_entry,
        section_index,
        width,
        height,
        manifest_id,
    )
    if result.get("status") != "GENERATED_PICTURE_APPEND_PASS":
        return result
    result["status"] = "GENERATED_PNG_PICTURE_INSERT_PASS"
    result["picture_inventory_after"] = picture_inventory(package)
    result["warnings"] = [
        {
            "type": "EXPERIMENTAL_SYNTHETIC_PICTURE_XML",
            "message": "The picture object is generated directly without a Hancom-authored picture template.",
        }
    ]
    return result
