"""HWPX-FORM-TEMPLATE-STORE-01.

서식 템플릿 저장·재사용 계층 — "한 번 셋팅 → 영구 자동입력" 모델의 핵심.

문제(기존):
- 같은 서식을 채울 때마다 `recognize_form`으로 셀 위치를 매번 재추론했다.
  → 재인식 비용·시간 발생, 인식 결과 변동성으로 신뢰도 흔들림.

해결(본 모듈):
- **셋팅 시(한 번)**: 인식 결과 + 사람 확인 → 필드↔정확한 셀 좌표 바인딩을
  `FormTemplate`으로 확정·저장한다.
- **채움 시(매번)**: 저장된 템플릿을 로드해 재인식 없이 값만 꽂는 계획(FillPlan)을
  만든다. 결정적·재현 가능하며 재인식 원가가 사라진다.

안전(관공서 서식 필수):
- 직인/결재/법령 안내표(unsafeTableIds)는 템플릿에 `excludedTableIds`로 박제되어
  채움 계획에서 절대 대상이 되지 않는다.
- 업로드 서식이 템플릿과 구조가 다르면(fingerprint 불일치) 블라인드 채움을 거부한다
  (엉뚱한 셀에 쓰는 사고 방지).

제약:
- HWPX 파일 직접 쓰기 미참조 — FillPlan(계획)까지만. 실제 writer는 별도.
- AI API / OCR 미참조. 값은 호출자가 `values_by_field`로 주입.
- raw 개인정보 저장 안 함 — 템플릿에는 셀 좌표·필드키·라벨만.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

CONTRACT_NAME = "HWPX-FORM-TEMPLATE-STORE-01"
CONTRACT_VERSION = "v1"
TEMPLATE_VERSION = "v1"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_TEMPLATE_DIR = PROJECT_ROOT / "data" / "drafts" / "form_templates"

# 채움 계획 상태
PLAN_READY = "READY"                       # 모든 필수 필드 값 있음
PLAN_NEEDS_INPUT = "NEEDS_INPUT"           # 필수 필드 값 누락
PLAN_FINGERPRINT_MISMATCH = "FINGERPRINT_MISMATCH"  # 구조 불일치 — 채움 거부


# ── 데이터 클래스 ─────────────────────────────────────────────────────

@dataclass
class CellTarget:
    tableId: str
    row: int
    col: int
    visualRow: int = 0
    visualCol: int = 0
    rowSpan: int = 1
    colSpan: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FieldBinding:
    """셋팅 시 확정된 필드↔셀 바인딩."""
    fieldKey: str
    label: str
    target: CellTarget
    required: bool = False
    confirmed: bool = False       # 사람이 셋팅 시 확인함
    valueSourceHint: str = ""     # 예: "사업자등록증"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class FormTemplate:
    templateId: str
    formName: str
    formType: str
    structureFingerprint: str
    excludedTableIds: list[str] = field(default_factory=list)
    bindings: list[FieldBinding] = field(default_factory=list)
    createdAt: str = ""
    mappingVersion: str = "v1"
    templateVersion: str = TEMPLATE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "contractName": CONTRACT_NAME,
            "templateId": self.templateId,
            "formName": self.formName,
            "formType": self.formType,
            "structureFingerprint": self.structureFingerprint,
            "excludedTableIds": list(self.excludedTableIds),
            "bindings": [b.to_dict() for b in self.bindings],
            "createdAt": self.createdAt,
            "mappingVersion": self.mappingVersion,
            "templateVersion": self.templateVersion,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "FormTemplate":
        bindings = []
        for b in d.get("bindings", []):
            tgt = b.get("target", {})
            bindings.append(FieldBinding(
                fieldKey=b["fieldKey"],
                label=b.get("label", ""),
                target=CellTarget(
                    tableId=tgt.get("tableId", ""),
                    row=int(tgt.get("row", 0)),
                    col=int(tgt.get("col", 0)),
                    visualRow=int(tgt.get("visualRow", 0)),
                    visualCol=int(tgt.get("visualCol", 0)),
                    rowSpan=int(tgt.get("rowSpan", 1)),
                    colSpan=int(tgt.get("colSpan", 1)),
                ),
                required=bool(b.get("required", False)),
                confirmed=bool(b.get("confirmed", False)),
                valueSourceHint=b.get("valueSourceHint", ""),
            ))
        return FormTemplate(
            templateId=d["templateId"],
            formName=d.get("formName", ""),
            formType=d.get("formType", ""),
            structureFingerprint=d.get("structureFingerprint", ""),
            excludedTableIds=list(d.get("excludedTableIds", [])),
            bindings=bindings,
            createdAt=d.get("createdAt", ""),
            mappingVersion=d.get("mappingVersion", "v1"),
            templateVersion=d.get("templateVersion", TEMPLATE_VERSION),
        )


@dataclass
class CellWrite:
    tableId: str
    row: int
    col: int
    visualRow: int
    visualCol: int
    fieldKey: str
    value: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FillPlan:
    templateId: str
    formName: str
    status: str
    cellWrites: list[CellWrite] = field(default_factory=list)
    missingRequired: list[str] = field(default_factory=list)
    skippedUnsafe: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "templateId": self.templateId,
            "formName": self.formName,
            "status": self.status,
            "cellWrites": [c.to_dict() for c in self.cellWrites],
            "missingRequired": list(self.missingRequired),
            "skippedUnsafe": list(self.skippedUnsafe),
        }


# ── 구조 지문(fingerprint) ────────────────────────────────────────────
#
# 업로드된 서식이 템플릿과 "같은 서식"인지 판별하는 결정적 해시.
# 표 역할 맵 + 슬롯 라벨/위치를 정렬해 SHA-256으로 요약한다.
# 라벨 텍스트나 좌표가 달라지면 지문이 바뀌어 블라인드 채움을 막는다.

def compute_structure_fingerprint(recognition_result) -> str:
    """FormRecognitionResult에서 구조 지문을 산출한다."""
    table_roles = getattr(recognition_result, "tableRoles", None)
    if table_roles is None and isinstance(recognition_result, dict):
        table_roles = recognition_result.get("tableRoles", {})
    table_roles = table_roles or {}

    slots = getattr(recognition_result, "enhancedSlots", None)
    if slots is None and isinstance(recognition_result, dict):
        slots = recognition_result.get("enhancedSlots", [])
    slots = slots or []

    role_part = "|".join(f"{tid}:{role}" for tid, role in sorted(table_roles.items()))

    slot_sigs = []
    for s in slots:
        tid = getattr(s, "tableId", None) if not isinstance(s, dict) else s.get("tableId")
        label = getattr(s, "labelText", None) if not isinstance(s, dict) else s.get("labelText")
        row = getattr(s, "row", None) if not isinstance(s, dict) else s.get("row")
        col = getattr(s, "col", None) if not isinstance(s, dict) else s.get("col")
        slot_sigs.append(f"{tid}:{label}:{row}:{col}")
    slot_part = "|".join(sorted(slot_sigs))

    raw = f"roles[{role_part}]slots[{slot_part}]"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# ── 셋팅: 인식 결과 → 템플릿 ─────────────────────────────────────────

def build_template_from_recognition(
    *,
    form_name: str,
    recognition_result,
    confirmed_field_keys: set[str] | None = None,
    required_field_keys: set[str] | None = None,
    value_hints: dict[str, str] | None = None,
    template_id: str | None = None,
    now: datetime | None = None,
) -> FormTemplate:
    """인식 결과 + 사람 확인으로 재사용 가능한 FormTemplate을 만든다.

    Args:
        confirmed_field_keys: 사람이 확인한 fieldKey 집합. None이면 안전 슬롯 전체를
            confirmed=False로 담는다(초안). 지정 시 해당 키만 confirmed=True.
        required_field_keys: 필수로 표시할 fieldKey 집합.
    """
    confirmed = confirmed_field_keys
    required = required_field_keys or set()
    value_hints = value_hints or {}

    excluded = list(getattr(recognition_result, "unsafeTableIds", None)
                    or (recognition_result.get("unsafeTableIds", [])
                        if isinstance(recognition_result, dict) else []))
    excluded_set = set(excluded)

    slots = getattr(recognition_result, "enhancedSlots", None)
    if slots is None and isinstance(recognition_result, dict):
        slots = recognition_result.get("enhancedSlots", [])
    slots = slots or []

    form_type = getattr(recognition_result, "formType", None)
    if form_type is None and isinstance(recognition_result, dict):
        form_type = recognition_result.get("formType", "unknown_form")
    form_type = form_type or "unknown_form"

    bindings: list[FieldBinding] = []
    seen_keys: set[str] = set()
    for s in slots:
        def _g(name, default=None):
            return (getattr(s, name, default) if not isinstance(s, dict)
                    else s.get(name, default))
        tid = _g("tableId", "")
        if tid in excluded_set:
            continue  # 안전 제외 표는 바인딩하지 않음
        field_key = _g("fieldGuess", "unknown")
        if field_key in (None, "", "unknown"):
            continue
        if field_key in seen_keys:
            continue  # 같은 필드는 첫 슬롯만(가장 신뢰도 높은 순서 가정)
        if confirmed is not None and field_key not in confirmed:
            continue
        seen_keys.add(field_key)
        bindings.append(FieldBinding(
            fieldKey=field_key,
            label=_g("labelText", ""),
            target=CellTarget(
                tableId=tid,
                row=int(_g("row", 0) or 0),
                col=int(_g("col", 0) or 0),
                visualRow=int(_g("visualRow", 0) or 0),
                visualCol=int(_g("visualCol", 0) or 0),
                rowSpan=int(_g("rowSpan", 1) or 1),
                colSpan=int(_g("colSpan", 1) or 1),
            ),
            required=field_key in required,
            confirmed=confirmed is not None,
            valueSourceHint=value_hints.get(field_key, ""),
        ))

    ref = now or datetime.now(timezone.utc)
    return FormTemplate(
        templateId=template_id or f"tpl_{uuid4().hex[:12]}",
        formName=form_name,
        formType=form_type,
        structureFingerprint=compute_structure_fingerprint(recognition_result),
        excludedTableIds=excluded,
        bindings=bindings,
        createdAt=ref.isoformat(),
    )


# ── 저장·로드 ─────────────────────────────────────────────────────────

def save_template(template: FormTemplate,
                  template_dir: str | Path | None = None) -> Path:
    directory = Path(template_dir) if template_dir else _DEFAULT_TEMPLATE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{template.templateId}.json"
    path.write_text(json.dumps(template.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def load_template(template_id: str,
                  template_dir: str | Path | None = None) -> FormTemplate | None:
    directory = Path(template_dir) if template_dir else _DEFAULT_TEMPLATE_DIR
    path = directory / f"{template_id}.json"
    if not path.exists():
        return None
    return FormTemplate.from_dict(json.loads(path.read_text(encoding="utf-8")))


def find_template_by_fingerprint(
    fingerprint: str,
    template_dir: str | Path | None = None,
) -> FormTemplate | None:
    """구조 지문으로 일치하는 템플릿을 찾는다(formName 문자열 매칭보다 견고)."""
    directory = Path(template_dir) if template_dir else _DEFAULT_TEMPLATE_DIR
    if not directory.exists():
        return None
    for path in sorted(directory.glob("*.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if d.get("structureFingerprint") == fingerprint:
            return FormTemplate.from_dict(d)
    return None


# ── 채움: 템플릿 + 값 → FillPlan ─────────────────────────────────────

def apply_template(
    template: FormTemplate,
    values_by_field: dict[str, str],
    *,
    uploaded_recognition=None,
) -> FillPlan:
    """저장된 템플릿에 값을 꽂아 채움 계획(FillPlan)을 만든다. 재인식 없음.

    Args:
        values_by_field: fieldKey → 채울 값 (AI 제안/소스 추출 결과).
        uploaded_recognition: 지정 시 업로드 서식의 구조 지문을 템플릿과 대조.
            불일치면 상태 FINGERPRINT_MISMATCH로 채움을 거부한다(안전).
    """
    plan = FillPlan(templateId=template.templateId,
                    formName=template.formName, status=PLAN_READY)

    # 구조 대조 — 다른 서식에 블라인드 채움 방지
    if uploaded_recognition is not None:
        uploaded_fp = compute_structure_fingerprint(uploaded_recognition)
        if uploaded_fp != template.structureFingerprint:
            plan.status = PLAN_FINGERPRINT_MISMATCH
            return plan

    excluded = set(template.excludedTableIds)
    for b in template.bindings:
        if b.target.tableId in excluded:
            plan.skippedUnsafe.append(b.fieldKey)
            continue
        value = values_by_field.get(b.fieldKey)
        if value in (None, ""):
            if b.required:
                plan.missingRequired.append(b.fieldKey)
            continue
        plan.cellWrites.append(CellWrite(
            tableId=b.target.tableId,
            row=b.target.row,
            col=b.target.col,
            visualRow=b.target.visualRow,
            visualCol=b.target.visualCol,
            fieldKey=b.fieldKey,
            value=str(value),
        ))

    if plan.missingRequired:
        plan.status = PLAN_NEEDS_INPUT
    return plan


# ── snapshot ─────────────────────────────────────────────────────────

def dump_contract_snapshot() -> dict[str, Any]:
    return {
        "contractName": CONTRACT_NAME,
        "contractVersion": CONTRACT_VERSION,
        "templateVersion": TEMPLATE_VERSION,
        "templateDir": str(_DEFAULT_TEMPLATE_DIR.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "planStatuses": [PLAN_READY, PLAN_NEEDS_INPUT, PLAN_FINGERPRINT_MISMATCH],
    }
