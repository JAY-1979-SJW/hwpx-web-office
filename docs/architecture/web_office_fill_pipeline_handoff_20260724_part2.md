# 서식 채움 공정 인계 (속편) — 기입 완성·검증·정책 통일

**작성**: 2026-07-24 (같은 날 후반)
**선행**: `web_office_fill_pipeline_handoff_20260724.md` — 그 문서의
"저장 단계에서 빈 칸에 못 쓴다"는 이 속편에서 **해결됨**. "4. 미해결 결함"
절은 이 문서로 갱신된다.

---

## 0. 한 줄 요약

기입 파이프라인이 **완성·전수 검증**됐다. 빈 칸 기입 결함을 잡고, 배치·에이전트용
직접채움 경로(1,100초→0.2초)를 만들고, AI 제3자 보호·읽기전용 구역 가드를 세웠다.
40서식 전수시험 유출 0, 역할 정확도 95.2%(무오염셋)로 재측정. 원본은 안 건드린다.

---

## 1. 이 세션(후반)에 한 것 — 커밋 순서

```
b9782a5  fix  셀 문단 조회를 격자주소→셀 순번 (좌표 결함)
3f94c2a  fix  셀 텍스트 손실(hp:t tail)+중첩 표 중복 (불일치 380→0)
0f12329  chore 잠금 재고정
517849c  fix  빈 입력칸에 못 쓰던 결함 (자동채움 전제)
ff714d0  perf 통합 재생성 배치 + 셀 조회 O(셀×섹션) 해소
8030895/9a3afa8 perf 재생성 샤드 분할 + DB잠금 수리
1df3133  feat HWPX 파싱 캐시 (재실행 2.9분→2초)
b992ad6  fix  읽기/쓰기 중첩 표 비대칭 (전량기입 유출)
837fd8a  feat 세션 점유 게이트
415174f  feat 서식 직접 채움 (1,100초→0.2초)
9d1f9a2  fix  AI 채움이 신청인 이름을 제3자 칸에 제안 (subject 보호)
0ec1bcd  feat 역할·의미 분리 (office 칸 52,598 회수)
cbcc906  feat 읽기 전용 자산 in-place 차단 (§4.4)
603233a  docs 역할 정확도 재측정 (94.2 무효→95.2 유효)
a9f96fe  docs 입력 census 범위 명시 (미푸시)
```

## 2. 지금 상태 (실측)

| 항목 | 값 |
|---|---|
| 서식·입력칸 | 38,049건 · 370,505칸 (paragraphId 100%) |
| promote | 완료 (forms=staging, 불일치 0) |
| sensitive_count | 3,018 (역할·의미 분리 후, +1,333) |
| 제3자칸 | 2,128 |
| 기입 정확성 | 40서식 356칸 전수, 유출 0, 원본 무변경 |
| 역할 정확도 | ③무오염셋 95.2%(99/104, 드리프트 0) |
| 직접채움 속도 | 서식당 0.2초 |

**전수 조사 범위 확정**: 입력 census 는 본문 표 셀 한정. 실측 표 밖 3.4%
(대부분 여백), header/footer 입력칸 0. 누락이 아니라 실익 없어 제외한 범위.

## 3. 핵심 자재 (새로 생긴 것)

- `scripts/hwpx/web_office/form_direct_fill.py` — **배치·에이전트 채움은
  이걸 쓴다.** 원본 사본에 1회 파싱·기입·저장. 원본 무수정. `fill_document_direct
  (source_rel, fills=[{paragraphId,value}], output_dir=)` → 새 파일. 정확성은
  `verify_output` 으로 재확인(저장본 다시 열어 제자리·유출 검사).
- `scripts/hwpx/web_office/parse_cache.py` — 파서 수정 때만 재생성, 규칙 변경은
  캐시 읽기. `PARSER_SOURCES` 관리가 핵심(빠뜨리면 조용히 낡음). `--verify` 가
  그 구멍을 잡는다.
- `scripts/hwpx/web_office/read_only_zones.py` — §4.4 가드. `is_read_only(rel)`.
- `scripts/ops/gate_hwpx_session_claim.py` — 세션 점유 게이트(pre-commit 배선).
- `build_input_schema_batch.py --backfill-semantics` — 라벨 전용 의미 재계산.

## 4. 저장 정책 — 출처가 정한다 (§4.3/§4.4)

- **편집기 저장(§4.3)**: 사용자 소유 문서 → verify7 통과 후 원본 직접 수정.
- **직접채움(§4.4)**: 카탈로그 템플릿 → 새 파일. 원본 무수정.
- 읽기 전용 구역(`data/drafts/form_library/`·`samples/`·`tests/fixtures/`·
  `data/recognition_corpus/`)은 in-place 금지 — 가드가 막는다.

## 5. 남은 것 (전부 채움 "바깥" 별도 공정 — 우선순위 순)

1. 🟡 **프론트 질문 패널** — 백엔드(`/fill-plan`·`/ai-fill`) 준비 완료, **UI 미구현**.
   사용자가 실제로 쓰려면 이게 다음 관문. `weboffice.html`/`app.mjs`(병행 세션 영역).
2. 🟡 **OCR 실촬영 종단** — `/source-extract` 를 더미가 아닌 **진짜 이미지**로 1회.
3. 🟡 **V1/V7 readback 검증기** — 여전히 하드코딩 FAIL(`V1_READBACK_UNSUPPORTED`).
   좌표가 수리됐으므로 이제 구현 가능. 기입은 되지만 파이프라인 내 위치검증이 스텁.
4. 🟢 **파싱 캐시 전량 생성** — 모듈·감리 완비. 파서가 안정된 뒤 6샤드로 1회
   (`parse_cache.py --build --shards 6`). 그러면 verify_output 재확인(181초)이 수초로.
5. 🟢 **세무 서식 수집 공백** — 종합소득세 4건뿐, 국세청이 기관 상위에 없음. 미조사.
6. 🟢 **`char_pr_height` 셀마다 header 재파싱(129초)** — 로드 지연의 대부분.
   `hwpx_table_ops.py` 가 타 공정 잠금이라 미착수.

## 6. 재개 시 반드시 (동시 세션 주의)

- **여러 세션이 같은 브랜치에 커밋한다.** 커밋 전 `git diff --cached --name-only`,
  후 `git show --stat HEAD` 필수. `amend`/`rebase` 금지.
- 세션 시작 시 `gate_hwpx_session_claim.py --session <ID> --claim <파일들>` 로
  점유 선언, 커밋 시 `HWPX_SESSION_ID=<ID>` 를 실어야 게이트 통과. 끝나면 `--release`.
- 잠금 기준(`BASELINE_COMMIT`)이 세션 간 번갈아 옮겨진다 — 재고정 전 **현재값을
  먼저 읽을 것**. `ro_view_importer.py`/`hwpx_paragraph_ops.py` 건드리면 잠금 다수 걸림.
- 서버 프로세스 죽일 때 **포트·시작시각으로 소유 구분** — 남의 서버 몰살 전례 있음.

## 7. 미푸시

`a9f96fe` 1건(범위 명시 문서). push 는 §4 명시 승인 필요.
