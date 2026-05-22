# OFFICE-ANALYSIS-P8E-HWPX-UPLOAD-FILETYPE-UPLOAD-GATE-HUNK

## 1. 기준선

- 기준 HEAD: `3681cc2fd684302b79e302d68081051c263b2ffe`
- branch: `main`
- hook 경로: `scripts/hooks`
- 기준 dirty: tracked 35건, staged 0건, untracked status entries 121건, deleted 0건
- push: 수행하지 않음
- working tree known-prefix quoted literal: 0건

## 2. P8E hunk 삽입 위치 재확인

대상: `src/main/java/com/haehan/engine/http/HwpxUploadHandler.java`

- 현재 상태: tracked dirty
- HEAD 기준 줄 수: 385
- working tree 줄 수: 2895
- 변경 규모: 2776 insertions / 327 deletions
- working tree upload 후보:
  - file input accept: `.hwpx`, `.hwp`
  - `.hwp` 감지 함수: `isHwpFile`
  - conversion 호출: `/convert-hwp-to-hwpx`
  - filename header: `X-Filename`, `X-Filename-Encoded`
  - filename sanitize 후보: `asciiSafeFileName`
  - parse 호출: `/api/hwpx/parse`

## 3. P8E hunk 분리 가능성

판정: **분리 불가 / 커밋 보류**

이유:

- 실제 P8E 후보 flow는 working tree의 대형 dirty 본문에만 존재한다.
- HEAD 기준 `HwpxUploadHandler`는 단순 `.hwpx` 업로드 page라 `.hwp` conversion UI flow가 없다.
- P8E hunk를 HEAD 기준으로 억지 staging하면 현재 working tree runtime과 불일치할 수 있다.
- `git add HwpxUploadHandler.java` 전체는 기존 대형 dirty 전체를 포함하므로 금지 조건에 해당한다.

따라서 이번 단계에서는 `HwpxUploadHandler.java` 본문을 수정/커밋하지 않았다.

## 4. Gate 상태

| Gate | P8E 결과 |
|---|---|
| `FileTypeGate` | 연결 보류 |
| `UploadSecurityGate` | 연결 보류 |
| `.hwpx` 처리 | 기존 flow 유지, gate hunk 미적용 |
| `.hwp` 처리 | 기존 dirty flow 유지, gate hunk 미적용 |
| unknown extension | gate block hunk 미적용 |
| path traversal | gate block hunk 미적용 |
| filename | 기존 sanitize 후보만 확인 |
| size | gate hunk 미적용 |

## 5. P8E Audit 결과

- 신규 스크립트: `scripts/audit_hwpx_upload_filetype_gate_hunk.py`
- 신규 테스트: `tests/test_hwpx_upload_filetype_gate_hunk.py`
- audit status: WARN
- hunk split possible: false
- findings:
  - tracked dirty handler
  - dirty body too large
  - `FileTypeGate` 직접 연결 없음
  - `UploadSecurityGate` 직접 연결 없음
  - P8E hunk commit deferred

## 6. 테스트 결과

| 항목 | 결과 |
|---|---|
| `python scripts/audit_hwpx_upload_filetype_gate_hunk.py` | WARN, 실행 PASS |
| `python -m pytest tests/test_hwpx_upload_filetype_gate_hunk.py -q` | PASS |
| `python scripts/audit_hwpx_upload_handler_split_readiness.py` | WARN, 실행 PASS |
| `python -m pytest tests/test_hwpx_upload_handler_split_readiness.py -q` | PASS |
| `python scripts/audit_handler_gate_runtime_connections.py` | WARN, 실행 PASS |
| P1~P8D audit tests | PASS |
| `.\gradlew.bat tasks` | PASS |
| `.\gradlew.bat test` | PASS |
| working tree known-prefix quoted literal scan | 0건 |

## 7. 남은 WARN/FAIL

WARN:

1. `HwpxUploadHandler.java` 본문은 여전히 tracked dirty 대형 파일
2. `FileTypeGate` / `UploadSecurityGate` 직접 연결 없음
3. P8E hunk가 기존 dirty와 섞여 커밋 불가
4. `.hwp` conversion flow는 후속 `ExecutionLocationGate` 단계 전에도 기준선 분리 필요

FAIL:

- 없음

## 8. 수행하지 않은 작업 확인

- `HwpxUploadHandler.java` 본문 수정/커밋 없음
- 기존 dirty/untracked 삭제 없음
- git clean/reset/restore/checkout/stash 없음
- pull/push 없음
- remote/upstream 변경 없음
- DB write/schema 변경 없음
- 외부 브라우저 실행 없음
- secret 값 출력 없음
- `ExecutionLocationGate` hunk 없음
- `OutputArtifactGate` hunk 없음
- HWPX engine 대형 변경 없음
- local-gui/Dockerfile 커밋 없음
- endpoint path 변경 없음
- API 응답 key 변경 없음

## 9. 다음 단계

**B안.**

P8E hunk가 기존 dirty와 섞여 handler 커밋이 불가하다. 다음 단계는 `HwpxUploadHandler` 기준선 분리 전략이다.

권장 순서:

1. 현재 working tree의 `HwpxUploadHandler.java` 전체 의도를 별도 기준선으로 검증
2. 기존 대형 dirty를 기능 단위로 분리할 수 있는지 판단
3. file type/upload gate hunk를 clean 기준으로 재적용

## 10. 최종 판정

WARN
