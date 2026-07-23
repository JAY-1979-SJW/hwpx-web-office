"""채움 계획 — 무엇을 자동으로 넣고, 무엇을 사용자에게 물을 것인가.

입력 스키마(form_input_schema)와 사용자 프로필을 받아 세 갈래로 나눈다:

    autoFill   프로필에 값이 있는 칸 → 바로 채움
    questions  값이 없는 신청인 칸 → 사용자에게 질문
    skipped    관공서 칸 → 건드리지 않음

**AI 는 값을 만들지 않는다.** 이 모듈이 하는 일은 "어느 자료의 어느 값이
어느 칸에 들어가는가" 를 잇는 것뿐이다. 프로필에도 없고 사용자가 답하지도
않은 칸은 빈칸으로 남는다 — 관공서 제출물에 그럴듯한 값을 지어 넣으면
허위 기재다.

민감칸(주민등록번호 등)은 프로필에 값이 있어도 자동으로 넣지 않는다.
매번 사용자 확인을 받는다(requiresConfirmation). 실수로 다른 사람의
주민번호가 서식에 박히는 사고를 구조적으로 막는다.

실측(표본 123건 · 신청인칸 745개): 프로필로 자동 연결 가능 37.9%,
나머지 62.1% 는 서식 고유 항목이라 물어봐야 한다. 최빈값이 4건뿐인
완전한 롱테일이라 규칙으로는 더 줄지 않는다.
"""
from __future__ import annotations

from typing import Any

# 의미 태그 → 사람이 읽는 질문 문구
_PROMPT = {
    "name": "성명(이름)을 알려주세요",
    "orgName": "상호·법인명을 알려주세요",
    "address": "주소를 알려주세요",
    "zipcode": "우편번호를 알려주세요",
    "phone": "연락처(전화번호)를 알려주세요",
    "email": "이메일 주소를 알려주세요",
    "birth": "생년월일을 알려주세요",
    "residentNo": "주민등록번호를 알려주세요",
    "bizNo": "사업자등록번호를 알려주세요",
    "date": "날짜를 알려주세요",
    "amount": "금액을 알려주세요",
    "account": "계좌 정보를 알려주세요",
    "gender": "성별을 알려주세요",
    "jobTitle": "직위·직급을 알려주세요",
    "affiliation": "소속을 알려주세요",
    "occupation": "직업·업종을 알려주세요",
    "agent": "대리인 정보를 알려주세요",
    "consent": "동의 여부를 선택해 주세요",
}


def _question_for(field: dict) -> str:
    """질문 문구 — 의미 태그가 있으면 그 문구, 없으면 라벨을 그대로 묻는다.

    라벨이 곧 서식의 표현이라 임의로 바꾸지 않는다. '등록의무자' 를
    '담당자' 로 바꿔 물으면 사용자가 다른 값을 적는다.
    """
    sem = field.get("semantic")
    if sem and sem in _PROMPT:
        return f"{field['label']} — {_PROMPT[sem]}"
    return f"{field['label']} 항목에 넣을 내용을 알려주세요"


def plan_fill(inputs: list[dict], profile: dict[str, Any] | None = None,
              *, history: dict[str, str] | None = None) -> dict[str, Any]:
    """채움 계획을 세운다.

    inputs   form_input_schema.build_input_schema()["inputs"]
    profile  {의미태그: 값}  예: {"name": "홍길동", "phone": "010-..."}
    history  {라벨: 값} — 같은 서식을 전에 냈을 때의 값(재사용)
    """
    profile = profile or {}
    history = history or {}

    auto: list[dict] = []
    questions: list[dict] = []
    skipped: list[dict] = []

    for f in inputs:
        if f.get("role") != "applicant":
            skipped.append({**f, "reason": "OFFICE_FIELD"})
            continue

        sem = f.get("semantic") or ""
        label = f.get("label", "")

        # 민감칸은 값이 있어도 자동 채움하지 않는다 — 반드시 확인을 받는다
        if f.get("sensitive"):
            questions.append({
                **f,
                "question": _question_for(f),
                "suggested": profile.get(sem) or history.get(label) or "",
                "requiresConfirmation": True,
                "reason": "SENSITIVE_NEEDS_CONFIRMATION",
            })
            continue

        # ① 전에 낸 같은 서식의 값 (가장 정확하다 — 그 서식 고유 항목까지 덮는다)
        if label in history and history[label]:
            auto.append({**f, "value": history[label], "source": "history"})
            continue

        # ② 프로필의 의미 태그 값 — 단, 본인 정보 칸일 때만.
        # '법정대리인성명'·'피신청인 주소' 같은 제3자 칸에 신청인 프로필을
        # 넣으면 엉뚱한 사람의 정보가 서식에 박힌다(실측으로 확인된 오채움).
        if sem and profile.get(sem) and f.get("subject", "self") == "self":
            auto.append({**f, "value": str(profile[sem]), "source": "profile"})
            continue

        # ③ 모르면 물어본다 — 지어내지 않는다
        questions.append({
            **f,
            "question": _question_for(f),
            "suggested": "",
            "requiresConfirmation": False,
            "reason": "UNKNOWN_NEEDS_INPUT",
        })

    applicant_total = len(auto) + len(questions)
    return {
        "autoFill": auto,
        "questions": questions,
        "skipped": skipped,
        "autoFillCount": len(auto),
        "questionCount": len(questions),
        "applicantTotal": applicant_total,
        "coverage": (len(auto) / applicant_total) if applicant_total else 0.0,
    }


def build_fill_commands(plan: dict, answers: dict[str, str] | None = None
                        ) -> list[dict]:
    """계획 + 사용자 답변 → 채움 명령 목록.

    answers 는 {라벨: 값}. 답하지 않은 칸은 명령을 만들지 않는다 —
    빈칸으로 남기는 것이 값을 지어내는 것보다 항상 안전하다.

    반환 형태는 편집기 명령과 같은 좌표 정보를 담는다. 실제 HWPX 기입은
    paragraph_writer_adapter 가 하며, 기존 charPr 을 물려받으므로 서식이
    바뀌지 않는다(§4 — 신규 charPr 생성 금지).
    """
    answers = answers or {}
    out: list[dict] = []
    for f in plan.get("autoFill", []):
        out.append(_cmd(f, f["value"], f.get("source", "profile")))
    for q in plan.get("questions", []):
        val = answers.get(q["label"])
        if val is None or val == "":
            continue
        out.append(_cmd(q, str(val), "answer"))
    return out


def _cmd(field: dict, value: str, source: str) -> dict:
    return {
        "type": "TYPE_TEXT",
        "text": value,
        "label": field.get("label"),
        "semantic": field.get("semantic") or "",
        "sensitive": bool(field.get("sensitive")),
        "tableIndex": field.get("tableIndex"),
        "row": field.get("row"),
        "col": field.get("col"),
        "source": source,
    }


def _self_test() -> list[str]:
    out: list[str] = []
    def eq(n, a, b):
        out.append(f"{'PASS' if a == b else 'FAIL'} {n} ({a!r})")

    inputs = [
        {"label": "성명", "role": "applicant", "semantic": "name",
         "inputType": "text", "sensitive": False,
         "tableIndex": 0, "row": 1, "col": 1},
        {"label": "연락처", "role": "applicant", "semantic": "phone",
         "inputType": "tel", "sensitive": False,
         "tableIndex": 0, "row": 2, "col": 1},
        {"label": "주민등록번호", "role": "applicant", "semantic": "residentNo",
         "inputType": "secret", "sensitive": True,
         "tableIndex": 0, "row": 3, "col": 1},
        {"label": "신청사유", "role": "applicant", "semantic": "",
         "inputType": "text", "sensitive": False,
         "tableIndex": 0, "row": 4, "col": 1},
        {"label": "접수번호", "role": "office", "semantic": "",
         "inputType": "text", "sensitive": False,
         "tableIndex": 0, "row": 0, "col": 1},
    ]
    profile = {"name": "홍길동", "phone": "010-1234-5678",
               "residentNo": "900101-1234567"}

    p = plan_fill(inputs, profile)
    eq("자동채움 2건", p["autoFillCount"], 2)
    eq("질문 2건(민감1+미상1)", p["questionCount"], 2)
    eq("관공서칸 제외", len(p["skipped"]), 1)
    eq("관공서 사유", p["skipped"][0]["reason"], "OFFICE_FIELD")

    qs = {q["label"]: q for q in p["questions"]}
    eq("주민번호는 자동채움 안 함", "주민등록번호" in qs, True)
    eq("주민번호 확인 필요", qs["주민등록번호"]["requiresConfirmation"], True)
    eq("주민번호 제안값 보유", qs["주민등록번호"]["suggested"], "900101-1234567")
    eq("미상칸은 제안 없음", qs["신청사유"]["suggested"], "")
    eq("라벨 보존 질문", "신청사유" in qs["신청사유"]["question"], True)

    # 답변 없이 명령 생성 — 자동채움분만
    cmds = build_fill_commands(p)
    eq("답변 전 명령 2건", len(cmds), 2)
    eq("지어내지 않음", all(c["source"] != "answer" for c in cmds), True)

    # 답변 후
    cmds2 = build_fill_commands(p, {"신청사유": "자격 갱신", "주민등록번호": "900101-1234567"})
    eq("답변 후 명령 4건", len(cmds2), 4)
    by = {c["label"]: c for c in cmds2}
    eq("좌표 유지", (by["신청사유"]["tableIndex"], by["신청사유"]["row"],
                 by["신청사유"]["col"]), (0, 4, 1))
    eq("민감 표시 유지", by["주민등록번호"]["sensitive"], True)

    # 이력 재사용 — 프로필에 없는 서식 고유 항목까지 덮는다
    p2 = plan_fill(inputs, profile, history={"신청사유": "자격 갱신"})
    eq("이력으로 자동채움 3건", p2["autoFillCount"], 3)
    eq("질문 1건으로 감소", p2["questionCount"], 1)
    eq("이력 출처 표시",
       next(a["source"] for a in p2["autoFill"] if a["label"] == "신청사유"),
       "history")

    # 프로필 없음
    p3 = plan_fill(inputs, None)
    eq("프로필 없으면 전부 질문", p3["questionCount"], 4)
    eq("자동채움 0", p3["autoFillCount"], 0)
    return out


if __name__ == "__main__":
    for line in _self_test():
        print(" ", line)
