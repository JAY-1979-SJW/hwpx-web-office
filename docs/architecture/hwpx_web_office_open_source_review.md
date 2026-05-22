# HWPX Web Office Editor — 오픈소스 후보 리뷰

> 공정명: HWPX-WEB-OFFICE-EDITOR-DEEP-ARCHITECTURE-01 (별책)
> 작성일: 2026-05-20
> 기준 HEAD: `99a636f`
> 본 문서는 설계서의 §16 라이선스 요약을 자재별 상세로 확장한다.
> 모든 채택 / 보류 / 배제 판단은 **현 시점 조사 기반**이며,
> core dependency 로 확정하려면 별도 §11-1 공정과 대표님 명시 승인이
> 필요하다.

---

## 1. 평가 기준

| 기준 | 설명 |
|------|------|
| 라이선스 | MIT / Apache-2.0 / BSD = 안전. LGPL = 조건부. GPL/AGPL = 강전염 → 본 단지 core dep 불가 |
| 활성도 | 최근 12 개월 commit / release |
| 한글 지원 | HWPX 의 한글·세로조판 적합도 |
| 자재 정합 | 본 단지의 자재 (parser, edit_tool, verify7) 와의 결합도 |
| 결정 | 채택 후보 / 보류 / 배제 |

---

## 2. HWPX read / write

| 후보 | 라이선스 | 활성도 | 한글 지원 | 결정 |
|------|---------|--------|-----------|------|
| **자체 자재** (`scripts/hwpx/*`) | 본 단지 정책 | 본 단지 commit 기준 활성 | 완전 | **채택** (확정) |
| python-hwpx | MIT (공개 시점 기준) | 외부 | 부분 | **배제** (자체 자재가 회귀 잠금 완료) |
| Hancom OpenAPI / Hancom SDK | 상용 / 비공개 | 상용 | 완전 | **배제** (§9 ANTHROPIC_API_KEY·외부 의존 금지 흐름과 동일) |

**결정 근거**: 자체 자재가 V1~V7 회귀로 잠금됨. 외부 라이브러리 신규 의존
도입은 LOCK_01 같은 회귀 자산을 무력화할 위험.

---

## 3. Browser grid / Table editor

| 후보 | 라이선스 | 활성도 | 결정 |
|------|---------|--------|------|
| **AG Grid Community** | MIT | 매우 활성 | **채택 후보** |
| **Handsontable Community** | Non-commercial (구) → 현 BSL/CE 검토 필요 | 활성 | **보류** (라이선스 재확인) |
| **Tabulator** | MIT | 활성 | **채택 후보** |
| **Glide Data Grid** | MIT | 활성 (canvas) | **보류** (대규모 표 우수, HWPX 병합 셀 매핑 검증 필요) |
| **TanStack Table (헤드리스)** | MIT | 매우 활성 | **채택 후보** (렌더 자유도 ↑) |

**잠정 채택 후보**: TanStack Table (헤드리스) + 자체 셀 렌더. 병합 셀 ·
visual coord 변환을 우리 코드로 통제하기 위함.

**보류 사유**: Handsontable 의 라이선스가 자주 변경됨 — 채택 확정 전 현 시점
라이선스 텍스트 재확인 필수 (시방서 "라이선스 불명확한 오픈소스를 core
dependency 로 확정 금지" 조항).

---

## 4. Document renderer (paragraph / inline)

| 후보 | 라이선스 | 활성도 | 결정 |
|------|---------|--------|------|
| **자체 SVG / DOM** | 본 단지 정책 | — | **채택** (확정 후보) |
| **SlateJS** | MIT | 활성 | **보류** (run 단위 모델은 적합, 단 자체 charPrIDRef 관리와 충돌 검토) |
| **ProseMirror** | MIT | 매우 활성 | **보류** (스키마 정의 비용↑, HWPX run 매핑 PoC 필요) |
| **TinyMCE / CKEditor 5** | LGPL / GPL+상용 듀얼 | 활성 | **배제** (라이선스 강전염 또는 상용 의존) |
| **Quill** | BSD-3 | 활성 | **보류** (Delta 모델이 단순, 표·HWPX 객체 매핑은 어려움) |

**잠정 채택**: 자체 SVG/DOM 렌더 + (Phase 3 시점에서) ProseMirror 의 model
PoC 평가. ProseMirror 채택 시 별도 공정으로 ADR 작성.

---

## 5. PDF output

| 후보 | 라이선스 | 활성도 | 결정 |
|------|---------|--------|------|
| **jsPDF** | MIT | 활성 | **보류** (한글 폰트 임베드 비용↑) |
| **pdfmake** | MIT | 활성 | **보류** (동일) |
| **WeasyPrint** | BSD-3 | 활성 (Python) | **채택 후보** (서버 사이드) |
| **wkhtmltopdf** | LGPL-3 | 정체 | **배제** (정체 + LGPL) |
| **Puppeteer / headless Chrome** | Apache-2.0 | 매우 활성 | **채택 후보** (HTML → PDF) |
| **한컴 한글 render** | 상용 | — | **별도** (서버 자재 검토) |

**잠정**: WeasyPrint (서버) 또는 Puppeteer 중 PoC 후 결정. 한컴 경로는 §1-2
비목표.

---

## 6. State / Command history

| 후보 | 라이선스 | 활성도 | 결정 |
|------|---------|--------|------|
| **Immer.js** | MIT | 매우 활성 | **채택 후보** (불변 트리 업데이트) |
| **Zustand** | MIT | 활성 | **채택 후보** (client state) |
| **Redux + Redux Toolkit** | MIT | 활성 | **보류** (오버엔지니어링 위험) |
| **Yjs / Automerge** (CRDT) | MIT | 활성 | **배제** (multi-collab 비목표, §1-2) |

**잠정 채택**: Immer + 자체 EditCommand 스택 (forward/inverse). 클라이언트
state 는 Zustand 검토.

---

## 7. XLSX 출력

| 후보 | 라이선스 | 활성도 | 결정 |
|------|---------|--------|------|
| **Apache POI** | Apache-2.0 | 매우 활성 | **채택** (확정 — §9 단지 정책) |
| **SheetJS / xlsx** | Apache-2.0 (커뮤니티) / Pro 상용 | 활성 | **배제** (POI 가 단지 표준) |
| **openpyxl** | MIT | 활성 | **배제** (§9 사용 금지) |

---

## 8. AI proposal (참고)

본 단지는 §10 정책으로 AI 회로가 별도 게이트 안에서만 동작. Web Office
편집기에서 사용하는 AI 인터페이스는:

- 운영: Claude Code CLI (Haiku) — `ENABLE_LIVE_HAIKU=1` (§10)
- 외부 손님 API: `ai_proposal_fn` callable inject
- 테스트: deterministic fixture (`tests/fixtures/ai_proposal_client_fixture.py`)

ANTHROPIC_API_KEY 직접 호출 금지 (§9). 외부 LLM SDK 신규 의존 도입은 본
설계 채택 후 별도 공정.

---

## 9. 종합 채택/보류/배제 표

| 영역 | 1순위 | 2순위 | 배제 |
|------|-------|-------|------|
| HWPX r/w | **자체** ✅ | — | python-hwpx, Hancom SDK |
| Grid | **TanStack Table** | AG Grid Community | Handsontable (보류) |
| Renderer | **자체 SVG/DOM** | (Phase 3) ProseMirror | TinyMCE, CKEditor 5 |
| PDF | **WeasyPrint** | Puppeteer | wkhtmltopdf |
| State | **Immer + 자체 stack** | Zustand | Redux, CRDT |
| XLSX | **Apache POI** ✅ | — | openpyxl, SheetJS Pro |
| AI | **Claude Code CLI Haiku** ✅ | inject callable | ANTHROPIC_API_KEY 직접 |

✅ = 확정. 그 외는 채택 후보 — 본 설계 채택 후 별도 §11-1 공정으로 ADR
작성 및 대표님 승인 필요.

---

## 10. 라이선스 위험 종합

- **배제된 항목**: GPL / AGPL / 상용 듀얼 라이선스
- **보류 사유 분류**:
  - 라이선스 변경 이력이 잦은 항목 (Handsontable, SheetJS) → 도입 시 현
    시점 라이선스 텍스트 보관 + 정기 재확인
  - PoC 미수행 항목 (ProseMirror, Glide) → Phase 3+ 시점에 별도 ADR
- **확정 항목 (자체 + Apache POI + Claude Code CLI)** 은 단지 정책과
  정합. 외부 신규 core dep 는 본 공정 범위 밖.

---

*생성: HWPX-WEB-OFFICE-EDITOR-DEEP-ARCHITECTURE-01 별책 (2026-05-20)*
