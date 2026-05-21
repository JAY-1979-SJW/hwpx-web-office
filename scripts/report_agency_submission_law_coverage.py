from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def main() -> None:
    trade_index = load_json("data/agency_submission_trade_index.web_expanded.json")
    law_records = load_json("data/agency_submission_law_form_collection.json")["records"]
    agency_records = load_json("data/agency_submission_agency_homepage_link_collection.json")["records"]
    law_manifest = json.loads(
        (ROOT / "tmp/agency_submission_law_form_downloads_final/download_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    agency_manifest = json.loads(
        (ROOT / "tmp/agency_submission_agency_homepage_downloads_final/download_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    trade_docs = []
    for trade in trade_index["trades"]:
        trade_name = trade["trade_name"]
        for document in trade.get("documents", []):
            trade_docs.append((trade_name, document))

    law_form_downloads = [row for row in law_manifest if row["kind"] == "form_link"]
    agency_form_downloads = [row for row in agency_manifest if row["kind"] == "form_link"]

    law_by_trade: dict[str, list[str]] = {}
    for row in law_form_downloads:
        law_by_trade.setdefault(row["agency_group"], []).append(row["document_set"])

    agency_by_trade: dict[str, list[str]] = {}
    for row in agency_form_downloads:
        agency_by_trade.setdefault(row["agency_group"], []).append(row["document_set"])

    rows = []
    for trade, document in trade_docs:
        law_hits = [name for name in law_by_trade.get(trade, []) if name in document or document in name]
        agency_hits = [name for name in agency_by_trade.get(trade, []) if name in document or document in name]
        rows.append(
            {
                "trade": trade,
                "document": document,
                "law_form_match": "; ".join(sorted(set(law_hits))),
                "agency_form_match": "; ".join(sorted(set(agency_hits))),
                "needs_more_collection": "N" if law_hits or agency_hits else "Y",
            }
        )

    out_csv = ROOT / "data/agency_submission_law_coverage_gap.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "trade",
                "document",
                "law_form_match",
                "agency_form_match",
                "needs_more_collection",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    matched = sum(1 for row in rows if row["needs_more_collection"] == "N")
    missing = len(rows) - matched
    law_ext = {}
    for row in law_manifest:
        if row["path"]:
            law_ext[Path(row["path"]).suffix.lower()] = law_ext.get(Path(row["path"]).suffix.lower(), 0) + 1

    report = ROOT / "docs/agency_submission_law_coverage_report.md"
    report.write_text(
        "\n".join(
            [
                "# 법제처 기준 제출서류 수집 보강 보고서",
                "",
                "- 기준일: 2026-05-11",
                "- 법제처 수집 목록: `data/agency_submission_law_form_collection.json`",
                "- 법제처 다운로드 폴더: `tmp/agency_submission_law_form_downloads_final`",
                "- 수집 대비표: `data/agency_submission_law_coverage_gap.csv`",
                "",
                "## 수집 결과",
                "",
                f"- 법제처 등록 서식 항목: {len(law_records)}",
                f"- 법제처 다운로드 작업: {len(law_manifest)}",
                f"- 법제처 다운로드 성공: {sum(1 for row in law_manifest if row['status'] == 'downloaded')}",
                f"- 법제처 실제 서식 파일: {len(law_form_downloads)}",
                f"- 기관 홈페이지 등록 항목: {len(agency_records)}",
                f"- 기관 홈페이지 실제 HWP 서식: {len(agency_form_downloads)}",
                f"- 기존 웹확장 제출문서 목록: {len(trade_docs)}",
                f"- 단순 명칭 매칭으로 수집 원본이 연결된 제출문서: {matched}",
                f"- 추가 수집 필요로 남은 제출문서: {missing}",
                f"- 법제처 다운로드 확장자: {law_ext}",
                "",
                "## 판단",
                "",
                "기관 홈페이지 수집만으로는 HWP 첨부가 소방 일부에 치우친다. 법제처 국가법령정보센터 별지서식을 기준 축으로 추가해야 건축, 기계설비, 전기, 가스, 승강기, 상하수도, 환경, 해체, 공통관리 문서까지 법정 서식 근거가 연결된다.",
                "",
                "이번 보강은 1차 법제처 핵심 서식 수집이다. `agency_submission_law_coverage_gap.csv`의 `needs_more_collection=Y` 항목은 발주기관 자체 양식, 지자체 서식, 공사감독/감리단 내부양식, 협회/공단 접수양식이 섞여 있으므로 다음 수집 라운드에서 기관별 사이트와 법령 별지서식을 함께 더 찾아야 한다.",
                "",
                "## 우선 추가 수집 대상",
                "",
                "- 건축: 감리보고, 중간감리보고, 공사감리일지, 관계전문기술자 협력 문서",
                "- 토목/상하수도: 도로점용, 하천점용, 굴착복구, 배수설비, 원인자부담금",
                "- 소방: 완공검사, 부분완공검사, 감리결과보고, 자체점검 결과보고",
                "- 전기/통신: 사용전검사 신청서 외 공사계획 신고, 설계도 확인, 감리원 배치",
                "- 기계설비: 사용 전 검사 확인증, 유지관리자 선임, 성능점검",
                "- 가스: LPG 특정사용시설, 도시가스 공급시설, 고압가스 검사/기술검토",
                "- 환경/안전: 건설폐기물, 비산먼지, 특정공사, 석면, 유해위험방지계획",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"law_records={len(law_records)}")
    print(f"law_download_jobs={len(law_manifest)}")
    print(f"law_form_downloads={len(law_form_downloads)}")
    print(f"trade_docs={len(trade_docs)} matched={matched} missing={missing}")
    print(f"csv={out_csv}")
    print(f"report={report}")


if __name__ == "__main__":
    main()
