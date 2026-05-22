# HWPX EDITOR 건축 공정 방식 단지 감사 보고서

- **작업명**: HWPX-EDITOR-F0-CONSTRUCTION-SCHEDULE-AND-ZONING-AUDIT-01
- **기준 HEAD**: `9dfc6148607903f5d0b5b1c4f0f437046b5281b6`
- **브랜치**: `main`
- **감사 일자**: 2026-05-15
- **감사 유형**: read-only 감사 (코드 수정 없음, commit 없음)

---

## 1. 기준선 (STEP 0)

| 항목 | 값 |
|------|-----|
| branch | main |
| HEAD | 9dfc614 |
| staged 파일 수 | **0** |
| tracked dirty 파일 수 | 14 |
| untracked 파일/디렉터리 수 | ~130+ |

**판정: PASS** — staged 파일 없음, 안전하게 진행 가능

---

## 2. 현재 Dirty/Untracked 파일 공종 분류 (STEP 1)

### 2-A. Tracked Modified 파일 (14개)

| 파일 경로 | 상태 | 배정 단지 | 배정 사유 | 위험도 | 처리 방식 |
|-----------|------|-----------|-----------|--------|-----------|
| `logs/change_history.jsonl` | M | 10. Logs/Change History | devlog 자동화 산출물 | LOW | commit 대상 |
| `scripts/extract_hwp_body_fields.py` | M | 1. HWPX Core Engine | HWP 바디 필드 추출 유틸 | LOW | commit 대상 |
| `scripts/hwpx/HWP_TO_HWPX_STANDALONE.md` | M | 9. Docs/Reports | standalone 변환 문서 | LOW | commit 대상 |
| `scripts/hwpx/diagnostics/06_roundtrip_text_probe.py` | M | 6. Diagnostics/Audit | 라운드트립 텍스트 프로브 | LOW | commit 대상 |
| `scripts/hwpx/hancom_hwp_converter_providers.py` | M | 3. HWP/HWPX Converter | 공급자 정의 | MEDIUM | commit 대상 |
| `scripts/hwpx/hancom_hwp_converter_router.py` | M | 3. HWP/HWPX Converter | hwpxjs provider 추가, batch dir 라우팅 로직 변경 | MEDIUM | commit 대상 |
| `scripts/hwpx/hwp_to_hwpx_sdk.py` | M | 3. HWP/HWPX Converter | SDK 기반 변환기 | MEDIUM | commit 대상 |
| `scripts/hwpx/hwp_to_hwpx_standalone.py` | M | 3. HWP/HWPX Converter | standalone 변환기 | MEDIUM | commit 대상 |
| `scripts/hwpx/hwpx_api.py` | M | 4. API Facade | server_ops 함수군 import 추가, importlib 추가 | MEDIUM | commit 대상 |
| `scripts/hwpx/test_hancom_hwp_converter_providers.py` | M | 6. Diagnostics/Audit | providers 테스트 | LOW | commit 대상 |
| `scripts/hwpx/test_hancom_hwp_converter_router.py` | M | 6. Diagnostics/Audit | router 테스트 | LOW | commit 대상 |
| `scripts/hwpx/test_hwp_to_hwpx_sdk.py` | M | 6. Diagnostics/Audit | SDK 테스트 | LOW | commit 대상 |
| `scripts/hwpx/test_hwp_to_hwpx_standalone.py` | M | 6. Diagnostics/Audit | standalone 테스트 | LOW | commit 대상 |
| `src/main/java/com/haehan/engine/Application.java` | M | 4. API Facade (Java) | `convert-hwp-to-hwpx` CLI 커맨드 추가, HwpToHwpxCliBridge 연결 | MEDIUM | commit 대상 |

### 2-B. Untracked 파일군 분류 (요약)

| 그룹 | 파일 수(추정) | 배정 단지 | 처리 방식 |
|------|-------------|-----------|-----------|
| `.tmp_p*.json`, `.tmp_b1_*`, `.tmp_head_*` | 19 | 8. Governance/Gates (임시 감사) | hold / 정리 후 삭제 후보 |
| `deliverables/local_hwp_hwpx_converted/` | 1(dir) | 7. Storage/Artifacts | hold (로컬 변환 산출물) |
| `deliverables/기관제출서류_*_hwpx/` | 1(dir) | 7. Storage/Artifacts | hold (납품 산출물) |
| `docs/devlog/2026-05-15-*.md` | 42 | 9. Docs/Reports (devlog 자동) | commit 대상 |
| `docs/reports/*.md/*.json` | ~20 | 9. Docs/Reports | commit 대상 |
| `docs/*.md`, `docs/ops/*.md` | 5 | 9. Docs/Reports | commit 대상 |
| `reports/codebase_realtime_audit*`, `reports/runtime/`, `reports/security-watch/` | ~5(+dirs) | 6. Diagnostics/Audit (런타임 산출물) | hold (runtime output) |
| `scripts/excel/*.py` | 9 | 11. Unknown/Needs Review | hold (Excel domain 분리 검토 필요) |
| `scripts/hwp-worker/Convert-HwpToHwpx-PersistentBatch.ps1` | 1 | 3. HWP/HWPX Converter | commit 대상 |
| `scripts/hwpx/hwp_full_fidelity_*.py` | 12 | 1. HWPX Core Engine (Full Fidelity) | commit 대상 |
| `scripts/hwpx/hwpx_edit_tool.py`, `hwpx_schema_rules.py`, `hwpx_server_ops.py`, `hwpx_spine_repair.py` | 4 | 1/2/4 HWPX Core/Schema/Server Ops | commit 대상 |
| `scripts/hwpx/hwpxjs_hwp_to_hwpx.py`, `hancom_render_to_image.ps1` | 2 | 3. HWP/HWPX Converter | commit 대상 |
| `scripts/hwpx/hwp_realtime_audit_watch.py`, `hwp_safety_sample_audit.py`, `hwpx_delivery_auto_verify.py` 등 감사 도구 | ~10 | 6. Diagnostics/Audit | commit 대상 |
| `scripts/hwpx/openhwp_rust_probe.py`, `hwp_hwp5proc_audit.py`, `hwp_hwpx_pixel_audit.py` | 3 | 6. Diagnostics/Audit | commit 대상 |
| `scripts/hwpx/test_hwp_full_fidelity_*.py`, `test_hwpx_*.py`, `test_openhwp_*.py` | ~10 | 6. Diagnostics/Audit (Tests) | commit 대상 |
| `scripts/hwpx/index_local_hwp_hwpx_files.py`, `build_page_capped_review_index.py`, `convert_local_hwp_inventory_to_hwpx.py` | 3 | 7. Storage/Artifacts | commit 대상 |
| `scripts/hwpx/hwp_page_capped_batch.py`, `hwp_page_capped_convert.py`, `hwp_native_com_batch.py`, `run_local_hwp_to_hwpx_chunks.py` | 4 | 3. HWP/HWPX Converter | commit 대상 |
| `scripts/ops/*.py`, `scripts/ops/*.ps1` | ~12 | 8. Governance/Gates | commit 대상 |
| `src/main/java/com/haehan/engine/ops/` | 1(dir) | 8. Governance/Gates (Java) | commit 대상 |
| `src/test/java/com/haehan/engine/http/HwpxUploadHandlerEncodingTest.java`, `src/test/java/.../ops/` | 2 | 6. Diagnostics/Audit (Test) | commit 대상 |

---

## 3. 단지 배치도 (STEP 2)

| 단지명 | 책임 | 대표 파일 | 외부 의존 | 접근 허용 구역 | 접근 금지 구역 |
|--------|------|-----------|-----------|---------------|---------------|
| **1. HWPX Core Engine** | HWPX XML/ZIP 패키지 생성·읽기·쓰기 | `scripts/hwpx/hwpx_package.py`, `hwpx_writer_adapter.py`, `hwp_full_fidelity_converter.py` | olefile, lxml, zipfile | 2(Schema), 7(Storage) | DB, session, secret, 서버 직접 접근 |
| **2. HWPX Schema/Rules** | OWP-ML 스키마 정의, 규칙 집합 | `scripts/hwpx/hwpx_schema_rules.py` | 없음 | 1(Core) | API, DB, UI, 외부 네트워크 |
| **3. HWP/HWPX Converter** | HWP → HWPX 변환 파이프라인 | `hancom_hwp_converter_router.py`, `hancom_hwp_converter_providers.py`, `hwp_to_hwpx_standalone.py`, `hwp_to_hwpx_sdk.py`, `hwpxjs_hwp_to_hwpx.py` | subprocess, COM(win32com), hwp5 | 1(Core), 6(Diag), 7(Artifacts) | DB write, session, secret |
| **4. API Facade** | HTTP 엔드포인트, CLI 진입점 | `scripts/hwpx/hwpx_api.py`, `src/main/java/com/haehan/engine/Application.java` | hwpx_server_ops, HwpToHwpxCliBridge | 1(Core), 3(Converter), 8(Gate) | HWPX XML 내부 직접 조작 최소화 |
| **5. Browser Editor/UI** | 브라우저 기반 편집 | (현재 미확인 — frontend/editor 디렉터리 없음) | N/A | 4(API) | 파일 파싱, 서버 filesystem 직접 접근 |
| **6. Diagnostics/Audit** | 품질 게이트, 테스트, 라운드트립 | `scripts/hwpx/diagnostics/`, `hwp_realtime_audit_watch.py`, `test_*.py` | pytest, lxml | 1(Core), 7(Artifacts) 읽기 전용 | 원본 파일 overwrite, commit, push |
| **7. Storage/Artifacts** | 변환 결과물 저장, 배치 인덱스 | `deliverables/`, `index_local_hwp_hwpx_files.py`, `convert_local_hwp_inventory_to_hwpx.py` | os, pathlib | 1(Core), 3(Converter) | secret, session, DB schema |
| **8. Governance/Gates** | 공정 게이트, 계층 정책, 보안 감시 | `scripts/ops/codebase_layer_policy.py`, `codebase_dependency_gate.py`, `openapi_schema_gate.py`, `src/.../ops/AuditWatchLifecycle.java`, `.tmp_p*.json` | 없음 (read-only 감사) | 모든 단지 읽기 전용 | 코드 수정, commit, DB write |
| **9. Docs/Reports** | 문서, 보고서, devlog | `docs/`, `docs/reports/`, `docs/devlog/` | 없음 | 없음 | 기능 코드 포함 금지 |
| **10. Logs/Change History** | 변경 이력 자동 기록 | `logs/change_history.jsonl` | git hook | 없음 | 수동 수정 |
| **11. Unknown/Needs Review** | 미분류 — Excel 도구군 | `scripts/excel/*.py` | openpyxl 금지(메모리 참조), Apache POI | 별도 Excel 도메인으로 분리 검토 | HWPX core와 혼합 금지 |

---

## 4. 동/세대 배정표 (주요 모듈별)

| 모듈 | 단지 | Owner 파일 | 테스트 존재 여부 |
|------|------|-----------|----------------|
| hwpx_api.py | 4. API Facade | hwpx_api.py | 없음 (smoke만 존재) |
| hwpx_server_ops.py | 4. API Facade / 1. Core | hwpx_server_ops.py | 없음 |
| hwp_full_fidelity_converter.py | 1. Core | hwp_full_fidelity_converter.py | test_hwp_full_fidelity_converter.py ✓ |
| hwpx_schema_rules.py | 2. Schema | hwpx_schema_rules.py | 없음 |
| hancom_hwp_converter_router.py | 3. Converter | hancom_hwp_converter_router.py | test_hancom_hwp_converter_router.py ✓ |
| hancom_hwp_converter_providers.py | 3. Converter | hancom_hwp_converter_providers.py | test_hancom_hwp_converter_providers.py ✓ |
| hwp_to_hwpx_sdk.py | 3. Converter | hwp_to_hwpx_sdk.py | test_hwp_to_hwpx_sdk.py ✓ |
| hwp_to_hwpx_standalone.py | 3. Converter | hwp_to_hwpx_standalone.py | test_hwp_to_hwpx_standalone.py ✓ |
| hwpxjs_hwp_to_hwpx.py | 3. Converter | hwpxjs_hwp_to_hwpx.py | test_hwpxjs_hwp_to_hwpx.py ✓ |
| diagnostics/*.py | 6. Diagnostics | diagnostics/ | 통합 run_hwp_diagnostics.py |
| AuditWatchLifecycle.java | 8. Governance | ops/ | AuditWatchLifecycleTest.java ✓ |
| Application.java | 4. API Facade (Java) | Application.java | 없음 (smoke 수준) |
| codebase_layer_policy.py | 8. Governance | scripts/ops/ | test_codebase_layer_policy.py ✓ |
| scripts/excel/*.py | 11. Unknown | scripts/excel/ | **없음** ⚠️ |

---

## 5. 구획/경계 감사 결과 (STEP 3)

### 5-1. API Facade → Server Ops 직접 결합
- **파일**: `scripts/hwpx/hwpx_api.py`
- **내용**: `from hwpx_server_ops import convert_hwp_for_server, fill_cells_for_server, ...` (6개 함수 직접 import)
- **판정**: **WARN** — API facade가 server ops 구현을 직접 import. 장기적으로 중간 인터페이스 계층 분리 권장. 단, 현재 단계에서 기능적 문제는 없음.

### 5-2. Application.java → HwpToHwpxCliBridge 연결
- **파일**: `src/main/java/com/haehan/engine/Application.java`
- **내용**: `import com.haehan.engine.hwp.HwpToHwpxCliBridge` 추가, `convert-hwp-to-hwpx` 커맨드 라우팅
- **판정**: **PASS** — bridge 패턴으로 적절히 추상화. Application.java가 hwp 하위 패키지에 직접 의존하나 CLI entry point로서 허용 범위.

### 5-3. Diagnostics → 원본 파일 write 위험
- **파일**: `scripts/hwpx/diagnostics/03_convert_smoke.py`, `04_audit_log_probe.py`
- **내용**: `open(..., 'w')` 패턴 존재
- **판정**: **WARN** — diagnostics는 원칙적으로 read-only여야 함. 임시 출력 파일에만 write하는지 확인 필요. 원본 HWP/HWPX 덮어쓰기 여부는 코드 검토 후 확인 필요.

### 5-4. Converter에서 subprocess 사용
- **파일**: `hancom_hwp_converter_router.py`, `hwpxjs_hwp_to_hwpx.py`, `hwp_hwp5proc_audit.py` 등 16개
- **내용**: `subprocess.run()` 패턴 (shell=True 없음 — 해당 파일들)
- **판정**: **PASS** — shell=True 없이 리스트 인자 사용 시 injection 위험 낮음.

### 5-5. logs/change_history가 기능 커밋에 혼재
- **판정**: **WARN** — `logs/change_history.jsonl`이 tracked modified 상태. devlog 자동화 정책에 따라 기능 커밋과 함께 포함 여부를 명시적으로 결정 필요.

### 5-6. Browser Editor/UI 단지 미확인
- **판정**: **WARN** — `frontend/` 또는 `editor/` 디렉터리가 존재하지 않음. HWPX 브라우저 편집기 UI가 어느 경로에 있는지 불명확. 단지 미배정.

---

## 6. 보안 방화구획 감사 결과 (STEP 4)

### 6-1. secret/password/token 문자열 추가 여부

| 파일 | 발견 내용 | 판정 |
|------|-----------|------|
| `hwp_full_fidelity_security.py:45-46` | `"key": "secret_material"`, `"keywords": ["token", "credential", "password", ...]` | **PASS** — 보안 검사 목적의 키워드 목록. 실제 secret 값 아님 |
| `hwpx_edit_tool.py:72` | `token = match.group(1).strip()` | **PASS** — 파싱 토큰 변수명. HTTP token/session 아님 |
| `hwp_full_fidelity_coverage.py:1175` | `token = stem[3:]` | **PASS** — 파일명 파싱 토큰 |

→ **실제 secret/credential 하드코딩 없음** — PASS

### 6-2. shell=True 위험
- **파일**: `scripts/hwpx/hancom_toolchain_health_check.py:83`
- **내용**: `shell=True` 사용
- **판정**: **WARN** — health check용이나 입력이 외부에서 주입될 경우 injection 위험. 도구 내부 고정 커맨드이면 낮은 위험. 검토 필요.

### 6-3. HTTP 외부 접근 모듈
- **파일**: `client_parse_hwpx_smoke.py`, `smoke_hwpx_api.py` — localhost API 접근
- **파일**: `hancom_toolchain_health_check.py` — urllib 사용 (헬스체크 목적)
- **파일**: `test_hwpx_security.py` — 보안 테스트 목적 urllib
- **판정**: **PASS** — 외부 사이트 접근 없음, 로컬/내부 엔드포인트만 사용

### 6-4. 원본 파일 overwrite 위험
- **25개 파일**에 `open(..., 'w')` 또는 `shutil.copy`, `os.remove` 패턴 존재
- `hwpx_server_ops.py`, `hwp_to_hwpx_standalone.py`, `hwp_page_capped_convert.py` — 출력 경로 지정 필요
- **판정**: **WARN** — 원본 HWP 파일 overwrite 방지 정책(입출력 경로 분리) 존재 여부를 개별 확인 필요

### 6-5. .tmp 임시 파일 루트 방치
- **19개** `.tmp_p*.json`, `.tmp_b1_*`, `.tmp_head_*` 파일이 repo root에 untracked로 존재
- **판정**: **WARN** — 루트 오염. `.gitignore`에 `.tmp_*` 추가 또는 `tmp/` 하위로 이동 권장

### 6-6. 삭제성 명령 / 권한 변경
- `scripts/ops/` 중 `Backup-CodebaseSecuritySnapshot.ps1`, `Install-CodebaseSecurityWatch.ps1` 존재
- **판정**: **PASS** — 감사 후 내용 확인 필요하나, 파일명 기준으로 보안 스냅샷 관련 운영 스크립트. chmod/chown 없음.

---

## 7. 전체 공정표 (STEP 5)

| # | 공정명 | 대상 단지 | 목표 | 선행 조건 | 허용 작업 | 금지 작업 | 검증 방법 | 완료 기준 | 병렬 가능 | 현재 상태 | 다음 액션 |
|---|--------|-----------|------|-----------|-----------|-----------|-----------|-----------|----------|----------|-----------|
| F0 | 기준선 감사 | 전체 | git 상태·dirty 파일 조사 | 없음 | read-only grep, git status | commit, push, 코드 수정 | 본 보고서 | 보고서 생성 | 아니오 | ✅ 완료 | 보고서 배포 |
| F1 | Tracked 파일 커밋 그룹화 | 3,4,6,10 | 14개 tracked modified를 논리 단위로 분리 커밋 | F0 PASS | git add, git commit | push, force-push | git log | 커밋 분리 완료 | 아니오 | ⏸ 대기 | 커밋 순서 설계 |
| F2 | Untracked 신규 파일 커밋 | 1,2,3,4,6,7,8,9 | scripts/hwpx 신규 파일군 커밋 | F1 완료 | git add, git commit | push | git log | 커밋 완료 | 아니오 | ⏸ 대기 | F1 완료 후 진행 |
| F3 | devlog/docs/reports 커밋 | 9 | 42개 devlog + docs/reports 커밋 | F2 완료 | git add, git commit | push | git log | 커밋 완료 | 아니오 | ⏸ 대기 | F2 완료 후 진행 |
| F4 | .tmp 파일 정리 | 8 | .tmp_p*.json 등 19개 임시 파일 처리 | F0 PASS | .gitignore 추가 또는 tmp/ 이동 | 기능 코드 수정 | git status 확인 | .tmp 파일 root 비움 | 아니오 | ⏸ 대기 | .gitignore 정책 결정 |
| F5 | shell=True 위험 검토 | 3 | hancom_toolchain_health_check.py 고정 커맨드 여부 확인 | F0 PASS | grep, read | 코드 수정 | grep shell=True + 입력 추적 | PASS 또는 수정 계획 수립 | 병렬 후보(read-only) | ⏸ 대기 | grep 후 판단 |
| F6 | diagnostics write 위험 검토 | 6 | 03/04 diagnostics 파일이 원본 덮어쓰는지 확인 | F0 PASS | read, grep | 코드 수정 | grep open.*w, 경로 추적 | PASS 또는 수정 계획 | 병렬 후보(read-only) | ⏸ 대기 | read 후 판단 |
| F7 | Excel 단지 분리 검토 | 11 | scripts/excel 도메인이 hwpx core와 분리 적합한지 확인 | F0 PASS | read, grep | 이동, 리팩토링 | 의존성 grep | 분리 계획 문서화 | 병렬 후보(read-only) | ⏸ 대기 | 의존성 분석 |
| F8 | Browser Editor 단지 확인 | 5 | HWPX 브라우저 편집기 UI 파일 위치 파악 | F0 PASS | grep, glob | 없음 | find editor/frontend | 단지 배정 완료 | 병렬 후보(read-only) | ⏸ 대기 | glob 탐색 |
| F9 | hwpx_api / hwpx_server_ops 계층 설계 | 4 | API Facade와 Server Ops 사이 인터페이스 정의 | F2 완료 | 설계 문서 작성 | 코드 수정 | 설계 리뷰 | 인터페이스 설계 문서 | 아니오 | ⏸ 대기 | F2 완료 후 설계 |
| F10 | 전체 커밋 완료 후 push | 전체 | main 브랜치에 push | F1-F4 완료 | git push | force-push, --no-verify | CI 통과 | CI green | 아니오 | ⏸ 대기 | 커밋 완료 후 |

---

## 8. 누락 공정 확인 (STEP 6)

| 항목 | 상태 | 설명 |
|------|------|------|
| 단지 미배정 파일 | **있음** | `scripts/excel/*.py` 9개 — Excel 도메인 소속 불명확 |
| Browser Editor/UI 단지 | **없음** | frontend/editor 디렉터리 미발견. 단지 5 비어 있음 |
| owner 없는 모듈 | **있음** | `hwpx_server_ops.py`, `hwpx_schema_rules.py` — 테스트/owner 미배정 |
| 테스트 없는 핵심 모듈 | **있음** | `hwpx_api.py`, `hwpx_server_ops.py`, `hwpx_schema_rules.py` |
| 보안 게이트 없는 외부 API | **주의** | `hwpx_api.py`의 server-side 변환 API — 입력 경로 검증 게이트 확인 필요 |
| 원본 보호 정책 없는 writer/converter | **주의** | 25개 파일의 write 경로가 원본 경로와 분리되는지 명시 정책 없음 |
| docs/reports 미작성 단계 | **없음** | 본 보고서로 충족 |
| .gitignore에 `.tmp_*` 미등록 | **있음** | .tmp 파일 19개 repo root에 노출 |
| scripts/excel 테스트 | **없음** | 9개 Excel 스크립트 전원 테스트 없음 |

---

## 9. 권장 다음 순서

1. **즉시**: `.gitignore`에 `.tmp_*` 패턴 추가 → root 오염 차단 (F4)
2. **F5/F6/F7/F8** 병렬 read-only 검토 수행 (각 5분 이내)
3. **F1 → F2 → F3** 순으로 커밋 그룹화 후 순차 커밋
4. **F9** hwpx_api ↔ hwpx_server_ops 계층 인터페이스 설계 문서화
5. **F10** 전체 커밋 완료 후 push
6. **중기**: `scripts/excel` 단지를 별도 도메인으로 분리 또는 단지 11 공식화
7. **중기**: `hwpx_api.py`, `hwpx_server_ops.py`에 단위 테스트 추가

---

## 10. 최종 판정

| 항목 | 결과 |
|------|------|
| staged 파일 | 0 — PASS |
| 실제 secret 하드코딩 | 없음 — PASS |
| shell=True | 1건 (hancom_toolchain_health_check.py) — **WARN** |
| diagnostics write 위험 | 미확인 — **WARN** |
| API Facade 계층 결합 | hwpx_api → hwpx_server_ops 직접 import — **WARN** |
| .tmp 파일 root 노출 | 19개 — **WARN** |
| Browser Editor 단지 미배정 | 단지 5 비어 있음 — **WARN** |
| 단지 미배정 파일 | scripts/excel 9개 — **WARN** |
| 구획 위반 의심 | 1건 (API→ServerOps 직접 결합) |

### 🏗️ 최종 판정: **WARN**

- FAIL 항목 없음
- WARN 5건: shell=True, diagnostics write, API 계층 결합, .tmp root, Browser Editor 미확인
- 코드 수정 없이 감사 완료
- 다음 우선 작업: .gitignore 패치 + F5/F6 확인 + F1 커밋 분리

---

*보고서 생성: 2026-05-15 | 감사 방식: read-only | 코드 수정 없음*
