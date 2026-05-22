# HWPX Direct Writer P53 Capability Coverage Gate

## 목적

HWPX direct writer/editor가 현재 어떤 기능을 구현했고, 어떤 기능이 아직 pending인지 스크립트로 전체 점검했다.

이번 단계는 새 문서를 생성하거나 변환하는 단계가 아니라, 현재 도구 체계의 기능 커버리지를 정적 검사로 고정하는 단계다. 한컴 실행, COM, GUI, 서버, Docker는 사용하지 않았다.

## 실행

```powershell
python scripts/hwpx/hwpx_capability_coverage.py `
  --out-dir tmp\hwpx_p53_capability_coverage `
  --report-json tmp\hwpx_p53_capability_coverage_report.json `
  --report-csv tmp\hwpx_p53_capability_coverage.csv `
  --report-md tmp\hwpx_p53_capability_coverage.md
```

## 결과

```text
overall: WARN
module_count: 53
capability_count: 23
implemented_verified: 15
P0/P1 implemented: 14/14
```

`WARN` 사유는 실패가 아니라 고급 기능이 아직 남아 있기 때문이다.

```text
EXPERIMENTAL: synthetic_picture_xml
PENDING: native_chart_object, toc_index, footnote_endnote, drawing_shapes
NOT_REQUIRED: field_form_controls
DEFERRED: browser_viewer
BLOCKED_EXTERNAL: hwp_to_hwpx_conversion
```

## 구현 검증된 기능

| capability | status | 근거 |
|---|---|---|
| package_zip_xml_io | IMPLEMENTED_VERIFIED | ZIP/XML validation 및 package audit 포함 |
| placeholder_text_replace | IMPLEMENTED_VERIFIED | P0/P2 template replacement PASS |
| paragraph_add | IMPLEMENTED_VERIFIED | generated paragraph 및 regression 포함 |
| table_create_and_basic_ops | IMPLEMENTED_VERIFIED | table-create, table-op, Java roundtrip PASS |
| table_merge_and_cell_layout | IMPLEMENTED_VERIFIED | merge/unmerge/cell layout 모듈 확인 |
| style_definitions | IMPLEMENTED_VERIFIED | border/header/list/style definitions 확인 |
| metadata_manifest_preview | IMPLEMENTED_VERIFIED | metadata/manifest/preview 모듈 확인 |
| section_page_layout | IMPLEMENTED_VERIFIED | section/page layout/page numbering 확인 |
| static_header_footer_page_numbering | IMPLEMENTED_VERIFIED | static header/footer/page numbering 확인 |
| bindata_image_seed_replace | IMPLEMENTED_VERIFIED | image-seed/image-replace 확인 |
| visible_picture_clone_rebind | IMPLEMENTED_VERIFIED | visible-image-insert 및 picture clone/rebind 확인 |
| chart_png_as_image | IMPLEMENTED_VERIFIED | chart-png 기반 이미지 삽입 경로 확인 |
| java_parser_roundtrip_gate | IMPLEMENTED_VERIFIED | full-scenario Java roundtrip 9/9 PASS |
| python_facade_api | IMPLEMENTED_VERIFIED | API/builder flow 확인 |
| batch_render_and_examples | IMPLEMENTED_VERIFIED | examples/batch/full-scenario 확인 |

## 남은 기능

### synthetic_picture_xml

현재는 `EXPERIMENTAL`이다. clone 가능한 picture fixture 없이 새 picture XML을 생성하는 경로이며, Java parser roundtrip은 가능해도 한컴 시각 검증이 아직 없다.

### native_chart_object

현재 그래프는 PNG 이미지로 삽입하는 경로가 구현되어 있다. 한컴 native chart 객체는 실제 chart XML fixture 또는 공식 schema mapping이 필요하다.

### field_form_controls

누름틀/필드/폼 컨트롤은 현재 목표 범위에서 제외한다. 향후 문서 workflow가 명시적으로 요구할 때만 재개한다.

### toc_index, footnote_endnote, drawing_shapes

목차, 각주/미주, 도형은 아직 fixture와 생성 규칙이 없다. heading/style 모델이 더 안정된 뒤 진행한다.

### browser_viewer

사용자 지시에 따라 보류한다.

### hwp_to_hwpx_conversion

HWP 변환은 HWPX direct writer 범위 밖이다. 공식 HWPX Converter Add-in 또는 SDK가 별도로 필요하다.

## 결론

HWPX direct writer는 현재 문서 생성/수정의 실무 핵심 경로를 갖췄다.

```text
문단: 가능
표 생성/수정/행 추가/삭제/병합/레이아웃: 가능
스타일/메타데이터/manifest/preview: 가능
섹션/쪽 레이아웃/header/footer: 가능
이미지 BinData/visible picture clone/rebind: 가능
그래프 PNG 삽입: 가능
Java parser roundtrip gate: 가능
batch/API/examples: 가능
```

최종 판정은 `WARN`이다. 이유는 HWPX direct writer의 핵심 기능 실패가 아니라, native chart, TOC, footnote, drawing shape처럼 샘플 fixture와 한컴 시각 검증이 필요한 고급 객체가 남아 있기 때문이다. 누름틀/필드는 현재 목표 범위가 아니다.

## 다음 단계

1. drawing shape/control fixture discovery 및 clone/edit 구현
2. native chart는 우선 PNG chart 경로 유지, 실제 chart fixture 확보 시 재개
3. visible picture는 synthetic bootstrap 대신 안정 fixture를 확보
4. TOC/footnote/endnote는 fixture 확보 후 후순위 진행
5. browser viewer는 도구 개발 안정화 이후 재개
