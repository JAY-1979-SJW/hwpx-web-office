# HWPX Editor App F0 Foundation Architecture Lock

**작업명:** HWPX-EDITOR-APP-F0-FOUNDATION-ARCHITECTURE-LOCK
**날짜:** 2026-05-15
**기준선 HEAD:** 9c081f2 (P14B-1 완료 커밋)
**최종 판정:** PASS

---

## 작업 내용

Foundation Architecture Lock (F0) 단계. 코드 수정 없음. 문서 작성만.

---

## 수정 파일

| 파일 | 변경 내용 |
|------|-----------|
| `docs/architecture/hwpx_editor_app_foundation_20260515.md` | 신규 생성 — 앱 전체 foundation 아키텍처 |
| `docs/architecture/hwpx_editor_operating_rules_20260515.md` | 버전 F0 갱신, Foundation 문서 참조 추가 |
| `docs/reports/hwpx_editor_app_f0_foundation_architecture_lock_20260515.md` | 신규 생성 — 이 파일 |

---

## Foundation 문서 구성

`docs/architecture/hwpx_editor_app_foundation_20260515.md` 12개 섹션:

| 섹션 | 내용 |
|------|------|
| 1. 앱 목적 | 편집 대상, 핵심 목적, 범위 밖 항목 명시 |
| 2. 앱 Boundary | UI/API/Command/Artifact/Storage/Security/Audit/Deployment 8개 영역 |
| 3. 레이어 구조 | 12개 레이어 다이어그램 + 의존성 방향 규칙 |
| 4. 권한/역할 모델 | F0 미구현 명시, 목표 4개 역할(viewer/editor/approver/admin), 현재 보안 게이트 |
| 5. Workflow State Machine | 15개 상태 + 전이 조건 표 |
| 6. Artifact Storage Policy | F0 정책, 발급 경로, 참조 정책, F1 목표 |
| 7. Command Policy | 허용 명령 3개, Request/Response 계약, 금지 정책 |
| 8. Gate 구조 | 5개 구현 Gate + 34개 architecture gate 검사 항목 |
| 9. API Route Boundary | 16개 엔드포인트 표, /parse-hwpx vs /api/hwpx/parse 분리 |
| 10. Audit/Event Log Policy | F0 현황, F1 목표, 현재 감사 대상 |
| 11. UI Navigation Skeleton | Upload → Parse → Command 루프 흐름도 |
| 12. Test Plan | 현재 커버리지 표, 테스트 추가 기준, F1 목표 |

---

## 운영규칙 갱신 내용

`docs/architecture/hwpx_editor_operating_rules_20260515.md`:
- 버전: P14B-1 → F0
- Foundation 문서 참조 헤더 추가
- 관련 문서 섹션에 foundation 문서 링크 추가

---

## 이번 단계에서 하지 않은 작업

- ApplyEngine 연결 없음
- PythonScriptBridge 연결 없음
- dryRun=false 허용 없음
- Artifact 영속화 없음
- 인증/인가 구현 없음
- DB/schema 변경 없음
- 서버 배포/재시작 없음
- push 없음
- 코드 수정 없음

---

## 보안 확인

- 신규 문서 내 credential/secret/token/password 노출 없음
- raw path 노출 없음

---

## Git

- 기준선: 9c081f2
- 추가 파일: 3개 (docs/architecture, docs/reports)
- push 미수행

---

## 다음 단계 (F1 이후)

- ArtifactRegistry 파일/DB 기반 영속화
- ApplyEngine 실제 연결 (dryRun=false 허용)
- outputArtifact 생성 및 다운로드
- 인증/인가 레이어 구현 (SessionManager, RoleGate)
- Audit/Event 로그 구현
- UI 인라인 편집 + diff 뷰
