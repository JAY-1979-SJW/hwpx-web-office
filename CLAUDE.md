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

### 보안/개인정보 금지
- `secret / token / password / env` 값 출력 금지
- 결제 / 송금 / 전자서명 / 제출 자동 실행 금지

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
