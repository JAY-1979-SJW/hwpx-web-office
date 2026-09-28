"""
HWPX-FORM-FIELD-CATALOG-SEED-01

form_field_catalog.py — 서식별 입력 필드 카탈로그 빌드.

데이터 흐름:
    per_file_form_type.jsonl   (maskedFileId → formName/domain/formKind)
    survey_input_cells_raw.jsonl (maskedFileId → adjacentLabel/guessedField/inputCellType)
    → label_taxonomy.classify_label()
    → 서식별 필드 목록 (required/optional, aliases, sourceEvidenceHint)

read-only. 파일 내용 수정 없음.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]

FORM_TYPE_JSONL = (
    PROJECT_ROOT / "data" / "reports" / "hwpx_form_type_classification" / "per_file_form_type.jsonl"
)
INPUT_CELLS_JSONL = (
    PROJECT_ROOT / "data" / "reports" / "hwpx_survey_drafts" / "survey_input_cells_raw.jsonl"
)

# ── 필드별 자료 출처 힌트 ────────────────────────────────────────────────────
_SOURCE_HINT: dict[str, str] = {
    "taskName": "공사계약서, 건축허가서, 착공신고서",
    "projectName": "건축허가서, 공사계약서",
    "number": "서식 자동부여",
    "receiptNumber": "접수증, 민원서류",
    "inspectionStatus": "검사기록부, 완공도서",
    "remarks": "현장 확인 후 직접 기재",
    "responsiblePerson": "건축사 면허증, 감리계약서, 사업자등록증",
    "quantity": "설계도면, 자재내역서",
    "contractorName": "사업자등록증, 공사계약서, 착공신고서",
    "durationDays": "공사계약서, 착공신고서",
    "startDate": "착공신고서, 공사계약서",
    "endDate": "완공신고서, 공사계약서",
    "completionDate": "완공신고서, 사용승인신청서",
    "address": "건축허가서, 토지대장, 건축물대장",
    "registrationNumber": "소방시설업 등록증, 사업자등록증, 면허증",
    "amount": "공사내역서, 계약서",
    "testType": "시험성적서, 품질검사보고서",
    "testItem": "시험성적서, 자재검수서",
    "testMethod": "시험성적서, 기술기준서",
    "inspectionDate": "검사신청서, 완공도서",
    "supervisorName": "감리계약서, 감리원 자격증",
    "licenseNumber": "건축사 면허증, 기술사 자격증",
    "ownerName": "건축허가서, 토지대장",
    "location": "건축허가서, 위치도",
    "buildingType": "건축허가서, 건축물대장",
    "floorArea": "건축허가서, 건축물대장",
    "floors": "건축허가서, 건축물대장",
}

# PII 패턴 필터 — adjacentLabel에서 실제 수치가 포함된 라벨 제외
_PII_FILTER = re.compile(r"\d{2,3}-\d{3,4}-\d{4}|\d{3}-\d{2}-\d{5}")

# required 판정 임계값: 해당 서식 파일 중 이 비율 이상에서 등장하면 필수
REQUIRED_RATIO = 0.40

# 최소 등장 파일 수 (너무 드물면 무시)
MIN_FILE_COUNT = 1


# ── 데이터 클래스 ─────────────────────────────────────────────────────────────


@dataclass
class FieldEntry:
    primaryLabel: str  # 가장 많이 등장한 라벨 (raw)
    labels: list[str]  # 모든 라벨 변형 (빈도순)
    semanticField: str  # 자동 매핑된 semantic field ("" = 미매핑)
    autoFillable: bool  # semanticField가 알려진 경우 True
    inputCellTypes: list[str]  # 셀 타입
    required: bool
    fileOccurrenceCount: int  # 몇 개 파일에 등장
    totalOccurrenceCount: int  # 전체 셀 수
    sourceEvidenceHint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "primaryLabel": self.primaryLabel,
            "labels": self.labels,
            "semanticField": self.semanticField,
            "autoFillable": self.autoFillable,
            "inputCellTypes": self.inputCellTypes,
            "required": self.required,
            "fileOccurrenceCount": self.fileOccurrenceCount,
            "totalOccurrenceCount": self.totalOccurrenceCount,
            "sourceEvidenceHint": self.sourceEvidenceHint,
        }


@dataclass
class FormCatalogEntry:
    formId: str
    formName: str
    domain: str
    formKind: str
    byeoljiNumber: str
    fileCount: int
    fields: list[FieldEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        auto_count = sum(1 for f in self.fields if f.autoFillable)
        req_count = sum(1 for f in self.fields if f.required)
        return {
            "formId": self.formId,
            "formName": self.formName,
            "domain": self.domain,
            "formKind": self.formKind,
            "byeoljiNumber": self.byeoljiNumber,
            "fileCount": self.fileCount,
            "fieldCount": len(self.fields),
            "autoFillableCount": auto_count,
            "requiredCount": req_count,
            "fields": [f.to_dict() for f in self.fields],
        }


# ── 빌드 함수 ─────────────────────────────────────────────────────────────────


def _load_jsonl_by_prefix(path: Path, *, single: bool) -> dict[str, Any]:
    """maskedFileId 앞부분(idx_prefix) 기준으로 jsonl 레코드를 모은다."""
    result: dict[str, Any] = {} if single else defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        prefix = rec["maskedFileId"].split("_")[0]
        if single:
            result[prefix] = rec
        else:
            result[prefix].append(rec)
    return result


def _group_files_by_form_key(ft_by_prefix: dict[str, dict]) -> dict[tuple, list[str]]:
    form_files: dict[tuple, list[str]] = defaultdict(list)
    for prefix, ft in ft_by_prefix.items():
        key = (ft["formName"], ft["domain"], ft["formKind"], ft["byeoljiNumber"])
        if ft["formName"]:
            form_files[key].append(prefix)
    return form_files


def _norm_label(s: str) -> str:
    return s.strip().lower().replace(" ", "")


def _aggregate_form_labels(
    prefixes: list[str], cells_by_prefix: dict[str, list[dict]]
) -> dict[str, dict]:
    from hwpx.recognition_corpus.label_taxonomy import CLS_HIGH, CLS_MEDIUM, classify_label

    # key: norm_label → {files, raw_labels, cell_types, sem_fields, guessed_fields, total}
    label_agg: dict[str, dict] = {}
    for prefix in prefixes:
        for cell in cells_by_prefix.get(prefix, []):
            raw_label = cell.get("adjacentLabel", "").strip()
            if not raw_label or len(raw_label) > 60 or _PII_FILTER.search(raw_label):
                continue

            norm = _norm_label(raw_label)
            if norm not in label_agg:
                label_agg[norm] = {
                    "files": set(),
                    "raw": Counter(),
                    "types": Counter(),
                    "sem": Counter(),
                    "guessed": Counter(),
                    "total": 0,
                }
            agg = label_agg[norm]
            agg["files"].add(prefix)
            agg["raw"][raw_label] += 1
            agg["types"][cell.get("inputCellType", "")] += 1
            agg["total"] += 1

            # semanticField 결정 (label_taxonomy 우선, guessedField 보조)
            clf = classify_label(raw_label)
            if clf.semanticField and clf.classification in (CLS_HIGH, CLS_MEDIUM):
                agg["sem"][clf.semanticField] += 1
            guessed = cell.get("guessedField", "")
            if guessed and guessed != "unknown":
                agg["guessed"][guessed] += 1
    return label_agg


def _build_field_entries(
    label_agg: dict[str, dict], n_files: int, required_ratio: float, min_file_count: int
) -> list[FieldEntry]:
    fields: list[FieldEntry] = []
    for norm, agg in label_agg.items():
        file_occ = len(agg["files"])
        if file_occ < min_file_count:
            continue
        ratio = file_occ / n_files

        top_raw = [lbl for lbl, _ in agg["raw"].most_common(8)]
        top_types = [t for t, _ in agg["types"].most_common(2)]
        primary = top_raw[0] if top_raw else norm

        # semanticField: taxonomy > guessedField > ""
        if agg["sem"]:
            sem = agg["sem"].most_common(1)[0][0]
        elif agg["guessed"]:
            sem = agg["guessed"].most_common(1)[0][0]
        else:
            sem = ""

        fields.append(
            FieldEntry(
                primaryLabel=primary,
                labels=top_raw,
                semanticField=sem,
                autoFillable=bool(sem),
                inputCellTypes=top_types,
                required=ratio >= required_ratio,
                fileOccurrenceCount=file_occ,
                totalOccurrenceCount=agg["total"],
                sourceEvidenceHint=_SOURCE_HINT.get(sem, "") if sem else "",
            )
        )

    # required → optional 순, 각 그룹 내 fileOccurrenceCount 내림차순
    fields.sort(key=lambda f: (not f.required, -f.fileOccurrenceCount))
    return fields


def build_catalog(
    form_type_jsonl: Path = FORM_TYPE_JSONL,
    input_cells_jsonl: Path = INPUT_CELLS_JSONL,
    required_ratio: float = REQUIRED_RATIO,
    min_file_count: int = MIN_FILE_COUNT,
    verbose: bool = False,
) -> list[FormCatalogEntry]:
    # 1. form_type 로드 — idx_prefix → rec
    ft_by_prefix: dict[str, dict] = _load_jsonl_by_prefix(form_type_jsonl, single=True)

    # 2. input cells 로드 — idx_prefix → list of cell dicts
    cells_by_prefix: dict[str, list[dict]] = _load_jsonl_by_prefix(input_cells_jsonl, single=False)

    # 3. 서식 키 기준으로 파일 그룹화
    form_files = _group_files_by_form_key(ft_by_prefix)

    if verbose:
        print(f"[build] 고유 서식: {len(form_files)}개, 전체 파일: {len(ft_by_prefix)}개")

    # 4. 서식별 필드 집계, 5. FieldEntry 생성
    catalog: list[FormCatalogEntry] = []
    for form_idx, (form_key, prefixes) in enumerate(sorted(form_files.items())):
        formName, domain, formKind, byeoljiNumber = form_key
        n_files = len(prefixes)

        label_agg = _aggregate_form_labels(prefixes, cells_by_prefix)
        fields = _build_field_entries(label_agg, n_files, required_ratio, min_file_count)

        catalog.append(
            FormCatalogEntry(
                formId=f"form_{form_idx:04d}",
                formName=formName,
                domain=domain,
                formKind=formKind,
                byeoljiNumber=byeoljiNumber,
                fileCount=n_files,
                fields=fields,
            )
        )

    return catalog


def build_summary(catalog: list[FormCatalogEntry]) -> dict[str, Any]:
    total_fields = sum(len(e.fields) for e in catalog)
    auto_fill_fields = sum(sum(1 for f in e.fields if f.autoFillable) for e in catalog)
    required_fields = sum(sum(1 for f in e.fields if f.required) for e in catalog)
    forms_with_fields = sum(1 for e in catalog if e.fields)
    domain_counts: Counter = Counter(e.domain for e in catalog)
    kind_counts: Counter = Counter(e.formKind for e in catalog)
    avg_fields = total_fields / len(catalog) if catalog else 0

    return {
        "totalForms": len(catalog),
        "formsWithFields": forms_with_fields,
        "totalFields": total_fields,
        "autoFillableFields": auto_fill_fields,
        "requiredFields": required_fields,
        "avgFieldsPerForm": round(avg_fields, 1),
        "domainCounts": dict(domain_counts.most_common()),
        "formKindCounts": dict(kind_counts.most_common()),
    }
