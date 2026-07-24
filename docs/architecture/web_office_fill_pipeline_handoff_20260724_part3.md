# 서식 채움 공정 인계 (속편 3) — 충실 뷰어 연결·관계자 오분류 수리

**작성**: 2026-07-24 (같은 날 야간)
**선행**: `web_office_fill_pipeline_handoff_20260724_part2.md` — 그 문서의
"기입 완성·검증" 위에, 이 속편은 **브라우저 앞단(질문 패널) 뷰어를 원본
배치 그대로 붙이고**, 그 과정에서 드러난 **관계자 오분류 결함을 수리**한다.

---

## 0. 한 줄 요약

독립 질문 패널에 **다른 창에서 개발한 충실 뷰어(좌표 페이지-분할
`coordinate_renderer`)를 연결**해 서식을 원본 배치대로 페이지마다 끊어
보여주고, 민원인/관계자 칸을 색으로 구분한다. 검증 중 "입력창이 안 뜨는"
서식을 실검증해 원인이 **역할 오분류**(보고서류를 전부 관계자로 죽임)임을
밝히고 수리했다. 병행 세션 작업 영역(app.mjs·coordinate_renderer 등)은
무접촉·read-only import 만.

---

## 1. 이 세션에 한 것 — 커밋 순서

```
96683ff  feat  질문 패널에 충실 뷰어(좌표 페이지-분할) 연결 + 역할 색 구분
a56c3c9  fix   '보고서'류를 민원신청으로 되살림 — 관계자 오분류 수리
```

(그 사이 31a0419 등은 병행 세션의 좌표 정합 커밋 — 이 세션 작업 아님.)

## 2. 충실 뷰어 연결 (96683ff)

**무엇을**: 흐름 보기(`document_view`, 표를 재-flow)에서 → 한컴 lineseg
좌표를 절대배치하는 `coordinate_renderer.renderCoordinateLayout` 로 교체.
서식을 **원본 페이지 경계 그대로 `.co-page` 로 끊어** 그린다.

**데이터 경로**: 프론트가 `/api/web-office/hwpx-layout` 로 레이아웃
(`pageWidthPx/HeightPx/pages/pagesDetail/lines/boxes/charPrDefs`)을 받아
렌더. 다른 창(app.mjs)과 **동일 엔드포인트**.

**핵심 조각** (`frontend/web_office_viewer/form_question_panel.mjs`):
- `loadCoordRenderer()` — `weboffice/coordinate_renderer.mjs` 동적 import
  (app.mjs 무접촉, coordinate_renderer/style_resolver 만 의존)
- `fetchLayout(rel)` — 레이아웃 수신(재시도 3회, REJECTED 는 재시도 안 함)
- `renderViewer()` — `.co-page` 렌더 → `fitPages()` 로 뷰어 폭에 균일 축소
  (가로 스크롤 제거, 페이지는 원본대로 끊겨 세로 스택) → `printFaithful()`
  로 페이지 경계 인쇄/PDF
- `roleByCellId(plan)` (순수·테스트) — paragraphId `par_t_sX_TTT_rR_cC_pN`
  → cellId `cell_t_sX_TTT_rR_cC` 유도(coordinate_layout._cell_id 와 동일
  네임스페이스). 민원인/관계자 칸을 레이아웃 박스 좌표에 반투명 틴트로 오버레이.

**백엔드 보조**:
- `editor_api_route.call_fill_plan` — `skipped`(관계자 칸 label·paragraphId·
  role·tableIndex·row·col) + `officeCount` 반환(예전엔 버려 패널이 못 봤다).
- `catalog_search.by_category` — `sourcePath` 노출(프론트가 hwpx-load/
  fill-plan 에 그대로 넘겨 서식 로드; 프로젝트 밖 절대경로는 제외).
- `editor_file_bridge.load_hwpx_for_editor` — 파싱 캐시 연결(hwpx-load /
  fill-plan 이중 파싱 제거).

**A4 관련 이력**: 초기엔 A4 한 장 래핑(210×297mm) + fit-to-page 로 갔으나,
대표님 지시("원본대로 끊어서 출력")로 **충실 좌표 렌더러로 전환**. A4 단일
페이지 접근은 폐기, 원본 페이지 분할이 최종안.

**검증(헤드리스, 프로덕션 모듈 직접 렌더)**:
| 서식 | .co-page | 역할칸 색칠 매칭 |
|------|:--:|:--:|
| 고압가스 수입신고서 | 1쪽 | 9/9 |
| 461_form(건보) | 17쪽 | 64/64 |
| 459_4(건보) | 49쪽 | 192/192 |

## 3. 관계자 오분류 수리 (a56c3c9)

**증상**: 질문 패널에서 일부 서식은 입력창(민원인 질문/자동채움)이 0개.

**실검증(18건)**: 신청칸 있는 서식은 정상(272·224·199·34·15·7행…).
입력행 0인 7건은 fill-plan 이 **실제로 0 반환** — 전부 `formKind=행정내부/
발급증서`. 그중 **오분류**: 선임보고서(사업장명·사업주·공사기간이 전부
관계자로 죽음)·감리보고서류. **정상**: 도로대장(대장기록)·인증서(발급증서).

**원인**: `form_input_schema._DOCTYPE_TO_KIND["보고통지"] = KIND_INTERNAL`.
`보고통지` 버킷이 **신청인 제출 보고서**와 **관공서 발급 통지·고지·독촉**을
한데 담아, 보고서까지 전 칸 office 로 죽였다.

**수리**(`resolve_form_kind`, 1파일, form_field_roles 무수정):
```python
if doc_type == T_NOTICE and _is_submitted_report(name):
    return FR.KIND_APPLICATION       # 이름에 '보고' → 신청인 제출 보고서
```
발급어(통지·통보·고지·독촉·결정)엔 '보고'가 없어 안전하게 갈림(통보 ⊅ 보고).
파일명 끝 시리얼(…보고서_32) 때문에 끝-고정(`보고서$`)은 실패 → **'보고'
포함**으로 판정.

**검증**: 정답셋 3셋 회귀 통과(하한 0.93/0.93/0.85 유지, 10 tests). 실측 —
보고서 8/8 민원신청 복원, 통지/통보/고지/독촉 12/12 office 유지(오flip 0),
선임보고서 입력행 0→19.

## 4. 지금 상태 (실측)

| 항목 | 값 |
|------|-----|
| 충실 뷰어 | 원본 페이지 분할 렌더 + 민원인/관계자 색, 헤드리스 3서식 PASS |
| 역할 분류 회귀 | 정답셋 3셋 통과(0.93/0.93/0.85 하한) |
| 관련 스위트 | node self-test + pytest 93건 통과 |
| 커밋 | 96683ff, a56c3c9 (게이트 PASS, PII/경로 유출 0) |
| push | **미실행** — §4 명시 승인 대기 |
| 서버 | 8791(질문 패널) 새 코드로 기동, 8773(병행 세션) 보존 |

## 5. 남은 것 (별도 공정)

- **현황표 구분**: docType=대장기록인 신청인 제출 현황표(인력보유현황표 등)는
  ledger 안전규칙(`test_ledger_keeps_fields_but_marks_office`)상 그대로
  office. 대장 안전선을 건드려야 해 미착수.
- OCR 실이미지 테스트, V1/V7 readback 검증기, 전체 파싱 캐시 빌드,
  세무 서식 수집 갭, char_pr_height 성능(잠금).
- push 승인(커밋 96683ff·a56c3c9 + 이전 미푸시분).

## 6. 안전 준수

- 원본 무수정(§4.3/§4.4) — 패널은 sandbox 사본에만 씀, AI/OCR 직접 호출 없음.
- 병행 세션 무접촉 — app.mjs·weboffice.html·coordinate_renderer 는 read-only.
- 커밋 스테이징 명시(§4) — 병행 세션 파일·자동생성 리포트 제외 검증 후 커밋.
