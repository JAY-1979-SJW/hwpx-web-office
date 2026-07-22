"""수집 서식 분류 체계 — 무엇을 채울 수 있는 문서인가.

수집분 38,165건은 균질하지 않다. 실측 결과:

    입력칸 0개          3,401건 ( 8.9%)  채울 게 없는 문서(기준표·안내문)
    '… 삭제' 문서         339건 ( 0.9%)  삭제된 조문의 빈 껍데기 (337/339 가 0칸)
    '별표' 문서         1,401건 ( 3.7%)  기준표 — 서식이 아니라 참고자료 (평균 5.6칸)
    '별지' 서식         6,004건 (15.7%)  진짜 서식 (평균 12.1칸)
    나머지            30,421건 (79.7%)  93% 가 법제처 별지서식(이름에서 '별지'가 탈락)

따라서 분류축은 두 개다:

    축1 fillable   채울 수 있는가 — 입력칸 유무 (자동채움 대상 판별)
    축2 docType    문서 유형 — 신청신고 / 증명발급 / 보고통지 / 대장기록 /
                              계약동의 / 계획내역 / 기준별표 / 기타

어휘는 지어내지 않고 수집분 이름 어미 분포에서 뽑았다(신청서 21.9% ·
신고서 8.6% · 대장 4.2% · 통지서 2.5% …).

축3(업무분야)은 institution 컬럼이 이미 담고 있어 여기서 만들지 않는다.
"""
from __future__ import annotations

import re

# ── 문서 유형 ─────────────────────────────────────────────────────────
T_APPLY = "신청신고"     # 신청서·신고서·청구서 — 자동채움 1순위
T_CERT = "증명발급"      # 증명서·허가증·등록증 — 관공서가 발급
T_NOTICE = "보고통지"    # 보고서·통지서·결정서
T_LEDGER = "대장기록"    # 대장·명부·일지·조서 — 행정 내부
T_AGREE = "계약동의"     # 계약서·동의서·위임장
T_PLAN = "계획내역"      # 계획서·내역서·정산서·현황
T_STANDARD = "기준별표"  # 별표·기준·요령 — 서식이 아닌 참고자료
T_ETC = "기타"

# 순서가 곧 우선순위다. 긴 어미를 먼저 봐야 '허가신청서'가 증명발급으로
# 새지 않는다(신청신고를 맨 앞에 둔 이유).
_RULES: list[tuple[str, re.Pattern]] = [
    (T_APPLY, re.compile(
        r"(신청서|신고서|청구서|요청서|제안서|응모서|지원서|청원서|진정서|"
        r"이의신청|심사청구|재심청구|접수증|응시원서|원서|청약서|요구서|"
        r"신청|신고(?!증)|청구)\s*$")),
    (T_CERT, re.compile(
        r"(증명서|확인서|허가증|등록증|자격증|수료증|면허증|인증서|지정서|"
        r"인정서|합격증|증서|증표|확인원|증명원|필증|검사증|신고증|"
        r"승인서|승인증|신분증|증명|허가서)\s*$")),
    (T_NOTICE, re.compile(
        r"(보고서|통지서|통보서|결정서|의견서|회신|명세서|고지서|안내문|"
        r"통지|통보|보고|처분서|명령서|촉구서|독촉장)\s*$")),
    (T_LEDGER, re.compile(
        r"(대장|명부|일지|조서|기록부|접수부|관리부|출납부|원부|목록|"
        r"카드|의결서|회의록|점검표|현황표|명단|등록부|일람표|대장부)\s*$")),
    (T_AGREE, re.compile(
        r"(계약서|동의서|위임장|서약서|각서|협약서|확약서|진술서|합의서|"
        r"약정서|승낙서|답변서|의뢰서|협의서)\s*$")),
    (T_PLAN, re.compile(
        r"(계획서|내역서|정산서|집계표|총계표|결산서|산출서|명세|현황|"
        r"실적서|조사서|평가서|검사서|성적서|결과서|요약서|명세표|"
        r"계획|실적|집계)\s*$")),
    # '양식|서식' 은 넣지 않는다 — '…지급신청 서식' 처럼 진짜 서식의 어미다
    (T_STANDARD, re.compile(r"(별표|기준|요령|지침|표준)\s*$")),
]

# 서식이 아닌 문서 — 채움 대상에서 제외
# '삭제 2014 7 29' 처럼 삭제 뒤에 개정일이 붙는 형태가 많다(미분류의 큰 덩어리였다).
# '… 으로 이동' 은 다른 서식으로 옮겨진 빈 껍데기다.
_DELETED = re.compile(r"삭제\s*$|삭제\s*[.\-·]|삭제\s*\d|으로\s*이동")
_ANNEX = re.compile(r"별표")


def clean_name(name: str) -> str:
    """카탈로그 이름 정규화 — 확장자·순번접두·해시접두·서식번호 제거.

    수집 경로에 따라 이름 앞에 잔재가 붙는다:
        'c563771748119 023 별지 제4호서식 건축관계자 변경신고서'
    해시 토큰과 일련번호, 그리고 '별지 제N호서식' 머리표를 떼어내면
    사람이 읽는 진짜 서식명만 남는다.
    """
    n = re.sub(r"\.hwpx?$", "", name or "", flags=re.I)
    n = re.sub(r"\.repaired$", "", n, flags=re.I)
    n = re.sub(r"^\d+[_\s]*", "", n)
    n = re.sub(r"[_\[\]()<>{}]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    # 해시 접두어(16진 8자 이상) + 뒤따르는 일련번호들
    n = re.sub(r"^[0-9a-f]{8,}\s*(?:\d{1,5}\s+)*", "", n, flags=re.I).strip()
    # '별지 제4호서식' / '별지 제27호의5서식' 머리표
    n = re.sub(r"^별지\s*제\s*\d+호(?:의\s*\d+)?\s*서식\s*", "", n).strip()
    return n or re.sub(r"\s+", " ", (name or "")).strip()


def classify_document(name: str, field_count: int | None = None) -> dict:
    """문서 1건의 분류 — 유형 + 채움 가능성."""
    c = clean_name(name)
    fc = field_count or 0

    if _DELETED.search(c):
        return {"docType": T_ETC, "fillable": False, "reason": "DELETED_STUB",
                "cleanName": c}
    if _ANNEX.search(c):
        # 별표는 기준·처분기준 표다. 빈 칸이 있어도 신청인이 채우는 칸이 아니라
        # 표의 여백이므로 채움 대상에서 뺀다.
        return {"docType": T_STANDARD, "fillable": False, "reason": "ANNEX_TABLE",
                "cleanName": c}

    for doc_type, rx in _RULES:
        if rx.search(c):
            fillable = fc > 0 and doc_type != T_STANDARD
            return {"docType": doc_type, "fillable": fillable,
                    "reason": "NAME_SUFFIX", "cleanName": c}

    # 어미로 안 잡히면 이름 중간 어휘로 한 번 더 (수집 과정에서 이름 뒷부분이
    # 잘린 건이 많다 — 기타 30,421건의 93% 가 이 경우다)
    if re.search(r"신청|신고|청구", c):
        return {"docType": T_APPLY, "fillable": fc > 0, "reason": "NAME_KEYWORD",
                "cleanName": c}
    if re.search(r"대장|명부|일지|조서|출납부|기록부|접수부|관리부|원부", c):
        return {"docType": T_LEDGER, "fillable": fc > 0, "reason": "NAME_KEYWORD",
                "cleanName": c}
    if re.search(r"증명|허가|등록증|인증", c):
        return {"docType": T_CERT, "fillable": fc > 0, "reason": "NAME_KEYWORD",
                "cleanName": c}
    if re.search(r"통지|통보|보고|결정", c):
        return {"docType": T_NOTICE, "fillable": fc > 0, "reason": "NAME_KEYWORD",
                "cleanName": c}

    # 끝 형태소 일반화 — 어휘를 계속 늘리는 대신 마지막 글자의 성격을 본다.
    # 한국 공문서명은 끝 형태소가 문서 성격을 규정한다:
    #   ~증(출입증·적합증·이수증) 증명 · ~부/록(사건부·처리부·회의록) 장부
    #   ~표(결과표·일람표) 집계 · ~장(위임장·독촉장) 의사표시 · ~서 제출문서
    # 개별 단어를 열거하면 새 어휘에 계속 뚫리지만 형태소는 닫혀 있다.
    # '증·부·록·표·원' 은 형태소만으로 성격이 결정된다(파일별 확인에서 전건 정확).
    # '송부·첨부' 는 장부가 아니라 행위다 — '추천서 송부' 가 대장으로 새던 건
    if re.search(r"(송부|첨부|이첩)\s*$", c):
        return {"docType": T_NOTICE, "fillable": fc > 0,
                "reason": "NAME_MORPHEME:송부", "cleanName": c}
    m = re.search(r"([증부록표원])\s*$", c)
    if m:
        by_morph = {"증": T_CERT, "부": T_LEDGER, "록": T_LEDGER,
                    "표": T_PLAN, "원": T_APPLY}
        return {"docType": by_morph[m.group(1)], "fillable": fc > 0,
                "reason": f"NAME_MORPHEME:{m.group(1)}", "cleanName": c}

    # '~서' 와 '~장' 은 형태소만으로는 너무 거칠다. 파일별 확인에서
    # '손익계산서·인사평정서'(집계) 와 '영장반환서·회신서'(통지) 가 신청서로,
    # '임명장'(발급) 과 '고발장'(제출) 이 계약동의로 잘못 갔다. 앞 음절로 가른다.
    if c.endswith("서"):
        if re.search(r"(계산서|명세서|정산서|평정서|검토서|기록서|산출서|"
                     r"집계서|내역서|일람서)$", c):
            kind = T_PLAN
        elif re.search(r"(회신서|통고서|반환서|이송서|송부서|고지서|경고서)$", c):
            kind = T_NOTICE
        else:
            kind = T_APPLY          # 제출문서 기본형 — 자동채움 후보로 남긴다
        return {"docType": kind, "fillable": fc > 0,
                "reason": "NAME_MORPHEME:서", "cleanName": c}
    if c.endswith("장"):
        if re.search(r"(임명장|임용장|표창장|수료장|위촉장|상장|감사장)$", c):
            kind = T_CERT
        elif re.search(r"(위임장|각서장|보증장|서약장)$", c):
            kind = T_AGREE
        elif re.search(r"(고발장|진정장|청원장|탄원장|소장)$", c):
            kind = T_APPLY
        elif re.search(r"(독촉장|최고장|경고장|통지장)$", c):
            kind = T_NOTICE
        else:
            return {"docType": T_ETC, "fillable": fc > 0,
                    "reason": "UNMATCHED", "cleanName": c}
        return {"docType": kind, "fillable": fc > 0,
                "reason": "NAME_MORPHEME:장", "cleanName": c}
    return {"docType": T_ETC, "fillable": fc > 0, "reason": "UNMATCHED",
            "cleanName": c}


def _self_test() -> list[str]:
    out: list[str] = []
    def eq(n, a, b):
        out.append(f"{'PASS' if a == b else 'FAIL'} {n} ({a!r})")
    g = lambda s, fc=5: classify_document(s, fc)
    eq("허가신청서→신청신고", g("13638955_도로 연결 허가신청서.hwpx")["docType"], T_APPLY)
    eq("대장→대장기록", g("18171247_화물자동차_허가대장.hwpx")["docType"], T_LEDGER)
    eq("허가증→증명발급", g("12227797_법인_설립허가증.hwpx")["docType"], T_CERT)
    eq("통지서→보고통지", g("17968491_체납자_명단공개_통지.hwpx")["docType"], T_NOTICE)
    eq("출납부→대장기록", g("15143467_현금출납부_시설용.hwpx")["docType"], T_LEDGER)
    eq("별표→기준별표", g("029_별표 24 용기등의 표시.hwpx")["docType"], T_STANDARD)
    eq("삭제→채움불가", g("006_별표 6 삭제.hwpx", 0)["fillable"], False)
    eq("0칸→채움불가", g("어떤 신청서.hwpx", 0)["fillable"], False)
    eq("이름정규화", clean_name("13638941_국가부담비용_정산서.hwpx"),
       "국가부담비용 정산서")
    return out


if __name__ == "__main__":
    for line in _self_test():
        print(" ", line)
