"""HWPX-API-CONTRACT-LOCK-01.

E동(출입구) 규격 표준화 — 외부 호출자(F동 프론트엔드, 외부 AI, 다른 앱)가
브라우저 편집기 API에 보낼 명령의 schema를 결정론적으로 잠근다.

본 모듈은 Java 측 contract (`com.haehan.engine.contract.HwpxEditorCommand`,
`ApiResponseMeta`)와 짝을 이룬다. Java 측이 진실이고, 본 모듈은 그 진실을
Python 클라이언트와 deterministic test에서 공유 가능한 형태로 잠근다.

방화구획:
- 본 모듈은 production fill_review / writer / live pipeline을 import 하지 않는다.
- raw HWPX / output / AI / OCR / secret 출력 금지.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CONTRACT_NAME = "HWPX-API-CONTRACT-LOCK-01"
CONTRACT_VERSION = "v1"

# Java 측 ApiResponseMeta.SCHEMA_VERSION / ENGINE_VERSION과 일치해야 한다.
EXPECTED_SCHEMA_VERSION = "1.0"
EXPECTED_ENGINE_VERSION_PREFIX = "0.6."  # patch revision은 무관

ALLOWED_COMMAND_TYPES: frozenset[str] = frozenset({
    # 기본 6개 (V1)
    "replaceText",
    "replacePlaceholder",
    "updateTableCell",
    "addTableRow",
    "deleteTableRow",
    "validateDocument",
    # V2 확장 9개 — 모두 기존 자재 wrapping/dispatch만 (신규 로직 없음)
    "fillScheduleBars",  # 공정표 막대 + 색
    "buildMonthlyScheduleTable",  # 월 단위 공정표 생성
    "buildDailyScheduleTable",  # 일 단위 공정표 생성
    "mergeCells",  # 셀 병합
    "splitCells",  # 셀 분할
    "setCellFill",  # 셀 색 채우기
    "applyStyleFromSource",  # 원본 폰트/스타일 유지
    "autoFillFromAI",  # AI 제안 일괄 입력 (자동채움설계실)
    "autoDetectInputSlots",  # 입력칸 자동 인지
})

# 각 commandType별 필수 target/payload 키
COMMAND_SPEC: dict[str, dict[str, list[str]]] = {
    "replaceText": {
        "required_target": ["paragraphIndex"],
        "required_payload": ["oldText", "replacement"],
    },
    "replacePlaceholder": {
        "required_target": [],
        "required_payload": ["key", "value"],
    },
    "updateTableCell": {
        "required_target": ["tableIndex", "row", "col"],
        "required_payload": ["value"],
    },
    "addTableRow": {
        "required_target": ["tableIndex"],
        "required_payload": ["values"],
    },
    "deleteTableRow": {
        "required_target": ["tableIndex", "row"],
        "required_payload": [],
    },
    "validateDocument": {
        "required_target": [],
        "required_payload": [],
    },
    # ── V2 확장 9개 ────────────────────────────────────────────────────
    "fillScheduleBars": {
        "required_target": ["tableIndex"],
        "required_payload": ["barPlan"],
    },
    "buildMonthlyScheduleTable": {
        "required_target": ["tableIndex"],
        "required_payload": ["items", "firstMonth", "monthCount"],
    },
    "buildDailyScheduleTable": {
        "required_target": ["tableIndex"],
        "required_payload": ["items", "startDate", "dayCount"],
    },
    "mergeCells": {
        "required_target": ["tableIndex", "row", "col"],
        "required_payload": ["rowSpan", "colSpan"],
    },
    "splitCells": {
        "required_target": ["tableIndex", "row", "col"],
        "required_payload": [],
    },
    "setCellFill": {
        "required_target": ["tableIndex", "row", "col"],
        "required_payload": ["color"],
    },
    "applyStyleFromSource": {
        "required_target": ["targetType"],
        "required_payload": ["sourceRef"],
    },
    "autoFillFromAI": {
        "required_target": [],
        "required_payload": ["proposals"],
    },
    "autoDetectInputSlots": {
        "required_target": [],
        "required_payload": [],
    },
}

# 응답 필드 — Java HwpxEditorCommandResult + ApiResponseMeta가 보장.
REQUIRED_RESPONSE_KEYS: tuple[str, ...] = (
    "schemaVersion",
    "engineVersion",
    "artifactId",
    "applied",
)
# 응답에 따라 추가 가능한 필드 (additive, 절대 제거 금지).
OPTIONAL_RESPONSE_KEYS: tuple[str, ...] = (
    "outputArtifactId",
    "status",
    "error",
    "errorCodes",
    "requestId",
    "commandId",
)

# 외부 호출자가 노출하면 안 되는 필드
FORBIDDEN_REQUEST_FIELDS: tuple[str, ...] = (
    "filesystemPath",
    "outputPath",
    "absolutePath",
    "credential",
    "token",
    "password",
    "secret",
    "sessionCookie",
)

_ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class ContractViolation(ValueError):
    """규격 위반."""


# ── command validation ─────────────────────────────────────────────────────


def is_known_command_type(t: str) -> bool:
    return t in ALLOWED_COMMAND_TYPES


def validate_command_envelope(cmd: dict) -> list[str]:
    """commandType, artifactId, dryRun 등 envelope 검증.

    return: 위반 코드 리스트. 비어 있으면 PASS.
    """
    errors: list[str] = []
    if not isinstance(cmd, dict):
        return ["COMMAND_NOT_OBJECT"]
    ct = cmd.get("commandType")
    if not ct or not isinstance(ct, str):
        errors.append("MISSING_COMMAND_TYPE")
    elif ct not in ALLOWED_COMMAND_TYPES:
        errors.append("UNKNOWN_COMMAND_TYPE")
    aid = cmd.get("artifactId")
    if not aid or not isinstance(aid, str):
        errors.append("MISSING_ARTIFACT_ID")
    elif not _ARTIFACT_ID_RE.match(aid):
        errors.append("INVALID_ARTIFACT_ID_FORMAT")
    if "dryRun" in cmd and not isinstance(cmd["dryRun"], bool):
        errors.append("DRY_RUN_NOT_BOOL")
    for forbidden in FORBIDDEN_REQUEST_FIELDS:
        if _contains_key_deep(cmd, forbidden):
            errors.append(f"FORBIDDEN_FIELD:{forbidden}")
    return errors


def validate_command_body(cmd: dict) -> list[str]:
    """commandType별 target/payload 필수 키 검증.

    envelope 검증을 먼저 수행하지 않는다 — 호출자가 chaining한다.
    """
    errors: list[str] = []
    ct = cmd.get("commandType")
    spec = COMMAND_SPEC.get(ct)
    if not spec:
        return ["UNKNOWN_COMMAND_TYPE"]
    target = cmd.get("target") or {}
    payload = cmd.get("payload") or {}
    if not isinstance(target, dict):
        errors.append("TARGET_NOT_OBJECT")
        target = {}
    if not isinstance(payload, dict):
        errors.append("PAYLOAD_NOT_OBJECT")
        payload = {}
    for k in spec["required_target"]:
        if k not in target or target.get(k) is None:
            errors.append(f"MISSING_TARGET:{k}")
    for k in spec["required_payload"]:
        if k not in payload or payload.get(k) is None:
            errors.append(f"MISSING_PAYLOAD:{k}")
    return errors


def validate_command(cmd: dict) -> dict:
    """envelope + body 통합 검증. return {ok, errors}."""
    env = validate_command_envelope(cmd)
    body = validate_command_body(cmd) if not env or env == ["UNKNOWN_COMMAND_TYPE"] else []
    # envelope에 UNKNOWN_COMMAND_TYPE이 있어도 body 검증은 skip
    if "UNKNOWN_COMMAND_TYPE" in env:
        body = []
    all_errors = env + body
    return {"ok": not all_errors, "errors": all_errors}


# ── response validation ────────────────────────────────────────────────────


def validate_response(resp: dict) -> dict:
    errors: list[str] = []
    if not isinstance(resp, dict):
        return {"ok": False, "errors": ["RESPONSE_NOT_OBJECT"]}
    for k in REQUIRED_RESPONSE_KEYS:
        if k not in resp:
            errors.append(f"MISSING_RESPONSE_KEY:{k}")
    sv = resp.get("schemaVersion")
    if sv is not None and sv != EXPECTED_SCHEMA_VERSION:
        errors.append(f"SCHEMA_VERSION_MISMATCH:{sv}")
    ev = resp.get("engineVersion")
    if ev is not None and not str(ev).startswith(EXPECTED_ENGINE_VERSION_PREFIX):
        errors.append(f"ENGINE_VERSION_OUTSIDE_RANGE:{ev}")
    if "applied" in resp and not isinstance(resp["applied"], bool):
        errors.append("APPLIED_NOT_BOOL")
    if resp.get("applied") is True and not resp.get("outputArtifactId"):
        errors.append("APPLIED_WITHOUT_OUTPUT_ARTIFACT_ID")
    return {"ok": not errors, "errors": errors}


# ── client-side builder ────────────────────────────────────────────────────


def build_command(  # ruff: ignore[too-many-arguments] -- API contract 빌더, 시그니처가 공개 계약이라 변경 보류
    *,
    command_type: str,
    artifact_id: str,
    target: dict | None = None,
    payload: dict | None = None,
    dry_run: bool = True,
    request_id: str | None = None,
    command_id: str | None = None,
) -> dict:
    """외부 호출자가 envelope을 만들 때 권장 형태.

    검증을 통과하지 못하면 ContractViolation을 발생시킨다.
    """
    cmd: dict[str, Any] = {
        "commandType": command_type,
        "artifactId": artifact_id,
        "target": target or {},
        "payload": payload or {},
        "dryRun": bool(dry_run),
    }
    if request_id is not None:
        cmd["requestId"] = request_id
    if command_id is not None:
        cmd["commandId"] = command_id
    result = validate_command(cmd)
    if not result["ok"]:
        raise ContractViolation(",".join(result["errors"]))
    return cmd


# ── helpers ────────────────────────────────────────────────────────────────


def _contains_key_deep(obj: Any, key: str) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                return True
            if _contains_key_deep(v, key):
                return True
    elif isinstance(obj, list):
        for v in obj:
            if _contains_key_deep(v, key):
                return True
    return False


# ── production isolation ───────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PATHS_FOR_API_CONTRACT: tuple[Path, ...] = (
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_contract.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_ui_adapter.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_live_pipeline.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/evidence_ingestion_contract.py",
)
FORBIDDEN_IMPORTS: tuple[str, ...] = (
    "api_contract.editor_command_contract",
    "ALLOWED_COMMAND_TYPES",
    "validate_command_envelope",
)


def audit_api_contract_isolation() -> dict:
    violations: list[dict] = []
    checked: list[str] = []
    for path in PRODUCTION_PATHS_FOR_API_CONTRACT:
        if not path.is_file():
            continue
        checked.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in FORBIDDEN_IMPORTS:
            if needle in text:
                violations.append({
                    "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "forbidden": needle,
                })
    return {"violations": violations, "ok": not violations, "filesChecked": checked}


def dump_contract_snapshot() -> dict:
    """현재창에 직접 출력 가능한 contract snapshot dict."""
    return {
        "contractName": CONTRACT_NAME,
        "contractVersion": CONTRACT_VERSION,
        "schemaVersion": EXPECTED_SCHEMA_VERSION,
        "engineVersionPrefix": EXPECTED_ENGINE_VERSION_PREFIX,
        "allowedCommandTypes": sorted(ALLOWED_COMMAND_TYPES),
        "commandSpec": COMMAND_SPEC,
        "requiredResponseKeys": list(REQUIRED_RESPONSE_KEYS),
        "optionalResponseKeys": list(OPTIONAL_RESPONSE_KEYS),
        "forbiddenRequestFields": list(FORBIDDEN_REQUEST_FIELDS),
    }


def dump_contract_snapshot_json() -> str:
    return json.dumps(dump_contract_snapshot(), ensure_ascii=False, indent=2)
