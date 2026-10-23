"""서식 칸 역할 분류 — "누가 적는 칸인가"를 구조로 판정.

정부 별지서식에서 뽑은 빈칸 라벨에는 세 종류가 섞여 있다:

    applicant  신청인이 채우는 칸        성명 · 주소 · 전화번호 · 신청내용
    office     관공서가 채우는 칸        접수번호 · 접수일 · 담당공무원확인사항
    noise      애초에 입력칸이 아닌 것    제목 · 흐름도 레인 · 구획제목 · (뒤쪽) · ▼▶◀

라벨 글자만으로는 갈리지 않는다. 실측 결과 서식에 「신청인 작성」 표기가 있는
비율은 0% 였고, 「처리기관 기재」 표기도 10% 뿐이었다. 대신 **구조**가 말해준다:

  · 「처리절차」 아래쪽 띠는 흐름도다 → 그 라벨은 전부 잡음.
    (F5 사례: '청구인·연금관리기관·금융기관' 은 입력칸처럼 보이지만 레인 이름)
    표를 통째로 죽이면 안 된다 — 서식 전체가 표 하나이고 하단에만 흐름도가
    붙은 경우가 흔해서, 본문 입력칸까지 함께 죽는다(실측 최대 오류 원인).
  · 관공서 기재란은 열거 가능한 닫힌 집합이다 → 규칙이 거의 틀리지 않는다.
  · 나머지는 신청인 기재로 본다(빠뜨리는 것보다 안전한 쪽).

또한 서식 자체가 민원서식이 아닌 경우가 있다. 대장·일지·의결서·송달서는
행정 내부문서라 신청인이 채울 칸이 0개다. 이를 못 가르면 자동채움이
관공서 대장을 채우려 든다 → formKind 로 먼저 가른다.

정확도는 tests/fixtures/web_office/field_role_ground_truth.json 정답셋으로
측정한다(tests/test_web_office_field_roles.py).
"""

from __future__ import annotations

import re
from typing import Any

# ── 서식 종류 ──────────────────────────────────────────────────────────
KIND_APPLICATION = "민원신청"  # 신청인이 작성해 제출
KIND_CERTIFICATE = "발급증서"  # 관공서가 발급 (허가증·증명서)
KIND_INTERNAL = "행정내부"  # 대장·일지·의결서 등 내부문서

_K_CERT = re.compile(
    r"(허가증|등록증|증명서|수료증|자격증|면허증|인정서|확인서|"
    r"지정서|합격증|증서)\s*$"
)
_K_INTERNAL = re.compile(
    r"(대장|일지|의결서|송달서|조서|명령서|통보서|처분서|"
    r"내역서|결과보고|심의서|회의록|관리부|점검표|기록부|"
    r"건의|지휘|기안|시행문|명부|현황표|카드)"
)
_K_APPLY = re.compile(r"(신청서|청구서|신고서|제출서|접수증|동의서|신청)")

# ── 관공서 기재란 (닫힌 집합) ─────────────────────────────────────────
_OFFICE = re.compile(
    r"^(접수\s*(번호|일자?|자)|처리\s*(일자?|기간|기관)|담당\s*공무원|"
    r"담당공무원확인사항|결재|협조자|시행일|발급\s*(번호|일자?)|"
    r"허가\s*번호|등록\s*번호\s*$|정리\s*번호|관리\s*번호|문서\s*번호|"
    r"수신자?|처리\s*결과|검토자|확인자?)\s*$"
)

# ── 잡음 ──────────────────────────────────────────────────────────────
_N_LAYOUT = re.compile(
    r"^(\(\s*(뒤|앞)\s*쪽\s*\)|\(\s*제?\s*\d+\s*쪽\s*\)|"
    r"[▼▶◀▲△▽◁▷→←↓↑]+|[-–—ㆍ·]+|[（()）\[\]]+|"
    r"계|합계|소계|총계|\d+|[（(]\s*[）)]|)$"
)
# 문서 끝 표기 — '붙임 … 끝.발신명의직인'
_N_TAIL = re.compile(r"끝\s*\.\s*발신명의|발신명의\s*직인|^붙임\b.*끝\s*\.")
# 주의: '비고 · 참고사항 · 처리기간' 은 넣지 않는다 — 실측 결과 실제 기입칸이다
# (검침표/대장의 비고, 송달서의 참고사항, 신청서의 처리기간=관공서 기재)
_N_SECTION = re.compile(
    r"^(첨부|구비|제출)\s*서류|^수수료|^처리\s*절차|"
    r"^유의\s*사항|^작성\s*(방법|요령)|^준수\s*사항|^안내\s*사항|"
    r"^기재\s*(방법|요령)|^행정정보\s*공동이용|^본인정보"
)
# 서식번호 표기 — '[별지 제7호서식] <개정 2017. 9. 22.>'
_N_FORMNO = re.compile(r"^\s*[\[(（]?\s*별지\s*제?\s*\d|^\s*[\[(（]\s*별지")
# 수신처 표기 — '○○부장관', '△△청장 귀하'
_N_ADDRESSEE = re.compile(
    r"(장관|처장|청장|위원장|위원회|시장|군수|구청장|원장|사장|이사장|서장|"
    r"교육감|도지사|관리청|지청장|공단|공사|[)）]\s*장)\s*(귀하|귀중)?\s*$"
    r"|(귀하|귀중)\s*$"
)

# ── 의미 타입 (신청인 칸에만 부여) ────────────────────────────────────
_SEMANTIC: list[tuple[str, str, re.Pattern]] = [
    ("residentNo", "secret", re.compile(r"주민\s*등록\s*번호|주민번호")),
    ("bizNo", "text", re.compile(r"사업자\s*등록\s*번호|법인\s*등록\s*번호")),
    # 이메일은 아래 email 태그가 따로 잡는다. 여기 두면 '주소(전자우편 주소:)'
    # 같은 라벨이 전화로 잡혀 전화번호가 주소칸에 들어간다(실측 오채움).
    ("phone", "tel", re.compile(r"전화|연락처|휴대폰|팩스")),
    ("address", "address", re.compile(r"주소|소재지|주소지|사업장\s*소재")),
    (
        "name",
        "text",
        re.compile(
            r"^성명|성\s*명|이름|신청인|신고인|청구인|제출인|"
            r"대표자|성명\s*\("
        ),
    ),
    # 건물·장소 이름은 신청인의 상호가 아니다. 실측에서 '아파트명' 칸에
    # 프로필 법인명이 들어가는 오채움이 확인돼 분리했다.
    (
        "buildingName",
        "text",
        re.compile(
            r"아파트\s*명|건물\s*명|공동주택\s*명|"
            r"단지\s*명|시설\s*명|점포\s*명"
        ),
    ),
    ("orgName", "text", re.compile(r"상호|법인명|기관명|업체명|^명칭|단체명")),
    # email 은 date 보다 앞에 둔다 — date 의 '^.{0,6}일$' 이
    # '이메일' 을 날짜로 오인한다(실측).
    ("email", "email", re.compile(r"이메일|전자우편|E-?mail", re.I)),
    ("birth", "date", re.compile(r"생년월일|생일")),
    ("date", "date", re.compile(r"년\s*월\s*일|일자$|일시$|^기간|^.{0,6}일$")),
    ("amount", "number", re.compile(r"금액|요금|비용|단가|원\)$|수량|사용량|면적")),
    ("account", "text", re.compile(r"계좌|금융\s*기관|은행")),
    ("consent", "checkbox", re.compile(r"동의(하십니까|함|여부)|□")),
    # 아래는 실측(표본 764칸)에서 '물어봐야 할 칸'으로 잡혔지만 사실 표준
    # 프로필 항목이라 자동 연결이 가능한 것들이다.
    ("gender", "select", re.compile(r"^성\s*별|남\s*/?\s*여")),
    ("jobTitle", "text", re.compile(r"직\s*(위|급|책)|계\s*급")),
    ("affiliation", "text", re.compile(r"^소\s*속|부\s*서|근무\s*처|소속및직위")),
    ("occupation", "text", re.compile(r"^직\s*업|^업\s*종|업\s*태|종\s*목")),
    ("agent", "text", re.compile(r"대\s*리\s*인|담\s*당\s*자|대\s*표\s*자")),
    ("zipcode", "text", re.compile(r"우편\s*번호")),
]

# 처리절차 흐름도의 단계 이름 — 표 밖에 흩어져 있어도 입력칸이 아니다.
# (실측: '신청서작성·접수·검토·결재' 가 처리절차 띠 밖에서 새어 나왔다)
# 주의: '확인·승인·결재·접수·검토' 같은 홑단어는 넣지 않는다. 발급증서·지정서의
# 실제 기입칸이라 정확도가 오히려 떨어졌다(회귀 테스트가 잡음). 흐름도에서만
# 쓰이는 복합어만 남긴다. 홑단어 단계는 처리절차 띠 규칙이 이미 걸러낸다.
_FLOW_STEP = re.compile(
    r"^(신청서\s*작성|신고서\s*작성|청구서\s*작성|서류\s*작성|신청서\s*제출|"
    r"신고서\s*제출|업무\s*처리\s*절차|결과\s*통보|서류\s*검토)$"
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _depunct(s: str) -> str:
    """공백·구두점을 털어낸 비교용 문자열."""
    return re.sub(r"[\s_·ㆍ,.\-–—()（）\[\]<>]+", "", s or "")


def _grid(table: dict) -> dict[tuple[int, int], dict]:
    return {
        (c["row"], c["col"]): c for c in table.get("cells", []) if not c.get("isCoveredByMerge")
    }


# 민원서식이 반드시 갖는 접수·처리 장치. 내부문서에는 없다.
_APP_MARKER = re.compile(
    r"접수\s*번호|처리\s*절차|처리\s*기간|담당\s*공무원\s*확인|"
    r"귀하|귀중|신청합니다|신고합니다|청구합니다|제출합니다|"
    r"(첨부|구비|제출)\s*서류|수수료"
)


def has_application_markers(doc_model: dict, render_payload: dict) -> bool:
    """민원 접수 장치의 존재 여부 — 서식 종류의 1차 근거.

    이름 어휘(기록·출납부·통지·증표…)는 열린 집합이라 규칙을 아무리 늘려도
    새 어휘에 계속 뚫린다. 반면 '접수번호·처리절차·귀하·첨부서류'는 민원서식이
    구조적으로 반드시 갖고 내부문서는 갖지 않으므로 훨씬 안정적이다."""
    for table in render_payload.get("tables", []):
        for cell in table.get("cells", []):
            if _APP_MARKER.search(_norm(cell.get("text"))):
                return True
    for p in doc_model.get("paragraphs", []):
        t = _norm("".join(r.get("text", "") for r in p.get("runs", [])))
        if t and _APP_MARKER.search(t):
            return True
    return False


def classify_form_kind(
    name: str, doc_model: dict | None = None, render_payload: dict | None = None
) -> str:
    """서식 종류 — 구조(접수장치) 우선, 이름 어휘는 보조."""
    if doc_model is not None and render_payload is not None:
        if has_application_markers(doc_model, render_payload):
            return KIND_APPLICATION
    t = _norm(name or "")
    t = re.sub(r"^\d+[_\s]*", "", t)
    t = re.sub(r"\.hwpx?$", "", t, flags=re.I).replace("_", " ")
    if not t and doc_model:
        for p in doc_model.get("paragraphs", [])[:3]:
            t = _norm("".join(r.get("text", "") for r in p.get("runs", [])))
            if t:
                break
    if _K_INTERNAL.search(t):
        return KIND_INTERNAL
    if _K_CERT.search(t):
        return KIND_CERTIFICATE
    if _K_APPLY.search(t):
        return KIND_APPLICATION
    # 접수장치도 없고 신청 어휘도 없다 → 내부문서로 본다.
    # (자동채움이 관공서 대장을 채우는 사고를 막는 쪽이 안전하다)
    return KIND_INTERNAL


def _find_adjacent_label(grid: dict, r: int, c: int) -> tuple[str, int, int]:
    """왼쪽 → 위쪽 순서로 인접 라벨 탐색. 반환: (label, label_row, label_col)."""
    for cc in range(c - 1, -1, -1):
        lcell = grid.get((r, cc))
        if lcell and _norm(lcell.get("text")):
            return _norm(lcell["text"]), r, cc
    for rr in range(r - 1, -1, -1):
        ucell = grid.get((rr, c))
        if ucell and _norm(ucell.get("text")):
            return _norm(ucell["text"]), rr, c
    return "", r, c


def _inherit_bare_header(grid: dict, label: str, lr: int, lc: int) -> str:
    """'1' '12' '계' 처럼 그 자체로는 뜻이 없는 라벨은 같은 열 위쪽의
    머리글을 물고 올라온다. 이걸 안 하면 월별 금액칸 같은 실제 입력칸이
    전부 잡음으로 죽는다(검증셋 최대 오류 원인)."""
    if not _BARE.match(label.replace(" ", "")):
        return label
    for rr in range(lr - 1, -1, -1):
        ucell = grid.get((rr, lc))
        head = _norm(ucell.get("text")) if ucell else ""
        if head and not _BARE.match(head.replace(" ", "")):
            return f"{head} {label}"
    return label


def extract_field_cells(doc_model: dict, render_payload: dict) -> list[dict]:
    """빈 셀의 라벨을 위치와 함께 뽑는다 (구조 판정에 표 소속이 필요하다)."""
    # 좌표 대신 paragraphId 를 함께 들고 나간다. 채움은 좌표가 아니라 문단
    # ID 로 겨냥해야 안전하다 — documentModel(셀 순번)과 renderPayload(격자
    # 주소)의 좌표계가 확장 셀 뒤에서 어긋나는 결함이 있기 때문이다
    # (tests/test_web_office_cell_coordinate_agreement.py 참조).
    empty: dict[tuple, str] = {}
    for p in doc_model.get("paragraphs", []):
        cs = p.get("containerScope") or {}
        if cs.get("kind") != "cell":
            continue
        if not "".join(r.get("text", "") for r in p.get("runs", [])).strip():
            key = (cs.get("tableIndex"), cs.get("rowIndex"), cs.get("colIndex"))
            empty.setdefault(key, p.get("paragraphId") or "")
    out: list[dict] = []
    seen: set[str] = set()
    for ti, table in enumerate(render_payload.get("tables", [])):
        grid = _grid(table)
        for (r, c), _cell in sorted(grid.items()):
            if (ti, r, c) not in empty:
                continue
            label, lr, lc_ = _find_adjacent_label(grid, r, c)
            label = _inherit_bare_header(grid, label, lr, lc_)
            if label and label not in seen and len(label) < 40:
                seen.add(label)
                out.append({
                    "label": label,
                    "tableIndex": ti,
                    "row": r,
                    "col": c,
                    "paragraphId": empty.get((ti, r, c), ""),
                })
    return out


def _procedure_bands(render_payload: dict) -> dict[int, int]:
    """흐름도 시작 위치 {표번호: 처리절차가 나온 행}.

    서식 전체가 표 하나이고 그 하단에 처리절차 띠가 붙은 경우가 흔하다.
    표를 통째로 잡음 처리하면 본문 입력칸까지 함께 죽는다(실측 최대 오류 원인).
    따라서 '처리절차 행 이후'만 흐름도로 본다."""
    out: dict[int, int] = {}
    for ti, table in enumerate(render_payload.get("tables", [])):
        for cell in table.get("cells", []):
            if re.match(r"^처리\s*절차", _norm(cell.get("text"))):
                r = cell.get("row", 0)
                out[ti] = min(out[ti], r) if ti in out else r
    return out


# 그 자체로는 뜻이 없는 라벨 — 머리글 상속 대상
_BARE = re.compile(r"^(\d{1,3}|계|합계|소계|총계|[가-힣]|[A-Za-z])$")


# 이 칸이 '누구의' 정보인가 — 신청인 본인이 아닌 제3자를 가리키는 표지.
# 실측 사고: '법정대리인성명' 이 name 태그를 받아 신청인 이름이 대리인 칸에
# 자동으로 들어갈 뻔했다. '피신청인 주소' 에 신청인 주소가 들어가는 것도
# 같은 부류다. 태그(입력형식·검증)는 그대로 두되 주체를 갈라 표시한다.
_THIRD_PARTY = re.compile(
    r"법정\s*대리인|대리인|임대|임차|피신청|피청구|피고|상대방|거래처|"
    r"수급인|도급인|발주자|양도인|양수인|배우자|보호자|채무자|채권자|"
    r"공급자|수급자|상속인|피상속인|대상자|위임자|수임자|보증인|"
    r"동거인|세대주(?!\s*본인)|가입자(?!\s*본인)"
)


def _subject_of(label: str) -> str:
    """'self' = 신청인 본인 정보 · 'thirdParty' = 남의 정보."""
    return "thirdParty" if _THIRD_PARTY.search(label) else "self"


def _semantic_of(label: str) -> tuple[str, str]:
    for sem, typ, rx in _SEMANTIC:
        if rx.search(label):
            return sem, typ
    return "", "text"


def classify_fields(
    doc_model: dict, render_payload: dict, *, name: str = "", force_kind: str | None = None
) -> dict[str, Any]:
    """서식 1건의 칸 역할을 판정한다.

    force_kind 를 주면 서식종류 판정을 건너뛰고 그 값을 쓴다 —
    분류체계(form_taxonomy.docType)가 이미 종류를 알고 있을 때 쓴다.
    """
    kind = force_kind or classify_form_kind(name, doc_model, render_payload)
    proc = _procedure_bands(render_payload)
    # 제목 대조는 구두점을 털고 한다 — 라벨은 '농약·농약활용기자재의…' 처럼
    # 가운뎃점이 들어가고 파일명은 '농약 농약활용기자재의…' 라 그냥은 안 맞는다
    title = _depunct(re.sub(r"\.hwpx?$", "", re.sub(r"^\d+[_\s]*", "", name or ""), flags=re.I))

    fields: list[dict] = []
    for f in extract_field_cells(doc_model, render_payload):
        lab = f["label"]
        flat = lab.replace(" ", "")
        band = proc.get(f["tableIndex"])
        if band is not None and f["row"] >= band:
            role, why = "noise", "PROCEDURE_BAND"
        elif _N_LAYOUT.match(flat) or _N_FORMNO.match(lab) or _N_TAIL.search(lab):
            role, why = "noise", "LAYOUT_OR_FORMNO"
        elif _FLOW_STEP.match(lab):
            role, why = "noise", "FLOW_STEP"
        elif title and (lambda d: d and (d == title or (len(d) > 8 and d in title)))(_depunct(lab)):
            role, why = "noise", "FORM_TITLE"
        elif _OFFICE.match(lab):
            role, why = "office", "OFFICE_FIELD"
        elif _N_SECTION.match(lab):
            role, why = "noise", "SECTION_HEADER"
        # 수신처는 민원서식에만 — 내부문서의 '위원장'은 서명 기입칸이다
        elif kind == KIND_APPLICATION and _N_ADDRESSEE.search(lab):
            role, why = "noise", "ADDRESSEE"
        elif kind in (KIND_INTERNAL, KIND_CERTIFICATE):
            role, why = "office", f"FORM_KIND:{kind}"
        else:
            role, why = "applicant", "DEFAULT_APPLICANT"
        # 의미·주체·민감은 **잡음이 아닌 모든 입력칸**에 계산한다. 역할이
        # office 라도(자동채움 차단은 유지) '무슨 칸인지'와 '민감한가'는 알아야
        # 물어볼 수 있고 보호할 수 있다. 이전엔 applicant 에만 계산해,
        # 발급증서·대장으로 분류된 서식의 성명·주민등록번호 칸이 의미도 민감
        # 표시도 없이 방치됐다(실측 40,096칸, 주민등록번호 672칸 포함).
        _known = role != "noise"
        sem, typ = _semantic_of(lab) if _known else ("", "")
        subj = _subject_of(lab) if _known else ""
        fields.append({
            **f,
            "role": role,
            "reason": why,
            "semantic": sem,
            "inputType": typ,
            "subject": subj,
        })

    ap = [f for f in fields if f["role"] == "applicant"]
    return {
        "formKind": kind,
        "fields": fields,
        "applicantFieldCount": len(ap),
        "officeFieldCount": sum(1 for f in fields if f["role"] == "office"),
        "noiseFieldCount": sum(1 for f in fields if f["role"] == "noise"),
        "sensitiveCount": sum(1 for f in ap if f["inputType"] == "secret"),
    }


def _self_test() -> list[str]:
    out: list[str] = []

    def eq(n, a, b):
        out.append(f"{'PASS' if a == b else 'FAIL'} {n} ({a!r})")

    eq("종류-신청서", classify_form_kind("13638955_도로연결 허가신청서.hwpx"), KIND_APPLICATION)
    eq("종류-대장", classify_form_kind("18195161_소방공무원기장_수여대장.hwpx"), KIND_INTERNAL)
    eq("종류-증서", classify_form_kind("12227797_법인_설립허가증.hwpx"), KIND_CERTIFICATE)
    eq("의미-주민번호", _semantic_of("주민등록번호"), ("residentNo", "secret"))
    eq("의미-주소", _semantic_of("사업장 소재지"), ("address", "address"))
    eq("의미-전화", _semantic_of("연락처"), ("phone", "tel"))

    rp = {
        "tables": [
            {
                "cells": [
                    {"row": 0, "col": 0, "text": "접수번호"},
                    {"row": 0, "col": 1, "text": ""},
                    {"row": 1, "col": 0, "text": "성명"},
                    {"row": 1, "col": 1, "text": ""},
                ]
            },
            {
                "cells": [
                    {"row": 0, "col": 0, "text": "처리절차"},
                    {"row": 1, "col": 0, "text": "청구인"},
                    {"row": 1, "col": 1, "text": ""},
                ]
            },
        ]
    }
    dm = {
        "paragraphs": [
            {
                "containerScope": {"kind": "cell", "tableIndex": 0, "rowIndex": 0, "colIndex": 1},
                "runs": [],
            },
            {
                "containerScope": {"kind": "cell", "tableIndex": 0, "rowIndex": 1, "colIndex": 1},
                "runs": [],
            },
            {
                "containerScope": {"kind": "cell", "tableIndex": 1, "rowIndex": 1, "colIndex": 1},
                "runs": [],
            },
        ]
    }
    r = classify_fields(dm, rp, name="연금 청구서.hwpx")
    by = {f["label"]: f["role"] for f in r["fields"]}
    eq("접수번호→관공서", by.get("접수번호"), "office")
    eq("성명→신청인", by.get("성명"), "applicant")
    eq("흐름도 청구인→잡음", by.get("청구인"), "noise")
    eq("신청인칸 수", r["applicantFieldCount"], 1)
    return out


if __name__ == "__main__":
    for line in _self_test():
        print(" ", line)
