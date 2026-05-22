# HWPX Direct Writer Function Modularization

## 목적

HWPX direct writer/editor에 이미 구현된 기능을 기능별 모듈로 분리했다.

기존 상태는 `hwpx_writer_adapter.py`와 `hwpx_template_engine.py`에 ZIP 패키지 처리, XML 검증, placeholder 치환, 문단 추가, 표 조작, 렌더링 orchestration, 이미지 BinData 조작, CLI 처리가 함께 섞여 있었다.

이번 작업의 목표는 기능별 책임을 분리하고, CLI 파일은 얇은 실행 레이어로 유지하는 것이다.

## 모듈 구조

| 모듈 | 책임 |
| --- | --- |
| `hwpx_package.py` | HWPX ZIP/XML 패키지 IO, XML entry 판별, XML decode/serialize, validation, JSON/CSV IO |
| `hwpx_text_ops.py` | placeholder 치환, placeholder 주입, 기존 문단 clone 기반 문단 추가 |
| `hwpx_table_ops.py` | 표 탐색, 셀 수정, 행 추가, 행 삭제, 표 clone, table-op 실행, table JSON 검증 |
| `hwpx_image_ops.py` | BinData 이미지 entry 탐색, 이미지 seed, 이미지 교체, content.hpf manifest 보강 |
| `hwpx_validation.py` | rendered HWPX 검증, placeholder 잔존 여부, expected text 검증 |
| `hwpx_template_render.py` | render/batch/self-test orchestration, mapping/table report, ordering warning |
| `hwpx_writer_adapter.py` | 기존 `HwpxEditor` API 호환 facade |
| `hwpx_template_engine.py` | CLI command routing |

## 기능별 분리 결과

### 패키지/검증

- `HwpxPackage`
- `HwpxValidator`
- `package_contains`
- `package_has_placeholders`
- `read_json`
- `write_json`
- `write_csv`
- `unique_path`

판정: `PASS`

### 텍스트/문단

- `replace_placeholders`
- `inject_placeholders`
- `append_paragraph`

판정: `PASS`

### 표

- `find_tables`
- `get_table_cells`
- `update_table_cells`
- `append_table_row`
- `delete_table_row`
- `clone_table`
- `replace_table_placeholder`
- `apply_table_operations`

판정: `PASS`

### 이미지 BinData

- `image_inventory`
- `add_bindata_image_data`
- `replace_image_data`
- `xml_references_for_entry`

판정: `PASS`

주의: 현재 단계는 BinData entry 생성/교체까지이며, 본문에 실제로 보이는 anchored picture XML 객체 생성은 후속 단계다.

### 템플릿 렌더링

- `render_one`
- `normalize_table_config`
- `validate_table_config`
- `expected_values`
- `write_self_test_inputs`
- `materialize_job_files`

판정: `PASS`

## 검증

### Python AST

대상:

- `scripts/hwpx/hwpx_package.py`
- `scripts/hwpx/hwpx_text_ops.py`
- `scripts/hwpx/hwpx_table_ops.py`
- `scripts/hwpx/hwpx_validation.py`
- `scripts/hwpx/hwpx_template_render.py`
- `scripts/hwpx/hwpx_writer_adapter.py`
- `scripts/hwpx/hwpx_template_engine.py`
- `scripts/hwpx/hwpx_image_ops.py`

결과: `PASS`

### CLI help

확인:

- `hwpx_template_engine.py --help`
- `render --help`
- `table-op --help`
- `image-seed --help`
- `image-replace --help`
- `hwpx_writer_adapter.py --help`

결과: `PASS`

### Self-test

명령:

```text
python scripts/hwpx/hwpx_template_engine.py self-test --template tmp\hwpx_writer_poc\template_seed.hwpx --out-dir tmp\hwpx_modularization_check --report-json tmp\hwpx_modularization_check\selftest_report.json
```

결과:

- render: `PASS`
- validate: `PASS`
- batch-render: `2/2 PASS`
- placeholder remaining: `false`
- expected missing: `[]`

판정: `PASS`

### Table-op

명령:

```text
python scripts/hwpx/hwpx_template_engine.py table-op --template tmp\hwpx_writer_poc\table_updated.hwpx --output tmp\hwpx_modularization_check\table_ops_result.hwpx --ops-json tmp\hwpx_table_ops_poc\table_ops.json --validate --report-json tmp\hwpx_modularization_check\table_ops_report.json
```

결과:

- 셀 수정: `PASS`
- 행 추가: `APPEND_ROW_PASS`
- 행 삭제: `DELETE_ROW_PASS`
- ZIP/XML: `PASS`
- 최종 status: `WARN`

WARN 사유:

- 테스트 ops가 삭제한 행의 값을 expected 목록에도 포함하고 있어 `missing_expected_values`가 발생했다.
- 표 조작 자체는 성공했다.

판정: `WARN`

### Image seed/replace

명령:

```text
python scripts/hwpx/hwpx_template_engine.py image-seed --template tmp\hwpx_writer_poc\template_seed.hwpx --output tmp\hwpx_modularization_check\image_seed_distinct.hwpx --image tmp\hwpx_image_replace_poc\seed_marker.png --validate --report-json tmp\hwpx_modularization_check\image_seed_distinct_report.json
```

```text
python scripts/hwpx/hwpx_template_engine.py image-replace --template tmp\hwpx_modularization_check\image_seed_distinct.hwpx --output tmp\hwpx_modularization_check\image_replaced_distinct.hwpx --image-index 0 --replacement tmp\hwpx_image_replace_poc\replacement_marker.png --validate --report-json tmp\hwpx_modularization_check\image_replace_distinct_report.json
```

결과:

- image seed: `PASS`
- image replace: `PASS`
- hash changed: `true`
- XML refs preserved: `true`
- ZIP/XML: `PASS`

판정: `PASS`

## 결론

기존 구현 기능 중 모듈화되지 않은 핵심 로직을 기능별 모듈로 분리했다.

현재 구조:

```text
CLI
→ template render orchestration
→ package / text / table / image / validation modules
→ HWPX ZIP/XML
```

최종 판정: `PASS`

## 남은 작업

1. 본문에 실제 표시되는 picture/control/anchor XML 객체 생성
2. 그래프 PNG 생성 후 visible image 삽입
3. HWPX 문서 작성 API 레이어 추가
4. table-op expected-value 정책 보강
