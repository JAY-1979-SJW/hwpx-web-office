"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-PREVIEW-01 준공검사.

read-only toolbar preview 의 정적·동적 검증:
  - payload additive (styles.charPrDefs) 노출 정합
  - 기존 payload key 보존
  - WebOfficeFormatPreview 컴포넌트 read-only (command/writer 호출 0)
  - dc9e6ad ApplyFormat 잠금 자재 무수정
"""
from __future__ import annotations
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))

PREVIEW_TSX = (PR / "frontend/web_office_viewer/components/"
                      "WebOfficeFormatPreview.tsx")
RENDER_PAYLOAD = (PR / "scripts/hwpx/web_office/render_payload.py")
BASELINE_COMMIT = "b992ad6"  # 중첩표 읽기/쓰기 대칭 준공 후 갱신 (f119308 → b992ad6)

# dc9e6ad ApplyFormat closeout 의 시공 자재 — 본 공정에서 무수정
# WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01: para_edit_state /
# para_edit_command 는 applyFormatToSelection helper + _applyFormat
# in-memory 적용 추가로 본 LOCKED 에서 제거됨.
LOCKED_FILES_VS_BASELINE = [
    "scripts/hwpx/hwpx_paragraph_ops.py",
    "scripts/hwpx/hwpx_edit_tool.py",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/charpr_inventory.py",
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]

# preview 컴포넌트가 절대 호출/import 해선 안 되는 패턴
PREVIEW_FORBIDDEN_PATTERNS = [
    # 실제 호출 패턴만 차단 (docstring 의 단순 언급은 허용).
    r"makeApplyFormatCommand\(",
    r"applyFormatToSelection\(",
    r"save_paragraph_edits\(",
    r"apply_paragraph_edits_plan\(",
    r"create_hwpx_document\(",
    r"write_package\(",
    r"\.write_xml\(",
    r"def\s+create_char_pr\b",
    r"package\.entries\[[^\]]*header\.xml[^\]]*\]\s*=",
    # commandLog mutation 도 차단 (append-only 자체를 건드리지 않음).
    r"commandLog\.push\(",
    r"commandLog\s*=",
]
PREVIEW_REQUIRED_PATTERNS = [
    r"export\s+function\s+WebOfficeFormatPreview\(",
    r"charPrDefs",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01:
    # 컴포넌트가 enableApplyCommand 토글 + data-applies-format 속성을
    # 둘 다 지원하면 read-only 보존 + command-mode 진입이 가능.
    r"data-applies-format",
    r"data-read-only",
    r"export\s+(type|interface)\s+CharPrDef",
    r"fontName",
    r"fontSizePt",
    r"textColor",
    r"bold",
    r"italic",
    r"underline",
]
RENDER_REQUIRED_PATTERNS = [
    r"char_pr_defs",
    r'"styles"',
    r"charPrDefs",
    r"WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-PREVIEW-01",
]
# 기존 payload key 보존 검증 — 다음 키들이 build_render_payload 결과에
# 여전히 포함되어야 한다.
PAYLOAD_REQUIRED_KEYS = (
    "schemaVersion", "engineVersion", "payloadVersion",
    "documentId", "sourceRef", "editable", "pages", "blocks",
    "tables", "objects", "warnings",
)

FORBIDDEN_AUDIT_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
    r"\.write_xml\(",
]


def _check_preview_static() -> list[dict]:
    findings: list[dict] = []
    if not PREVIEW_TSX.is_file():
        findings.append({"code": "PREVIEW_FILE_MISSING",
                          "level": "FAIL",
                          "detail": str(PREVIEW_TSX)})
        return findings
    src = PREVIEW_TSX.read_text(encoding="utf-8")
    for pat in PREVIEW_REQUIRED_PATTERNS:
        if not re.search(pat, src):
            findings.append({"code": "PREVIEW_PATTERN_MISSING",
                              "level": "FAIL", "detail": pat})
    for pat in PREVIEW_FORBIDDEN_PATTERNS:
        if re.search(pat, src):
            findings.append({
                "code": "PREVIEW_FORBIDDEN_CALL",
                "level": "FAIL", "detail": pat})
    return findings


def _check_render_payload_static() -> list[dict]:
    findings: list[dict] = []
    if not RENDER_PAYLOAD.is_file():
        findings.append({"code": "RENDER_PAYLOAD_MISSING",
                          "level": "FAIL"})
        return findings
    src = RENDER_PAYLOAD.read_text(encoding="utf-8")
    for pat in RENDER_REQUIRED_PATTERNS:
        if not re.search(pat, src):
            findings.append({"code": "RENDER_PATTERN_MISSING",
                              "level": "FAIL", "detail": pat})
    return findings


def _check_locked_files() -> list[dict]:
    findings: list[dict] = []
    for rel in LOCKED_FILES_VS_BASELINE:
        try:
            r = subprocess.run(
                ["git", "diff", BASELINE_COMMIT, "--", rel],
                capture_output=True, text=True, cwd=str(PR), timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            findings.append({"code": "GIT_DIFF_FAILED", "level": "WARN",
                              "detail": f"{rel}: {e}"})
            continue
        if r.returncode != 0:
            findings.append({"code": "GIT_DIFF_RC", "level": "WARN",
                              "detail": f"{rel}: rc={r.returncode}"})
            continue
        if r.stdout.strip():
            findings.append({"code": "LOCKED_FILE_CHANGED",
                              "level": "FAIL", "detail": rel})
    return findings


def _check_audit_no_writer_calls() -> list[dict]:
    findings: list[dict] = []
    me = Path(__file__).read_text(encoding="utf-8")
    for sym in FORBIDDEN_AUDIT_WRITER_SYMBOLS:
        if re.search(sym, me):
            findings.append({"code": "AUDIT_FORBIDDEN_WRITER_CALL",
                              "level": "FAIL", "detail": sym})
    return findings


def _fixture() -> Path | None:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        # 레거시 corpus DB 부재 — 카탈로그 표본으로 대체한다.
        # 이게 없으면 감리가 조용히 SKIP 되어 안 돈 채 통과처럼 보인다.
        from scripts.hwpx.web_office.hwpx_sample_source import (
            resolve_sample as _catalog_sample)
        return _catalog_sample()
    try:
        conn = sqlite3.connect(db)
        row = conn.execute("""
            SELECT d.source_path FROM hwpx_documents d
            WHERE d.inventory_status='FOUND'
              AND d.file_size BETWEEN 30000 AND 200000
            ORDER BY d.first_seen_at LIMIT 1
        """).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    p = PR / row[0]
    return p if p.is_file() else None


def _run_dynamic(fixture: Path) -> dict[str, Any]:
    """build_render_payload (with + without char_pr_defs) 호출 → payload
    schema 검증. writer 호출 0건.
    """
    from scripts.hwpx.web_office.render_payload import (  # noqa: E402
        build_render_payload)
    from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
        import_hwpx_as_ro_view)
    from scripts.hwpx.web_office.charpr_inventory import (  # noqa: E402
        char_pr_defs_only)

    doc = import_hwpx_as_ro_view(fixture)
    payload_baseline = build_render_payload(doc)
    defs = char_pr_defs_only(fixture)
    payload_with_defs = build_render_payload(doc, char_pr_defs=defs)
    return {
        "ok": True,
        "fixture": str(fixture.relative_to(PR)),
        "baselineKeys": sorted(payload_baseline.keys()),
        "withDefsKeys": sorted(payload_with_defs.keys()),
        "styles_present_baseline": "styles" in payload_baseline,
        "styles_present_with_defs": "styles" in payload_with_defs,
        "charPrDefsSize": (
            len((payload_with_defs.get("styles") or {})
                  .get("charPrDefs") or {})),
        "sampleCharPrEntry": next(
            iter(((payload_with_defs.get("styles") or {})
                          .get("charPrDefs") or {}).values()), None),
    }


def _check_dynamic(dyn: dict) -> list[dict]:
    findings: list[dict] = []
    if not dyn.get("ok"):
        findings.append({"code": "DYNAMIC_SKIPPED", "level": "WARN",
                          "detail": dyn.get("reason",
                                                            "fixture missing")})
        return findings
    # 기존 key 모두 보존 (양쪽 payload 에서)
    for key in PAYLOAD_REQUIRED_KEYS:
        if key not in dyn["baselineKeys"]:
            findings.append({"code": "PAYLOAD_KEY_REMOVED",
                              "level": "FAIL",
                              "detail": f"baseline missing {key}"})
        if key not in dyn["withDefsKeys"]:
            findings.append({"code": "PAYLOAD_KEY_REMOVED",
                              "level": "FAIL",
                              "detail": f"with_defs missing {key}"})
    # styles are now part of the read model; explicit char_pr_defs remains
    # supported for older toolbar callers.
    if not dyn["styles_present_baseline"]:
        findings.append({"code": "STYLES_NOT_EXPOSED_BY_DEFAULT",
                          "level": "FAIL",
                          "detail":
                              "document styles must be present by default"})
    if not dyn["styles_present_with_defs"]:
        findings.append({"code": "STYLES_NOT_EXPOSED",
                          "level": "FAIL",
                          "detail":
                              "char_pr_defs 전달 시 styles 키 미출현"})
    if dyn["charPrDefsSize"] <= 0:
        findings.append({"code": "CHARPR_DEFS_EMPTY",
                          "level": "FAIL"})
    sample = dyn["sampleCharPrEntry"]
    if isinstance(sample, dict):
        for field in ("charPrId", "fontName", "fontSizePt",
                                  "textColor", "bold", "italic",
                                  "underline"):
            if field not in sample:
                findings.append({"code": "CHARPR_ENTRY_FIELD_MISSING",
                                  "level": "FAIL", "detail": field})
    return findings


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_preview_static())
    findings.extend(_check_render_payload_static())
    findings.extend(_check_locked_files())
    findings.extend(_check_audit_no_writer_calls())
    fx = _fixture()
    dyn: dict[str, Any] = ({"ok": False, "reason": "fixture missing"}
                                              if fx is None else {})
    if fx is not None:
        try:
            dyn = _run_dynamic(fx)
        except Exception as e:  # noqa: BLE001
            dyn = {"ok": False, "reason": f"dynamic raised: {e}"}
            findings.append({"code": "DYNAMIC_RAISED",
                              "level": "FAIL", "detail": dyn["reason"]})
    findings.extend(_check_dynamic(dyn))
    fail = [f for f in findings if f["level"] == "FAIL"]
    warn = [f for f in findings if f["level"] == "WARN"]
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-APPLYFORMAT-"
                          "TOOLBAR-PREVIEW-01",
        "baseline": BASELINE_COMMIT,
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
        "dynamic": dyn,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
