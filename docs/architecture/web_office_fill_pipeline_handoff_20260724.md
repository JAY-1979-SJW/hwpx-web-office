# 서식 채움 공정 인계 — 좌표·텍스트 수리부터 종단 시험까지

**작성**: 2026-07-24
**직전 인계**: `docs/architecture/web_office_form_fill_handoff.md` (2026-07-23)
— 그 문서의 "3. 미해결 결함" 절은 **이 문서로 대체**된다.

---

## 0. 한 줄 요약

파싱 계층의 결함 3종을 잡아 좌표 불일치를 0으로 만들고 파생물을 전량
재생성했다. 그러나 **저장 단계에서 빈 칸에 글자를 쓰지 못하는 결함**을
발견해, 자동채움은 아직 파일로 나가지 못한다.

---

## 1. 이번 공정에서 수리한 것

### ① 셀 문단 조회가 옆 칸을 집어옴 (`b9782a5`)

최초 진단("두 뷰가 다른 좌표계")은 **틀렸다.** 양쪽 다 같은 값(셀 순번)을
쓰는데, 문단을 가져올 때만 그 번호를 **격자 주소로 조회**했다.

```
table_parser._parse_table_element   col = ci                  ← 행 안 셀 순번
ro_view_importer._find_cell_elem    cellAddr/@colAddr 로 매칭  ← 격자 주소
```

`colSpan>1` 셀이 하나 지나가면 그 뒤로 전부 어긋난다. 조회가 아예 빗나가
`None` 이 되면 조용히 합성 fallback 으로 빠져 **텍스트는 맞지만 run·charPr
정밀도를 잃었다**(눈에 안 보이던 두 번째 얼굴).

### ② `hp:t` 인라인 자식 뒤 글자 유실 (`3f94c2a`)

`_cell_raw_text` 가 `elem.text` 만 읽어, 인라인 자식 뒤 글자(`child.tail`)를
통째로 버렸다.

```
<hp:t>(서명<hp:fwSpace/>또는<hp:fwSpace/></hp:t>   →  '(서명'

'(서명 또는 인)'          → '(서명인)'
'[]천장재[]단열재…'        → '[][][]'
'건축법 시행령」제15조'     → '건축법제15조'
```

이 값은 `renderPayload.cells[].text` 를 타고 **뷰어 표시와 라벨 추출까지**
갔다. 같은 저장소의 `ro_view_importer._inline_text_content` 는 tail 을
제대로 훑고 있었다 — 한쪽만 고쳐져 있었다.

### ③ 중첩 표 내용 중복 (`3f94c2a`)

중첩 표는 renderPayload 에 별도 표로 이미 실리는데 바깥 셀이 삼켰다.
**경로가 넷이라 다 막아야 했다**:

- `_cell_raw_text` — `continue` 는 `tbl` 원소만 거르고 서브트리는 훑는다
- `_iter_paragraphs_in_cell_elem` — 중첩 표 안 `hp:p` 제외
- `_extract_runs_from_paragraph_elem` — **중첩 표는 문단이 아니라 문단 안
  `hp:run` 속에 있다.** `paragraph_runs` 가 `.iter()` 라 딸려온다
- `_inline_text_content` — `tbl` 서브트리 진입 차단

### ④ 셀 조회가 O(셀수 × 섹션크기) (`ff714d0`)

프로파일(결산보고서 305KB·표 86개·셀 6,854개, 전체 636초):

```
_find_table_elem   6,940회 470초   ← 셀마다 섹션 XML 전체 재훑기
local_name       5억 9,276만회 215초
```

호출부가 표 원소를 이미 갖고 있었다. 넘겨 쓰도록 바꿔 **파일당 33.1초 →
18.2초**.

### 실측 결과 (표본 40건 · 비교 셀 12,727개)

| | 수리 전 | 최종 |
|---|---|---|
| 좌표 불일치 | 380건 (3.2%) | **0건** |
| 영향 서식 | 38/40 | **0/40** |
| run 정밀도저하 경고 | 4,745 | 4,159 |

고정 테스트 `tests/test_web_office_cell_coordinate_agreement.py` 는
xfail 해제되어 **실제 회귀 감시**로 전환됐다.

---

## 2. 새로 지은 자재

### `rebuild_form_derivations_batch.py` — 파생물 통합 재생성

셋(입력 스키마·행정 요건·라벨 색인)이 전부 같은 HWPX 를 연다. 한 번 열어
셋을 함께 만든다. `field_count` 를 먼저 뽑고 그걸로 분류(`fillable`)한 뒤,
새 `fillable` 기준으로 스키마를 만든다. `subject` 도 여기서 끝내
**별도 backfill 패스가 필요 없다.**

- 기존 `forms`/`fields` 를 **건드리지 않고** 스테이징 테이블
  `derivations_rebuild` 에만 쌓는다
- 반영은 `--promote` 별도 단계, 커버리지 미달이면 거부
- `--shard k --shards N` 병렬 (16코어 기계에서 1코어만 쓰던 문제)

### `parse_cache.py` — 파싱 캐시

파서를 고칠 때만 1회 재생성하고, 라벨·역할 규칙 변경은 캐시 읽기로 끝난다.

```
JSON 무압축   원본의 45.6배      gzip 압축   원본의 1.8배 (전량 3.76GB)
캐시 읽기     0.041 초/건        같은 12건 재실행: 2.9분 → 2초
```

조용히 낡는 것을 두 겹으로 막는다:
① **파서 버전 태그** — `PARSER_SOURCES` 15개 파일의 내용 해시가 저장 경로에
들어간다. 파서가 바뀌면 캐시가 통째로 빗나가 자동 재생성.
② **`--verify`** — 표본을 실제 재파싱해 대조. ①의 목록 누락이 유일한 구멍인데
그걸 잡는다.

> ★ **파싱 경로에 모듈을 추가하면 `PARSER_SOURCES` 에도 반드시 추가할 것.**

감리 `tests/test_web_office_parse_cache.py` 13건.

---

## 3. 지금 상태

### 재생성 — **완료, 미반영**

```
스테이징 38,049 / 38,049   실패 0
  OK 35,793 · SKIP_OUTSIDE_PROJECT 2,256
  스키마 보유 31,408건 · 입력칸 370,505 · 제3자칸 2,128
```

**`--promote` 는 아직 실행하지 않았다.** 반영하면 바뀌는 행:

| 컬럼 | 달라지는 행 |
|---|---|
| `input_schema` | 30,073 (79.0%) |
| `field_count` | 25,704 (67.6%) |
| `input_count` | 22,028 (57.9%) |
| `req_status` | 8,260 (21.7%) |
| `fillable` | 2,312 (6.1%) |
| `doc_type` | 2,256 (5.9%) |

절반 이상이 바뀐다 — 텍스트 손실 수리의 영향 범위가 그만큼이다.

---

## 4. 발견한 미해결 결함 (우선순위 순)

### 🔴 ① 빈 칸에 글자를 못 쓴다 — **최우선**

전기사용신청서로 종단 시험한 결과:

```
rejected: RUN_TEXT_NODE_MISSING
verify7:  V1_RANGE_POSITION_OK FAIL · V4 FAIL · V5 FAIL · V7 FAIL
applied = ∅
```

대상 칸의 실제 모습:

```json
runs: [{"runId":"…_run0", "text":"", "charPrIDRef":"11"}]
```

**빈 칸의 run 에는 `<hp:t>` 텍스트 노드가 없다.** writer 가 넣을 자리가
없어 거부한다.

**자동채움이 노리는 칸은 정의상 전부 빈 칸이다.** 즉 현재 writer 로 채울 수
있는 칸이 하나도 없다. 기존 문단 편집 시험이 통과해온 것은 **이미 글자가
있는 칸을 고치는 경우**였기 때문이다.

원본은 안전하다 — `sourceUnchanged: true`, `V6_OUTPUT_ISOLATED: PASS`.

수리 방향: writer 가 빈 run 에 `<hp:t>` 를 생성하도록 한다. `charPrIDRef`
는 기존 run 것을 그대로 쓰므로 §4 "신규 charPr 금지"에 저촉되지 않는다.

### 🔴 ② AI 경로가 제3자 보호를 우회한다

```
/ai-fill 제안: {'label':'법정대리인성명', 'value':'홍길동', 'confidence':0.9}
```

신청인 이름을 **법정대리인 칸**에 넣으라고 제안했다. `subject=thirdParty`
보호(스테이징 2,128칸)가 AI 경로에는 적용되지 않는다. 규칙 경로
(`/fill-plan`)는 제대로 걸렀다 — **보호는 있는데 AI 경로만 안 본다.**

프론트가 ai-fill 제안을 그대로 쓰면 관공서 제출물에 허위 대리인이 기재된다.
§4 원칙 3번 위반.

수리 방향: `ai_form_fill.propose_values` 가 입력 스키마의 `subject` 를 받아
`thirdParty` 칸은 제안에서 제외하거나 `requiresConfirmation` 을 강제.

### 🟡 ③ 역할 판정이 의미까지 끈다

`form_field_roles.py:303`

```python
elif kind in (KIND_INTERNAL, KIND_CERTIFICATE):
    role, why = "office", f"FORM_KIND:{kind}"   # 서식 전체를 일괄 office
...
sem, typ = _semantic_of(lab) if role == "applicant" else ("", "")
```

office 174,428칸 중 **150,528칸(86.3%)이 서식종류 일괄 처리**이고, 그중
**40,096칸은 라벨만 보면 의미가 나온다**:

```
2,589 성명→name   2,186 주소→address   1,237 생년월일→birth
1,001 전화번호→phone   672 주민등록번호→residentNo
```

**주민등록번호 672칸이 의미도 민감칸 표시도 없이 방치**돼 있다.

원래 취지(행정 내부문서 자동채움 방지)는 옳으나, "자동채움 금지"와
"무슨 칸인지 알아보지도 않기"를 **같이 껐다.**

수리 방향: `role` 은 그대로 두되(자동채움 차단 유지) `semantic`·`sensitive`
는 전 칸에 계산한다. §4 원칙은 그대로 지켜지고 모르는 칸이 40,096개 준다.

### 🟡 ④ 역할 판정 정확도 94.2% 는 무효

정답셋을 **손실된 텍스트**로 만들었다. 재측정 전까지 근거로 쓸 수 없다.

### 🟡 ⑤ `char_pr_height` 가 셀마다 header.xml 재파싱

6,957회 129초(전체 636초 중). 문서당 1회면 될 일이다.
`hwpx_table_ops.py` 가 writer_para_plan 공정의 잠금 대상이라 착수하지 않았다.

---

## 5. 재개 순서

```
① 빈 run 텍스트 노드 생성        ← 이게 막히면 앞단이 다 무의미
② AI 경로 subject 보호 연결
③ 재생성 --promote 결재 후 반영
④ 역할·의미 분리 (40,096칸 회수)
⑤ 정확도 재측정
⑥ 파싱 캐시 1회 생성 → 이후 ④⑤류 재계산은 수 분
```

④가 **캐시의 첫 수혜 사례**가 된다 — 재파싱 없이 끝난다.

### 명령

```bash
python scripts/hwpx/web_office/rebuild_form_derivations_batch.py --status
python scripts/hwpx/web_office/rebuild_form_derivations_batch.py --promote
python scripts/hwpx/web_office/parse_cache.py --build --shard 0 --shards 6
python scripts/hwpx/web_office/parse_cache.py --verify --sample 25
```

로컬 서버:
```bash
python -m uvicorn scripts.hwpx.web_office.editor_api_route:app --port 8790
# 8765는 다른 앱이 점유
```

---

## 6. 확인된 사실 (재조사 불필요)

- **입력셀 주소는 100% 확보** — 입력칸 전부가 `paragraphId` + `(표,행,열)`
  을 갖는다. 겨냥 못 하는 칸이 있는 서식 0건.
- **입력 census 는 본문 표 셀(containerScope.kind=="cell") 한정** — 실측
  (표본 60건): 빈 문단의 96.6%가 표 셀, 표 밖은 3.4%뿐이고 그마저 대부분
  표 사이 여백(결산보고서류)이지 입력칸이 아니다. header/footer 입력칸은
  0(헤더는 제목·페이지번호 등 고정 내용). 즉 "표 밖 산문 빈칸·헤더"는
  census 대상이 아니며, 이는 누락이 아니라 **실익 없어 제외한 범위**다.
- **OCR·AI 경로는 이미 구현돼 있다** — `/source-extract`(Claude 비전),
  `/ai-fill`, `/fill-plan`, `/para-save-apply`. 종단 시험에서 ①②③ 은 실제로
  작동했다.
- **사전에 없는 칸도 질문은 만들어진다** — `전기사용장소*`, `사용용도` 처럼
  semantic 이 없어도 라벨 그대로 질문이 생성된다. 사전을 키우는 것보다
  OCR·AI 로 값을 받는 쪽이 구조적으로 맞다.
- **서버 이관은 택하지 않았다** — 파싱 대상 1.62GB(35,791파일)에 제3자 회사
  작성 문서가 포함되고, 기존 배포 스크립트도 코퍼스를 의도적으로 제외한다.
  대신 재파싱 자체를 없애는 캐시로 갔다.

---

## 7. 동시 작업 주의

`feat/hwpx-coord-fidelity` 브랜치에 **여러 세션이 동시에 커밋한다.**
실제 사고: 경로 지정 커밋을 준비하는 사이 다른 세션이 커밋하면서 내 작업
파일 10개를 자기 커밋(`f6d36c4`)에 쓸어갔다. 내용은 반영됐으나 메시지는
무관하게 남았다.

- 커밋 직전 `git diff --cached --name-only` **필수**
- 커밋 후 `git show --stat HEAD` 로 **실제로 무엇이 담겼는지 확인**
- `amend`/`rebase` 금지 — 다른 세션 작업을 파괴한다

잠금 기준(`BASELINE_COMMIT`)도 여러 세션이 번갈아 옮긴다
(`334d665` → `b9782a5` → `3f94c2a` → `2f7db75` → `e9517fc`).
`ro_view_importer.py` 를 건드리면 잠금 8곳이 걸리므로, 준공 후 기준점을
옮기고 시방서 2건에 갱신 이력을 덧붙인다.
