# WEB-OFFICE-BROWSER-VIEWER-PROTOTYPE-01 잔여 실패 2건 — 이슈 등록

Date: 2026-07-23

Process:
- 대표님 지시: "pytest 잔여 실패 2건은 '기존 결함'으로 방치하지 말고 이슈로 등록"

## 1. 대상

`tests/test_web_office_browser_viewer_prototype.py` (WEB-OFFICE-BROWSER-VIEWER-PROTOTYPE-01 계약 테스트) 중:

```
2 failed, 3 passed, 3 skipped
FAILED test_index_html_loads_payload_via_fetch_only
FAILED test_audit_returns_pass
```

## 2. 근본 원인 (실측 확인 완료)

이번 세션의 좌표/렌더링 작업과 무관한 **기존(선행) 아키텍처 드리프트**임을
git 이력으로 확인했다.

### 2.1 `test_index_html_loads_payload_via_fetch_only`

- 검증 대상: `frontend/web_office_viewer/index.html` 이 `payload.json` 을
  `fetch()` 로 직접 읽는 구(舊) 프로토타입 계약을 만족하는지.
- 실측: 현재 `index.html` 은 `editor_ui_bridge.mjs` 모듈을 통해
  `mountWebOfficeEditor()` 를 호출하는 모듈형 구조로 이미 교체되어 있다
  (`fetch("./payload.json")` 문자열이 더 이상 존재하지 않음).
- 이력: 테스트 파일은 저장소 분리 초기 커밋(`e04d325`) 이후 무수정.
  `index.html` 은 그 뒤 `9a3a15d Serve web office editor UI bridge`
  (모듈형 뷰어/에디터 전환, 상위 이력의 "블록 읽기순서 + 표-포맷 정밀도 +
  모듈형 web office 뷰어/에디터" 작업)에서 구조가 바뀌었다.
- 결론: **테스트가 구(舊) 프로토타입 계약을 그대로 검증하고 있어, 신
  아키텍처 전환 시 함께 갱신되지 않은 것** — 코드 결함이 아니라 테스트
  노후화(stale contract test).

### 2.2 `test_audit_returns_pass`

- 검증 대상: `scripts/ops/audit_web_office_browser_viewer_prototype.py`
  의 `audit()` 가 `PASS` 를 반환하는지.
- 실측 실패 사유: `{"verdict": "FAIL", "reason": "need ≥1 fixture, got 0"}`
- 원인: `audit()` 이 로컬 `data/recognition_corpus/corpus.sqlite3` 에서
  `fillable_form` 분류의 30~120KB 문서를 최대 3건 조회해 fixture 로
  쓰는데, 이 실행 환경에 그 코퍼스 DB 가 없거나(또는 조건에 맞는 행이
  없어) 0건이 조회된다.
- 참고: 같은 파일의 다른 3개 테스트는 `@pytest.mark.skipif(len(FIXTURES)
  < 1, ...)` 로 이 조건을 이미 가드하는데, `test_audit_returns_pass` 만
  그 가드가 빠져 있어 fixture 부재 시 SKIP 이 아니라 FAIL 로 떨어진다.
- 결론: **로컬 실행 환경의 데이터 의존성 문제** (코퍼스 DB 미존재) +
  **테스트 자체의 가드 누락**(같은 파일 내 다른 테스트와 일관성 없음)
  두 가지가 겹친 것.

## 3. 이번 세션 작업과의 관계

이번 세션에서 수정한 파일(`coordinate_layout.py` 컬럼-리셋 구분,
이미지-흐름 반영, 세로쓰기 되돌림 등)은 이 두 테스트가 검사하는 대상
(`index.html` 모듈 구조, `corpus.sqlite3` 존재 여부)과 무관하다.
두 실패는 이번 세션 이전부터 존재했다(회귀 아님).

## 4. 제안 조치 (미착수 — 별도 승인 필요)

| 실패 | 제안 | 비고 |
|---|---|---|
| `test_index_html_loads_payload_via_fetch_only` | 모듈형 구조(`editor_ui_bridge.mjs`)에 맞게 계약을 재작성하거나, 구 프로토타입 테스트를 폐기 | 프로토타입 계약 자체를 다시 정의해야 하므로 스코프 판단 필요 |
| `test_audit_returns_pass` | `test_audit_returns_pass` 에도 다른 3개 테스트와 동일한 `skipif(len(FIXTURES) < 1)` 가드 추가 | 로컬 실행 환경 일관성 문제이므로 저위험 수정으로 보이나, "기능 금지선" 밖 여부 확인 후 진행 |

이 문서는 실패를 등록·설명하는 것으로 그친다. 수정은 대표님 승인 후
별도 작업으로 진행한다.
