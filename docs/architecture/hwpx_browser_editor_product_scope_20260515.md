# HWPX Browser Editor — Product Scope

**버전:** P11A  
**날짜:** 2026-05-15  
**상태:** CONFIRMED

---

## 1. 제품 정의

HWPX 브라우저 편집기는 서버 사이드 HWPX 엔진을 브라우저 UI로 조작하는 제품이다.
브라우저는 **command(편집 의도)**만 생성하고, HWPX XML/ZIP 직접 조작은 금지한다.
서버 usecase/engine이 HWPX 수정·검증·저장을 전담한다.

---

## 2. 핵심 원칙

| 원칙 | 내용 |
|------|------|
| 브라우저 역할 | command 생성 + 결과 표시만 |
| 서버 역할 | HWPX 수정, 검증, 저장, 다운로드 |
| HWPX XML 접근 | 서버만 허용, 브라우저 직접 접근 금지 |
| HWP/Hancom | 서버·브라우저 모두 직접 실행 금지 |
| 외부 브라우저 자동 실행 | 금지 |
| endpoint path 변경 | 금지 |
| 기존 gate 동작 변경 | 금지 |

---

## 3. 1차 지원 기능 (MVP)

| 기능 | 설명 | 서버 endpoint |
|------|------|---------------|
| HWPX 업로드 | 파일 업로드 + 구조 파싱 | POST /parse-hwpx |
| 문서 구조 보기 | 블록/단락/표 트리 렌더링 | POST /parse-hwpx |
| 문단 텍스트 편집 | paragraph 텍스트 수정 command | POST /api/hwpx/editor (apply) |
| 표 셀 텍스트 편집 | table cell 수정 command | POST /api/hwpx/editor (apply) |
| 행 추가/삭제 | table row add/remove command | POST /api/hwpx/editor (apply) |
| placeholder 치환 | 키-값 매핑 기반 치환 | POST /api/hwpx/editor (apply) |
| 저장/다운로드 | 서버 저장 + 파일 다운로드 | POST /api/hwpx/editor (apply) |
| package validation | ZIP 구조 + XML 스키마 검증 | usecase 내부 |
| roundtrip validation | 편집 전후 텍스트 동일성 검증 | usecase 내부 |

---

## 4. 2차 지원 기능 (Post-MVP)

| 기능 | 설명 |
|------|------|
| 이미지 교체 | 기존 이미지 자산 교체 |
| 차트 삽입 | schedule_graph command 활용 |
| 스타일 편집 | 폰트/정렬/색상 스타일 변경 |
| 공정표 builder 연결 | schedule_graph + Excel binding |
| 안전서류 builder 연결 | 감리/검측 문서 template 연결 |
| Excel/내역서 분석 결과 binding | workbook parse 결과 → HWPX fill_cells |

---

## 5. 제외 기능 (영구 제외)

| 기능 | 제외 이유 |
|------|-----------|
| .hwp 직접 브라우저 편집 | HWP binary format 브라우저 지원 불가 |
| Hancom 자동 실행 | 서버 환경 의존성, gate 금지 |
| 인증서/OTP/전자서명 | ExecutionLocationGate: USER_PRESENT_REQUIRED |
| 외부 사이트 제출/투찰 | 외부 브라우저 자동 실행 금지 |
| 서버에서 HWP 변환 직접 실행 | local_worker 의존, 서버 gate 통과 불가 |

---

## 6. 기존 구조 활용 계획

| 현재 컴포넌트 | P11A 활용 |
|-------------|-----------|
| `HwpxEditorApiHandler` | apply/create operation 그대로 사용 |
| `HwpxUploadParseUseCase` | 업로드 게이트 그대로 사용 |
| `HwpxDownloadExportUseCase` | 다운로드/artifact ref 그대로 사용 |
| `FileTypeGate` | .hwpx 허용 판단 그대로 사용 |
| `UploadSecurityGate` | 파일 크기/이름 검증 그대로 사용 |
| `OutputArtifactGate` | 출력 경로 가드 그대로 사용 |
| `hwpx_edit_tool.py` | 편집 실행 엔진 그대로 사용 |
| `hwpx_server_ops.py` | fill_cells, schedule_graph 그대로 사용 |

---

## 7. 미구현 컴포넌트 (신규 개발 필요)

| 컴포넌트 | 레이어 | 설명 |
|---------|--------|------|
| `HwpxEditorCommandUseCase` | usecase | command 검증 + edit plan 생성 |
| `HwpxEditorSessionUseCase` | usecase | 편집 세션 상태 관리 |
| `HwpxEditorValidationGate` | gate | command 유효성 검사 |
| browser editor UI | frontend (static HTML/JS) | 브라우저 편집기 페이지 |
| `GET /hwpx-editor` (확장) | http | 현재 존재, UI 기능 확장 필요 |

---

## 정책

- `no_endpoint_path_change: true`
- `no_existing_gate_change: true`
- `no_browser_hwpx_direct_access: true`
- `no_hancom_auto_run: true`
- `push_forbidden: true`
- `db_write_forbidden: true`
