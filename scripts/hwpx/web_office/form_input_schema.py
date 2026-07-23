"""서식 입력 스키마 — "이 서식에 무엇을 넣어야 하는가"의 최종 산출물.

두 계층을 합친다:

    form_taxonomy      문서가 무엇인가 (docType · fillable)
    form_field_roles   칸을 누가 채우는가 (applicant / office / noise)

설계 원칙 — **역할로 칸을 버리지 않는다.**
초기 설계는 서식종류가 '행정내부'면 칸을 통째로 관공서용으로 돌려 신청인
입력칸을 지워버렸다. 종류 판정이 한 건 틀리면 그 서식의 모든 칸이 사라지는
구조라, 실측에서 정확도를 68%까지 끌어내렸다. 지금은 잡음만 제외하고
모든 실입력칸을 남기며 역할은 꼬리표로만 단다. 종류를 틀려도 칸은 살아 있다.

측정(3개 정답셋, tests/fixtures/web_office/):
    ①튜닝 96.7%  ②검증 97.5%  ③최종(무오염) 88.5%
    — 이름만 보던 초기안 68.3% 대비 +20.2%p

민감칸(주민등록번호 등)은 sensitive 로 표시만 하고 값은 다루지 않는다.
"""
from __future__ import annotations

import re
from typing import Any

from scripts.hwpx.web_office import form_field_roles as FR
from scripts.hwpx.web_office.form_taxonomy import classify_document

# 분류체계의 문서유형 → 칸 역할 판정에 쓰는 서식종류
_DOCTYPE_TO_KIND = {
    "신청신고": FR.KIND_APPLICATION,
    "계약동의": FR.KIND_APPLICATION,
    "계획내역": FR.KIND_APPLICATION,
    "증명발급": FR.KIND_CERTIFICATE,
    "대장기록": FR.KIND_INTERNAL,
    "보고통지": FR.KIND_INTERNAL,
    "기준별표": FR.KIND_INTERNAL,
}


# 이름이 무엇이든 이 장치가 다 있으면 접수되는 민원서식이다.
_STRONG = ("접수번호", "담당공무원확인")


def _strong_application_evidence(render_payload: dict) -> bool:
    """접수번호 + 담당공무원확인 처럼 반박하기 어려운 접수장치."""
    found = set()
    for table in render_payload.get("tables", []):
        for cell in table.get("cells", []):
            t = (cell.get("text") or "").replace(" ", "")
            for k in _STRONG:
                if k in t:
                    found.add(k)
    return len(found) >= 2


# '(인)' 은 넣지 않는다. 신청서 하단의 '(서명 또는 인)' 까지 직인으로 오인해
# 민원서식이 발급증서로 넘어간다 — A/B 측정에서 ①-5.3%p ②-11.1%p 였다.
# '직인' 만 엄격히 보면 ①② 손실 0, ③ +3.8%p 로 순수 이득이다.
_SEAL = re.compile(r"직\s*인|印")
_ADDRESSED = re.compile(r"귀\s*하|귀\s*중")


def _issuer_seal_without_addressee(render_payload: dict) -> bool:
    """발급문서 신호 — 관서장 명의 + 직인이 있고 수신처(귀하)가 없다.

    서식을 직접 읽어보고 찾은 단서다. 신청서는 하단에 '○○장관 귀하'(수신처)가
    오고, 증서는 '○○전파관리소장 [직인]'(발급자 명의)이 온다.
    정답셋 40건 실측: 발급증서 6/6 이 이 조합에 걸리고 민원신청 23건은 0건.
    이름만 보던 규칙은 '무선국 신고증명서'의 '신고' 때문에 신청서로 오판했다.
    """
    seal = addressed = False
    for table in render_payload.get("tables", []):
        for cell in table.get("cells", []):
            t = cell.get("text") or ""
            if not seal and _SEAL.search(t):
                seal = True
            if not addressed and _ADDRESSED.search(t):
                addressed = True
            if seal and addressed:
                return False
    return seal and not addressed


def resolve_form_kind(doc_type: str, doc_model: dict,
                      render_payload: dict) -> str:
    """서식종류 — 구조가 이름을 이긴다.

    이름 기반 문서유형은 틀릴 수 있다. 실측 사례: '…세액감면신청서 증여받은
    농지등의 명세서' 는 이름 어미가 '명세서'라 보고통지로 분류됐지만, 본문에는
    접수번호·담당공무원확인사항·세무서장귀하가 모두 있는 명백한 신청서였다.
    이름을 믿고 내부문서로 돌리면 그 서식의 신청인 입력칸이 통째로 사라진다.
    그래서 강한 접수장치가 확인되면 이름 판정을 뒤집는다.
    """
    if _strong_application_evidence(render_payload):
        return FR.KIND_APPLICATION
    if _issuer_seal_without_addressee(render_payload):
        return FR.KIND_CERTIFICATE
    kind = _DOCTYPE_TO_KIND.get(doc_type)
    if kind:
        return kind
    return (FR.KIND_APPLICATION
            if FR.has_application_markers(doc_model, render_payload)
            else FR.KIND_INTERNAL)


def build_input_schema(doc_model: dict, render_payload: dict, *,
                       name: str = "", field_count: int | None = None
                       ) -> dict[str, Any]:
    """서식 1건의 입력 스키마."""
    tax = classify_document(name, field_count)
    kind = resolve_form_kind(tax["docType"], doc_model, render_payload)
    roles = FR.classify_fields(doc_model, render_payload, name=name,
                               force_kind=kind)

    inputs: list[dict] = []
    for f in roles["fields"]:
        if f["role"] == "noise":
            continue                      # 잡음만 제외 — 실입력칸은 모두 남긴다
        inputs.append({
            "label": f["label"],
            "role": f["role"],            # applicant | office
            "inputType": f["inputType"] or "text",
            "semantic": f["semantic"],
            # self = 신청인 본인 정보 · thirdParty = 대리인·상대방 등 남의 정보.
            # thirdParty 는 프로필에서 자동으로 채우면 안 된다.
            "subject": f.get("subject") or "self",
            "sensitive": f["inputType"] == "secret",
            # 채움은 좌표가 아니라 paragraphId 로 겨냥한다(좌표계 결함 우회)
            "paragraphId": f.get("paragraphId") or "",
            "tableIndex": f["tableIndex"],
            "row": f["row"],
            "col": f["col"],
        })

    applicant = [i for i in inputs if i["role"] == "applicant"]
    return {
        "docType": tax["docType"],
        "cleanName": tax["cleanName"],
        "fillable": bool(tax["fillable"]) and bool(inputs),
        "formKind": kind,
        "inputs": inputs,
        "inputCount": len(inputs),
        "applicantCount": len(applicant),
        "officeCount": len(inputs) - len(applicant),
        "sensitiveCount": sum(1 for i in inputs if i["sensitive"]),
        "noiseDropped": roles["noiseFieldCount"],
    }


def _self_test() -> list[str]:
    out: list[str] = []
    def eq(n, a, b):
        out.append(f"{'PASS' if a == b else 'FAIL'} {n} ({a!r})")

    rp = {"tables": [
        {"cells": [{"row": 0, "col": 0, "text": "접수번호"},
                   {"row": 0, "col": 1, "text": ""},
                   {"row": 1, "col": 0, "text": "성명"},
                   {"row": 1, "col": 1, "text": ""},
                   {"row": 2, "col": 0, "text": "주민등록번호"},
                   {"row": 2, "col": 1, "text": ""}]},
        {"cells": [{"row": 0, "col": 0, "text": "처리절차"},
                   {"row": 1, "col": 0, "text": "청구인"},
                   {"row": 1, "col": 1, "text": ""}]},
    ]}
    cell = lambda ti, r, c: {"containerScope": {"kind": "cell", "tableIndex": ti,
                                                "rowIndex": r, "colIndex": c},
                             "runs": []}
    dm = {"paragraphs": [cell(0, 0, 1), cell(0, 1, 1), cell(0, 2, 1), cell(1, 1, 1)]}

    s = build_input_schema(dm, rp, name="연금 청구서.hwpx", field_count=4)
    eq("문서유형", s["docType"], "신청신고")
    eq("서식종류", s["formKind"], FR.KIND_APPLICATION)
    eq("입력칸 3개(흐름도 제외)", s["inputCount"], 3)
    eq("신청인칸 2개", s["applicantCount"], 2)
    eq("관공서칸 1개", s["officeCount"], 1)
    eq("민감칸 1개", s["sensitiveCount"], 1)
    labs = {i["label"]: i for i in s["inputs"]}
    eq("주민번호 민감", labs["주민등록번호"]["sensitive"], True)
    eq("성명 의미", labs["성명"]["semantic"], "name")
    eq("흐름도 청구인 제외", "청구인" in labs, False)

    # 대장이어도 입력칸은 살아 있어야 한다(역할만 관공서로)
    s2 = build_input_schema(dm, rp, name="채혈금지대상자 관리대장.hwpx", field_count=4)
    eq("대장 문서유형", s2["docType"], "대장기록")
    eq("대장도 칸 보존", s2["inputCount"], 3)
    eq("대장은 신청인칸 0", s2["applicantCount"], 0)
    return out


if __name__ == "__main__":
    for line in _self_test():
        print(" ", line)
