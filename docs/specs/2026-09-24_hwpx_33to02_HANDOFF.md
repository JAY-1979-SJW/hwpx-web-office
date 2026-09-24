# 인계: HWPX 02↔33 통합 + 골격 점검 (2026-09-24 세션 종료 시점)

**재개 위치: `C:\work\02. hwpx-web-office`** (HWPX 정본 저장소). 새 창에서 이 폴더로 열고 이 문서를 먼저 읽는다.
재개 명령 예: "docs/specs/2026-09-24_hwpx_33to02_HANDOFF.md 읽고 골격 점검 이어서"

## 1. 현재 상태
| 항목 | 상태 |
|---|---|
| 브랜치 | 02 `chore/absorb-33-hwpx` (push 안 함) |
| 커밋 1 | 33 분리 후 HWPX 변경 흡수 — RO-VIEW 렌더 서비스(`scripts/hwpx/web_office/service.py`)·셀 공백 교정(표시층) — 기준서 `2026-09-24_hwpx_33to02_merge_phase1_spec.md` |
| 커밋 2 | HWPX 범위 밖 레거시 스크립트 94개 삭제(`scripts/` 최상위, 33에 바이트 동일 원본 존재·코드 참조 0) |
| 검증 | `test_web_office_*` 738 passed / 163 skipped / failed 0, 테스트 수집 3244 오류 0, 코드맵 import 실패 신규 0 |
| 33 저장소 | **변경 없음**(코드맵 도구만 미추적 설치: `scripts/ops/code_map/`, `scripts/ops/verify_change.py`, `scripts/ops/merge_stage.py`, `configs/verify_change.json`, 출력 `data/code_map/`) |
| 02 코드맵 도구 | 커밋 가드(미추적 파일도 검사)에 걸려 세션 scratchpad 로 임시 이동. 재설치: `python ~/.claude/skills/verify-change/install.py "C:/work/02. hwpx-web-office" --apply` — 커밋하려면 `scripts/ops/classify_hwpx_repo_inventory.py` 의 scripts/ops 토큰에 `/code_map/`·`merge_stage` 등록 필요 |
| 기존 미커밋(손대지 않음) | `data/reports/hwpx_form_auto_fill_construction_work_design/construction_work_design_summary.json`, `logs/change_history.jsonl`, `docs/devlog/2026-09-13-29de082.md` |

## 2. 절차 위치 (program-skeleton-audit 스킬)
- [x] 코드맵(02·33) — build / determinism SAME / runcheck R0·R1 전수 재검(오탐 판정 포함)
- [x] 1단계 실측 A~F (Sonnet 6 병렬) + 메인 재조회 감리
- [ ] **2단계 기준값 스냅샷** ← 다음 할 일 (샘플 20건 × 02·33 렌더 결과: 드라이런 스크립트 재사용 가능 — 아래 5)
- [ ] 3단계 결함 목차 `docs/defect_index.json` (아래 3의 후보를 번호 부여해 등록)
- [ ] 4단계 설계서(대표 승인) — 02↔33 통합 목표 구조·단계 순서
- [ ] 5단계 단계별 시공 / 6단계 기계 강제

## 3. 결함 목차 후보 (실측, 미등록)
| # | 분류 | 내용 | 근거 |
|---|---|---|---|
| 1 | 구조 | 5/22 HWPX 분리 불완전 — 02가 33에만 있는 파일 import | `scripts/ops/batch_hwpx_100_ai_demo.py`, `batch_hwpx_e2e_demo.py` → `tests/fixtures/ai_proposal_client_fixture.py`; `claude_inline_full_integration_demo.py` → `scripts/ops/verify_e2e_input_precision.py` |
| 2 | 구조 | 5/22 Excel 분리 불완전 — 33 감사 15개·`local/desk_connector.py`·`scripts/excel/convert/convert_cli.py` 가 06으로 옮겨진 모듈 import, 06에 사본 없음 → **삭제 금지, 06 이관 대상** | 33 코드맵 import_failed 24건 |
| 3 | import | `hwpx` 이름 충돌 — 33 `scripts/hwpx/__init__.py` 없음 → pip `hwpx`(site-packages) 로 해석, `hwpx.parser` 실패 15건. 02도 sys.path 순서 의존 | `python -c "import hwpx"` 저장소별 결과 |
| 4 | import | `scripts/hwpx/hwp_full_fidelity_{analyzer,audit,coverage}.py` → `scripts/extract_hwp_body_fields.py` 경로 누락, 직접 실행해도 ModuleNotFoundError (02·33) | R0 FAIL 3 |
| 5 | 강제장치 | 커밋 가드가 비ASCII 경로(git quotepath 인용)를 분류 못함 → 한글 파일명 신규 파일 전부 UNKNOWN 차단 | 이번 커밋 |
| 6 | 강제장치 | 두 저장소 CI 없음, 33 `pre-commit.orig` 없음(저장소 고유 게이트 0), 02 `.git/hooks/pre-commit` 죽은 파일(없는 스크립트 참조) | 축 E |
| 7 | 운영 | g2b 가 호출하는 `hwpx-ro-view-engine:8090` 컨테이너 정의가 어느 저장소 compose 에도 없음 — 서버(haehan-app) 수동 기동 추정, 운영 코드=HEAD 확인 불가 | 축 B/E + 메인 grep |
| 8 | 식별자 | cellId f-string 2곳(`parser/table_parser.py`, `pipeline/generic_edit_plan_writer_executor_live_sandbox.py`), `make_request_id` 2곳, 33 Java `HwpxParser` 별도 tableId 형식 | 축 A |
| 9 | 스키마 | 스키마 버전 장치 0(양쪽), SCHEMA_VERSION 상수 30곳+ 산개 | 축 C |
| 10 | 조용한실패 | 02 except→pass 71·빈값 반환 111·bare except 24 / 33 Java 빈 catch 51(`OpenAiLlmApiClient.java:72` 등) | 축 F |
| 11 | 경로 | 개인 OneDrive 절대경로 하드코딩 02:41·33:32, 33 localhost 포트 20+ | 축 B |
| 12 | 도구 | 코드맵 스킬 패키지에 `scripts/ops/codebase_layer_audit.py`·`scripts/op_log` 누락 → `modules.py`(순환 검사)·`skeleton_gate.py` 실행 불가 | 코드맵 R0 |
| 13 | 테스트 | `tests/test_hwpx_*.py` 전체 25분 내 미완료, 진행 중 FAILED ~200·ERROR 31 관찰 — 미분석 | 기준선 에이전트 |

## 4. 2단계(통합) 대표 결정 대기
1. 33이 02를 쓰는 방식: 33 Java(`HwpToHwpxCliBridge`, `PythonScriptBridge`)·`build.gradle.kts`·`Dockerfile.hwpx-engine` 이 `scripts/hwpx` 를 배포본에 포함 → 단순 삭제 불가. (A) 02→33 단방향 동기화+불일치 게이트 / (B) submodule / (C) 빌드 시 02 경로 주입
2. `hwpx-ro-view-engine` 배포 출처 33→02 전환 (g2b `HWPX_RO_VIEW_ENGINE_URL` 불변). 02 빌드: `docker build -f scripts/hwpx/web_office/Dockerfile.hwpx-ro-view .`
3. 33→02 이관 25개(02에 없는 HWPX 의존 파일 — 결함 #1 포함)
4. 33 미추적 2개(`scripts/hwpx/hancom_render_to_image.ps1`, `HWP_FULL_FIDELITY_CONVERTER.md`) 주인 확인

## 5. 재사용 자료 (세션 scratchpad — 창 종료 후 사라질 수 있음, 필요 시 재생성)
- 드라이런: `dryrun_ro_view.py <label> <repo> <importer> [--service <service.py>]`, 샘플 목록 `samples.json`(02 fixtures 4 + 33 fixtures 8 + 33 deliverables 8)
- 삭제 판정: `del_cand2.py` (조건: 분리 보고서 LEGACY_EXPERIMENT ∧ 33 바이트 동일 ∧ 코드 참조 0 ∧ HWPX 이름 아님)
- 판정 근거: `data/reports/hwpx_repo_inventory_classification/repo_inventory_files.json` (5월 분리 때 파일별 분류)

## 6. 작업 방식 (대표 지시)
- 스킬 기반 분업: 메인=판단·기준서·감리, Sonnet=시공·조사, Haiku=실행(pytest·코드맵). 읽기 조사는 병렬, 같은 파일 시공은 직렬.
- 서브에이전트의 부정 결론("없다")은 메인이 원문 재조회 후 채택.
- 커밋: 명시 pathspec, 신규 테스트는 `.gitignore:28 test_*.py` 때문에 `git add -f`. 커밋 가드는 미추적 파일도 검사함.
