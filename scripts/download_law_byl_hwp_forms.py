from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


LAW_GO_KR = "https://www.law.go.kr"


TARGET_LAWS = [
    {
        "trade": "건설공사 공통관리",
        "law_name": "건설기술 진흥법 시행규칙",
        "lsi_seq": "279455",
        "keywords": ["품질", "안전", "건설사업관리", "감리", "배치", "착공", "준공"],
    },
    {
        "trade": "건축",
        "law_name": "건축법 시행규칙",
        "lsi_seq": "283727",
        "keywords": ["건축", "대수선", "용도변경", "착공", "감리", "사용승인", "가설"],
    },
    {
        "trade": "소방",
        "law_name": "소방시설공사업법 시행규칙",
        "lsi_seq": "282735",
        "keywords": ["소방", "착공", "완공", "부분완공", "감리", "배치", "결과보고"],
    },
    {
        "trade": "소방",
        "law_name": "소방시설 설치 및 관리에 관한 법률 시행규칙",
        "lsi_seq": "280195",
        "keywords": ["소방", "자체점검", "점검", "이행", "외관", "보고"],
    },
    {
        "trade": "전기",
        "law_name": "전력기술관리법 시행규칙",
        "lsi_seq": "278995",
        "keywords": ["감리", "배치", "설계", "전력", "확인"],
    },
    {
        "trade": "기계설비",
        "law_name": "기계설비법 시행규칙",
        "lsi_seq": "285589",
        "keywords": ["기계설비", "사용", "검사", "착공", "유지관리", "성능점검"],
    },
    {
        "trade": "정보통신",
        "law_name": "정보통신공사업법 시행규칙",
        "lsi_seq": "272931",
        "keywords": ["정보통신", "사용전검사", "설계도", "감리", "착공"],
    },
    {
        "trade": "가스",
        "law_name": "고압가스 안전관리법 시행규칙",
        "lsi_seq": "278693",
        "keywords": ["고압가스", "기술검토", "중간검사", "완성검사", "정기검사", "신고", "신청"],
    },
    {
        "trade": "가스",
        "law_name": "액화석유가스의 안전관리 및 사업법 시행규칙",
        "lsi_seq": "282369",
        "keywords": ["액화석유가스", "LPG", "기술검토", "완성검사", "정기검사", "신고", "신청"],
    },
    {
        "trade": "가스",
        "law_name": "도시가스사업법 시행규칙",
        "lsi_seq": "285295",
        "keywords": ["도시가스", "공사계획", "사용", "검사", "신고", "신청"],
    },
    {
        "trade": "승강기",
        "law_name": "승강기 안전관리법 시행규칙",
        "lsi_seq": "268955",
        "keywords": ["승강기", "설치검사", "안전검사", "정밀안전", "신고", "신청"],
    },
    {
        "trade": "상하수도/수자원",
        "law_name": "하수도법 시행규칙",
        "lsi_seq": "285059",
        "keywords": ["하수", "배수설비", "개인하수", "공공하수", "사용", "신고", "신청"],
    },
    {
        "trade": "상하수도/수자원",
        "law_name": "수도법 시행규칙",
        "lsi_seq": "285093",
        "keywords": ["수도", "급수", "저수조", "검사", "신고", "신청"],
    },
    {
        "trade": "전기",
        "law_name": "전기안전관리법 시행규칙",
        "lsi_seq": "279943",
        "keywords": ["전기", "공사계획", "사용전검사", "사용전점검", "정기검사", "안전점검", "신고", "신청"],
    },
    {
        "trade": "전기",
        "law_name": "전기사업법 시행규칙",
        "lsi_seq": "278987",
        "keywords": ["전기", "전기사용", "공급", "공사계획", "신고", "신청"],
    },
    {
        "trade": "폐기물/환경",
        "law_name": "건설폐기물의 재활용촉진에 관한 법률 시행규칙",
        "lsi_seq": "278871",
        "keywords": ["건설폐기물", "처리계획", "배출", "신고", "신청", "보고"],
    },
    {
        "trade": "폐기물/환경",
        "law_name": "대기환경보전법 시행규칙",
        "lsi_seq": "283605",
        "keywords": ["대기", "배출시설", "방지시설", "비산먼지", "신고", "신청"],
    },
    {
        "trade": "폐기물/환경",
        "law_name": "물환경보전법 시행규칙",
        "lsi_seq": "282047",
        "keywords": ["폐수", "배출시설", "방지시설", "비점오염", "신고", "신청"],
    },
    {
        "trade": "건설공사 공통관리",
        "law_name": "건설산업기본법 시행규칙",
        "lsi_seq": "282375",
        "keywords": ["건설", "하도급", "대금", "시공", "신고", "신청"],
    },
    {
        "trade": "안전/노동",
        "law_name": "산업안전보건법 시행규칙",
        "lsi_seq": "271485",
        "keywords": ["안전", "보건", "유해", "위험", "공사", "계획", "신고", "신청"],
    },
    {
        "trade": "소방",
        "law_name": "위험물안전관리법 시행규칙",
        "lsi_seq": "262765",
        "keywords": ["위험물", "제조소", "저장소", "취급소", "완공검사", "신고", "신청"],
    },
]


def slugify(value: str) -> str:
    value = re.sub(r'[\\/:*?"<>|]+', "_", value)
    value = re.sub(r"\s+", "_", value).strip("._ ")
    return value or "untitled"


def request_bytes(url: str, data: bytes | None = None) -> tuple[bytes, Any]:
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124",
            "Referer": "https://www.law.go.kr/",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(), response.headers


def fetch_byl_list(lsi_seq: str, ef_yd: str) -> list[dict[str, Any]]:
    params = {
        "lsiSeq": lsi_seq,
        "mode": "8",
        "chapNo": "1",
        "nwYn": "1",
        "efYd": ef_yd,
        "gubun": "save",
    }
    url = f"{LAW_GO_KR}/LSW/joListRInc.do?{urllib.parse.urlencode(params)}"
    data, _ = request_bytes(url)
    text = data.decode("utf-8", errors="replace").strip()
    if not text.startswith("["):
        return []
    rows = json.loads(text)
    return rows if isinstance(rows, list) else []


def is_hwp(data: bytes) -> bool:
    return data.startswith(bytes.fromhex("d0 cf 11 e0 a1 b1 1a e1"))


def fetch_han_fl_seq(byl_seq: str) -> str:
    params = {"bylSeq": byl_seq, "chrClsCd": "010202"}
    url = f"{LAW_GO_KR}/LSW/lsBylContentsInfoR.do?{urllib.parse.urlencode(params)}"
    data, _ = request_bytes(url)
    text = data.decode("utf-8", errors="replace")
    match = re.search(r'id="hanFlSeq"\s+name="hanFlSeq"\s+value="(\d+)"', text)
    return match.group(1) if match else ""


def relevant(row: dict[str, Any], keywords: list[str], collect_all: bool) -> bool:
    if collect_all:
        return True
    title = row.get("joTit", "")
    return any(keyword in title for keyword in keywords)


def download_law(law: dict[str, Any], output_dir: Path, ef_yd: str, collect_all: bool) -> list[dict[str, Any]]:
    rows = fetch_byl_list(law["lsi_seq"], ef_yd)
    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        hwp_path = row.get("bylFlPth", "")
        title = row.get("joTit", "")
        byl_seq = str(row.get("joLink", ""))
        if not byl_seq:
            continue
        if not relevant(row, law["keywords"], collect_all):
            continue

        out_dir = output_dir / slugify(law["trade"]) / slugify(law["law_name"])
        out_name = f"{index:03d}_{slugify(title)}.hwp"
        out_path = out_dir / out_name
        han_fl_seq = ""
        url = ""
        if out_path.exists():
            data = out_path.read_bytes()
            results.append(
                {
                    "trade": law["trade"],
                    "law_name": law["law_name"],
                    "lsi_seq": law["lsi_seq"],
                    "title": title,
                    "jo_link": byl_seq,
                    "byl_img_fl_seq": row.get("bylImgFlSeq", ""),
                    "han_fl_seq": "",
                    "byl_fl_path": hwp_path,
                    "url": "",
                    "status": "downloaded" if is_hwp(data) else "downloaded_non_hwp_signature",
                    "content_type": "existing-file",
                    "path": str(out_path),
                    "bytes": len(data),
                    "error": "",
                }
            )
            continue
        try:
            han_fl_seq = fetch_han_fl_seq(byl_seq)
            if not han_fl_seq:
                raise RuntimeError("hanFlSeq not found")
            url = f"{LAW_GO_KR}/LSW/flDownload.do?flSeq={han_fl_seq}"
            data, headers = request_bytes(url)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)
            status = "downloaded" if is_hwp(data) else "downloaded_non_hwp_signature"
            error = ""
            content_type = headers.get("Content-Type", "")
        except Exception as exc:
            data = b""
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            content_type = ""

        results.append(
            {
                "trade": law["trade"],
                "law_name": law["law_name"],
                "lsi_seq": law["lsi_seq"],
                "title": title,
                "jo_link": byl_seq,
                "byl_img_fl_seq": row.get("bylImgFlSeq", ""),
                "han_fl_seq": han_fl_seq,
                "byl_fl_path": hwp_path,
                "url": url,
                "status": status,
                "content_type": content_type,
                "path": str(out_path) if data else "",
                "bytes": len(data),
                "error": error,
            }
        )
        time.sleep(0.15)
    return results


def write_manifest(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "download_manifest.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path = output_dir / "download_manifest.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()) if rows else ["status"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="tmp/agency_submission_law_byl_hwp_downloads")
    parser.add_argument("--ef-yd", default="20260511")
    parser.add_argument("--all", action="store_true", help="download every HWP appendix/form for target laws")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    all_rows: list[dict[str, Any]] = []
    for law in TARGET_LAWS:
        law_rows = download_law(law, output_dir, args.ef_yd, args.all)
        print(f"{law['law_name']}: {len(law_rows)}")
        all_rows.extend(law_rows)

    write_manifest(output_dir, all_rows)
    print(f"records={len(all_rows)}")
    print(f"downloaded={sum(1 for row in all_rows if row['status'] == 'downloaded')}")
    print(f"non_hwp_signature={sum(1 for row in all_rows if row['status'] == 'downloaded_non_hwp_signature')}")
    print(f"failed={sum(1 for row in all_rows if row['status'] == 'failed')}")
    print(f"output_dir={output_dir}")


if __name__ == "__main__":
    main()
