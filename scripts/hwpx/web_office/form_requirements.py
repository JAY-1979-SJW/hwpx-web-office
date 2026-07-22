"""서식 해부 — 무엇을 적고, 무엇을 첨부하고, 어디에 내는지 구조화 추출.

정부 별지서식은 표 안에 라벨/값 쌍으로 행정정보를 담는다:
    [첨부서류] [1. …  2. …]      [처리기간] [7일]     [수수료] [없음]
    「○○법」 제○조 …            ○○부장관  귀하

이 모듈은 파싱된 HWPX(documentModel + renderPayload)에서 다음을 뽑는다:
    attachments   첨부/구비/제출 서류 목록(번호·가나다 항목 분해)
    processingTime 처리기간
    fee            수수료
    legalBasis     근거법령(「법령」 + 조항)
    submitTo       제출처(장관·시장·청장 …)
    inputFields    입력해야 할 빈칸 라벨(기존 추출 재사용)

순수함수 — 파일/DB 비의존. 라벨의 "값"은 오른쪽 인접 셀을 우선하고 없으면 아래 셀을 본다
(한국 관공서 서식의 통상 배치).
"""
from __future__ import annotations

import re
from typing import Any

# 라벨 인식 (공백·중점 변형 허용)
_L_ATTACH = re.compile(r"^(첨부|구비|제출)\s*서류")
_L_TIME = re.compile(r"^처리\s*기간")
_L_FEE = re.compile(r"^수수료")
_L_PROC = re.compile(r"^처리\s*절차")

_LAW = re.compile(r"「([^」]{2,60})」\s*(제\s*\d+조(?:의\s*\d+)?(?:\s*제\s*\d+항)?)?")
_SUBMIT = re.compile(
    r"([가-힣\s]{2,30}?(?:장관|처장|청장|위원장|시장|군수|구청장|원장|사장|이사장))"
    r"\s*(?:귀하|귀중)?\s*$")
# 항목 분해: "1." "2)" "가." "①" 앞에서 자른다
_ITEM_SPLIT = re.compile(r"(?=(?:\d{1,2}\s*[.)]|[가-힣]\s*[.)]|[①-⑮]))")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _grid(table: dict) -> dict[tuple[int, int], dict]:
    return {(c["row"], c["col"]): c for c in table.get("cells", [])
            if not c.get("isCoveredByMerge")}


_LABELISH = re.compile(
    r"^(첨부|구비|제출)\s*서류|^처리\s*기간|^수수료|^처리\s*절차|^접수\s*(번호|일)|"
    r"^담당\s*(자|부서)|^신청인|^성명|^주소|^대표자|^명칭|^전화|^등록번호|^신청\s*내용")


def _inline_value(text: str, label_rx: re.Pattern) -> str:
    """'수수료 없음' 처럼 라벨과 값이 한 셀에 붙은 경우 값만 떼어낸다."""
    m = label_rx.match(text)
    if not m:
        return ""
    rest = text[m.end():].lstrip(" :·|")
    return rest.strip() if len(rest.strip()) >= 1 else ""


def _value_for(grid: dict, cell: dict, label_rx: re.Pattern | None = None,
               max_span: int = 6) -> str:
    """라벨 셀의 값 — 같은 셀 내 인라인 값 → 오른쪽 인접 → 아래.
    다른 라벨처럼 보이는 셀은 값이 아니므로 건너뛴다(오추출 방지)."""
    if label_rx is not None:
        inline = _inline_value(_norm(cell.get("text")), label_rx)
        if inline:
            return inline
    r, c = cell["row"], cell["col"]
    for dc in range(1, max_span + 1):
        v = grid.get((r, c + dc))
        t = _norm(v.get("text")) if v else ""
        if not t:
            continue
        if _LABELISH.match(t):      # 옆 칸이 또 다른 라벨이면 값 아님
            continue
        return t
    for dr in range(1, 3):
        v = grid.get((r + dr, c))
        t = _norm(v.get("text")) if v else ""
        if t and not _LABELISH.match(t):
            return t
    return ""


def split_items(text: str) -> list[str]:
    """번호/가나다/원문자 항목을 개별 서류로 분해."""
    t = _norm(text)
    if not t:
        return []
    parts = [p.strip(" .·,") for p in _ITEM_SPLIT.split(t) if p and p.strip(" .·,")]
    # 분해가 안 되면(단일 항목) 통째로
    items = [re.sub(r"^(?:\d{1,2}\s*[.)]|[가-힣]\s*[.)]|[①-⑮])\s*", "", p).strip()
             for p in parts]
    items = [i for i in items if len(i) >= 2]
    return items or ([t] if len(t) >= 2 else [])


def extract_requirements(doc_model: dict, render_payload: dict) -> dict[str, Any]:
    """서식 1건에서 행정 요건을 구조화 추출."""
    attachments: list[str] = []
    processing_time = fee = submit_to = ""
    procedure = ""
    laws: list[str] = []

    all_text: list[str] = []
    for table in render_payload.get("tables", []):
        grid = _grid(table)
        for cell in grid.values():
            t = _norm(cell.get("text"))
            if not t:
                continue
            all_text.append(t)
            if _L_ATTACH.match(t) and not attachments:
                attachments = split_items(_value_for(grid, cell, _L_ATTACH))
            elif _L_TIME.match(t) and not processing_time:
                processing_time = _value_for(grid, cell, _L_TIME)
            elif _L_FEE.match(t) and not fee:
                fee = _value_for(grid, cell, _L_FEE)
            elif _L_PROC.match(t) and not procedure:
                procedure = _value_for(grid, cell, _L_PROC)

    for p in doc_model.get("paragraphs", []):
        t = _norm("".join(r.get("text", "") for r in p.get("runs", [])))
        if t:
            all_text.append(t)

    joined = " ".join(all_text)
    for m in _LAW.finditer(joined):
        law = m.group(1).strip()
        art = _norm(m.group(2) or "")
        entry = f"{law} {art}".strip()
        if entry not in laws:
            laws.append(entry)

    for t in all_text:
        m = _SUBMIT.search(t)
        if m:
            submit_to = _norm(m.group(1))
            break

    fields = _input_fields(doc_model, render_payload)
    return {
        "attachments": attachments,
        "attachmentCount": len(attachments),
        "processingTime": processing_time,
        "fee": fee,
        "procedure": procedure,
        "legalBasis": laws[:5],
        "submitTo": submit_to,
        "inputFields": fields,
        "inputFieldCount": len(fields),
    }


def _input_fields(doc_model: dict, render_payload: dict) -> list[str]:
    """빈 셀의 라벨 = 사용자가 채워야 할 항목 (build_form_catalog 와 동일 규칙)."""
    empty: set[tuple] = set()
    for p in doc_model.get("paragraphs", []):
        cs = p.get("containerScope") or {}
        if cs.get("kind") != "cell":
            continue
        if not "".join(r.get("text", "") for r in p.get("runs", [])).strip():
            empty.add((cs.get("tableIndex"), cs.get("rowIndex"), cs.get("colIndex")))
    out: list[str] = []
    seen: set[str] = set()
    for ti, table in enumerate(render_payload.get("tables", [])):
        grid = _grid(table)
        for (r, c), cell in grid.items():
            if (ti, r, c) not in empty:
                continue
            label = ""
            for cc in range(c - 1, -1, -1):
                lc = grid.get((r, cc))
                if lc and _norm(lc.get("text")):
                    label = _norm(lc["text"]); break
            if not label:
                for rr in range(r - 1, -1, -1):
                    uc = grid.get((rr, c))
                    if uc and _norm(uc.get("text")):
                        label = _norm(uc["text"]); break
            if label and label not in seen and len(label) < 40:
                seen.add(label); out.append(label)
    return out


def _self_test() -> list[str]:
    out = []
    eq = lambda n, a, b: out.append(f"{'PASS' if a == b else 'FAIL'} {n} ({a!r})")
    eq("항목분해 숫자", split_items("1. 지정서 2. 시설현황 3. 고용증명"),
       ["지정서", "시설현황", "고용증명"])
    eq("항목분해 원문자", split_items("①신분증 ②등본"), ["신분증", "등본"])
    eq("항목분해 단일", split_items("주민등록등본 1부"), ["주민등록등본 1부"])
    eq("빈값", split_items(""), [])
    rp = {"tables": [{"cells": [
        {"row": 0, "col": 0, "text": "첨부서류"},
        {"row": 0, "col": 1, "text": "1. 지정서 2. 현황표"},
        {"row": 1, "col": 0, "text": "처리기간"},
        {"row": 1, "col": 1, "text": "7일"},
        {"row": 2, "col": 0, "text": "수수료"},
        {"row": 2, "col": 1, "text": "없음"},
        {"row": 3, "col": 0, "text": "「건설기술 진흥법」 제20조에 따라 신청합니다"},
        {"row": 4, "col": 0, "text": "국토교통부장관"},
    ]}]}
    r = extract_requirements({"paragraphs": []}, rp)
    eq("첨부서류 2건", r["attachments"], ["지정서", "현황표"])
    eq("처리기간", r["processingTime"], "7일")
    eq("수수료", r["fee"], "없음")
    eq("근거법령", r["legalBasis"][0], "건설기술 진흥법 제20조")
    eq("제출처", r["submitTo"], "국토교통부장관")
    return out


if __name__ == "__main__":
    for line in _self_test():
        print(" ", line)
