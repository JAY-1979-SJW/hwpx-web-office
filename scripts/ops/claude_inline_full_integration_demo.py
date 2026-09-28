"""Claude inline AI — 한 HWPX에 5 도메인 통합 자동 채움.

CLAUDE.md §9 + §10 준수:
- 외부 API 호출 0
- Claude(이 assistant) inline 판단을 코드 내 callable로 inject
- 신규 도구 작성 0 (§11-6) — 기존 자재 5종 호출만

도메인 (5):
  ① 본문 라벨 입력 (set_cells)
  ② 헤더 텍스트 (apply_page_numbering)
  ③ 도장 이미지 (insert_generated_png_picture + content.hpf)
  ④ 메타데이터 (apply_document_metadata)
  ⑤ 차트 PNG (generate_bar_chart_png + insert)

검증: V1~V7 + V10/V11/V12/V14 통합
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts/hwpx"))


# 1x1 sample PNG (도장 대용)
_SAMPLE_PNG_HEX = (
    "89504e470d0a1a0a0000000d49484452000000010000000108020000007e9b55"
    "5500000010494441545829636bdcffff7f060081020fdbc8f80700"
    "fd80e6730000000049454e44ae426082"
)


# ── Claude inline 판단 5 도메인 ──────────────────────────────────────

# D1 라벨 사전 (2026-05-20 확장): corpus 100건 채굴로 미매칭 상위 30개 분석 후
# 신규 카테고리 추가. 순서가 판정 우선순위다 — 위에서부터 첫 매치를 쓴다.
_LABEL_JUDGE_RULES: list[tuple] = [
    # 연락처 — 팩스는 FAX로 분리 (W-02)
    (lambda s: "팩스" in s, ("FAX", "02-1234-5679", 0.93)),
    (lambda s: "전화" in s or "연락처" in s, ("PHONE", "02-1234-5678", 0.95)),
    # 날짜 — semantic 키는 기존 START_DATE 유지 (W-01 하류 호환)
    # 공사기간·계약기간도 DATE류로 흡수 (W-04)
    (
        lambda s: any(
            k in s
            for k in (
                "일자",
                "년월일",
                "연월일",
                "착공일",
                "준공일",
                "접수일",
                "허가일",
                "신청일",
                "제출일",
                "공사기간",
                "계약기간",
                "용역기간",
                "기간",
            )
        ),
        ("START_DATE", "2026-05-20", 0.92),
    ),
    # 주소
    (
        lambda s: any(k in s for k in ("주소", "소재지", "위치", "현장위치")),
        ("ADDRESS", "서울특별시 강남구 테헤란로 123", 0.93),
    ),
    # 회사·발주처
    (
        lambda s: any(
            k in s
            for k in (
                "소속",
                "사업장",
                "회사",
                "상호",
                "신청인",
                "신고인",
                "건축주",
                "발주처",
                "수급인",
                "도급인",
            )
        ),
        ("COMPANY_NAME", "(주)○○건설", 0.90),
    ),
    # 대표·담당자 — semantic 키는 기존 REPRESENTATIVE_NAME 유지 (W-01)
    (
        lambda s: any(
            k in s
            for k in (
                "대표자",
                "대표",
                "성명",
                "담당자",
                "현장대리인",
                "현장소장",
                "책임시공",
                "기술관리",
                "소방기술자",
            )
        ),
        ("REPRESENTATIVE_NAME", "홍길동", 0.90),
    ),
    # 사업자 등록번호
    (
        lambda s: any(k in s for k in ("사업자", "등록번호")),
        ("BUSINESS_REGISTRATION_NUMBER", "123-45-67890", 0.93),
    ),
    # 사업명·공사명·용역명
    (
        lambda s: any(k in s for k in ("공사명", "사업명", "용역명", "과업명", "시설명", "현장명")),
        ("PROJECT_NAME", "○○건축 신축공사", 0.93),
    ),
    # 행정 처리 번호·접수
    (
        lambda s: any(k in s for k in ("접수번호", "허가번호", "관리번호", "문서번호", "신고번호")),
        ("DOC_NUMBER", "2026-001", 0.90),
    ),
    (lambda s: "접수" in s and "번호" not in s, ("ADMIN_STATUS", "접수완료", 0.85)),
    # 처리 단계
    (
        lambda s: any(k in s for k in ("처리절차", "처리상태", "처리결과", "결재", "검토", "완료")),
        ("PROCESS_STAGE", "검토완료", 0.85),
    ),
    # 첨부서류·종류·비고 — V2(no leak)를 위해 distinctive 값 사용 (W-05)
    # 공통어인 "특이사항 없음"/"일반"은 substring leak 위험이 커서
    # 토큰 단위 distinctive 어휘를 부여
    (lambda s: "첨부서류" in s or "구비서류" in s, ("ATTACHMENTS", "사업자등록증 사본 1부", 0.85)),
    (lambda s: s.strip() in {"비고", "기타", "참고"}, ("NOTE", "비고기재없음(2026)", 0.80)),
    (lambda s: s.strip() in {"종류", "구분"}, ("CATEGORY", "일반구분(공통)", 0.80)),
    # 자격증·번호
    (lambda s: "자격증" in s or "면허" in s, ("LICENSE_NUMBER", "L-2026-001", 0.85)),
    # 수량·면적 — V2 substring leak 회피 위해 distinctive 값 사용
    (
        lambda s: any(k in s for k in ("수량", "개수", "면적", "m2", "㎡", "연면적", "건축면적")),
        ("QUANTITY", "1,234.5㎡", 0.85),
    ),
    # 기관명 — "공단"/"협회"만 사용. "공사" 단독은 사업명/공사기간과
    # 중복 위험이 커 INSTITUTION 가드에서 제외 (W-03)
    (lambda s: any(k in s for k in ("공단", "협회")), ("INSTITUTION_NAME", "한국OO공단", 0.80)),
    # 페이지/방향 마커
    (lambda s: s.strip() in {"앞쪽", "뒤쪽", "표지", "본문"}, None),
    # 신고
    (lambda s: s.strip() == "신고", ("ADMIN_STATUS", "신고완료", 0.80)),
    # 검사·점검 종류
    (
        lambda s: any(k in s for k in ("검사종류", "점검", "시험")),
        ("INSPECTION_TYPE", "정기검사", 0.85),
    ),
    # 단일 글자 / 너무 짧음
    (lambda s: len(s.strip()) <= 1, None),
]


def claude_judge_labels(label: str) -> tuple[str, str, float] | None:
    """본문 라벨 → (semantic, value, confidence). 외부 API 없음."""
    # UI 마커·화살표·빈문자 — 입력 라벨 아님
    if not label or label.strip() in {"", "▼", "▶", "◀", "‣", "▷", "▽"}:
        return None
    for predicate, result in _LABEL_JUDGE_RULES:
        if predicate(label):
            return result
    return None


def claude_judge_header_footer() -> dict:
    return {
        "section_index": 0,
        "start_page": 1,
        "page_starts_on": "BOTH",
        "page_number_mode": "STATIC_TEXT",
        "visible_header": True,
        "header_text": "○○건축 안전관리계획서",
        "header_align": "CENTER",
        "visible_footer": True,
        "footer_text": "Page {page}",
        "footer_align": "CENTER",
    }


def claude_judge_metadata() -> dict:
    return {
        "title": "○○건축 안전관리계획서",
        "creator": "(주)○○건설",
        "subject": "건축물 검사 확인증",
        "description": "Claude inline 통합 자동 채움 결과",
        "keywords": ["검사", "확인증", "통합"],
        "language": "ko",
    }


def claude_judge_chart() -> dict:
    return {
        "title": "월별 검측 통계",
        "series": [
            {"label": "1월", "value": 12},
            {"label": "2월", "value": 18},
            {"label": "3월", "value": 25},
            {"label": "4월", "value": 30},
        ],
    }


# ── partial-success 헬퍼 (테스트 가능 단위) ──────────────────────────


def _filter_applied_cells_by_coord(
    set_cells: list[dict], operations: list[dict]
) -> tuple[list[dict], list[dict]]:
    """operations를 (table,row,col) 좌표로 매칭해 applied/rejected 분리.

    동일 라벨이 여러 셀에 있어도 좌표 기준이므로 semantic 추론에 의존하지
    않는다 (W-06). 매칭 실패한 셀은 rejected에 op status를 함께 기록.
    """
    op_by_key: dict[tuple, dict] = {}
    op_by_partial: dict[tuple, dict] = {}
    for op in operations:
        if not isinstance(op, dict):
            continue
        t = op.get("table_index")
        r = op.get("row_index")
        c = op.get("col_index")
        full_key = (t, r, c)
        # 키 충돌(같은 좌표 중복 op) 시 PASS를 우선 유지
        if full_key not in op_by_key or op.get("status") == "PASS":
            op_by_key[full_key] = op
        # 실패 op는 c가 None일 수 있어 (t,r,None) / (t,None,None)
        # 부분 키로도 등록 — set_cells의 원래 좌표와 매칭하기 위함
        for partial in ((t, r, None), (t, None, None)):
            if partial not in op_by_partial and op.get("status") != "PASS":
                op_by_partial[partial] = op
    applied: list[dict] = []
    rejected: list[dict] = []
    for cell in set_cells:
        key = (cell["table"], cell["row"], cell["col"])
        op = op_by_key.get(key)
        if op is None:
            # fallback — invalid 좌표 op(col=None 등) 매칭
            op = (
                op_by_partial.get((cell["table"], cell["row"], None))
                or op_by_partial.get((cell["table"], None, None))
                or {}
            )
        if op.get("status") == "PASS":
            applied.append(cell)
        else:
            rejected.append({**cell, "status": op.get("status", "UNMATCHED")})
    return applied, rejected


def _summarize_apply_text(set_cells: list[dict], applied: list[dict], rejected: list[dict]) -> dict:
    """PASS/PARTIAL/FAIL/SKIPPED 4-way 분기."""
    total = len(set_cells)
    applied_n = len(applied)
    rejected_statuses = [r.get("status", "UNKNOWN") for r in rejected]
    if total == 0:
        return {"status": "SKIPPED", "cellsApplied": 0, "cellsFailed": 0}
    if applied_n == total:
        return {"status": "PASS", "cellsApplied": applied_n, "cellsFailed": 0}
    if applied_n > 0:
        return {
            "status": "PARTIAL",
            "cellsApplied": applied_n,
            "cellsFailed": total - applied_n,
            "failedExamples": rejected_statuses[:3],
        }
    return {
        "status": "FAIL",
        "cellsApplied": 0,
        "cellsFailed": total,
        "failedExamples": rejected_statuses[:3],
    }


def _decide_verify7(
    applied_cells: list[dict], source_hwpx: Path, out_path: Path, verify_one_fn
) -> dict:
    """applied=∅ 시 verify7 vacuous PASS 방지하고 SKIPPED 명시 (W-07)."""
    expected = [
        {"table": c["table"], "row": c["row"], "col": c["col"], "value": c["value"]}
        for c in applied_cells
    ]
    if not expected:
        return {
            "status": "SKIPPED",
            "reason": "applied operations empty — verify7 vacuous PASS 방지",
        }
    return verify_one_fn(src_path=source_hwpx, out_path=out_path, expected_set_cells=expected)


# ── 통합 demo ──────────────────────────────────────────────────────


def run_full_integration(source_hwpx: Path, sandbox_dir: Path) -> dict:
    from hwpx_chart_png import generate_bar_chart_png
    from hwpx_header_footer_ops import apply_page_numbering
    from hwpx_image_ops import add_content_manifest_item
    from hwpx_metadata_ops import apply_document_metadata
    from hwpx_package import HwpxPackage
    from hwpx_visible_image_ops import insert_generated_png_picture
    from scripts.hwpx import hwpx_edit_tool as edit_tool
    from scripts.hwpx.ai_proposal import target_resolver as tr
    from scripts.hwpx.parser.parser_engine import parse_hwpx_v2

    sandbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = sandbox_dir / f"{source_hwpx.stem}__full_inline.hwpx"
    stamp_png = sandbox_dir / "stamp.png"
    chart_png = sandbox_dir / "chart.png"
    stamp_png.write_bytes(bytes.fromhex(_SAMPLE_PNG_HEX.replace(" ", "")))

    # ──① 본문 라벨 입력 ─────────────────────────────
    parser_result = parse_hwpx_v2(source_hwpx)
    tid_to_idx = {tbl.tableId: i for i, tbl in enumerate(parser_result.tables)}
    set_cells = []
    seen_keys = set()
    proposals_count = 0
    for slot in parser_result.inputSlotCandidates:
        label = (getattr(slot, "labelText", "") or "").strip()
        norm = tr.normalize_label(label)
        if not norm:
            continue
        tbl = getattr(slot, "tableId", "")
        if tbl not in tid_to_idx:
            continue
        t_idx = tid_to_idx[tbl]
        row = getattr(slot, "row", 0)
        col = getattr(slot, "col", 0)
        cell_key = f"t{t_idx}:r{row}:c{col}"
        if cell_key in seen_keys:
            continue
        seen_keys.add(cell_key)
        judgment = claude_judge_labels(norm)
        if judgment is None:
            continue
        semantic, value, conf = judgment
        proposals_count += 1
        # InputSlotCandidate.row/col = target input cell (label 셀 아님)
        # 정확한 위치 사용 — col+1 단순화 제거
        set_cells.append({"table": t_idx, "row": row, "col": col, "value": value})

    # apply set_cells — 헬퍼로 partial-success 산출 (W-06)
    applied_cells: list[dict] = []
    rejected_cells: list[dict] = []
    if set_cells:
        r = edit_tool.apply_edit_plan(
            source_hwpx, out_path, {"set_cells": set_cells}, dry_run=False
        )
        applied_cells, rejected_cells = _filter_applied_cells_by_coord(
            set_cells, r.get("operations", [])
        )
    else:
        shutil.copy2(source_hwpx, out_path)
    apply_text_result = _summarize_apply_text(set_cells, applied_cells, rejected_cells)

    # ──② 헤더·푸터 ─────────────────────────────────
    package = HwpxPackage(out_path)
    hf_spec = claude_judge_header_footer()
    hf_result = apply_page_numbering(package, hf_spec)

    # ──③ 도장 이미지 ───────────────────────────────
    stamp_entry = "BinData/claude_full_stamp.png"
    img_result = insert_generated_png_picture(
        package,
        image_path=stamp_png,
        image_entry=stamp_entry,
        section_index=0,
        width=4000,
        height=4000,
    )
    add_content_manifest_item(package.entries, stamp_entry)

    # ──④ 메타데이터 ────────────────────────────────
    meta_spec = claude_judge_metadata()
    meta_result = apply_document_metadata(package, meta_spec)

    # ──⑤ 차트 PNG ─────────────────────────────────
    chart_spec = claude_judge_chart()
    generate_bar_chart_png(chart_spec, chart_png)
    chart_entry = "BinData/claude_full_chart.png"
    chart_insert = insert_generated_png_picture(
        package,
        image_path=chart_png,
        image_entry=chart_entry,
        section_index=0,
        width=12000,
        height=9000,
    )
    add_content_manifest_item(package.entries, chart_entry)

    package.write_package(out_path)

    # ── 통합 검증 ────────────────────────────────────
    from scripts.ops.verify_e2e_input_precision import verify_one

    verify7 = _decide_verify7(applied_cells, source_hwpx, out_path, verify_one)

    # 도메인별 byte-grep 검증
    domain_checks = {}
    try:
        blob = ""
        with zipfile.ZipFile(str(out_path)) as z:
            names = z.namelist()
            for n in names:
                if n.endswith(".xml") or n.endswith(".hpf"):
                    blob += z.read(n).decode("utf-8", "ignore")
        domain_checks["V10_header"] = hf_spec["header_text"] in blob
        domain_checks["V11_stamp_entry"] = stamp_entry in names
        domain_checks["V11_stamp_hpf"] = stamp_entry in blob
        domain_checks["V12_meta_title"] = meta_spec["title"] in blob
        domain_checks["V12_meta_creator"] = meta_spec["creator"] in blob
        domain_checks["V14_chart_entry"] = chart_entry in names
        domain_checks["V14_chart_hpf"] = chart_entry in blob
    except Exception as e:  # ruff: ignore[blind-except] (검증 스크립트 — 실패해도 err 기록 후 계속)
        domain_checks["err"] = str(e)[:100]

    return {
        "src": str(source_hwpx),
        "output": str(out_path),
        "domain_1_label_input": {
            "proposals": proposals_count,
            "setCellsBuilt": len(set_cells),
            "applyStatus": apply_text_result.get("status"),
            "cellsApplied": apply_text_result.get("cellsApplied", 0),
            "cellsRejected": apply_text_result.get("cellsFailed", 0),
            "cellsSkipped": 0 if set_cells else len(set_cells),
            "rejectedStatuses": [r.get("status") for r in rejected_cells],
        },
        "domain_2_header_footer": {
            "status": hf_result.get("status", "OK"),
            "header": hf_spec["header_text"],
        },
        "domain_3_image_stamp": {"status": img_result.get("status"), "entry": stamp_entry},
        "domain_4_metadata": {"status": meta_result.get("status"), "title": meta_spec["title"]},
        "domain_5_chart": {
            "status": chart_insert.get("status"),
            "entry": chart_entry,
            "pngBytes": chart_png.stat().st_size,
        },
        "verify7": {k: v for k, v in verify7.items() if k.startswith("V") or k == "verdict"},
        "domain_checks": domain_checks,
    }


def main():
    import sqlite3

    conn = sqlite3.connect("data/recognition_corpus/corpus.sqlite3")
    row = conn.execute("""
        SELECT d.source_path FROM hwpx_documents d
        JOIN document_classifications c ON c.document_id=d.document_id
        WHERE d.inventory_status='FOUND'
          AND c.document_type='fillable_form'
          AND d.file_size BETWEEN 30000 AND 80000
        ORDER BY d.first_seen_at LIMIT 1
    """).fetchone()
    conn.close()
    path = PROJECT_ROOT / row[0]
    if not path.is_file():
        print(json.dumps({"error": "source missing"}))
        return 1
    sandbox = PROJECT_ROOT / "data/drafts/claude_inline_full_sandbox"
    out = run_full_integration(path, sandbox)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
