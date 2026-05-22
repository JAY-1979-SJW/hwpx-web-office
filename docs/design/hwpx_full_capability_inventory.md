# HWPX 전체 기능 인벤토리 + 우선순위 분석서

> 작성일: 2026-05-19
> 기준 HEAD: `7dec95e` (공정표 설계서 직후)
> 라이프사이클: §11-1 ② 시공 계획서
> 목적: HWPX 단지의 **모든 자재(57+ 파일)** 인벤토리 + 활용 가능성 + 우선순위

---

## 1. 자재 인벤토리 — 10대 영역 그룹화

### 그룹 A — 패키지·골조 (이미 활용 ★)

| 자재 | 상태 | 활용 |
|------|------|------|
| hwpx_package | ✅ 검증됨 | ZIP/XML 처리 |
| hwpx_package_inspector | ✅ | 무결성 |
| hwpx_package_audit | ✅ | 감사 |
| hwpx_manifest_ops | ✅ | manifest |
| hwpx_validation | ✅ | 스키마 검증 |
| hwpx_schema_rules | ✅ | 규칙 |

→ **이번 세션에서 100% 활용** (V1~V7 검증 핵심).

### 그룹 B — 본문 텍스트 (이미 활용 ★)

| 자재 | 상태 |
|------|------|
| hwpx_text_ops | ✅ |
| hwpx_section_ops | ✅ |
| hwpx_special_text | ✅ (검증 안 함) |
| parser/block_parser | ✅ |
| parser/parser_engine | ✅ |

→ **라벨 입력에서 활용**. 특수 텍스트(자동번호, 각주 등)는 미검증.

### 그룹 C — 표 (이미 활용 ★)

| 자재 | 상태 | 활용 |
|------|------|------|
| hwpx_table_ops | ✅ | set_cells |
| hwpx_table_cell_style | ✅ | 폰트 보존 (V4) |
| hwpx_table_cell_layout_ops | ⚠️ 부분 | 정렬 |
| hwpx_table_cell_layout_style | ⚠️ 부분 | 정렬 스타일 |
| hwpx_table_cell_address_style | ⚠️ | 주소 |
| hwpx_table_dimension_style | ⚠️ | 폭/높이 |
| hwpx_table_merge_ops | ❌ 미가동 | **셀 병합 자동화** |
| hwpx_table_merge_style | ❌ 미가동 | **병합 스타일** |
| hwpx_table_style_audit | ⚠️ | 감사 |

→ 표 기본 입력은 검증됨. **병합·합치기는 미가동** (E-규격서에 mergeCells/splitCells 명령은 있으나 Java handler placeholder).

### 그룹 D — 스타일·폰트 (V4/V5로 검증 ★)

| 자재 | 상태 |
|------|------|
| hwpx_style_ops | ✅ |
| hwpx_style_resolver | ✅ (V4/V5 검증) |
| hwpx_header_style | ⚠️ |
| hwpx_border_fill_style | ⚠️ (공정표 설계서에 활용 예정) |
| hwpx_list_style_ops | ❌ 미가동 |

→ 보존은 검증. **목록 스타일·테두리 색은 미검증**.

### 그룹 E — 공정표·일정 (설계서 작성 ★)

| 자재 | 상태 |
|------|------|
| hwpx_schedule_diagrams | ⚠️ 자재만 |
| pipeline/schedule_bar_color_policy | ⚠️ |
| pipeline/schedule_bar_plan_generator | ⚠️ |
| parser/schedule_detector | ⚠️ |

→ 설계서 작성됨 (PoC 대기).

### 그룹 F — 이미지·도형 (❌ 미검증)

| 자재 | 상태 |
|------|------|
| hwpx_image_ops | ❌ 미가동 |
| hwpx_image_policy | ❌ |
| hwpx_picture_ops | ❌ |
| hwpx_visible_image_ops | ❌ |
| parser/object_parser | ⚠️ B동 진단만 |

→ **이미지 삽입·교체·삭제 = 미검증 영역**.

### 그룹 G — 헤더·푸터 (❌ 미검증)

| 자재 | 상태 |
|------|------|
| hwpx_header_footer_ops | ❌ |
| hwpx_header_footer_discovery | ❌ |
| hwpx_header_field_detector | ⚠️ 일부 |

→ **헤더/푸터 입력·자동 채움 = 미검증**.

### 그룹 H — 페이지·메타데이터 (❌ 미검증)

| 자재 | 상태 |
|------|------|
| hwpx_page_layout_ops | ❌ |
| hwpx_metadata_ops | ❌ |
| hwpx_spine_repair | ❌ |

→ **페이지 설정·메타 수정 = 미검증**.

### 그룹 I — 차트·고급 (❌ 미검증)

| 자재 | 상태 |
|------|------|
| hwpx_chart_png | ❌ |
| hwpx_compose_examples | ❌ |
| hwpx_compose_regression | ❌ |
| hwpx_compose_schema_reference | ❌ |
| hwpx_composer | ❌ |
| hwpx_template_engine | ❌ |
| hwpx_template_render | ❌ |

→ **차트 삽입·템플릿 합성 = 미검증**.

### 그룹 J — 검증·게이트 (이미 활용 ★)

| 자재 | 상태 |
|------|------|
| hwpx_write_gate | ✅ |
| hwpx_writer_adapter | ✅ |
| hwpx_java_roundtrip | ⚠️ 자재만 (한컴 호환 검증) |
| hwpx_capability_coverage | ❌ |
| hwpx_delivery_auto_verify | ❌ |
| hwpx_preview_ops | ❌ |

---

## 2. 검증 매트릭스 — 한눈에

| 그룹 | 자재 수 | 검증 | 미검증 | 활용도 |
|------|--------|------|------|------|
| A 패키지·골조 | 6 | 6 | 0 | ★★★★★ |
| B 본문 텍스트 | 5 | 4 | 1 | ★★★★ |
| C 표 | 9 | 6 | 3 | ★★★★ |
| D 스타일·폰트 | 5 | 3 | 2 | ★★★ |
| E 공정표 | 4 | 0 (설계서만) | 4 | ★ |
| **F 이미지** | 5 | 0 | 5 | ❌ |
| **G 헤더·푸터** | 3 | 0 | 3 | ❌ |
| **H 페이지·메타** | 3 | 0 | 3 | ❌ |
| **I 차트·템플릿** | 7 | 0 | 7 | ❌ |
| J 검증·게이트 | 6 | 3 | 3 | ★★★ |
| **합계** | **57+** | **22** | **31** | |

→ **38% 검증, 62% 미검증**. 미검증 영역이 4개 그룹 (F·G·H·I).

---

## 3. 우선순위 추천 (실용성 기반)

### 1순위 — 즉시 사용 가치 큰 영역

| 그룹 | 사유 | 효과 |
|------|------|------|
| **E 공정표** | 설계서 이미 작성, PoC만 남음 | 막대 색·날짜 자동 채움 가능 |
| **C 표 병합/분할** | E-규격서에 명령 잠금됨 | 셀 병합 자동 |
| **G 헤더·푸터** | 정부 양식 절반 이상이 헤더 양식 사용 | 헤더 자동 채움 |

### 2순위 — 시각·디자인 기능

| 그룹 | 사유 |
|------|------|
| F 이미지 | 도장·서명 이미지 삽입 |
| D 목록·테두리 색 | 양식 디자인 보존 |

### 3순위 — 고급 기능

| 그룹 | 사유 |
|------|------|
| I 템플릿·차트 | 양식 합성·차트 자동 |
| H 페이지·메타 | 페이지 번호·메타 수정 |
| B 특수 텍스트 | 자동 번호·각주 |

---

## 4. 분석 옵션 (대표님 선택)

| 옵션 | 진행 |
|------|------|
| **(A) 1순위 3그룹만 분석** | 공정표 + 셀 병합 + 헤더·푸터 (3 설계서 작성) |
| **(B) 2순위까지 확장** | 5 그룹 (+ 이미지, 디자인) |
| **(C) 모든 미검증 31개 자재 분석** | 4개 그룹 모두 (큰 작업) |
| **(D) 사용 시나리오 기반** | 대표님이 처리할 양식 종류 알려주시면 그에 맞춰 |

---

## 5. 권장

> **(A) 1순위 3그룹** 분석 후 우선순위 재정렬
> 
> 이유:
> - 정부 양식 처리 가치 최대 (헤더 + 표 병합 + 공정표)
> - 31개 모두 분석은 ROI 낮음 (사용 안 할 가능성 큼)
> - 사용 시나리오 명확해진 후 2/3순위 결정

---

## 6. 각 그룹별 분석 시 산출물

각 그룹 분석 시 다음 산출:
- 자재 함수 시그니처 정리
- 활용 시나리오
- 신규 검증 항목 (V8~V10 같이)
- 위험 등기 (RISK-LEDGER 후보)
- PoC 시공 계획

---

## 7. 대표님 결정 사항

1. **분석 범위**: 1순위 3그룹 / 2순위 5그룹 / 전체 / 시나리오 기반
2. **각 그룹 PoC**: 분석 후 1건 시공까지 / 분석만
3. **우선순위 그룹**: 헤더·푸터 / 셀병합 / 공정표 중 어느 것부터?

---

## 부록. 본 문서 작성 경위

- 대표님 지시: "hwpx 문서에 다른 기능도 넣어야 하니 나머지도 모두 확인해서 분석할까?"
- 57+ HWPX 자재 인벤토리 정리
- 검증 38% / 미검증 62%
- 우선순위 3 단계 추천
- §11-1 ② 시공 계획서 형태
