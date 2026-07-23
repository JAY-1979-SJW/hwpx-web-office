# 서식 자동채움 공정 — 인계 문서

**작성 시점**: 2026-07-23
**커밋 범위**: `42c4f16` … `28993d4` (6건, 전부 로컬 — **push 미실행**)

---

## 1. 이 공정이 만든 것

HWPX 서식을 열면 **무엇을 채워야 하는지 알아내고, 아는 값은 채우고, 모르는
값은 물어보는** 계층.

```
HWPX → 분류 → 입력칸 추출 → 역할·의미 판정 → 채움 계획 → 기입 → 8관문 → 저장
```

### 모듈 (전부 `scripts/hwpx/web_office/`)

| 모듈 | 역할 |
|---|---|
| `form_taxonomy.py` | 문서 유형 8종 분류 · 채움가능 여부 |
| `form_field_roles.py` | 칸 역할(신청인/관공서/잡음) · 의미 태그 · 주체(self/thirdParty) |
| `form_input_schema.py` | 위 둘을 합친 최종 입력 스키마 (paragraphId 포함) |
| `form_fill_planner.py` | 자동채움 / 질문 / 제외 3갈래 라우팅 |
| `form_requirements.py` | 첨부서류·처리기간·수수료·근거법령·제출처 추출 |
| `para_save_apply_bridge.py` | 문단 명령 → 저장 파이프라인 브리지 |
| `hwpx_sample_source.py` | 테스트·감리용 표본 해석기 (레거시 DB 부재 대응) |

### 배치

| 배치 | 상태 |
|---|---|
| `classify_forms_batch.py` | 완료 — 38,165건 분류 |
| `extract_requirements_batch.py` | 완료 — 29,049건 해부 (실패 0) |
| `build_input_schema_batch.py` | **진행 중** — 30,868 적재 / 482 남음 |
| `ingest_external_hwpx.py` | 완료 — 원드라이브 6,004건 반입 |

### 엔드포인트 (`editor_api_route.py`)

```
POST /api/web-office/fill-plan         채움 계획 (프로필은 요청이 실어 보냄)
POST /api/web-office/para-save-apply   문단 편집 저장 (신설)
POST /api/web-office/cell-save-apply   셀 편집 저장 (기존)
POST /api/web-office/hwpx-load         로드
```

---

## 2. 다음 세션에서 바로 이어갈 것

### ① 질문 패널 프론트엔드 (백엔드 준비 완료)

`/fill-plan` 이 이미 다음을 돌려준다:
```json
{ "autoFill": [{label, value, paragraphId, semantic, source}],
  "questions": [{label, question, paragraphId, suggested, requiresConfirmation}],
  "autoFillCount", "questionCount", "coverage" }
```

프론트에 필요한 것:
1. 프로필 입력 — **브라우저 로컬 저장**(localStorage). 서버 저장 금지
   (주민등록번호 등 고유식별정보 처리자 책임을 지지 않기 위함)
2. 질문 목록 표시 + 답변 입력
3. "채우기" → `paragraphId` 로 `TYPE_TEXT` 명령 발행 → `/para-save-apply`

`weboffice_edit.html` 의 `saveDocument()` 가 저장 경로의 참고 구현이다.

### ② 남은 배치
```
python3 scripts/hwpx/web_office/build_input_schema_batch.py            # 482건
python3 scripts/hwpx/web_office/build_input_schema_batch.py --backfill-subject
```
두 번째는 **반드시 실행해야 한다.** subject(제3자 표시)가 없으면
'법정대리인성명' 같은 칸에 신청인 프로필이 자동으로 들어간다.
라벨만으로 계산되므로 재파싱 없이 수초에 끝난다.

---

## 3. 미해결 결함 (순서 있음)

### 🔴 셀 좌표계 불일치 — 선행 과제
```
renderPayload.cells[].col          격자 주소 (colSpan 반영)
documentModel.containerScope.colIndex   셀 순번
```
확장·병합 셀 뒤부터 어긋난다. 실측 **표본 40건 · 셀 4,810개 중 473개(9.8%)
불일치 · 영향 서식 40/40**.

- 고정 테스트: `tests/test_web_office_cell_coordinate_agreement.py`
  (xfail strict — 수리되면 xpass 로 실패해 반드시 인지된다)
- **수리 시 시각회귀 baseline 재고정이 함께 필요하다.**
- 이 영역은 다른 작업이 동시에 건드리고 있었다(`334d665`, `443fb79`,
  `65df04a`, `a99c965`). 충돌 확인 후 착수할 것.

### 🔴 문단 readback 검증기 미구현 — 좌표 수리 이후
`paragraph_save_verify7.py` 에서 `V1_RANGE_POSITION_OK` 가 하드코딩 FAIL
(`V1_READBACK_UNSUPPORTED`). V7 은 V1 종속. 즉 저장은 되지만 **"쓴 위치가
정확한가" 를 기계가 확인하지 못한다.** 실제로 검증되는 것은 V4(charPr)·
V5(parPr)·V6(출력격리) 뿐이다.

문단 ID 는 원본·출력에서 동일함을 확인했으므로 원리적으로는 가능하다.
다만 좌표계가 어긋난 상태에서 얹으면 옆 칸을 제 칸으로 오인한다.

### 🟡 정확도 수치의 한계
역할 판정 정확도 **94.2%**(무오염 정답셋 `field_role_testset.json`)는
정답셋을 같은 추출 결과로 만들었기 때문에 **좌표 정확성을 검증하지 못한다.**
좌표 수리 후 재측정 필요.

### 🟡 잡음 규칙이 놓치는 사례
파일명이 실제 제목과 다르면 제목·수신처가 질문 목록에 올라온다.
(예: `교육기관대행갱신신청서`, `국토교통부장관교육관리기관의장`)

### 🟡 기타
- 문서유형 `기타` 15.2% (5,818건) — 이름 어미로 안 잡히는 것들
- 감리 FAIL 3종: `para_edit_ime_live`(잠금 재고정 필요) ·
  `browser_viewer_prototype` · `applyformat_existing_charpr_closeout`

---

## 4. 반드시 지킬 설계 원칙

1. **AI 는 값을 만들지 않는다.** 모르는 칸은 빈칸으로 남긴다 — 관공서
   제출물에 그럴듯한 값을 넣으면 허위 기재다.
2. **민감칸은 프로필에 값이 있어도 자동으로 넣지 않는다.** 매번 확인
   (`requiresConfirmation`).
3. **제3자 칸(`subject == "thirdParty"`)에 신청인 프로필을 넣지 않는다.**
4. **클라이언트를 믿지 않는다.** 문단 내용·containerScope·문서 해시는
   서버가 원본에서 다시 만든다.
5. **채움은 좌표가 아니라 `paragraphId` 로 겨냥한다** (좌표 결함 우회).
6. **프로필을 서버에 저장하지 않는다.**
7. §4 유지: 신규 charPr/paraPr 금지 · `header.xml` 불변 · 원본 무수정 ·
   출력은 sandbox 별도 파일.

---

## 5. 실측 수치 (근거)

| 항목 | 수치 |
|---|---|
| 수집 서식 | 38,165건 |
| 분류 | 신청신고 15,308 · 증명발급 5,321 · 보고통지 4,827 · 대장기록 3,316 · 기타 5,818 · 계획내역 1,464 · 기준별표 1,445 · 계약동의 666 |
| 채움가능 | 33,604건 (88.0%) |
| 해부 | 근거법령 19,627 · 처리기간 8,471 · 제출처 8,247 · 첨부서류 7,281(항목 21,953) · 수수료 7,272 |
| 스키마 | 30,868건 적재 · 신청인칸 86,243 · 관공서칸 108,538 · 민감칸 791 |
| 역할 판정 정확도 | ①튜닝 96.7% ②검증 97.5% **③무오염 94.2%** |
| 프로필 자동연결률 | 37.9% (나머지 62.1%는 서식 고유 항목 — 롱테일이라 규칙으로 더 안 줄어든다) |
