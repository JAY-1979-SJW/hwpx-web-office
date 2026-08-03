# hwpx-web-office 작업 표준시방서 (CLAUDE.md)

이 저장소는 **HWPX 전체 도메인** 공정 전용이다.
Excel·기타 비HWPX 도메인은 이 저장소 범위 밖이다.

---

## 1. 저장소 범위 (SCOPE)

| 포함 (IN_SCOPE) | 제외 (OUT_OF_SCOPE) |
|----------------|-------------------|
| `frontend/web_office_viewer/` | Excel 관련 파일 일체 |
| `scripts/hwpx/` (전체 서브모듈 포함) | `scripts/excel/` |
| `tests/test_hwpx_*.py` | 서버 배포 자동화 |
| `tests/test_web_office_*.py` | price-classifier 등 타 도메인 |
| `scripts/ops/audit_hwpx_*.py` | |
| `scripts/ops/audit_web_office_*.py` | |
| `docs/architecture/hwpx_*.md` | |
| `docs/architecture/web_office_*.md` | |
| `docs/contracts/`, `docs/deploy/`, `docs/design/` (hwpx 관련) | |
| `docs/reports/` (hwpx/web_office 관련) | |
| `tests/fixtures/hwpx/` | |
| `samples/` (hwpx 샘플) | |
| `data/drafts/` (hwpx 데이터) | |

---

## 2. 건축 공정 방식 (§1 of parent CLAUDE.md 계승)

이 프로젝트의 개발 작업은 건축 현장 공정과 동일한 용어 체계를 사용한다.

| 건축 용어 | 개발 대응 |
|-----------|----------|
| 건축 현장 | 코드 개발 |
| 동 | 도메인 |
| 세대 | 파일 |
| 감리검사 | 테스트 / audit |
| 공정 완료 | commit |
| 준공 반영 | push |

---

## 3. 현재창 보고 강제 규칙 (MANDATORY)

기본 보고는 현재 채팅창에 직접 출력한다. `docs/reports/*.md` 파일 생성은
사용자가 명시적으로 요청한 경우에만 허용한다.

### 건축공사 비유 강제 (§4-A 계승)

모든 작업 보고에 건축공사 비유를 반드시 포함한다.

### 3-A. 토큰 절감 원칙 (2026-08-03 신설)

Claude Code 세션은 다음을 지킨다:

- **원시 데이터 통째 출력 금지** — JSON/셀 구조/좌표맵 등을 확인할 때
  필요한 필드만 뽑아 출력한다. `borderFill`/`cellMargin` 같은 미사용
  필드까지 pretty-print 하지 않는다.
- **재확인 최소화** — 이미 검증된 내용을 같은 세션에서 다시 덤프하지 않는다.
- **진단 결과는 verdict/핵심 수치만** — 게이트·훅 JSON 응답 전체 대신
  `scripts/ops/gate_concise.py <대상 스크립트>` 로 실행해 verdict/실패
  목록만 본다. 전체 출력은 `data/reports/gate_concise_logs/`에 자동 보관된다.
- **큰 산출물은 파일로 저장, 대화창엔 요약만** — 대량 목록/리포트는
  파일에 쓰고 대화에는 건수·핵심 사례만 보고한다.
- 새로 짠 진단 스크립트는 커밋 전
  `python scripts/ops/audit_verbose_output_lint.py <파일...>` 로 장황한 통째
  출력 패턴(`json.dumps(..., indent=..)`/`pprint.pprint()`)이 있는지
  점검한다(정보성 — 빌드를 막지 않음).

---

## 4. 안전 금지선 (ABSOLUTE PROHIBITIONS)

### Git 금지
- `git add .` — 전체 스테이징 금지. **반드시 파일명 명시 스테이징**
- `git clean` / `git reset --hard` / `git checkout -- .` 금지
- commit 전 `git diff --cached --name-only` 검증 필수 — Excel/타 도메인 파일 있으면 STOP

### 기능 금지
- header/footer paragraph 편집 활성화 금지 (단, §4.2 조건 충족 시 예외 — **텍스트 내용만**)
- image/shape/media 편집 구현 금지
- table structure edit 구현 금지
- 신규 charPr 생성 금지 (단, §4.1 서식 편집 조건 충족 시 예외)
- `header.xml` mutation 금지 (단, §4.1 charProperties append 는 예외)
- Excel 파일 수정 금지
- push 전 사용자 명시 승인 필수

### 4.1 서식 편집 (조건부 허용, 2026-07-23 개정 / 2026-07-24 확장)

문단 **서식 속성**(글꼴 종류·크기·색상·굵게/기울임/밑줄) 변경을 위한
신규 charPr 추가에 한해 아래 조건 전부를 만족하면 허용한다. 그 외
(table structure, image/shape, header/footer paragraph 등)는 위
금지선을 그대로 유지한다.

- `header.xml` charProperties 에 신규 charPr 추가 허용 — **append-only**
- 기존 charPr 의 수정·삭제·ID 재사용 금지
- 신규 ID 는 기존 최대값+1부터 순차 부여
- 글꼴(fontFace)은 **문서 안에 이미 존재하는 폰트 리소스만** 참조 —
  header.xml 의 fontfaces 테이블에 신규 폰트 항목 추가는 금지(기존
  글꼴 중 선택만 허용, 폰트 리소스 자체의 신규 등록 아님)
- 커밋 게이트: 한컴 정상 열림 + 무편집 라운드트립 동일 + 구조 diff 기준선 미초과

### 4.2 머리말/꼬리말 편집 (조건부 허용, 2026-07-24 신설)

`<hp:header>`/`<hp:footer>` 안 문단의 **텍스트 내용 편집**(삭제·삽입·
치환)에 한해 허용한다. 본문 문단과 동일한 명령(TYPE_TEXT/
REPLACE_TEXT_RANGE/DELETE_TEXT_RANGE)만 쓰고, 신규 프리미티브를
만들지 않는다 — §11-6 자재 재사용 원칙과 동일.

- 허용: header/footer 안 문단의 텍스트 삭제·삽입·치환
- 금지(그대로 유지): header/footer **구조** 변경(신규 header/footer
  추가·삭제, applyPageType 변경), header/footer 안 **표 구조** 변경
  (표는 이미 위 "table structure edit 구현 금지"로 막혀 있음 — 표
  안 텍스트 편집은 본문 표 셀과 동일하게 허용, 행/열 자체는 불가),
  header/footer 안 이미지/도형 편집
- 페이지 번호 자동필드(pageNumCtrl) 등 자동 갱신 필드는 텍스트로
  취급하지 않는다 — 편집 대상에서 제외
- 커밋 게이트: 한컴 정상 열림 + 무편집 라운드트립 동일 + 구조 diff 기준선 미초과

### 4.3 원본 직접 수정 (조건부 허용, 2026-07-24 신설 — 대표님 명시 지시)

web_office 편집(셀/문단/서식) 저장은 기본적으로 sandbox 사본에
쓰던 것을 원본 파일에 직접 반영하는 방식으로 전환한다("내가 사용자고
운영규칙은 내가 정해 원본 편집을 하도록 수정해" — 대표님 직접 지시,
기존 "원본 무수정" 원칙의 이 기능 한정 명시적 폐기).

- 순서 고정: 기존 verify7 등 검증은 그대로 sandbox 산출물에 대해
  먼저 수행 → PASS/PARTIAL 로 확인된 결과물**만** 원본 파일에
  덮어쓴다. "검증 안 된 내용을 원본에 바로 쓰는" 것은 금지 — 검증
  통과 후 반영만 허용.
- API 요청 필드 `editInPlace: true` 로 활성화(cell-save-apply,
  para-save-apply, apply-format 3개 엔드포인트 공통). 프런트엔드는
  세 경로 모두 이 값을 고정 전송한다.
- 반영 후 sourcePath 는 원본 그대로 유지(새 sandbox 파일로 체이닝
  하지 않음).
- 커밋 게이트: 한컴 정상 열림 확인(실측) — 원본 파일이 실제로
  깨지지 않고 정상 재조판되는지 반드시 확인 후 commit.
- 이 조항은 §4.1/§4.2 의 편집 범위 제한(header/footer 텍스트만,
  charPr append-only 등)을 대체하지 않는다 — "무엇을 편집할 수
  있는가"의 제한은 그대로, "어디에 쓰는가"만 바뀐 것.

### 4.4 원본 직접 수정의 대상 한정 (2026-07-24 신설 — 정책 통일)

§4.3 의 원본 직접 수정은 **사용자 소유 문서에만** 허용한다. 아래
읽기 전용 자산 구역은 editInPlace 대상이 될 수 없으며, 그 위에서의
편집·채움은 **항상 새 파일로 산출**한다(원본 무수정).

- 읽기 전용 구역(하위 전체): `data/drafts/form_library/`(카탈로그
  템플릿 — 채움의 원천 라이브러리), `data/recognition_corpus/`,
  `samples/`, `tests/fixtures/`
- 근거: 카탈로그 템플릿(38,000+건)은 채움의 원천이다. 편집기로 열어
  editInPlace 로 저장하면 그 원본이 사라진다 — 되돌릴 수 없는 파괴.
- 강제: `read_only_zones.is_read_only()` 가 판정하고,
  `_apply_in_place_if_requested` 가 읽기 전용이면 in-place 를 거부하고
  사본을 보존한다(`inPlaceRefused: READ_ONLY_ZONE`).
- 두 저장 경로의 역할 분담:
  · 편집기 저장(§4.3): 사용자 업로드/작업 문서 → 원본 직접 수정
  · 배치·에이전트 직접채움(`form_direct_fill`): 카탈로그 템플릿 →
    채워진 새 문서 생성 (원본 무수정, 사본만)
- 공통 불변식: ① 검증(verify) 먼저, 통과분만 기록  ② 결제·송금·
  전자서명·제출 자동 실행 금지(아래 보안 금지선 그대로)

### 4.5 AI 자동채움 드라이 런 의무 (2026-08-01 신설 — 대표님 지시)

AI 해석·자동채움은 **드라이 런(무기입 실행)을 선행하지 않으면 기입
단계로 넘어갈 수 없다.** 기준서:
`docs/design/hwpx_ai_doc_interpretation_fill_standard.md`

- 드라이 런 = 문맥 추출→AI 해석→검증까지만 수행, HWPX 기입 없음.
  산출은 보고서(JSON)뿐이다.
- 기입 허용 조건: 드라이 런 게이트 PASS 인 제안만. 민감칸은 추가로
  사람 확인 후에만.
- 게이트: 비창조 위반(`NON_SOURCE_VALUE`) 통과 0건 · 제3자 칸 제안
  0건 · 주소 해석 실패(`ADDRESS_UNRESOLVED`) 통과 0건.
- AI 는 값을 만들지 않는다 — 소스 데이터에서 유래를 입증 못 하는
  제안은 검증기가 기계적으로 폐기한다.

### 4.6 파싱 우선 · AI 판정 원칙 (2026-08-01 신설 — 대표님 지시)

공정 순서를 고정한다: **① 서류별 파싱(구조 추출) → ② AI 분석 → ③ 무엇을
어느 칸에 넣을지 판정**. 규칙(rule)이 AI 앞에 서서 후보를 미리 잘라내는
것을 금지한다.

- **금지**: 빌드타임 해석에서 규칙 역할(applicant/office)로 AI 입력을
  사전 축소하는 것. `build_context_fields(..., roles=None)` 를 써서 전
  입력칸을 싣는다. 규칙 역할은 `ruleRole` 힌트로만 동승한다.
- **근거(실측)**: 검측요청서 #5067 — 파싱은 셀 338개·빈 칸 241개를
  뽑았는데 규칙이 22칸을 전부 관공서 칸으로 판정해 **AI 가 보는 칸이 0**
  이었다. 시공사가 쓰는 검측부위·검측요구일시·공사량이 통째로 죽었다.
  카탈로그 전체로는 입력창 0개인 '죽은 서식'이 13,858건(44.1%)이다.
- **규칙의 역할은 게이트**다 — AI 판정을 가두는 필터가 아니라, AI 판정을
  적용할 때 합의를 요구하는 안전장치로만 쓴다(아래 두 신호 원칙).
- **두 신호 합의 원칙**: AI 단독 판정으로 칸의 운명을 바꾸지 않는다.
  파일럿 실측에서 AI 단독 강등은 정상 입력칸의 15.8% 를 죽였다.
  · 강등(입력칸→noise): AI + 규칙 패턴이 **둘 다** 아니라 할 때만
    (`should_demote`).
  · 역할 교정(관계자→작성자): 문서 전체가 죽어 있을 때만
    (`should_promote_to_user`, `applicant_count==0`), 보호 구역
    (대장기록·증명발급·발급증서)은 제외 — 잘 도는 서식은 건드리지 않는다.
- **런타임 값 채움은 예외**: 이미 확정된 역할대로 사용자 칸만 채운다
  (`roles=("applicant",)` 기본값 유지). 이 조항은 빌드타임 해석 공정에
  적용된다.
- 커밋 게이트: `scripts/ops/gate_hwpx_ai_interpretation_pipeline.py` PASS.

### 4.7 빌드타임 해석 모델 상향 (2026-08-01 신설 — 대표님 명시 지시)

계승 규칙 §9("Claude Code CLI 최하위 모델(Haiku)만")를 **빌드타임 필드
해석 공정에 한해** 개정한다("모델 조정해서 캐시 공사하자" — 대표님 직접
지시).

- 대상: `ai_field_interpretation`(캐시 생성) — **이 경로만**. 해석 결과는
  한 번 굳으면 카탈로그에 영구히 남아 이후 모든 채움의 근거가 되므로,
  일회성 런타임 호출보다 품질 가치가 크다.
- 모델: `claude-sonnet-5`. 환경변수 `HWPX_AI_INTERPRET_MODEL` 로 조정
  가능(무설정 시 위 값).
- **그대로 유지되는 경로**: 런타임 값 채움(`ai_form_fill`,
  `ai_doc_interpret`)은 Haiku 고정 — 사용자 요청마다 도는 경로라 §9 의
  비용·지연 근거가 그대로 유효하다.
- 안전선 불변: AI 는 여전히 값을 만들지 않고(§4.5 비창조), 두 신호 합의
  없이는 칸의 운명을 바꾸지 못한다(§4.6). 모델을 올려도 게이트는 그대로다.

### 4.8 API 호출은 Claude Code에서만 (2026-08-02 신설)

저장소 스크립트는 API를 호출하지 않는다. Claude Code(나의 세션)에서만 API 호출.
이렇게 하면 스크립트에 API 키가 필요 없고 보안 위험이 없다.

**역할 분담:**
- **스크립트** (data processing): 파싱, 필터링, 검증, 캐시 생성 등
- **Claude Code** (AI work): 필드 해석, 검증, 맥락 분석 등 (API 자동 포함)

**규칙:**
- 금지: 스크립트에서 `os.getenv()`, `os.environ`, 설정 파일로 API 키 접근
- 허용: Claude Code 세션에서 직접 작업 (`from anthropic import Anthropic` 등)
- 훅: `scripts/ops/gate_api_key_detection.py` — API 접근 코드 탐지
  · `os.getenv('ANTHROPIC_API_KEY')` 등 탐지 → commit 거부
  · 커밋 게이트: API 키 접근 코드 0건 통과 필수

**예:**
```python
# ❌ 금지 (스크립트)
from anthropic import Anthropic
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ✅ 허용 (Claude Code 세션에서만)
from anthropic import Anthropic
client = Anthropic()  # 세션 인증 자동 사용
```

### 보안/개인정보 금지
- `secret / token / password / env` 값 출력 금지
- 결제 / 송금 / 전자서명 / 제출 자동 실행 금지
- **API 키 보호** (§4.8 참조): 스크립트에 기입 금지, Claude Code 세션만 사용

---

## 5. 공용창고 규칙

| 창고 경로 | 역할 |
|-----------|------|
| `data/audit/` | 감사 기록, append-only |
| `logs/change_history.jsonl` | 커밋 이력, KNOWN_HOLD |

---

## 6. 건축 시공 표준 절차 (계승)

```
① 대지 조사 → ② 시공 계획서 → ③ 대표님 승인 →
④ 시공 → ⑤ 감리검사 → ⑥ 준공검사 (audit) →
⑦ 회귀 → ⑧ commit + 현재창 보고
```

- 기능 FAIL 시 commit 금지
- commit 전 staged 파일 검증 필수 (HWPX 범위 외 파일 있으면 STOP)

---

## 7. AI fill 파이프라인 범위

AI fill(자동 입력) 로직은 `scripts/hwpx/pipeline/`, `scripts/hwpx/ai_proposal/`,
`scripts/hwpx/recognition_corpus/` 등에 포함되어 있으며 이 저장소에서 관리한다.
단, AI inject 없이 자동 입력 실행은 금지한다.

---

*분리 일: 2026-05-22*
*원본 저장소: office-analysis-engine (33. office-analysis-engine)*
