# HWPX Editor F0 Cleanup-1E Scripts/HWPX Subgroup Triage

**작업명:** HWPX-EDITOR-F0-CLEANUP-1E-SCRIPTS-HWPX-SUBGROUP-TRIAGE
**날짜:** 2026-05-15
**기준선 HEAD:** 6a9d2e1
**최종 판정:** PASS

---

## 남은 Dirty 목록 (triage 시점)

| 파일 | 라인 변화 |
|------|-----------|
| `scripts/hwpx/HWP_TO_HWPX_STANDALONE.md` | +30 |
| `scripts/hwpx/diagnostics/06_roundtrip_text_probe.py` | +18/-8 |
| `scripts/hwpx/hancom_hwp_converter_providers.py` | +95 |
| `scripts/hwpx/hancom_hwp_converter_router.py` | +104/-8 |
| `scripts/hwpx/hwp_to_hwpx_sdk.py` | +5 |
| `scripts/hwpx/hwp_to_hwpx_standalone.py` | +612/-87 |
| `scripts/hwpx/hwpx_api.py` | +127/-4 |
| `scripts/hwpx/hwpx_capability_coverage.py` | +2/-2 |
| `scripts/hwpx/hwpx_compose_schema_reference.py` | +2/-2 |
| `scripts/hwpx/hwpx_element_factory.py` | +23/-7 |
| `scripts/hwpx/hwpx_image_policy.py` | +1/-3 |
| `scripts/hwpx/hwpx_job_schema.py` | +7/-4 |
| `scripts/hwpx/hwpx_list_style_ops.py` | +1/-22 |
| `scripts/hwpx/hwpx_package.py` | +236 |
| `scripts/hwpx/hwpx_style_ops.py` | -118 (전체 이전, hwpx_schema_rules.py로) |
| `scripts/hwpx/hwpx_table_cell_address_style.py` | +1/-23 |
| `scripts/hwpx/test_hancom_hwp_converter_providers.py` | +45 |
| `scripts/hwpx/test_hancom_hwp_converter_router.py` | +105/-8 |
| `scripts/hwpx/test_hwp_to_hwpx_sdk.py` | +5 |
| `scripts/hwpx/test_hwp_to_hwpx_standalone.py` | +263/-54 |
| `scripts/extract_hwp_body_fields.py` | +91/-6 |
| `src/main/java/com/haehan/engine/Application.java` | B-2 hunk |
| `logs/change_history.jsonl` | +3 |

---

## 파일별 세부 분류

| 파일 | 변경 목적 | 목표 집 | web editor core | P14C ApplyEngine | Hancom 의존 | local-gui 의존 | raw path 위험 | 원본 덮어쓰기 위험 | 독립 커밋 |
|------|-----------|---------|-----------------|------------------|-------------|----------------|---------------|---------------------|-----------|
| `hwpx_package.py` | normalize_entry_name + HwpxValidator.validate_entries (in-memory validation) | hwpx-apply-engine | NO | YES | NO | NO | NO | NO | YES |
| `hwpx_element_factory.py` | create_picture_object position 파라미터 추가 (z_order, text_wrap, offset 등) | hwpx-apply-engine | NO | YES | NO | NO | NO | NO | YES |
| `hwpx_image_policy.py` | hwpx_schema_rules로 상수 이전 (thin wrapper) | hwpx-apply-engine | NO | YES | NO | NO | NO | NO | YES |
| `hwpx_job_schema.py` | hwpx_schema_rules 의존 통일 (import 정리) | hwpx-apply-engine | NO | YES | NO | NO | NO | NO | YES |
| `hwpx_list_style_ops.py` | OUTLINE_PRESETS hwpx_schema_rules로 이전 | hwpx-apply-engine | NO | YES | NO | NO | NO | NO | YES |
| `hwpx_style_ops.py` | normalize_* 함수 hwpx_schema_rules로 전량 이전 (파일 거의 비워짐) | hwpx-apply-engine | NO | YES | NO | NO | NO | NO | YES |
| `hwpx_table_cell_address_style.py` | normalize_cell_address hwpx_schema_rules로 이전 | hwpx-apply-engine | NO | YES | NO | NO | NO | NO | YES |
| `hwpx_compose_schema_reference.py` | import 정리 (hwpx_schema_rules 사용) | hwpx-apply-engine | NO | NO | NO | NO | NO | NO | YES (E-1에 묶기) |
| `hwpx_capability_coverage.py` | footnote blocker 메시지 갱신 | hwpx-apply-engine | NO | NO | NO | NO | NO | NO | YES (E-1에 묶기) |
| `hwpx_api.py` | repair_document_for_server, convert_hwp_document_for_server, verify_delivery_for_server 추가; hwpx_server_ops import | server-ops-api | NO | YES (간접) | NO | NO | NO | NO | YES (E-4에 묶기) |
| `hwpx_package.py` | HwpxValidator.validate_entries 추가 (in-memory ZIP validate) | hwpx-apply-engine | NO | YES | NO | NO | NO | NO | YES (E-1) |
| `hancom_hwp_converter_providers.py` | HwpxJsProvider 추가 (hwpxjs open-source CLI 탐지) | hwp-to-hwpx-converter | NO | NO | NO | NO | NO | NO | YES (E-2) |
| `hancom_hwp_converter_router.py` | hwpxjs provider 라우팅, batch-mode auto 선택 개선, explicit provider 선택 | hwp-to-hwpx-converter | NO | NO | NO | NO | NO | NO | YES (E-2) |
| `hwp_to_hwpx_sdk.py` | embed_original 옵션 추가 | hwp-to-hwpx-converter | NO | NO | NO | NO | NO | NO | YES (E-2) |
| `hwp_to_hwpx_standalone.py` | repair_output_package, apply_decoded_style_bridge, embed_original, visual object gate; MIMETYPE → owpml | hwp-to-hwpx-converter | NO | NO | NO | NO | WARN (output_path 로그용) | WARN (backup-replace 패턴, 안전) | YES (E-2) |
| `HWP_TO_HWPX_STANDALONE.md` | --embed-original 옵션 문서 | hwp-to-hwpx-converter | NO | NO | NO | NO | NO | NO | YES (E-2에 묶기) |
| `diagnostics/06_roundtrip_text_probe.py` | xml_local_name 추가, paragraph-aware 텍스트 추출 | verification-tooling | NO | NO | NO | NO | NO | NO | YES (E-5) |
| `extract_hwp_body_fields.py` | HWP record tag 추가(28,30~32,90~98,115), FIDELITY_RISK_TAGS 확장, row_cell_counts, _distributed_col_spans | hwp-to-hwpx-converter (parser-tooling) | NO | NO | NO | NO | NO | NO | YES (E-2에 묶기) |
| `test_hancom_hwp_converter_providers.py` | HwpxJsProvider 탐지 테스트 추가 | hwp-to-hwpx-converter (test) | NO | NO | NO | NO | NO | NO | YES (E-2에 묶기) |
| `test_hancom_hwp_converter_router.py` | hwpxjs 라우팅 테스트, explicit provider 테스트 | hwp-to-hwpx-converter (test) | NO | NO | NO | NO | NO | NO | YES (E-2에 묶기) |
| `test_hwp_to_hwpx_sdk.py` | embed_original 옵션 테스트 | hwp-to-hwpx-converter (test) | NO | NO | NO | NO | NO | NO | YES (E-2에 묶기) |
| `test_hwp_to_hwpx_standalone.py` | repair_output_package, visual gate, decoded_style_bridge 테스트 | hwp-to-hwpx-converter (test) | NO | NO | NO | NO | NO | NO | YES (E-2에 묶기) |

---

## Application.java B-2 분류

| 항목 | 내용 |
|------|------|
| 변경 내용 | `HwpToHwpxCliBridge` import, `Arrays` import, `convert-hwp-to-hwpx` CLI switch case, `runConvertHwpToHwpx()` 메서드, help 문구 |
| 목표 집 | **hwp-to-hwpx-converter-flow** |
| web editor core 포함 | NO — CLI boundary |
| P14C ApplyEngine | NO |
| 묶음 전략 | E-2 커밋 (`feat(converter): extend hwp-to-hwpx cli and standalone converter`)에 포함 |
| 주의 | 실제 변환 실행 금지. HwpToHwpxCliBridge는 CLI 진입점만. |

---

## extract_hwp_body_fields.py 분류

| 항목 | 내용 |
|------|------|
| 변경 내용 | HWP record tag 목록 확장 (TRACK_CHANGE, FORM_OBJECT, VIDEO_DATA 등), FIDELITY_RISK_TAGS 확장, row_cell_counts 파싱, _distributed_col_spans 추가 |
| 목표 집 | **hwp-to-hwpx-converter (parser-tooling)** |
| web editor core | NO |
| Hancom 의존 | NO (순수 binary OLE 파싱) |
| Docker 의존 | olefile → Dockerfile에 이미 추가됨 |
| 묶음 전략 | E-2 커밋에 포함 (`scripts/extract_hwp_body_fields.py`) |

---

## 위험 문자열 검사 결과

| 항목 | 발견 | 판정 |
|------|------|------|
| password/otp/certificate/session/cookie | 없음 | PASS |
| SECRET/TOKEN/API_KEY | 없음 | PASS |
| HwpObject/win32gui/pyautogui | 없음 | PASS |
| shutil.copy2 | `hwp_to_hwpx_standalone.py` 5곳 | WARN — 모두 backup-then-replace 패턴, output 파일 대상, 원본 HWPX 덮어쓰기 아님 |
| output_path 로그 | `hwp_to_hwpx_standalone.py` | WARN — 서버 응답에 포함 안 됨, converter CLI 내부 로깅 |
| 원본 HWPX 덮어쓰기 위험 | 없음 | PASS |

---

## 테스트 후보

| 그룹 | 테스트 | 가능 여부 |
|------|--------|-----------|
| E-1 (hwpx writer) | `test_hwpx_edit_tool.py`, `test_hwpx_table_ops.py`, `test_hwpx_write_gate.py` | pytest 가능 |
| E-2 (converter) | `test_hwp_to_hwpx_standalone.py`, `test_hwp_to_hwpx_sdk.py`, `test_hancom_hwp_converter_providers.py`, `test_hancom_hwp_converter_router.py` | pytest 가능 (Hancom 실행 없음) |
| E-4 (server ops/api) | `hwpx_api.py`는 직접 테스트 없음 | py_compile만 |
| E-5 (verification) | `diagnostics/06_roundtrip_text_probe.py` | py_compile만 |
| 모두 | py_compile | ALL PASS |

---

## 권장 커밋 전략

### 커밋 E-1: hwpx writer/engine utility 정리
```
feat(hwpx): consolidate writer utilities into schema-rules module
```

**대상:**
- `scripts/hwpx/hwpx_package.py` — normalize_entry_name, HwpxValidator.validate_entries
- `scripts/hwpx/hwpx_element_factory.py` — position 파라미터 확장
- `scripts/hwpx/hwpx_image_policy.py` — schema_rules import 정리
- `scripts/hwpx/hwpx_job_schema.py` — schema_rules import 통일
- `scripts/hwpx/hwpx_list_style_ops.py` — OUTLINE_PRESETS 이전
- `scripts/hwpx/hwpx_style_ops.py` — normalize_* 함수 전량 이전
- `scripts/hwpx/hwpx_table_cell_address_style.py` — normalize_cell_address 이전
- `scripts/hwpx/hwpx_compose_schema_reference.py` — import 정리
- `scripts/hwpx/hwpx_capability_coverage.py` — blocker 메시지 갱신

**테스트:** `pytest scripts/hwpx/test_hwpx_edit_tool.py scripts/hwpx/test_hwpx_table_ops.py scripts/hwpx/test_hwpx_write_gate.py`

**P14C ApplyEngine 후보:** YES — hwpx_package, hwpx_element_factory 직접 사용 예정

---

### 커밋 E-2: HWP→HWPX converter 확장
```
feat(converter): extend hwp-to-hwpx standalone converter and cli flow
```

**대상:**
- `scripts/hwpx/hwp_to_hwpx_standalone.py` — repair_output_package, embed_original, visual gate, OWPML MIME
- `scripts/hwpx/hwp_to_hwpx_sdk.py` — embed_original 옵션
- `scripts/hwpx/hancom_hwp_converter_providers.py` — HwpxJsProvider 추가
- `scripts/hwpx/hancom_hwp_converter_router.py` — hwpxjs 라우팅, explicit provider 선택
- `scripts/hwpx/HWP_TO_HWPX_STANDALONE.md` — --embed-original 문서
- `scripts/extract_hwp_body_fields.py` — record tag 확장, row_cell_counts
- `scripts/hwpx/test_hwp_to_hwpx_standalone.py`
- `scripts/hwpx/test_hwp_to_hwpx_sdk.py`
- `scripts/hwpx/test_hancom_hwp_converter_providers.py`
- `scripts/hwpx/test_hancom_hwp_converter_router.py`
- `src/main/java/com/haehan/engine/Application.java` B-2 hunk (HwpToHwpxCliBridge CLI)

**테스트:** `pytest scripts/hwpx/test_hwp_to_hwpx_standalone.py scripts/hwpx/test_hwp_to_hwpx_sdk.py scripts/hwpx/test_hancom_hwp_converter_providers.py scripts/hwpx/test_hancom_hwp_converter_router.py`

**주의:**
- Application.java B-2는 `git add -p` 또는 `git apply --cached` 방식으로 단독 staging 필요
- 실제 Hancom 실행 금지. hwpxjs CLI 실행 금지.
- web editor core와 완전 분리

---

### 커밋 E-4: server ops / API facade 갱신
```
chore(hwpx): extend hwpx server ops and api facade
```

**대상:**
- `scripts/hwpx/hwpx_api.py` — repair_document_for_server, convert_hwp_document_for_server, verify_delivery_for_server

**테스트:** py_compile만 (직접 테스트 없음)

---

### 커밋 E-5: verification tooling 갱신
```
fix(hwpx): improve roundtrip text probe paragraph extraction
```

**대상:**
- `scripts/hwpx/diagnostics/06_roundtrip_text_probe.py` — xml_local_name, paragraph-aware 추출

**테스트:** py_compile PASS

---

### 커밋 E-devlog: devlog 기록
```
chore(devlog): record hwpx converter and writer cleanup history
```

**대상:**
- `logs/change_history.jsonl`

**전략:** E-2 또는 마지막 docs 커밋에 포함 권장. 단독 커밋 불필요.

---

## P14C ApplyEngine 후보

| 파일 | 이유 |
|------|------|
| `hwpx_package.py` | HwpxPackage.open(), write_section_xml(), validate_entries() |
| `hwpx_element_factory.py` | create_picture_object(position=...) — 이미지 배치 정확도 개선 |
| `hwpx_list_style_ops.py` | 목록 스타일 적용 |
| `hwpx_style_ops.py` → `hwpx_schema_rules.py` | normalize_paragraph_style, normalize_table_style |
| `hwpx_table_cell_address_style.py` → `hwpx_schema_rules.py` | normalize_cell_address — updateTableCell 좌표 변환 |

---

## web editor core 포함 금지 항목

| 파일 | 이유 |
|------|------|
| `hancom_hwp_converter_providers.py` | HWP→HWPX converter 흐름. web editor는 이미 HWPX 파일을 받음. |
| `hancom_hwp_converter_router.py` | 동일 |
| `hwp_to_hwpx_standalone.py` | 동일 |
| `hwp_to_hwpx_sdk.py` | 동일 |
| `extract_hwp_body_fields.py` | HWP binary 파싱 — converter tooling |
| `Application.java B-2` | CLI 변환 명령 — web editor route 아님 |

---

## 최종 판정: PASS

- 커밋 가능 그룹: E-1, E-2, E-4, E-5, E-devlog (E-1과 E-2 분리 가능)
- 위험 항목 없음 (shutil.copy2는 backup-replace 패턴으로 안전)
- web editor core 포함 필요 없음
- 실제 코드 수정 없음 (read-only triage)
- py_compile 모든 Python 파일 PASS
