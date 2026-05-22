# HWPX Browser Editor P14B-1A Legacy Edit Capability Map

**작업명:** HWPX-BROWSER-EDITOR-P14B-1A-LEGACY-HWPX-EDIT-CAPABILITY-MAP
**날짜:** 2026-05-15
**기준선 HEAD:** 9c081f2cd960930809790489dc49046cf5a3da1a
**단계 성격:** Read-only 감사 — 코드 수정 없음
**최종 판정:** PASS

---

## 기존 HWPX 수정 코드 후보 목록

### Python 레이어 (scripts/hwpx/)

| 모듈 | 역할 | 핵심 함수 |
|------|------|-----------|
| `hwpx_package.py` | ZIP/XML 패키지 IO | `HwpxPackage`, `read_xml`, `write_xml`, `write_package`, `copy_package_to` |
| `hwpx_text_ops.py` | 텍스트/placeholder 수정 | `replace_placeholders`, `inject_placeholders`, `append_paragraph` |
| `hwpx_table_ops.py` | 표 셀 수정/행 추가/삭제 | `set_table_cell_text`, `set_table_visual_cell_text`, `append_table_row`, `delete_table_row`, `find_table`, `get_table_cell_matrix` |
| `hwpx_table_merge_ops.py` | 셀 병합/해제 | `merge_table_cells`, `unmerge_table_cell` |
| `hwpx_image_ops.py` | BinData 이미지 교체/추가 | `replace_image_data`, `add_bindata_image_data` |
| `hwpx_picture_ops.py` | 가시적 Picture 오브젝트 | `rebind_picture_object`, `clone_picture_object` |
| `hwpx_visible_image_ops.py` | 가시적 이미지 삽입 | `insert_visible_image_from_template`, `insert_generated_png_picture` |
| `hwpx_manifest_ops.py` | 패키지 manifest 갱신 | `repair_package_manifest` |
| `hwpx_preview_ops.py` | preview text 갱신 | (preview text 재생성) |
| `hwpx_writer_adapter.py` | 통합 facade API | `HwpxEditor` — 위 모든 모듈의 단일 진입점 |
| `hwpx_composer.py` | Job 기반 문서 composer | `compose_hwpx`, `compose_from_job_file` |
| `hwpx_document_builder.py` | Document builder facade | `document()`, `DocumentBuilder` |
| `hwpx_edit_tool.py` | JSON plan 기반 편집 파이프라인 | `apply_edit_plan`, `create_hwpx_document`, `inspect_hwpx`, `batch_apply` |
| `hwpx_server_ops.py` | 서버 사이드 ops 통합 | `fill_cells_for_server`, `insert_table_for_server`, `insert_schedule_for_server`, `repair_for_server` |
| `hwpx_api.py` | 외부 노출 Python API | `render_document`, `compose_document`, `fill_cells_for_server_document` |
| `hancom_hwpx_form_input.py` | 안전서류 폼 입력 | `mark_input_required`, `apply_final_layout_adjustments` |
| `hancom_hwpx_work_schedule_demo.py` | 공정표 삽입 | `append_work_schedule` |
| `hwpx_schedule_diagrams.py` | 공정표 다이어그램 | 공정표 월/일 테이블 생성 |
| `hwpx_java_roundtrip.py` | Java parser roundtrip 검증 | `run_java_roundtrip`, `run_many_java_roundtrips` |
| `hwpx_write_gate.py` | 쓰기 gate + audit log | `build_write_gate`, `write_write_audit_log` |
| `hwpx_section_ops.py` | section 추가/관리 | `append_section`, `inspect_sections` |
| `hwpx_element_factory.py` | XML 요소 factory | `create_table_paragraph`, `create_text_paragraph`, `append_generated_table` |

### Java 레이어 (src/main/java/)

| 클래스 | 역할 |
|--------|------|
| `HwpxParser.java` | HWPX ZIP → 구조 파싱 → `DocumentParseResponse` |
| `HwpxParserCli.java` | CLI entry point (Gradle `parseHwpxCli` task) |

---

## Capability Map

| 기능 | 상태 | 근거 |
|------|------|------|
| HWPX ZIP/XML 열기·닫기 | IMPLEMENTED_VERIFIED | `HwpxPackage` + roundtrip 9/9 PASS |
| XML 읽기 | IMPLEMENTED_VERIFIED | `read_xml`, section/xml entry 순회 |
| XML 쓰기 + ZIP 재패키징 | IMPLEMENTED_VERIFIED | `write_xml` + `write_package` + Java roundtrip PASS |
| placeholder 치환 (`{{key}}`) | IMPLEMENTED_VERIFIED | `replace_placeholders` + `test_hwpx_edit_tool` PASS |
| 표 셀 텍스트 수정 (visual addr) | IMPLEMENTED_VERIFIED | `set_table_visual_cell_text` + test PASS |
| 표 셀 텍스트 수정 (physical) | IMPLEMENTED_VERIFIED | `set_table_cell_text` + test PASS |
| 표 행 추가 | IMPLEMENTED_VERIFIED | `append_table_row` + test PASS |
| 표 행 삭제 | IMPLEMENTED_VERIFIED | `delete_table_row` + test PASS |
| 셀 병합 / 해제 | IMPLEMENTED_VERIFIED | `merge_table_cells`, `unmerge_table_cell` |
| BinData 이미지 교체 | IMPLEMENTED_VERIFIED | `replace_image_data` + test PASS |
| BinData 이미지 추가 | IMPLEMENTED_VERIFIED | `add_bindata_image_data` |
| 가시적 Picture 오브젝트 rebind | IMPLEMENTED_VERIFIED | `rebind_picture_object` + P46/P47 PASS |
| PNG 이미지 생성 후 삽입 | IMPLEMENTED_VERIFIED | `insert_generated_png_picture` + test PASS |
| manifest/preview 갱신 | IMPLEMENTED_VERIFIED | `repair_package_manifest` + composer에서 항상 호출 |
| 문단 추가 | IMPLEMENTED_VERIFIED | `append_paragraph` + regression PASS |
| section 추가 | IMPLEMENTED_VERIFIED | `append_section` + multi-section regression |
| JSON plan 기반 batch 편집 | IMPLEMENTED_VERIFIED | `apply_edit_plan` + `batch_apply` + test PASS |
| Java parser roundtrip 검증 | IMPLEMENTED_VERIFIED | `hwpx_java_roundtrip.py` + Gradle task + 9/9 PASS |
| 공정표 생성 (월/일 테이블) | IMPLEMENTED_VERIFIED | `append_work_schedule` + test PASS |
| 안전서류 폼 입력 (표 셀 좌표 기반) | IMPLEMENTED_VERIFIED | `mark_input_required` + form input test PASS |
| 쓰기 gate + audit log | IMPLEMENTED_VERIFIED | `hwpx_write_gate.py` + composer 통합 |
| native chart 오브젝트 | PENDING | fixture 없음, PNG 이미지 대체만 가능 |
| 목차/각주/미주/도형 | PENDING | fixture 없음 |
| synthetic picture XML | EXPERIMENTAL | Java roundtrip 가능, 한컴 시각 검증 미완 |
| HWP → HWPX 변환 | BLOCKED_EXTERNAL | Hancom 실행 의존 |

---

## 기존 테스트/보고서 근거

| 테스트 | fixture 방식 | roundtrip | PASS |
|--------|-------------|-----------|------|
| `test_hwpx_edit_tool.py` | tmp_path에 ZIP 직접 생성 (실제 파일 불필요) | Java roundtrip 없음 | PASS |
| `test_hwpx_table_ops.py` | tmp_path에 XML+ZIP 직접 생성 | 없음 | PASS |
| `test_hwpx_write_gate.py` | tmp_path | 없음 | PASS |
| `test_hancom_hwpx_work_schedule_demo.py` | tmp_path | 없음 | PASS |
| `test_hancom_hwpx_form_input_validation.py` | tmp_path | 없음 | PASS |
| `hwpx_java_roundtrip.py` full-scenario | 실제 HWPX 생성 후 Java CLI 호출 | **있음** 9/9 PASS | PASS |
| `diagnostics/06_roundtrip_text_probe.py` | 실제 HWP→HWPX 변환 후 텍스트 비교 | **있음** | 조건부 |

**공통 특성:**
- 대부분 테스트는 `tmp_path`에 최소 유효 HWPX ZIP을 직접 생성 (실제 감리 문서 파일 불필요)
- Java roundtrip 검증은 `hwpx_java_roundtrip.py`를 통해 `parseHwpxCli` Gradle task 호출
- 현재 브라우저 편집기와 연결된 테스트 없음

---

## 현재 브라우저 Command와 매핑

### replaceText command

| 기존 기능 | 연결 가능성 | 필요 작업 |
|-----------|------------|-----------|
| `replace_placeholders()` — `{{key}}` → value | **바로 연결 가능 후보** | HWPX path를 artifactId로 resolve하는 adapter 필요 |
| `apply_edit_plan()` replace_nodes operation | **바로 연결 가능 후보** | JSON plan을 command에서 조립하는 adapter 필요 |
| `hwpx_server_ops.fill_cells_for_server()` | 부분 연결 가능 | 셀 채우기 특화, 색상 설정 포함 → replaceText 보다 updateTableCell에 적합 |

**매핑 판정:** `replaceText` command → `apply_edit_plan()` replace_nodes 경로가 가장 범용. adapter에서 command.target(paragraphIndex) + command.payload(oldText, replacement)를 plan JSON으로 변환 후 호출.

### updateTableCell command

| 기존 기능 | 연결 가능성 | 필요 작업 |
|-----------|------------|-----------|
| `set_table_visual_cell_text()` — visual row/col 기반 | **바로 연결 가능 후보** | command.target의 tableIndex/row/col → visual addr 직접 매핑 |
| `HwpxEditor.set_table_visual_cell_text()` | **바로 연결 가능 후보** | HwpxEditor facade 사용 |
| `fill_cells_for_server()` | 가능하나 색상 포함 | browser editor에서 색상 지정 없으면 단순 텍스트 수정으로 대체 |

**매핑 판정:** `updateTableCell` command → `set_table_visual_cell_text(package, table_index, visual_row, visual_col, value)` 직접 연결이 가장 단순. 좌표 체계가 Java parser response와 동일(visual addr 기반).

### validateDocument command

| 기존 기능 | 연결 가능성 |
|-----------|------------|
| `inspect_hwpx()` — 섹션/표/이미지/placeholder 검사 | 연결 가능 (read-only) |
| `HwpxValidator.validate_hwpx()` — ZIP 구조 검증 | 연결 가능 (read-only) |
| Java `HwpxParser.parse()` — 전체 문서 파싱 | 이미 `ParseHwpxHandler`에서 연결됨 |

**매핑 판정:** validateDocument는 이미 dryRun 형태로 APPLY_DEFERRED 반환. 실제 validate 내용이 필요하면 `inspect_hwpx()` 결과를 command 응답에 포함 가능.

---

## ApplyEngine 후보

### P14C 바로 연결 후보 (adapter 필요)

| 후보 | 대상 command | 조건 |
|------|-------------|------|
| `set_table_visual_cell_text()` | `updateTableCell` | artifactId → file path resolve + 결과 검증 후 outputArtifact 구조로 감싸기 |
| `replace_placeholders()` / `apply_edit_plan() replace_nodes` | `replaceText` | 동일 |
| `hwpx_write_gate.build_write_gate()` | 공통 | 쓰기 후 gate 검증 필수 |
| `repair_package_manifest()` | 공통 | 모든 수정 후 manifest 자동 갱신 필수 |

**ApplyEngine 조건 충족 여부:**
- 원본 파일 직접 덮어쓰지 않음: `copy_package_to()` + 임시 경로 출력 → **충족 가능**
- raw path 외부 노출 금지: `artifactId` 기반 resolve + 응답에 path 미포함 → **adapter 설계 필요**
- 예외 처리: 기존 `status: PASS/FAIL/WARN` 구조 → **충족**
- 테스트: 기존 unit test 존재 → **충족**
- outputArtifact 구조: 현재 없음 → **P14C에서 ArtifactRegistry에 output 등록 필요**

### P14C 전 adapter 필요

- `HwpxEditorApplyAdapter` (신규): `HwpxEditorCommand` → Python 함수 호출 변환
  - `command.target` + `command.payload` → `apply_edit_plan` plan dict
  - artifactId → 서버 내 HWPX file path resolve (ArtifactMetadata에 path 추가 필요)
  - 출력 HWPX → output artifactId 신규 발급 + ArtifactRegistry 등록

### P14D 이후 후보

- `append_table_row` / `delete_table_row` → 신규 command (`addTableRow`, `deleteTableRow`) 필요, P14C 이후
- `merge_table_cells` / `unmerge_table_cell` → 신규 command, P14D 이후
- `insert_visible_image_from_template` → 신규 `replaceImage` command, P14D 이후

### 별도 document builder로 분리

- `append_work_schedule()` (공정표) → browser editor command가 아니라 서버 사이드 Document Generation UseCase
- `mark_input_required()` (안전서류) → template generation flow, 별도 API endpoint
- `compose_hwpx()` / `compose_from_job_file()` → document composition API, editor command와 분리

---

## 분리해야 할 기능

| 기능 | 이유 | 권고 위치 |
|------|------|-----------|
| 공정표 생성 (월/일 테이블 + 색상) | 복잡한 데이터 모델 필요, UI command와 다른 입력 구조 | `DocumentGenerationUseCase` / `/api/hwpx/generate` |
| 안전서류 폼 입력 (`mark_input_required`) | 문서 종류별 좌표 하드코딩, 특수 로직 | `FormTemplateUseCase` / 별도 endpoint |
| HWP → HWPX 변환 | Hancom 실행 의존, Docker container 필요 | 기존 `/convert-hwp` endpoint 유지 |
| Batch compose (여러 파일 일괄 생성) | editor command와 1:1 매핑 아님 | `/api/hwpx/batch-compose` 별도 |

---

## 위험/Gap 분석

| 위험 | 상태 | 설명 |
|------|------|------|
| **파일 경로 기반** | 위험 있음 | 기존 코드는 `input_path`, `output_path`를 Path 객체로 직접 처리. browser editor 연결 시 artifactId → path resolve 레이어 필수 |
| **원본 덮어쓰기** | 주의 | `shutil.copy2(source, output)` 후 same path로 쓰면 덮어씀. output_path를 항상 별도 경로로 강제해야 함 |
| **raw path 응답 노출** | 위험 있음 | `apply_edit_plan()` 결과에 `"output": str(output_path)` 포함됨. ApplyEngine adapter에서 필터링 필수 |
| **secret/log 노출** | 현재 없음 | 기존 코드는 credential 처리 없음 |
| **Hancom COM 의존** | 일부 모듈 | `hwp_to_hwpx_standalone.py`, `scripts/local-gui/*` — browser editor 연결 대상 아님 |
| **Windows local 전용** | 해당 모듈만 | Hancom COM 의존 모듈만 Windows 전용. Python XML/ZIP 기반 모듈은 cross-platform |
| **테스트 없이 동작 보고** | 없음 | 기존 코드 모두 pytest 단위 테스트 또는 Java roundtrip 검증 보유 |
| **manifest/preview 누락** | 위험 | 일부 저수준 함수는 manifest 갱신 미포함. ApplyEngine adapter에서 `repair_package_manifest()` 반드시 호출 필요 |
| **ArtifactMetadata에 file path 없음** | Gap | 현재 `ArtifactMetadata`는 `artifactId`, `originalFileName`, `contentType`만 보유. apply를 위해 서버 내 HWPX 파일 경로 연결 메커니즘 필요 |
| **outputArtifact 구조 미구현** | Gap | 현재 ArtifactRegistry는 parse-time에만 등록. apply 결과를 output artifact로 등록하는 흐름 없음 |

---

## 보고서 경로

`docs/reports/hwpx_browser_editor_p14b1a_legacy_edit_capability_map_20260515.md`

---

## P14B-2로 넘길 항목

- ArtifactMetadata에 서버 내 HWPX 파일 경로(또는 임시 저장 위치) 연결 설계
- ArtifactRegistry 영속화 설계 (in-memory → 파일/DB)
- outputArtifact 등록 흐름 설계

## P14C ApplyEngine 연결 후보

1. `updateTableCell` → `set_table_visual_cell_text()` via `HwpxEditorApplyAdapter`
2. `replaceText` → `apply_edit_plan() replace_nodes` via `HwpxEditorApplyAdapter`
3. 공통: `repair_package_manifest()` + `hwpx_write_gate.build_write_gate()` 자동 적용

---

## 최종 판정: PASS
