"""Style and layout normalization for direct HWPX generation.

This module intentionally avoids creating new HWPX style definitions. It maps
job-level style hints to references and dimensions that the current generated
paragraph/table/picture builders can apply without mutating the document header.
"""

from __future__ import annotations

from hwpx_schema_rules import normalize_image_layout, normalize_paragraph_style, normalize_table_style


__all__ = ["normalize_image_layout", "normalize_paragraph_style", "normalize_table_style"]
