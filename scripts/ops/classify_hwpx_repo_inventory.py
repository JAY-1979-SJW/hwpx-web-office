"""Repo-wide inventory classification for HWPX form auto-fill separation planning."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_inventory_classification"

PASS_VERDICT = "PASS_HWPX_REPO_INVENTORY_CLASSIFICATION"
FAIL_VERDICT = "FAIL_HWPX_REPO_INVENTORY_CLASSIFICATION"

CATEGORIES = {
    "ACTIVE_AUTOFILL",
    "ACTIVE_HWPX_CORE",
    "FRONTEND_VIEWER",
    "AUDIT_GATE",
    "TEST_ONLY",
    "TEST_FIXTURE",
    "REPORT_DOC",
    "CONFIG_BUILD",
    "LEGACY_EXPERIMENT",
    "UNKNOWN_REVIEW_REQUIRED",
}
ZONES = {
    "input_parse",
    "review_approval",
    "writer_readback",
    "download_export",
    "batch_api_browser",
    "closeout_security",
    "browser_ui",
    "hwpx_core",
    "docs_reports",
    "test_support",
    "unassigned",
}

ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/][^\s\"']*|/(home|tmp|var|Users)/[^\s\"']*)")
# (?![-\w.]) — ".hwpx" 뒤에 하이픈/글자/점이 더 이어지면 실제 hwpx 문서
# 확장자가 아니라 "Dockerfile.hwpx-ro-view" 같은 코드 파일명의 일부다.
# \b 만으로는 하이픈도 단어 경계로 쳐서 이런 파일을 오탐(raw filename leak)
# 처리했다 — classify_repo() 가 저장소 자체를 못 도는 실제 회귀였다(2026-09-28).
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx(?![-\w.])", re.IGNORECASE)
DATE_SEGMENT_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)

TEXT_SUFFIXES = {
    ".bat",
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".mjs",
    ".py",
    ".sql",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yml",
    ".yaml",
}


def _run_git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _hash_path(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def safe_path(path: str) -> str:
    path = ABS_PATH_RE.sub("<abs-path>", path.replace("\\", "/"))
    parts = []
    for part in path.split("/"):
        dated = DATE_SEGMENT_RE.sub("<date>", part)
        if part.lower().endswith(".hwpx"):
            parts.append("<date>-<hwpx-file>" if "<date>" in dated else "<hwpx-file>")
        else:
            parts.append(dated)
    path = "/".join(parts)
    path = PII_RE.sub("<masked>", path)
    return path


def _read_text_sample(path: str, max_bytes: int = 512_000) -> str:
    file_path = ROOT / path
    if file_path.suffix.lower() not in TEXT_SUFFIXES:
        return ""
    try:
        with file_path.open("rb") as handle:
            raw = handle.read(max_bytes)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")


def classify_path(path: str) -> tuple[str, str, str]:
    lower = path.lower()
    name = Path(path).name.lower()

    if lower.startswith(".githooks/"):
        return "CONFIG_BUILD", "unassigned", "keep_git_hooks"
    # .claude/ 는 프로젝트 도구 설정(훅 등록 등)이다 — .githooks 와 같은 성격.
    if lower.startswith(".claude/"):
        return "CONFIG_BUILD", "unassigned", "keep_claude_config"
    # .github/ 는 CI 워크플로 등 저장소 빌드/자동화 설정 — 같은 성격.
    if lower.startswith(".github/"):
        return "CONFIG_BUILD", "unassigned", "keep_github_config"
    # 여러 스크립트(hwpx_api.py 등)의 기본 스모크 템플릿 인자값 — 저장소
    # 루트에 있어야 하는 테스트 자재.
    if path == "smoke-test.hwpx":
        return "TEST_FIXTURE", "test_support", "keep_smoke_template"
    if path in {".gitignore", "CLAUDE.md"} or name in {
        "package.json",
        "package-lock.json",
        "pyproject.toml",
        "requirements.txt",
    }:
        return "CONFIG_BUILD", "unassigned", "keep_root_config"
    if lower.startswith("data/reports/"):
        return "REPORT_DOC", "docs_reports", "keep_pii_safe_report"
    if lower.startswith("docs/"):
        return "REPORT_DOC", "docs_reports", "keep_documentation"
    if lower.startswith("tests/fixtures/"):
        return "TEST_FIXTURE", "test_support", "keep_test_fixture"
    if lower.startswith("tests/"):
        return "TEST_ONLY", _infer_zone(path), "keep_test"
    if lower.startswith("frontend/"):
        if "form_autofill" in lower:
            return "ACTIVE_AUTOFILL", "batch_api_browser", "keep_active_autofill_frontend"
        return "FRONTEND_VIEWER", "browser_ui", "keep_frontend_viewer"
    if lower.startswith("scripts/ops/"):
        # scripts/ops/hooks/ 는 게이트를 자동 집행하는 감리 기반시설이다
        # (편집 시점에 게이트를 돌려 규칙 위반을 즉시 잡는다) — 이름이
        # `gate_` 로 시작하지 않아도 성격은 AUDIT_GATE 다.
        # `build_` 도 같은 성격이다 - 기존 build_hwpx_repo_separation_owner_review.py·
        # build_hwpx_repo_separation_execution_plan_draft.py·
        # build_hwpx_repo_manifest_promotion_candidates.py 전부 이 규칙으로 새 파일이었다면
        # 똑같이 막혔을 선례(감사 산출물을 read-only로 만드는 스크립트) - 토큰 목록 공백이었다.
        if any(
            token in lower
            for token in (
                "audit_",
                "gate_",
                "verify_",
                "install_",
                "classify_",
                "build_",
                "dashboard",
                "history",
                "candidate_scan",
                "candidate_upload",
                "upload_hwpx_candidates",
                "/hooks/",
            )
        ):
            return "AUDIT_GATE", "closeout_security", "keep_gate_audit"
        if "hwpx_form_autofill" in lower or "form_auto_fill" in lower:
            return "ACTIVE_AUTOFILL", _infer_zone(path), "keep_active_autofill_ops"
        return "LEGACY_EXPERIMENT", "unassigned", "review_legacy_ops"
    if lower.startswith("scripts/hwpx/pipeline/"):
        if any(
            token in lower
            for token in (
                "form_auto_fill",
                "form_field_mapper",
                "review_panel",
                "approval_gate",
                "download_review",
                "final_export",
                "readback",
                "upload_document_parser",
            )
        ):
            return "ACTIVE_AUTOFILL", _infer_zone(path), "keep_active_autofill_pipeline"
        return "ACTIVE_HWPX_CORE", "hwpx_core", "keep_hwpx_pipeline_core"
    if lower.startswith("scripts/hwpx/"):
        if "/test_" in lower or name.startswith("test_"):
            return "TEST_ONLY", "test_support", "keep_script_test"
        if any(
            part in lower
            for part in ("/parser/", "/recognition_corpus/", "/source_extractor/", "/web_office/")
        ):
            return "ACTIVE_HWPX_CORE", "hwpx_core", "keep_hwpx_core"
        if any(token in lower for token in ("hancom", "hwp_to_hwpx", "converter", "native_com")):
            return "LEGACY_EXPERIMENT", "hwpx_core", "review_hancom_or_converter_line"
        return "ACTIVE_HWPX_CORE", "hwpx_core", "keep_hwpx_core"
    if lower.startswith("scripts/hwp-worker/"):
        # 한컴 COM 변환 워커(HWP→HWPX) — 부모 저장소서 복원한 컨버터 라인.
        return "LEGACY_EXPERIMENT", "hwpx_core", "review_hancom_or_converter_line"
    if lower.startswith("scripts/local/") or lower.startswith("tmp/"):
        return "LEGACY_EXPERIMENT", "unassigned", "review_legacy_experiment"
    if lower.startswith("scripts/"):
        return "LEGACY_EXPERIMENT", "unassigned", "review_general_script"
    return "UNKNOWN_REVIEW_REQUIRED", "unassigned", "manual_review_required"


def _infer_zone(path: str) -> str:
    lower = path.lower()
    if "web_office" in lower:
        return "test_support"
    if any(
        token in lower
        for token in (
            "repo_separation",
            "repo_inventory",
            "detailed_separation",
            "new_file_classification",
            "app_structure_drift",
            "monitor_structure_drift",
        )
    ):
        return "closeout_security"
    if any(
        token in lower
        for token in (
            "existing_file_classification",
            "module_log_contract",
            "module_audits",
            "persistent_gates",
            "fail_fast",
            "zone_gates",
        )
    ):
        return "closeout_security"
    if any(
        token in lower
        for token in (
            "api_route",
            "frontend_contract",
            "browser_smoke",
            "browser_batch",
            "ui_connect",
            "module_communication",
        )
    ):
        return "batch_api_browser"
    if any(
        token in lower
        for token in ("e2e_smoke", "real_like_sandbox_batch", "api_browser", "api_batch")
    ):
        return "batch_api_browser"
    if any(
        token in lower
        for token in ("field_mapping", "field_mapper", "parser", "preflight", "upload_document")
    ):
        return "input_parse"
    if any(
        token in lower
        for token in (
            "field_catalog",
            "index_and_recommend",
            "type_classification",
            "construction_work_design",
        )
    ):
        return "input_parse"
    if any(token in lower for token in ("review_panel", "approval_gate", "human_approval")):
        return "review_approval"
    if any(
        token in lower
        for token in ("writer_sandbox", "readback", "write_sandbox", "rwedit", "backend_rwedit")
    ):
        return "writer_readback"
    if any(token in lower for token in ("download_review", "final_export")):
        return "download_export"
    if any(token in lower for token in ("api_batch", "browser_batch", "api_browser", "real_like")):
        return "batch_api_browser"
    if any(
        token in lower
        for token in (
            "closeout",
            "security",
            "audit",
            "gate",
            "dashboard",
            "history",
            "deploy_verifier",
            "server_deploy",
        )
    ):
        return "closeout_security"
    return "unassigned"


def _risk_tags(path: str, text: str) -> list[str]:
    lower_path = path.lower()
    lower_text = text.lower()
    combined = f"{lower_path}\n{lower_text}"
    risks = []
    if any(
        token in combined
        for token in ("production write", "write-production", "production_adapters")
    ):
        risks.append("PRODUCTION_WRITE_REVIEW")
    if any(
        token in combined
        for token in ("overwrite-source", "source overwrite", "source_path", "output_path")
    ):
        risks.append("SOURCE_MUTATION_REVIEW")
    if any(token in combined for token in ("openai", "anthropic", "chatcompletion", "gemini")):
        risks.append("AI_API_REVIEW")
    if any(token in combined for token in ("pytesseract", "easyocr", "paddleocr", "ocr")):
        risks.append("OCR_REVIEW")
    if any(token in combined for token in ("hancom", "hwpctrl", "native_com")):
        risks.append("HANCOM_DEPENDENCY_REVIEW")
    if ABS_PATH_RE.search(text):
        risks.append("RAW_PATH_PATTERN_REVIEW")
    if RAW_FILENAME_RE.search(text):
        risks.append("RAW_FILENAME_PATTERN_REVIEW")
    if PII_RE.search(text):
        risks.append("PII_PATTERN_REVIEW")
    if "real user file" in combined or "real_user" in combined:
        risks.append("REAL_USER_FILE_REVIEW")
    return sorted(set(risks))


def _safety_class(category: str, risk_tags: list[str]) -> str:
    if category in {"LEGACY_EXPERIMENT", "UNKNOWN_REVIEW_REQUIRED"}:
        return "REVIEW_REQUIRED"
    if any(
        tag in risk_tags
        for tag in ("PRODUCTION_WRITE_REVIEW", "SOURCE_MUTATION_REVIEW", "PII_PATTERN_REVIEW")
    ):
        return "HIGH_REVIEW"
    if risk_tags:
        return "STANDARD_REVIEW"
    return "LOW_REVIEW"


def classify_file(path: str) -> dict[str, Any]:
    category, zone, separation = classify_path(path)
    text = _read_text_sample(path)
    risks = _risk_tags(path, text)
    file_path = ROOT / path
    try:
        size = file_path.stat().st_size
    except OSError:
        size = 0
    return {
        "pathHash": _hash_path(path),
        "safePath": safe_path(path),
        "category": category,
        "zone": zone,
        "separationPlan": separation,
        "safetyClass": _safety_class(category, risks),
        "riskTags": risks,
        "suffix": file_path.suffix.lower() or "<none>",
        "sizeBytes": size,
    }


def classify_repo(report_dir: Path = REPORT_DIR) -> dict[str, Any]:
    paths = _run_git_ls_files()
    files = [classify_file(path) for path in paths]
    category_counts = Counter(item["category"] for item in files)
    zone_counts = Counter(item["zone"] for item in files)
    safety_counts = Counter(item["safetyClass"] for item in files)
    risk_counts: Counter[str] = Counter()
    for item in files:
        risk_counts.update(item["riskTags"])
    unknown = [item for item in files if item["category"] == "UNKNOWN_REVIEW_REQUIRED"]
    legacy = [item for item in files if item["category"] == "LEGACY_EXPERIMENT"]
    payload = {
        "schemaVersion": "hwpx_repo_inventory_classification_v1",
        "verdict": PASS_VERDICT,
        "baselineHead": _git_head(),
        "scope": "tracked_files_only",
        "summary": {
            "totalFiles": len(files),
            "categories": dict(sorted(category_counts.items())),
            "zones": dict(sorted(zone_counts.items())),
            "safetyClasses": dict(sorted(safety_counts.items())),
            "riskTags": dict(sorted(risk_counts.items())),
            "legacyExperimentFiles": len(legacy),
            "unknownReviewRequiredFiles": len(unknown),
        },
        "files": files,
        "separationRecommendations": {
            "phase1NoMove": "classification only; do not move or delete files",
            "phase2Plan": "review LEGACY_EXPERIMENT and UNKNOWN_REVIEW_REQUIRED before any split",
            "phase3ActiveLine": "protect ACTIVE_AUTOFILL, AUDIT_GATE, and FRONTEND_VIEWER with fail-fast gates",
            "phase4ArchiveCandidate": "archive only after import and test impact review",
        },
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
        },
        "warnings": [
            "WARN_CLASSIFICATION_ONLY_NO_FILE_MOVE",
            "WARN_TRACKED_FILES_ONLY",
            "WARN_REVIEW_REQUIRED_BEFORE_SPLIT",
        ],
    }
    _write_reports(report_dir, payload)
    return payload


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return result.stdout.strip()


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "repo_inventory.json", payload)
    _safe_write(report_dir / "repo_inventory_files.json", payload["files"])
    _safe_write(report_dir / "repo_inventory_summary.json", payload["summary"])
    lines = [
        "# HWPX Repo Inventory Classification",
        "",
        f"- verdict: {payload['verdict']}",
        f"- baseline: {payload['baselineHead']}",
        f"- scope: {payload['scope']}",
        f"- total files: {payload['summary']['totalFiles']}",
        f"- legacy experiment files: {payload['summary']['legacyExperimentFiles']}",
        f"- unknown review required files: {payload['summary']['unknownReviewRequiredFiles']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Categories",
    ]
    for name, count in payload["summary"]["categories"].items():
        lines.append(f"- {name}: {count}")
    lines.extend(["", "## Zones"])
    for name, count in payload["summary"]["zones"].items():
        lines.append(f"- {name}: {count}")
    lines.extend(["", "## Next Separation"])
    for value in payload["separationRecommendations"].values():
        lines.append(f"- {value}")
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError("unsafe inventory markdown")
    (report_dir / "repo_inventory_summary.md").write_text(text, encoding="utf-8")


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"unsafe inventory payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    payload = classify_repo(report_dir=Path(args.report_dir))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
