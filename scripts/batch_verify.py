#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/batch_verify.py

실제 공사 내역서 파일들을 Java parse-workbook으로 일괄 검증.

실행:
  python scripts/batch_verify.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

JAVA_HOME = r"C:\Program Files\Microsoft\jdk-21.0.10.7-hotspot"
ENGINE_DIR = Path(__file__).resolve().parents[1]
ENGINE_BIN = ENGINE_DIR / "build" / "install" / "office-analysis-engine" / "bin" / "office-analysis-engine.bat"

# ── 검증 대상 파일 목록 ────────────────────────────────────────────────────────
BASE = Path(r"C:\Users\skyjw\OneDrive\03. PYTHON\01. 기성내역서 자동")

TEST_FILES = [
    # (파일경로, 설명, 기대_detail_시트수)
    (BASE / "계약내역서(뇌병변장애인비젼센터리모델링소방공사)0404.xlsx",
     "계약내역서(소방)", 1),

    (BASE / "04. 기성내역서(뇌병변장애인비젼센터리모델링소방공사).xlsx",
     "기성내역서(소방)", 1),

    (BASE / "uploads" / "계약내역서(뇌병변장애인비젼센터리모델링소방공사)0404.xlsx",
     "계약내역서(소방)-uploads", 1),

    (BASE / "uploads" / "240607_내역서(분당 어린이종합지원센터 건립 소방공사)-낙찰률적용.xlsx",
     "내역서(분당어린이센터소방)", 1),

    (BASE / "uploads" / "5-1 원가계산조서(24-1107)-소방-기갑여다.xlsx",
     "원가계산조서(소방)", 1),

    (BASE / "uploads" / "승민F&G계약_위례신도시 주차장13호 및 노인복지회관 소방공사.xlsx",
     "계약내역서(위례신도시소방)", 1),

    (BASE / "temp" / "서부 청소년 5 (소방) 내역서(기계+전기)n683_일반,이윤,관급 조정(24.02.26).xlsx",
     "내역서(서부청소년소방)", 1),

    (BASE / "output" / "공종별내역서(기계소방)_개선버전.xlsx",
     "공종별내역서(기계소방)", 1),

    (BASE / "output" / "공종별내역서(전기소방)_개선버전.xlsx",
     "공종별내역서(전기소방)", 1),

    (BASE / "output" / "기성내역서_1차_20250826_214408.xlsx",
     "기성내역서_1차(출력본)", 1),
]


# ── 파싱 실행 ──────────────────────────────────────────────────────────────────

def run_parse(file_path: Path) -> dict | None:
    env = os.environ.copy()
    env["JAVA_HOME"] = JAVA_HOME
    env["PATH"] = os.path.join(JAVA_HOME, "bin") + os.pathsep + env.get("PATH", "")
    env["JAVA_TOOL_OPTIONS"] = "-Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8"

    try:
        result = subprocess.run(
            [str(ENGINE_BIN), "parse-workbook", str(file_path)],
            capture_output=True, text=True, timeout=60, env=env,
            encoding="utf-8", errors="replace"
        )
        if result.returncode != 0 and not result.stdout.strip():
            return {"_error": result.stderr.strip()[:300]}
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {"_error": f"JSON parse fail: {e} | stdout={result.stdout[:200]}"}
    except subprocess.TimeoutExpired:
        return {"_error": "TIMEOUT"}
    except Exception as e:
        return {"_error": str(e)}


# ── 결과 분석 ─────────────────────────────────────────────────────────────────

def analyze(data: dict, expected_detail: int) -> dict:
    if "_error" in data:
        return {"verdict": "FAIL", "reason": data["_error"], "detail_count": 0, "item_count": 0, "issues": []}

    sheets = data.get("sheets", [])
    total_sheets = len(sheets)
    detail_sheets = [s for s in sheets if s.get("sheet_role") == "detail_sheet"]
    total_items = sum(len(s.get("items", [])) for s in detail_sheets)

    issues = []

    # 역할 판정 점검
    if len(detail_sheets) == 0 and expected_detail > 0:
        issues.append("MISS_DETAIL: detail_sheet 0건 (예상 {})".format(expected_detail))

    # 품목 0건
    if len(detail_sheets) > 0 and total_items == 0:
        issues.append("NO_ITEMS: detail_sheet 있으나 품목 0건")

    # 헤더 미감지
    for s in detail_sheets:
        if s.get("header_row_index", -1) == -1:
            issues.append(f"NO_HEADER: {s['sheet_name']}")
        col_map = s.get("column_map") or {}
        missing_cols = [c for c in ["item_name", "unit", "qty", "unit_price", "amount"] if c not in col_map]
        if missing_cols:
            issues.append(f"MISS_COL({s['sheet_name']}): {missing_cols}")

    # summary/unknown이 detail이어야 할 가능성 점검
    for s in sheets:
        if s.get("sheet_role") in ("unknown", "summary_sheet"):
            # 헤더는 있는데 detail로 판정 안된 경우
            if s.get("header_row_index", -1) >= 0:
                col_map = s.get("column_map") or {}
                if "item_name" in col_map and ("unit_price" in col_map or "amount" in col_map):
                    issues.append(f"MISS_CLASSIFY({s['sheet_name']}): {s['sheet_role']}로 분류됨, detail 후보")

    if not issues and total_items > 0:
        verdict = "PASS"
    elif not issues and total_items == 0 and len(detail_sheets) == 0:
        verdict = "WARN"  # 구조적으로 실패는 아니지만 품목 없음
    elif issues:
        verdict = "WARN" if total_items > 0 else "FAIL"
    else:
        verdict = "WARN"

    return {
        "verdict": verdict,
        "total_sheets": total_sheets,
        "detail_count": len(detail_sheets),
        "item_count": total_items,
        "issues": issues,
        "detail_sheets": [s["sheet_name"] for s in detail_sheets],
    }


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    if not ENGINE_BIN.exists():
        print(f"[ERROR] 엔진 바이너리 없음: {ENGINE_BIN}")
        print("office-analysis-engine 폴더에서 ./gradlew installDist 실행 필요")
        sys.exit(1)

    results = []
    for file_path, label, expected_detail in TEST_FILES:
        if not file_path.exists():
            results.append({
                "label": label,
                "file": file_path.name,
                "verdict": "SKIP",
                "reason": "파일 없음",
                "detail_count": 0,
                "item_count": 0,
                "issues": [],
            })
            continue

        print(f"  파싱: {label}...", end="", flush=True)
        data = run_parse(file_path)
        analysis = analyze(data, expected_detail)
        analysis["label"] = label
        analysis["file"] = file_path.name
        print(f" {analysis['verdict']} (시트:{analysis.get('total_sheets','?')} detail:{analysis['detail_count']} 품목:{analysis['item_count']}건)")
        results.append(analysis)

    print_report(results)


def print_report(results):
    print("\n" + "="*80)
    print("파일별 파싱 검증 결과")
    print("="*80)

    header = f"{'No':>3} {'파일명':<40} {'판정':>6} {'시트':>4} {'detail':>6} {'품목':>6}  이슈"
    print(header)
    print("-"*80)

    all_issues = []
    for i, r in enumerate(results, 1):
        issues_str = "; ".join(r.get("issues", []))[:50] if r.get("issues") else "-"
        print(f"{i:>3} {r['file'][:39]:<40} {r['verdict']:>6} "
              f"{r.get('total_sheets', 0):>4} {r['detail_count']:>6} {r['item_count']:>6}  {issues_str}")
        all_issues.extend(r.get("issues", []))

    # 공통 실패 패턴
    print("\n" + "="*80)
    print("공통 실패 패턴 분석")
    print("="*80)
    from collections import Counter
    pattern_keys = {
        "MISS_DETAIL": "detail_sheet 미감지",
        "NO_ITEMS": "품목 0건 (헤더 있음)",
        "NO_HEADER": "헤더 미감지",
        "MISS_COL": "컬럼 매핑 누락",
        "MISS_CLASSIFY": "역할 오분류 (detail→unknown/summary)",
    }
    pattern_counts = Counter()
    for issue in all_issues:
        for key in pattern_keys:
            if issue.startswith(key):
                pattern_counts[key] += 1
    if pattern_counts:
        for k, cnt in pattern_counts.most_common():
            print(f"  {k:<20}: {cnt}건  -- {pattern_keys.get(k, '')}")
    else:
        print("  공통 실패 패턴 없음")

    # 최종 판정
    pass_cnt = sum(1 for r in results if r["verdict"] == "PASS")
    warn_cnt = sum(1 for r in results if r["verdict"] == "WARN")
    fail_cnt = sum(1 for r in results if r["verdict"] == "FAIL")
    skip_cnt = sum(1 for r in results if r["verdict"] == "SKIP")
    total    = len(results)

    print(f"\n요약: PASS={pass_cnt} WARN={warn_cnt} FAIL={fail_cnt} SKIP={skip_cnt} / {total}건")

    if fail_cnt == 0 and pass_cnt >= total * 0.6:
        final = "PASS"
    elif fail_cnt <= total * 0.3:
        final = "WARN"
    else:
        final = "FAIL"
    print(f"최종 판정: {final}")


if __name__ == "__main__":
    main()
