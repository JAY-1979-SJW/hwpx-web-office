from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def manifest(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def count_ext(rows):
    result: dict[str, int] = {}
    for row in rows:
        if row.get("path"):
            ext = Path(row["path"]).suffix.lower()
            result[ext] = result.get(ext, 0) + 1
    return result


def main() -> None:
    collections = [
        (
            "기관 홈페이지",
            load_json("data/agency_submission_agency_homepage_link_collection.json")["records"],
            manifest("tmp/agency_submission_agency_homepage_downloads_final/download_manifest.json"),
        ),
        (
            "법제처 1차",
            load_json("data/agency_submission_law_form_collection.json")["records"],
            manifest("tmp/agency_submission_law_form_downloads_final/download_manifest.json"),
        ),
        (
            "법제처 2차",
            load_json("data/agency_submission_law_form_collection_phase2.json")["records"],
            manifest("tmp/agency_submission_law_form_phase2_downloads_final/download_manifest.json"),
        ),
    ]

    lines = [
        "# 기관 제출서류 전체 추적 현황",
        "",
        "- 기준일: 2026-05-11",
        "- 추적 축: 기관 홈페이지, 정부24 민원안내, 법제처 국가법령정보센터 별지/별표",
        "",
        "## 수집 집계",
        "",
        "| 구분 | 등록 항목 | 다운로드 작업 | 성공 | 실패 | 실제 서식 파일 | 확장자 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]

    total_records = 0
    total_jobs = 0
    total_downloaded = 0
    total_failed = 0
    total_forms = 0

    for label, records, rows in collections:
        form_rows = [row for row in rows if row["kind"] == "form_link"]
        downloaded = sum(1 for row in rows if row["status"] == "downloaded")
        failed = sum(1 for row in rows if row["status"] == "failed")
        lines.append(
            f"| {label} | {len(records)} | {len(rows)} | {downloaded} | {failed} | {len(form_rows)} | {count_ext(rows)} |"
        )
        total_records += len(records)
        total_jobs += len(rows)
        total_downloaded += downloaded
        total_failed += failed
        total_forms += len(form_rows)

    lines.extend(
        [
            f"| 합계 | {total_records} | {total_jobs} | {total_downloaded} | {total_failed} | {total_forms} |  |",
            "",
            "## 이번 2차 추적에서 보강한 영역",
            "",
            "- 건축: 감리보고서, 공사감리일지, 임시사용승인신청서",
            "- 소방: 부분완공검사, 자체점검 실시결과, 이행완료보고, 외관점검표",
            "- 전기: 전력기술관리법상 감리원 배치현황 신고서, 배치확인서, 설계감리자확인증",
            "- 정보통신: 착공전 설계도 확인업무 관리대장",
            "- 환경: 비산먼지 발생사업 신고서, 신고증명서",
            "- 해체·석면: 석면해체ㆍ제거작업 신고서, 변경신고서, 석면해체작업감리인 지정 신고서",
            "",
            "## 남은 추적 방향",
            "",
            "- 법제처 검색에 바로 잡히지 않는 HWP/HWPX 원본은 지자체 서식 게시판과 공단/협회 자료실에서 별도 추적한다.",
            "- 정보통신 사용전검사 신청서, 착공전 설계도 확인 신청서처럼 법령 조문에는 있으나 별지 직접 링크가 검색되지 않는 항목은 정부24/지자체 첨부파일로 보강한다.",
            "- 도로점용, 하천점용, 굴착복구, 원인자부담금, 가설울타리/광고물, 특정공사 사전신고 등 토목·인허가 주변 문서는 다음 라운드 우선 대상이다.",
        ]
    )

    out = ROOT / "docs/agency_submission_law_tracking_summary.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
