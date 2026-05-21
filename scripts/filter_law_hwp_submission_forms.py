from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

INCLUDE_TERMS = [
    "신청서",
    "신고서",
    "보고서",
    "계획서",
    "의뢰서",
    "요청서",
    "제출서",
    "착공",
    "완공",
    "사용승인 신청",
    "사용전검사",
    "자체점검",
    "이행완료",
    "배치 현황 제출",
    "배치 및 철수 현황 통보",
    "감리원 배치현황 신고",
]

EXCLUDE_TERMS = [
    "삭제",
    "별표",
    "기준",
    "수수료",
    "범위",
    "대장",
    "허가서",
    "신고필증",
    "확인증",
    "사용승인서",
    "임시사용승인서",
    "등록증",
    "증명서",
    "지정서",
    "인증서",
    "수첩",
    "표지",
    "업무의 내용",
    "평가기준",
    "산정기준",
    "기술기준",
    "처분기준",
    "과징금",
    "경력",
    "신기술",
    "건설엔지니어링업",
    "공장인증",
    "국고보조금",
]

# Some "확인서" forms are submitted by the contractor/designer, not issued by the agency.
ALLOW_EXCLUDED_IF = [
    "피난안전 확인서",
    "내진설계 확인서",
    "구조안전 확인서",
    "설계감리자확인증",
]

PROJECT_TERMS = [
    "건축",
    "대수선",
    "용도변경",
    "가설건축물",
    "착공",
    "사용승인",
    "공사",
    "감리",
    "소방",
    "방염",
    "자체점검",
    "점검",
    "기계설비",
    "정보통신",
    "전력",
    "전기",
    "하도급",
    "고압가스",
    "액화석유가스",
    "도시가스",
    "가스",
    "승강기",
    "하수",
    "수도",
    "급수",
    "배수설비",
    "폐수",
    "배출시설",
    "비산먼지",
    "비점오염",
    "건설폐기물",
    "위험물",
    "산업안전",
    "안전보건",
]

BUSINESS_OR_AGENCY_EXCLUDE_TERMS = [
    "\ub4f1\ub85d\uc2e0\uccad",
    "\ub4f1\ub85d\uc0ac\ud56d",
    "\ub4f1\ub85d\ubcc0\uacbd",
    "\ub4f1\ub85d, \ubcc0\uacbd\ub4f1\ub85d",
    "\ud734\uc5c5",
    "\ud3d0\uc5c5",
    "\uc7ac\uac1c\uc5c5",
    "\uc9c0\uc704\uc2b9\uacc4",
    "\uc591\ub3c4",
    "\uc591\uc218",
    "\uc0c1\uc18d",
    "\ud569\ubcd1",
    "\uc2dc\uacf5\ub2a5\ub825",
    "\uc810\uac80\ub2a5\ub825",
    "\uc2e0\uc778\ub3c4",
    "\uc790\uaca9 \uc778\uc815",
    "\uc804\ub825\uae30\uc220\uc778 \ud604\ud669",
    "\uc804\ubb38\uc778\ub825 \uc591\uc131\uae30\uad00",
    "\uacb0\uacfc \ud1b5\ubcf4\uc11c",
    "\uacb0\uacfc \ud1b5\uc9c0\uc11c",
    "\ud1b5\uc9c0\uc11c",
    "\uc7ac\ubc1c\uae09",
    "\ud3c9\uac00 \uc2e0\uccad",
    "\ud3c9\uac00\uc2e0\uccad",
    "\uad00\ub9ac\uc0ac\uc99d",
    "\uc720\uc9c0\uad00\ub9ac\uc790",
    "\ub4f1\ub85d\uc2e0\uace0",
    "\uac74\ucd95\ud589\uc815\uc804\uc0b0\uc790\ub8cc",
    "\uac74\ucd95\ud611\uc815",
    "\uc804\ub825\uae30\uc220\uc778",
    "\uac10\ub9ac\uc6d0 \ud604\ud669\uc2e0\uace0\uc11c",
    "\uc815\ubcf4\ud1b5\uc2e0\uacf5\uc0ac\uc5c5 \ubcc0\uacbd\uc2e0\uace0\uc11c",
    "\uc815\ubcf4\ud1b5\uc2e0\uc124\ube44 \uc720\uc9c0\ubcf4\uc218",
    "\ucc29\uacf5\uc5f0\uae30\ud655\uc778\uc11c",
]


def is_submission_form(title: str) -> tuple[bool, str]:
    if not any(term in title for term in PROJECT_TERMS):
        return False, "excluded_not_project_submission"
    if any(term in title for term in ALLOW_EXCLUDED_IF):
        return True, "allowlisted_submitter_confirmation"
    if any(term in title for term in BUSINESS_OR_AGENCY_EXCLUDE_TERMS):
        return False, "excluded_business_or_agency_issued_form"
    if any(term in title for term in EXCLUDE_TERMS):
        return False, "excluded_non_submission_or_agency_issued"
    if any(term in title for term in INCLUDE_TERMS):
        return True, "included_submission_keyword"
    return False, "no_submission_keyword"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-manifest",
        default="tmp/agency_submission_law_byl_hwp_all_downloads_final/download_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        default="tmp/agency_submission_law_byl_hwp_submission_only_core_final",
    )
    args = parser.parse_args()

    source_manifest = ROOT / args.source_manifest
    output_dir = ROOT / args.output_dir
    if output_dir.exists():
        shutil.rmtree(output_dir)
    rows = json.loads(source_manifest.read_text(encoding="utf-8"))

    filtered = []
    rejected = []
    for row in rows:
        keep, reason = is_submission_form(row["title"])
        target = dict(row)
        target["filter_reason"] = reason
        if keep:
            if not row.get("path"):
                target["filter_reason"] = "excluded_missing_downloaded_file"
                rejected.append(target)
                continue
            src = ROOT / row["path"]
            if not src.is_file():
                target["filter_reason"] = "excluded_missing_downloaded_file"
                rejected.append(target)
                continue
            rel_parts = Path(row["path"]).parts
            # Keep the trade/law/title folder structure under the new root.
            try:
                tmp_idx = rel_parts.index("agency_submission_law_byl_hwp_all_downloads_final")
                rel = Path(*rel_parts[tmp_idx + 1 :])
            except ValueError:
                rel = Path(row["trade"]) / Path(row["path"]).name
            dst = output_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            target["submission_path"] = str(dst)
            filtered.append(target)
        else:
            rejected.append(target)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "submission_manifest.json").write_text(
        json.dumps(filtered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "rejected_manifest.json").write_text(
        json.dumps(rejected, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "submission_manifest.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        fields = list(filtered[0].keys()) if filtered else ["title"]
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        writer.writerows(filtered)
    with (output_dir / "rejected_manifest.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        fields = list(rejected[0].keys()) if rejected else ["title"]
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rejected)

    print(f"source={len(rows)}")
    print(f"submission={len(filtered)}")
    print(f"rejected={len(rejected)}")
    print(f"output_dir={output_dir}")


if __name__ == "__main__":
    main()
