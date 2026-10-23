"""Object facade for building HWPX compose jobs.

The builder does not mutate HWPX packages directly. It creates the same
declarative job dictionaries consumed by ``hwpx_composer`` so the low-level
editing modules remain the single implementation path.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from hwpx_composer import compose_hwpx
from hwpx_image_policy import normalize_image_mode
from hwpx_package import write_json


def _page_numbering_expected_values(spec: dict[str, Any]) -> list[str]:
    values: list[str] = []
    start_page = spec.get("start_page", 1)
    if not isinstance(start_page, int) or start_page < 1:
        start_page = 1
    if spec.get("visible_header") and isinstance(spec.get("header_text"), str):
        values.append(spec["header_text"].replace("{page}", str(start_page)))
    if spec.get("visible_footer") and isinstance(spec.get("footer_text"), str):
        values.append(spec["footer_text"].replace("{page}", str(start_page)))
    return values


class DocumentBuilder:
    """Small fluent API for assembling HWPX compose jobs."""

    def __init__(
        self, template: str | Path | None = None, output: str | Path | None = None
    ) -> None:
        self._job: dict[str, Any] = {
            "validate": True,
        }
        if template is not None:
            self.template(template)
        if output is not None:
            self.output(output)

    def template(self, path: str | Path) -> DocumentBuilder:
        self._job["template"] = str(path)
        return self

    def output(self, path: str | Path) -> DocumentBuilder:
        self._job["output"] = str(path)
        return self

    def validate(self, enabled: bool = True) -> DocumentBuilder:
        self._job["validate"] = bool(enabled)
        return self

    def mapping(self, values: dict[str, Any]) -> DocumentBuilder:
        self._job.setdefault("mapping", {}).update({
            str(key): str(value) for key, value in values.items()
        })
        return self

    def metadata(self, **values: Any) -> DocumentBuilder:
        metadata = self._job.setdefault("document_metadata", {})
        for key, value in values.items():
            if value is not None:
                metadata[str(key)] = value
        return self

    def package_manifest(self, enabled: bool = True) -> DocumentBuilder:
        self._job["package_manifest"] = {"enabled": bool(enabled)}
        return self

    def write_audit_log(
        self, path: str | Path | None = None, enabled: bool = True
    ) -> DocumentBuilder:
        self._job["write_audit_log"] = {"enabled": bool(enabled)}
        if path is not None:
            self._job["write_audit_log"]["path"] = str(path)
        return self

    def preview_text(
        self, enabled: bool = True, include_metadata: bool = True, max_chars: int = 4000
    ) -> DocumentBuilder:
        self._job["preview_text"] = {
            "enabled": bool(enabled),
            "include_metadata": bool(include_metadata),
            "max_chars": int(max_chars),
        }
        return self

    def sections(self, count: int, clear_body: bool = True) -> DocumentBuilder:
        self._job["sections"] = {
            "count": int(count),
            "clear_body": bool(clear_body),
        }
        return self

    def expect(self, *values: Any) -> DocumentBuilder:
        self._job.setdefault("expected_values", []).extend(str(value) for value in values)
        return self

    def style_definitions(self, definitions: dict[str, Any]) -> DocumentBuilder:
        current = self._job.setdefault("style_definitions", {})
        for group, values in definitions.items():
            if isinstance(values, dict):
                current.setdefault(group, {}).update(values)
            else:
                current[group] = values
        return self

    def char_style(self, name: str, **style: Any) -> DocumentBuilder:
        self._job.setdefault("style_definitions", {}).setdefault("char_styles", {})[name] = style
        return self

    def paragraph_style(self, name: str, **style: Any) -> DocumentBuilder:
        self._job.setdefault("style_definitions", {}).setdefault("para_styles", {})[name] = style
        return self

    def border_fill(self, name: str, **style: Any) -> DocumentBuilder:
        self._job.setdefault("style_definitions", {}).setdefault("border_fills", {})[name] = style
        return self

    def list_style(self, name: str, **style: Any) -> DocumentBuilder:
        self._job.setdefault("style_definitions", {}).setdefault("list_styles", {})[name] = style
        return self

    def page_layout(self, **layout: Any) -> DocumentBuilder:
        self._job["page_layout"] = layout
        return self

    def section_page_layout(self, section_index: int, **layout: Any) -> DocumentBuilder:
        spec = dict(layout)
        spec["section_index"] = int(section_index)
        self._job.setdefault("page_layouts", []).append(spec)
        return self

    def page_numbering(self, **numbering: Any) -> DocumentBuilder:
        self._job["page_numbering"] = numbering
        return self

    def section_page_numbering(self, section_index: int, **numbering: Any) -> DocumentBuilder:
        spec = dict(numbering)
        spec["section_index"] = int(section_index)
        self._job.setdefault("page_numberings", []).append(spec)
        self.expect(*_page_numbering_expected_values(spec))
        return self

    def page_number_mode(self, mode: str) -> DocumentBuilder:
        numbering = self._job.setdefault("page_numbering", {})
        numbering["page_number_mode"] = str(mode)
        return self

    def native_dynamic_page_numbers(self) -> DocumentBuilder:
        return self.page_number_mode("NATIVE_DYNAMIC")

    def visible_footer(
        self,
        text: str = "Page {page}",
        align: str = "CENTER",
        section_index: int = 0,
        start_page: int | None = None,
    ) -> DocumentBuilder:
        numbering = self._job.setdefault("page_numbering", {})
        numbering["visible_footer"] = True
        numbering["footer_text"] = str(text)
        numbering["footer_align"] = str(align)
        numbering["section_index"] = int(section_index)
        if start_page is not None:
            numbering["start_page"] = int(start_page)
        rendered = str(text).replace("{page}", str(numbering.get("start_page", 1)))
        self.expect(rendered)
        return self

    def section_visible_footer(
        self,
        section_index: int,
        text: str = "Page {page}",
        align: str = "CENTER",
        start_page: int | None = None,
    ) -> DocumentBuilder:
        spec: dict[str, Any] = {
            "section_index": int(section_index),
            "visible_footer": True,
            "footer_text": str(text),
            "footer_align": str(align),
        }
        if start_page is not None:
            spec["start_page"] = int(start_page)
        self._job.setdefault("page_numberings", []).append(spec)
        self.expect(*_page_numbering_expected_values(spec))
        return self

    def visible_header(
        self,
        text: str,
        align: str = "CENTER",
        section_index: int = 0,
        start_page: int | None = None,
    ) -> DocumentBuilder:
        numbering = self._job.setdefault("page_numbering", {})
        numbering["visible_header"] = True
        numbering["header_text"] = str(text)
        numbering["header_align"] = str(align)
        numbering["section_index"] = int(section_index)
        if start_page is not None:
            numbering["start_page"] = int(start_page)
        rendered = str(text).replace("{page}", str(numbering.get("start_page", 1)))
        self.expect(rendered)
        return self

    def section_visible_header(
        self,
        section_index: int,
        text: str,
        align: str = "CENTER",
        start_page: int | None = None,
    ) -> DocumentBuilder:
        spec: dict[str, Any] = {
            "section_index": int(section_index),
            "visible_header": True,
            "header_text": str(text),
            "header_align": str(align),
        }
        if start_page is not None:
            spec["start_page"] = int(start_page)
        self._job.setdefault("page_numberings", []).append(spec)
        self.expect(*_page_numbering_expected_values(spec))
        return self

    def paragraph(
        self, text: str, style: dict[str, Any] | None = None, section_index: int = 0
    ) -> DocumentBuilder:
        item: dict[str, Any] = {
            "text": str(text),
            "section_index": int(section_index),
        }
        if style:
            item["style"] = style
        self._job.setdefault("paragraphs", []).append(item)
        self.expect(text)
        return self

    def table(
        self,
        rows: list[list[Any]],
        style: dict[str, Any] | None = None,
        section_index: int = 0,
    ) -> DocumentBuilder:
        item: dict[str, Any] = {
            "rows": [[str(cell) for cell in row] for row in rows],
            "section_index": int(section_index),
        }
        if style:
            item["style"] = style
        self._job.setdefault("tables", []).append(item)
        self.expect(*(cell for row in item["rows"] for cell in row))
        return self

    def table_operation(self, operation: dict[str, Any]) -> DocumentBuilder:
        self._job.setdefault("table_operations", []).append(operation)
        return self

    def image_png(  # ruff: ignore[too-many-arguments] - 공개 fluent 빌더 API(chart_png과 동일 사유), 시그니처 변경 보류
        self,
        path: str | Path,
        width: int | None = None,
        height: int | None = None,
        section_index: int = 0,
        image_entry: str | None = None,
        manifest_id: str | None = None,
        prefer_visible: bool = False,
        picture_index: int = 0,
        mode: str | None = None,
    ) -> DocumentBuilder:
        image: dict[str, Any] = {
            "mode": normalize_image_mode(mode, prefer_visible=prefer_visible, chart=False),
            "path": str(path),
            "section_index": int(section_index),
        }
        if width is not None:
            image["width"] = int(width)
        if height is not None:
            image["height"] = int(height)
        if image_entry:
            image["image_entry"] = image_entry
        if manifest_id:
            image["manifest_id"] = manifest_id
        if image["mode"].startswith("visible_"):
            image["picture_index"] = int(picture_index)
        self._job.setdefault("images", []).append(image)
        return self

    def visible_image_png(
        self,
        path: str | Path,
        width: int | None = None,
        height: int | None = None,
        picture_index: int = 0,
        image_entry: str | None = None,
        manifest_id: str | None = None,
    ) -> DocumentBuilder:
        return self.image_png(
            path,
            width=width,
            height=height,
            image_entry=image_entry,
            manifest_id=manifest_id,
            prefer_visible=True,
            picture_index=picture_index,
        )

    def synthetic_image_png(
        self,
        path: str | Path,
        width: int | None = None,
        height: int | None = None,
        section_index: int = 0,
        image_entry: str | None = None,
        manifest_id: str | None = None,
    ) -> DocumentBuilder:
        return self.image_png(
            path,
            width=width,
            height=height,
            section_index=section_index,
            image_entry=image_entry,
            manifest_id=manifest_id,
            mode="png_insert",
        )

    def chart_png(  # ruff: ignore[too-many-arguments] -- 공개 fluent-builder API, image_png과 동일 사유로 시그니처 유지
        self,
        chart: dict[str, Any],
        width: int | None = None,
        height: int | None = None,
        section_index: int = 0,
        image_entry: str | None = None,
        chart_output: str | Path | None = None,
        manifest_id: str | None = None,
        prefer_visible: bool = False,
        picture_index: int = 0,
        mode: str | None = None,
    ) -> DocumentBuilder:
        image: dict[str, Any] = {
            "mode": normalize_image_mode(mode, prefer_visible=prefer_visible, chart=True),
            "chart": chart,
            "section_index": int(section_index),
        }
        if width is not None:
            image["width"] = int(width)
        if height is not None:
            image["height"] = int(height)
        if image_entry:
            image["image_entry"] = image_entry
        if chart_output:
            image["chart_output"] = str(chart_output)
        if manifest_id:
            image["manifest_id"] = manifest_id
        if image["mode"].startswith("visible_"):
            image["picture_index"] = int(picture_index)
        self._job.setdefault("images", []).append(image)
        return self

    def visible_chart_png(  # ruff: ignore[too-many-arguments] -- chart_png()와 파라미터를 그대로 거울처럼 맞춘 fluent builder, 외부 호출부 있어 변경 보류
        self,
        chart: dict[str, Any],
        width: int | None = None,
        height: int | None = None,
        picture_index: int = 0,
        image_entry: str | None = None,
        chart_output: str | Path | None = None,
        manifest_id: str | None = None,
    ) -> DocumentBuilder:
        return self.chart_png(
            chart,
            width=width,
            height=height,
            image_entry=image_entry,
            chart_output=chart_output,
            manifest_id=manifest_id,
            prefer_visible=True,
            picture_index=picture_index,
        )

    def synthetic_chart_png(  # ruff: ignore[too-many-arguments] -- chart_png()와 파라미터를 그대로 거울처럼 맞춘 fluent builder, 외부 호출부 있어 변경 보류
        self,
        chart: dict[str, Any],
        width: int | None = None,
        height: int | None = None,
        section_index: int = 0,
        image_entry: str | None = None,
        chart_output: str | Path | None = None,
        manifest_id: str | None = None,
    ) -> DocumentBuilder:
        return self.chart_png(
            chart,
            width=width,
            height=height,
            section_index=section_index,
            image_entry=image_entry,
            chart_output=chart_output,
            manifest_id=manifest_id,
            mode="chart_png",
        )

    def to_job(self) -> dict[str, Any]:
        return deepcopy(self._job)

    def write_job(self, path: str | Path) -> dict[str, Any]:
        job = self.to_job()
        write_json(Path(path), job)
        return job

    def compose(
        self, output: str | Path | None = None, report_json: str | Path | None = None
    ) -> dict[str, Any]:
        result = compose_hwpx(self.to_job(), Path(output) if output else None)
        if report_json:
            write_json(Path(report_json), result)
        return result


def document(
    template: str | Path | None = None, output: str | Path | None = None
) -> DocumentBuilder:
    """Return a new HWPX document builder."""
    return DocumentBuilder(template, output)


__all__ = ["DocumentBuilder", "document"]
