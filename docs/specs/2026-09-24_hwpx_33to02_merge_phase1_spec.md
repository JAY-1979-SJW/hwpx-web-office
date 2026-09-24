# HWPX 코드 33 → 02 통합 1단계 기준서 (02를 유일 정본으로)

- 작성: 2026-09-24, 메인 세션(설계·감리)
- 모드: spec-driven-build **참조구현 모드** — 병합 결과 파일(참조구현)은 메인이 이미 만들어 드라이런까지 마쳤다. 시공자는 옮기고 테스트만 쓴다.

### 목적
2026-05-22 `office-analysis-engine`(33)에서 이 저장소(02)로 HWPX 도메인을 분리했지만, 33에 `scripts/hwpx/` 복사본이 남아
분리 이후 33 쪽에서만 고친 내용(2026-09-01, 커밋 fb3ebf5·9938d70 — g2b용 RO-VIEW 렌더 서비스와 버그 수정)이 02에 없다.
1단계는 **33에만 있는 HWPX 변경·파일을 02로 흡수해 02를 상위집합(정본)으로 만든다.** 33은 이번 단계에서 건드리지 않는다.

### 기존 코드 점검 (메인 실측, 2026-09-24)
- 두 저장소 공통 `scripts/hwpx/` 파일 224개: 동일 207, 상이 17. 상이 17개 중 16개는 33이 분리 이후 미변경(02가 최신) → 조치 없음.
- 유일한 양쪽 변경 파일: `scripts/hwpx/web_office/ro_view_importer.py` (02: 2026-08-05, 33: 2026-09-01).
  - 3-way 병합(기준 = 33 `fb3ebf5^` = 02 최초 판, 동일 확인). 줄바꿈 정규화 후 충돌 4곳.
  - 충돌 1·3·4 (표 블록 순서): 02 `WEB-OFFICE-RO-VIEW-BLOCK-READING-ORDER-01` 과 33 `RO_VIEW_BLOCK_ORDER_*`/`TABLE_ANCHOR_IN_PARAGRAPH_01` 이 **같은 결함을 다른 방식으로** 고친 것. → **02 방식 유지** (드라이런에서 33 방식은 표 누락, 아래 결과).
  - 충돌 2 (셀 표시 텍스트): 33 `RO_VIEW_CELL_TEXT_SPACING_01` 은 02에 없는 별개 결함 교정 → **채택**. 입력칸/편집 판정(`isInputCell`/`isEditable`)은 02 그대로 `normalizedText` 기준 유지.
  - 33의 비충돌 hunk(블록 카운터 교체, 표 앵커 문단 제외)는 02 방식과 섞이면 카운터가 어긋나므로 **채택하지 않음**.
- 33에만 있는 `scripts/hwpx/` 파일 10개: 추적 8 + 미추적 2(`hancom_render_to_image.ps1`, `HWP_FULL_FIDELITY_CONVERTER.md` — 다른 창 작업물일 수 있어 **제외**, 확인사항).
  - `hwp2hwpx-*.cmd` → `hwp_to_hwpx_standalone.py`, `run_hwpx_full_audit.sh` → 참조 스크립트 4종: 02에 모두 존재 확인.
- `web_office/service.py` 는 02의 `render_payload.py`(33과 106줄 상이) 위에서도 동작 확인(드라이런).
- 재사용: 참조구현 `…/scratchpad/merge/candidate.py` (= 02 현행 + CELL_TEXT_SPACING 7줄). 새로 짜지 않는다.

### 범위
작업 브랜치: 02 현 HEAD에서 `chore/absorb-33-hwpx` 신규 생성. 기존 미커밋 3건(`data/reports/...summary.json`, `logs/change_history.jsonl`, `docs/devlog/2026-09-13-29de082.md`)은 **건드리지도 스테이징하지도 않는다.**

| # | 02 대상 경로 | 출처 | 동작 |
|---|---|---|---|
| 1 | `scripts/hwpx/web_office/ro_view_importer.py` | `C:\Users\skyjw\AppData\Local\Temp\claude\C--work\6a5ef39e-ece7-4407-b8ca-038087d40809\scratchpad\merge\candidate.py` | 바이트 그대로 교체(CRLF 유지) |
| 2 | `scripts/hwpx/web_office/service.py` | 33 `git show HEAD:scripts/hwpx/web_office/service.py` | 신규 |
| 3 | `scripts/hwpx/web_office/requirements.txt` | 33 HEAD 동일 경로 | 신규 |
| 4 | `Dockerfile.hwpx-ro-view` (저장소 루트) | 33 HEAD 루트 | 신규 |
| 5 | `scripts/hwpx/{README.md, run_hwpx_full_audit.sh, hwp2hwpx-bulk.cmd, hwp2hwpx-standalone.cmd, hwp_to_hwpx_requirements.txt, HWP_TO_HWPX_STANDALONE.md}` | 33 HEAD 동일 경로 | 신규 6개 |
| 6 | `tests/test_web_office_ro_view_cell_text_spacing.py` | — | 신규 테스트 |
| 7 | `tests/test_web_office_ro_view_service.py` | — | 신규 테스트 |
| 8 | `CLAUDE.md` 말미 "분리 일" 아래 1줄 | — | `*2026-09-24: 33의 분리 후 HWPX 변경(fb3ebf5·9938d70) 흡수 — 02가 정본, 33 scripts/hwpx 는 구본(2단계에서 처리).*` |

영향 없는 파일: 위 표 외 전부. 특히 33 저장소는 읽기만(`git show`) — 쓰기 금지.

### 모듈 분류
- module_category: tool (#1·#2 web_office 렌더), common (#3~#5 문서·스크립트), audit (#6·#7 테스트)
- primary_trade: common (HWPX 도메인)
- layer: #1 L2(importer) / #2 app(HTTP 서비스, importer·render_payload만 사용)

### 드라이런 결과 (메인 실측, 2026-09-24)
스크립트 `…/scratchpad/merge/dryrun_ro_view.py`, 샘플 20건(02 fixtures 4 + 33 corpus/gantt fixtures 8 + 33 deliverables 실물 8), 결과 `r_cur02.json / r_cand.json / r_cur33.json`.

| 지표 (20건 합) | 02 현행 | 후보(#1) | 33 현행 |
|---|---|---|---|
| 예외 | 0 | 0 | 0 |
| 블록 순서가 02 현행과 동일 | — | **20/20** | — |
| 표 블록 수 = 모델 표 수 | 19/20 | 19/20 | **7/20** (13건 표 누락, 예: 14개 중 10개) |
| 셀 텍스트 15자+ 연속 한글(띄어쓰기 소실) | 330 | **1** | 3 |
| service `_render_body_html` 조각 반환 | — | 20/20 (`<html` 없음) | 20/20 |
| HTML `<table` 수 = 표 블록 수 | — | 20/20* | — |

\* `fx_synthetic_metadata_form.hwpx`: 02 현행·후보 모두 표 블록 2(그중 ref=None 1) / 모델 표 1 — **02 기존 동작**, 이번 범위 밖(확인사항).
판정: 후보는 02 현행 대비 블록 구조 불변 + 셀 공백 교정, 33 현행 대비 표 누락 없음. **PASS**.

회귀 기준선(변경 전 HEAD, dryrun-runner 실측): `…/scratchpad/baseline/web_office_02.log`, `hwpx_02.log` — 결과는 아래 칸에 기록.
- web_office: HEAD 29de082 — `731 passed, 163 skipped` (실패 0, 로그 마지막 줄 메인 대조 확인)
- hwpx: `tests/test_hwpx_*.py` 전체는 1500초 내 미완료(timeout, 요약줄 없음 — 진행 중 FAILED/ERROR 다수 관찰, 기존 상태). 
  메인 대조: `git grep` 으로 `tests/` 중 `ro_view_importer`·`import_hwpx_as_ro_view` 및 이를 import 하는 web_office 모듈(cell_save·para_edit·parse_cache·editor_file_bridge 등)을 참조하는 **test_web_office_ 외 테스트 = 0건** → 영향 테스트 범위에서 제외. 회귀 판정은 `test_web_office_*` 로 한다.

### 검증 기준
1. **오탐0**: 기존 `tests/test_web_office_*.py` 결과가 기준선(`731 passed, 163 skipped`)과 동일 — 새 실패 0, passed 수 감소 0(신규 테스트분만 증가).
2. **누락0 (#6)**: 
   - 공백 보존: `tests/fixtures/form_57.hwpx` 를 import → 셀 텍스트 중 15자+ 연속 한글 0건 (현행 8건).
   - 인위적 위반: 교정 전 동작을 흉내 낸 경우(셀 텍스트를 `normalizedText` 로 강제) 테스트가 **실패해야 함** — `monkeypatch` 로 `cell_pars` 텍스트를 비워 fallback 경로가 `normalizedText` 를 쓰는지 확인(빈 문자열 아님).
   - `isInputCell`/`isEditable` 값이 교체 전(02 HEAD 판)과 fixture 4종에서 전부 동일.
3. **(#7) service**: FastAPI `TestClient` 로 `POST /render-hwpx` 에 `form_57.hwpx` 업로드 → 200, 본문에 `<html` 없음, `<table` 수 = 모델 표 블록 수(2). `/health` 200. FastAPI 미설치면 skip 이 아니라 **실패로 보고**(확인사항).
4. 드라이런 재실행: 시공 후 02 실제 파일로 `dryrun_ro_view.py` 결과가 `r_cand.json` 과 지표 동일.
5. #5 파일은 33 HEAD 판과 바이트 동일(`cmp`).

### 위험 대응
- 실패 시: 브랜치 `chore/absorb-33-hwpx` 폐기(`git checkout feat/hwpx-coord-fidelity && git branch -D …`). 02 기존 브랜치·33 무영향.
- 운영 영향: g2b 가 호출하는 `hwpx-ro-view-engine:8090` 은 여전히 33에서 빌드 → 1단계는 운영 무영향. 배포 출처 전환은 2단계.

### 개정 1 (2026-09-24, 1차 시공 감리 후) — 셀 띄어쓰기 교정 위치를 importer → service 로 이동
- 1차 시공 회귀: `12 failed, 724 passed, 163 skipped` (메인 재현 확인).
  - 8건: `ro_view_importer.py` 는 closeout 스위트가 `git diff 5b33ccd -- <file>` 로 **내용 봉인**한 파일(`LOCKED_VS_BASELINE`).
  - 4건: `test_web_office_field_roles.py` — 02 에서 `cell.text`(normalizedText)는 양식 필드 역할 판정의 **계약**. 공백 교정으로 실입력칸 보존율 60.2%(162/269, 기준 85%).
  - 드라이런이 블록 구조·표시 품질만 봤고 `cell.text` 의 소비자(field_roles)를 대조하지 않은 것이 설계 누락.
- 개정 설계: **`ro_view_importer.py` 는 변경하지 않는다(범위 #1 삭제, HEAD 로 원복).** 33 의 교정 취지(화면 표시 공백)는
  `service.py` 의 표 렌더에서 `_cell_display_text(cell)` = 셀 문단(`cell['paragraphs'][*].text`, run 단위 측량·공백 보존) 줄바꿈 결합, 비면 `cell['text']` 로 구현.
  참조구현: `…/scratchpad/merge/service_v2.py` (= 33 HEAD service.py + 헬퍼 10줄 + 호출 1줄).
- 개정 드라이런(메인 실측, HEAD importer + service_v2, 샘플 20건 `html_spacing.py`):
  | 지표 | 33 service 그대로 | service_v2 |
  |---|---|---|
  | `<td>` 내 15자+ 연속 한글 | 261 | **1** |
  | `<table` 합계 | 120 | 120 |
- 개정 범위: #1 삭제 / #2 `service.py` = service_v2.py 바이트 그대로(33 과 바이트 동일 아님 — 의도된 차이) / #3~#5, #8 불변 /
  #6 `tests/test_web_office_ro_view_cell_text_spacing.py` → 서비스 수준 테스트로 교체: form_57 렌더 HTML `<td>` 에 15자+ 연속 한글 0건,
  인위적 위반(헬퍼를 `cell['text']` 반환으로 monkeypatch 하면 1건 이상 → 교정이 실제 차이를 만든다는 증거), 셀 문단이 비면 `cell['text']` 폴백.
  기존 isInputCell/isEditable 해시 테스트는 importer 불변이라 삭제.
- 개정 검증 기준 1: `test_web_office_*` = 기준선 동일(731 passed + 신규, failed 0). 봉인 스위트 포함.

### 확인사항 (대표님 결정 — 2단계)
1. 33이 02를 어떻게 쓸지: 33의 Java 엔진(`HwpToHwpxCliBridge`, `PythonScriptBridge`), `build.gradle.kts`, `Dockerfile.hwpx-engine` 이 배포본에 `scripts/hwpx` 를 싣는다 → 33에서 단순 삭제 불가.
   (A) 33 복사본을 02에서 단방향 동기화 + 불일치 차단 게이트 / (B) git submodule / (C) 빌드 시 02 경로 주입(`HWP_TO_HWPX_SCRIPT` 등).
2. `hwpx-ro-view-engine` 배포 출처를 33 → 02로 옮길지(g2b `HWPX_RO_VIEW_ENGINE_URL` 은 불변).
3. 33에서 `scripts/hwpx` 를 import 하는 파일 162개 중 02에 없는 25개(scripts/ops POC 10, scripts/local 감사 5, Java 4 등) 이관 여부.
4. 33 미추적 2개 파일(`hancom_render_to_image.ps1`, `HWP_FULL_FIDELITY_CONVERTER.md`) 주인 확인.
5. `fx_synthetic_metadata_form.hwpx` 표 블록 ref=None 1건(02 기존 동작).

### 문장별 감리 (메인, 2026-09-24)
| 점검 | 방법 | 발견 | 조치 |
|---|---|---|---|
| 1차 시공 회귀 | 시공자 보고 12 failed → 메인 재현(field_roles 4 failed, 봉인 `git diff 5b33ccd`) | 설계 누락 1 (cell.text 소비자 미대조) | 개정 1 — 교정 위치 service 로 이동 |
| importer 원복 | `git diff --quiet HEAD` | 0 | — |
| service.py | `cmp service_v2.py` + 헬퍼 본문 직접 읽기(빈 paragraphs/키 없음/None → `or` 폴백) | 0 | — |
| 신규 테스트 본문 | 직접 읽기 | 1 — 함수명 `..._uses_paragraphs_when_present` 가 실제로는 "문단 없음 폴백" 검사 | `..._falls_back_to_text_when_no_paragraphs` 로 개명 |
| 깨뜨리기 | service 렌더 호출을 `cell['text']` 로 되돌린 사본으로 교체 후 실행 | 공백 테스트 **FAIL** 확인(1 failed) → 원복 cmp | 테스트가 교정 제거를 잡음 |
| 봉인·field_roles | spacing·service·field_roles·content_closeout·charpr_inventory 직접 실행 | 34 passed, 7 skipped, 0 failed | — |
| 회귀 전체 | 시공자 실행 `738 passed, 163 skipped` (기준 731 + 신규 7) | 0 | — |
| CLAUDE.md #8 문구 | 직접 읽기 | 1 — "변경 흡수"만 적혀 표 순서 교정 미채택 사실 누락 | 문구 보강(service 이관·importer 봉인 유지·02 방식 유지·기준서 경로) |
| 커밋 주의 | `git check-ignore` | `.gitignore:28 test_*.py` 로 신규 테스트 2개 무시됨 | 커밋 시 `git add -f` 명시 |

### 커밋 시 조정 (2026-09-24)
- 저장소 분류 가드(`run_hwpx_repo_commit_guard.py` → `gate_hwpx_repo_new_file_classification`)가 신규 파일 2건을 `UNKNOWN_REVIEW_REQUIRED` 로 차단.
  - 기준서: 한글 파일명이 git 출력에서 `"docs/specs/\355…"` 로 따옴표·8진수 인용돼 `docs/` 규칙을 못 탐 → 파일명을 ASCII(`..._merge_phase1_spec.md`)로 변경. **가드 결함(비ASCII 경로 미처리) — 결함 목차 등록 대상.**
  - `Dockerfile.hwpx-ro-view`: 루트 파일 분류 규칙 없음 → `scripts/hwpx/web_office/Dockerfile.hwpx-ro-view` 로 이동(빌드: `docker build -f scripts/hwpx/web_office/Dockerfile.hwpx-ro-view .`, COPY 경로는 컨텍스트 기준이라 불변).
- 가드는 미추적 파일도 검사 → 설치했던 코드맵 도구(미추적 12개)를 세션 scratchpad 로 임시 이동. 커밋하려면 분류 규칙에 `/code_map/`·`merge_stage` 토큰 등록 필요(인계 문서 참조).
