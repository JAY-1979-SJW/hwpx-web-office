# P3 HWPX 문서 자동화 엔진 경계 고정 보고서

## 1. 작업명

OFFICE-ANALYSIS-P3-HWPX-DOCUMENT-ENGINE-BOUNDARY-LOCK

## 2. 기준

- 기준 HEAD: 804031cd2d690f9b9838331b2d8e1815d464e844
- 기준 브랜치: main
- push: 수행하지 않음
- history secret 위험: 사용자 처리 항목으로 유지
- working tree known prefix quoted literal: 0건

## 3. HWPX 실제 코드 위치

### Package / ZIP / manifest / metadata

- scripts/hwpx/hwpx_package.py
- scripts/hwpx/hwpx_manifest_ops.py
- scripts/hwpx/hwpx_metadata_ops.py
- scripts/hwpx/hwpx_package_audit.py
- scripts/hwpx/hwpx_package_inspector.py
- scripts/hwpx/hwp_full_fidelity_package.py

### XML edit / section / table / cell / style

- scripts/hwpx/hwpx_element_factory.py
- scripts/hwpx/hwpx_style_ops.py
- scripts/hwpx/hwpx_list_style_ops.py
- scripts/hwpx/hwpx_table_cell_address_style.py
- scripts/hwpx/hwpx_compose_schema_reference.py
- scripts/hwpx/hwpx_spine_repair.py

### Template / generation / delivery

- scripts/hwpx/hwpx_api.py
- scripts/hwpx/hwpx_full_scenario.py
- scripts/hwpx/hwpx_delivery_auto_verify.py
- src/main/java/com/haehan/engine/http/HwpxUploadHandler.java
- src/main/java/com/haehan/engine/http/HwpxEditorApiHandler.java
- src/main/java/com/haehan/engine/http/ConvertHwpToHwpxHandler.java

### Validation / fixture / roundtrip

- scripts/hwpx/test_hwp_to_hwpx_standalone.py
- scripts/hwpx/test_hancom_hwp_converter_router.py
- scripts/hwpx/test_hancom_hwp_converter_providers.py
- src/test/java/com/haehan/engine/parser/HwpxParserTableCoordinatesTest.java
- src/test/java/com/haehan/engine/http/HwpxUploadHandlerEncodingTest.java

### HWP/Hancom local worker 후보

- scripts/hwpx/hancom_hwp_converter_router.py
- scripts/hwpx/hancom_hwp_converter_providers.py
- scripts/hwpx/index_local_hwp_hwpx_files.py
- scripts/local-gui/hancom_hwp_to_hwpx_local_gui.py
- src/main/java/com/haehan/engine/hwp/HwpToHwpxCliBridge.java
- src/main/java/com/haehan/engine/hwp/PythonScriptBridge.java

## 4. 책임 경계

HWPX 엔진은 다음 경계로 고정한다.

- HWPX Package Layer: ZIP read/write, manifest, metadata, section XML, preview, bindata, media.
- HWPX XML Edit Layer: paragraph, table, cell, row, style, image, chart 편집.
- HWPX Template Layer: placeholder, template render, safety document builder, schedule builder, report builder.
- HWPX Validation Layer: package validation, XML validation, roundtrip validation, golden validation.
- Adapter Boundary: filesystem, Java/Python bridge, local Hancom/HWP converter adapter, external converter provider adapter.

금지 경계는 문서화했다.

- HWPX Engine이 Excel parser를 직접 호출하지 않는다.
- Excel Engine이 HWPX 내부 XML writer를 직접 호출하지 않는다.
- HWP/Hancom 변환은 server runtime에서 직접 실행하지 않는다.
- HWPX package editor와 local-gui를 직접 결합하지 않는다.
- API handler에 HWPX 세부 XML 조작을 직접 구현하지 않는다.
- 테스트 없는 HWPX runtime 변경을 완료로 보지 않는다.

## 5. Cycle 상태

- P3 시작 시 scripts/hwpx cycle: 2건
- P3 감사 후 cycle: 0건
- 처리 방식: 기능 변경 없이 정적 import 결합을 지연 로딩 경계로 낮췄다.
- 관련 파일:
  - scripts/hwpx/hwp_to_hwpx_standalone.py
  - scripts/hwpx/hwpx_api.py
  - scripts/hwpx/hwp_full_fidelity_audit.py

주의: scripts/hwpx/hwp_full_fidelity_audit.py는 기존 untracked HWPX 작업 범위에 남아 있으며, 이번 P3 커밋에는 포함하지 않는 후보로 분류한다.

## 6. HWP/Hancom local worker gate 판단

- 서버 허용: HWPX XML/ZIP 편집, package validation, report generation.
- local worker 필요: HWP/Hancom 변환, GUI 기반 변환, 사용자 PC 앱 제어.
- user-present 필요: 비밀번호, OTP, 인증서, 전자서명, 결제, 송금, 투찰, 제출.

P3 감사 스크립트는 src/main/java/com/haehan/engine/hwp 하위 bridge를 local worker adapter 후보로 분류한다. 해당 bridge가 process execution을 포함하면 FAIL이 아니라 WARN으로 보고하고, HTTP handler에서 직접 process execution이 보이면 FAIL로 판단한다.

## 7. Excel/HWPX adapter boundary 판단

Excel scripts의 HWP/HWPX reference 후보는 P2 WARN으로 유지한다. 이는 Excel 분석 결과가 HWPX/보고서 생성으로 넘어가는 연결부가 P4 통합 usecase에서 adapter boundary로 정리되어야 한다는 신호이며, 현재 P3 차단 오류는 아니다.

## 8. Upload/package gate WARN

다음 위치는 HWPX upload/package validation gate의 구체화가 필요한 후보로 남았다.

- src/main/java/com/haehan/engine/http/ConvertHwpToHwpxHandler.java
- src/main/java/com/haehan/engine/http/HwpxEditorApiHandler.java
- src/main/java/com/haehan/engine/http/EngineHttpServer.java
- src/main/java/com/haehan/engine/http/HwpxProxyHandler.java
- src/main/java/com/haehan/engine/http/ParseHwpxHandler.java

P3에서는 handler 대형 리팩터링을 하지 않고, P4/P5에서 upload/file gate 구현 경계로 넘긴다.

## 9. 테스트 결과

- python scripts/audit_hwpx_engine_boundaries.py: WARN, cycle_count=0
- python -m pytest tests/test_hwpx_engine_boundary_audit.py -q: PASS
- python -m pytest tests/test_layer_boundary_audit.py -q: PASS
- python -m pytest tests/test_import_cycle_audit.py -q: PASS
- python -m pytest tests/test_execution_location_gate_audit.py -q: PASS
- python -m pytest tests/test_upload_file_gate_audit.py -q: PASS
- python -m pytest tests/test_excel_statement_boundary_audit.py -q: PASS
- .\gradlew.bat tasks: PASS
- .\gradlew.bat test: PASS

## 10. 남은 WARN/FAIL

### WARN

- HWP/Hancom bridge의 local worker gate 명시를 runtime usecase 연결부에서 더 구체화해야 한다.
- API handler의 HWPX package/upload validation gate가 더 명시되어야 한다.
- Excel 분석 결과와 HWPX/보고서 생성 연결부는 adapter boundary로 정리해야 한다.
- 기존 HWPX/local-gui/Docker/src main dirty 변경분은 별도 커밋 단위로 남아 있다.
- history secret 위험은 사용자 처리 항목으로 남아 있다.

### FAIL

- P3 감사 기준에서 신규 FAIL 없음.

## 11. P4 권장안

P4는 통합 usecase 경계 고정으로 진행한다.

- Excel/내역서 분석 결과를 domain model로 고정한다.
- domain model에서 HWPX/보고서/안전서류/공정표 생성 adapter로 넘긴다.
- upload/package/file gate를 usecase 진입점에 배치한다.
- local worker required 작업은 server runtime에서 직접 실행되지 않도록 명시한다.
- 다운로드/API 응답 key는 기존 호환성을 유지한다.

## 12. 수행하지 않은 작업 확인

- history rewrite 없음
- git filter-repo 없음
- BFG 없음
- reset/restore/checkout 없음
- git clean 없음
- stash 없음
- pull 없음
- push 없음
- remote 변경 없음
- upstream 설정 없음
- DB write 없음
- schema 변경 없음
- 외부 브라우저 실행 없음
- secret 값 출력 없음
- HWPX 기능 대량 추가 없음
- local-gui 대형 변경 없음
- Dockerfile 변경 없음
- src/main 대형 handler 리팩터링 없음

## 13. 최종 판정

WARN

P3의 목적이었던 HWPX 문서 자동화 엔진 책임 경계, 감사 스크립트, 감사 테스트, cycle 2건 감소는 완료했다. 남은 항목은 P4 통합 usecase와 upload/local worker gate 구현 경계에서 처리한다.
