"""Python SDK for standalone HWP -> HWPX conversion.

The SDK exposes a stable import surface for application code. It uses the
standalone converter engine and does not launch Hancom Office, COM automation,
GUI automation, or external converter programs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import hwp_to_hwpx_standalone as core

Extractor = Callable[[Path], dict[str, Any]]
ResultCallback = Callable[[dict[str, Any]], None]


class HwpToHwpxSdkError(ValueError):
    """Raised when SDK options or inputs are invalid before conversion."""


@dataclass(frozen=True)
class HwpToHwpxOptions:
    expected_texts: tuple[str, ...] = field(default_factory=tuple)
    strict_quality: bool = False
    existing_policy: str = "fail"
    fidelity_policy: str = "text"
    embed_original: bool = False
    pattern: str = "*.hwp"
    fail_fast: bool = False
    workers: int = 1
    log_path: str | None = None
    log_level: str = "INFO"
    audit_log_path: str | None = None
    audit_level: str = "standard"
    job_id: str | None = None

    @classmethod
    def from_values(  # ruff: ignore[too-many-arguments] -- 공개 SDK 팩토리, 각 인자가 dataclass 필드와 1:1 대응
        cls,
        *,
        expected_texts: list[str] | tuple[str, ...] | None = None,
        strict_quality: bool = False,
        existing_policy: str = "fail",
        fidelity_policy: str = "text",
        embed_original: bool = False,
        pattern: str = "*.hwp",
        fail_fast: bool = False,
        workers: int = 1,
        log_path: str | Path | None = None,
        log_level: str = "INFO",
        audit_log_path: str | Path | None = None,
        audit_level: str = "standard",
        job_id: str | None = None,
    ) -> HwpToHwpxOptions:
        return cls(
            expected_texts=tuple(expected_texts or ()),
            strict_quality=bool(strict_quality),
            existing_policy=str(existing_policy),
            fidelity_policy=str(fidelity_policy or "text"),
            embed_original=bool(embed_original),
            pattern=str(pattern or "*.hwp"),
            fail_fast=bool(fail_fast),
            workers=max(1, int(workers or 1)),
            log_path=str(log_path) if log_path else None,
            log_level=str(log_level or "INFO"),
            audit_log_path=str(audit_log_path) if audit_log_path else None,
            audit_level=str(audit_level or "standard"),
            job_id=str(job_id) if job_id else None,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["expected_texts"] = list(self.expected_texts)
        return data


def validate_options(options: HwpToHwpxOptions | None = None) -> HwpToHwpxOptions:
    resolved = options or HwpToHwpxOptions()
    if resolved.existing_policy not in core.EXISTING_POLICIES:
        raise HwpToHwpxSdkError(f"Invalid existing_policy: {resolved.existing_policy}")
    if resolved.fidelity_policy not in core.FIDELITY_POLICIES:
        raise HwpToHwpxSdkError(f"Invalid fidelity_policy: {resolved.fidelity_policy}")
    if resolved.audit_level not in core.AUDIT_LEVELS:
        raise HwpToHwpxSdkError(f"Invalid audit_level: {resolved.audit_level}")
    if not resolved.pattern.strip():
        raise HwpToHwpxSdkError("pattern must not be empty")
    if resolved.workers < 1:
        raise HwpToHwpxSdkError("workers must be 1 or greater")
    return resolved


class HwpToHwpxConverter:
    """Reusable converter facade for SDK consumers."""

    def __init__(self, options: HwpToHwpxOptions | None = None):
        self.options = validate_options(options)
        if self.options.log_path:
            core.configure_logging(Path(self.options.log_path), level=self.options.log_level)

    def with_options(self, options: HwpToHwpxOptions) -> HwpToHwpxConverter:
        return HwpToHwpxConverter(options)

    def convert_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        options: HwpToHwpxOptions | None = None,
        extractor: Extractor | None = None,
    ) -> dict[str, Any]:
        resolved = validate_options(options or self.options)
        if resolved.log_path:
            core.configure_logging(Path(resolved.log_path), level=resolved.log_level)
        kwargs: dict[str, Any] = {
            "expected_texts": list(resolved.expected_texts),
            "strict_quality": resolved.strict_quality,
            "existing_policy": resolved.existing_policy,
            "fidelity_policy": resolved.fidelity_policy,
            "embed_original": resolved.embed_original,
        }
        if extractor is not None:
            kwargs["extractor"] = extractor
        result = core.convert_hwp_to_hwpx(Path(input_path), Path(output_path), **kwargs)
        core.log_result("sdk_file_complete", result)
        if resolved.audit_log_path:
            core.write_audit_log(
                Path(resolved.audit_log_path),
                result,
                event="sdk_file_conversion",
                audit_level=resolved.audit_level,
            )
        return result

    def convert_directory(
        self,
        input_dir: str | Path,
        output_dir: str | Path,
        *,
        options: HwpToHwpxOptions | None = None,
        on_result: ResultCallback | None = None,
    ) -> dict[str, Any]:
        resolved = validate_options(options or self.options)
        if resolved.log_path:
            core.configure_logging(Path(resolved.log_path), level=resolved.log_level)
        report = core.convert_batch(
            Path(input_dir),
            Path(output_dir),
            expected_texts=list(resolved.expected_texts),
            strict_quality=resolved.strict_quality,
            pattern=resolved.pattern,
            existing_policy=resolved.existing_policy,
            fidelity_policy=resolved.fidelity_policy,
            embed_original=resolved.embed_original,
            fail_fast=resolved.fail_fast,
            workers=resolved.workers,
            job_id=resolved.job_id,
        )
        if on_result:
            for result in report.get("results", []):
                if isinstance(result, dict):
                    on_result(result)
        if resolved.audit_log_path:
            audit_path = Path(resolved.audit_log_path)
            core.write_audit_log(
                audit_path, report, event="sdk_batch_conversion", audit_level=resolved.audit_level
            )
            core.write_forensic_item_audit(audit_path, report, audit_level=resolved.audit_level)
        return report

    def plan_directory(
        self,
        input_dir: str | Path,
        output_dir: str | Path,
        *,
        options: HwpToHwpxOptions | None = None,
    ) -> dict[str, Any]:
        resolved = validate_options(options or self.options)
        report = core.build_batch_plan(
            Path(input_dir),
            Path(output_dir),
            pattern=resolved.pattern,
            existing_policy=resolved.existing_policy,
        )
        if resolved.audit_log_path:
            core.write_audit_log(
                Path(resolved.audit_log_path),
                report,
                event="sdk_batch_plan",
                audit_level=resolved.audit_level,
            )
        return report

    def convert_auto(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        options: HwpToHwpxOptions | None = None,
    ) -> dict[str, Any]:
        source = Path(input_path)
        if source.is_dir():
            return self.convert_directory(source, output_path, options=options)
        return self.convert_file(source, output_path, options=options)

    def write_reports(
        self,
        report: dict[str, Any],
        *,
        json_path: str | Path | None = None,
        csv_path: str | Path | None = None,
    ) -> None:
        core.write_report(Path(json_path) if json_path else None, report)
        core.write_report_csv(Path(csv_path) if csv_path else None, report)
        core.LOGGER.info(
            "sdk_reports_written json_path=%s csv_path=%s status=%s",
            json_path,
            csv_path,
            report.get("status"),
        )


def convert_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    options: HwpToHwpxOptions | None = None,
    extractor: Extractor | None = None,
) -> dict[str, Any]:
    return HwpToHwpxConverter(options).convert_file(input_path, output_path, extractor=extractor)


def convert_directory(
    input_dir: str | Path,
    output_dir: str | Path,
    *,
    options: HwpToHwpxOptions | None = None,
    on_result: ResultCallback | None = None,
) -> dict[str, Any]:
    return HwpToHwpxConverter(options).convert_directory(input_dir, output_dir, on_result=on_result)


def plan_directory(
    input_dir: str | Path,
    output_dir: str | Path,
    *,
    options: HwpToHwpxOptions | None = None,
) -> dict[str, Any]:
    return HwpToHwpxConverter(options).plan_directory(input_dir, output_dir)


def convert_auto(
    input_path: str | Path,
    output_path: str | Path,
    *,
    options: HwpToHwpxOptions | None = None,
) -> dict[str, Any]:
    return HwpToHwpxConverter(options).convert_auto(input_path, output_path)


__all__ = [
    "HwpToHwpxConverter",
    "HwpToHwpxOptions",
    "HwpToHwpxSdkError",
    "convert_auto",
    "convert_directory",
    "convert_file",
    "plan_directory",
    "validate_options",
]
