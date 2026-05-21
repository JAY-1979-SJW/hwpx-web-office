# hwpx-web-office 작업 표준시방서 (CLAUDE.md)

이 저장소는 **HWPX 편집 브라우저** 공정 전용이다.
Excel·AI fill·기타 도메인은 이 저장소 범위 밖이다.

---

## 1. 저장소 범위 (SCOPE)

| 포함 (IN_SCOPE) | 제외 (OUT_OF_SCOPE) |
|----------------|-------------------|
| `frontend/web_office_viewer/` | Excel 관련 파일 일체 |
| `scripts/hwpx/web_office/` | `scripts/excel/` |
| `tests/test_web_office_*.py` | AI 자동 입력 (§10) |
| `scripts/ops/audit_web_office_*.py` | 서버 배포 자동화 |
| `docs/architecture/web_office_*.md` | price-classifier 등 타 도메인 |

---

## 2. 건축 공정 방식 (§1 of parent CLAUDE.md 계승)

이 프로젝트의 개발 작업은 건축 현장 공정과 동일한 용어 체계를 사용한다.

| 건축 용어 | 개발 대응 |
|-----------|----------|
| 건축 현장 | 코드 개발 |
| 동 | 도메인 |
| 세대 | 파일 |
| 감리검사 | 테스트 / audit |
| 공정 완료 | commit |
| 준공 반영 | push |

---

## 3. 현재창 보고 강제 규칙 (MANDATORY)

기본 보고는 현재 채팅창에 직접 출력한다. `docs/reports/*.md` 파일 생성은
사용자가 명시적으로 요청한 경우에만 허용한다.

### 건축공사 비유 강제 (§4-A 계승)

모든 작업 보고에 건축공사 비유를 반드시 포함한다.

---

## 4. 안전 금지선 (ABSOLUTE PROHIBITIONS)

### Git 금지
- `git add .` — 전체 스테이징 금지. **반드시 파일명 명시 스테이징**
- `git clean` / `git reset --hard` / `git checkout -- .` 금지
- commit 전 `git diff --cached --name-only` 검증 필수 — Excel/타 도메인 파일 있으면 STOP

### 기능 금지
- header/footer paragraph 편집 활성화 금지
- image/shape/media 편집 구현 금지
- table structure edit 구현 금지
- 신규 charPr 생성 금지
- `header.xml` mutation 금지
- Excel 파일 수정 금지
- push 전 사용자 명시 승인 필수

### 보안/개인정보 금지
- `secret / token / password / env` 값 출력 금지
- 결제 / 송금 / 전자서명 / 제출 자동 실행 금지

---

## 5. 공용창고 규칙

| 창고 경로 | 역할 |
|-----------|------|
| `data/audit/` | 감사 기록, append-only |
| `logs/change_history.jsonl` | 커밋 이력, KNOWN_HOLD |

---

## 6. 건축 시공 표준 절차 (계승)

```
① 대지 조사 → ② 시공 계획서 → ③ 대표님 승인 →
④ 시공 → ⑤ 감리검사 → ⑥ 준공검사 (audit) →
⑦ 회귀 → ⑧ commit + 현재창 보고
```

- 기능 FAIL 시 commit 금지
- commit 전 staged 파일 검증 필수 (HWPX 범위 외 파일 있으면 STOP)

---

## 7. AI 없이 자동 입력 금지 (§10 계승)

AI inject 없이 자동 입력 진행 금지.

---

*분리 일: 2026-05-22*
*원본 저장소: office-analysis-engine (33. office-analysis-engine)*
