# OFFICE-ANALYSIS-P8D-HWPX-UPLOAD-HANDLER-BASELINE-SPLIT-AUDIT

## 1. 기준선

- 기준 HEAD: `3aa5c19d0bdb66a334fad366449d3cc4e454585a`
- branch: `main`
- hook 경로: `scripts/hooks`
- 기준 dirty: tracked 35건, staged 0건, untracked status entries 120건, deleted 0건
- push: 수행하지 않음
- working tree known-prefix quoted literal: 0건

## 2. HwpxUploadHandler 책임 구조 감사

대상: `src/main/java/com/haehan/engine/http/HwpxUploadHandler.java`

- 상태: tracked dirty
- 현재 줄 수: 2895
- 변경 규모: 2776 insertions / 327 deletions
- endpoint:
  - `/hwpx-editor`
  - `/hwpx-upload`
- 책임 후보:
  - HTML page response
  - browser HWPX editor UI
  - `.hwpx` upload/parse UI flow
  - `.hwp` upload/conversion UI flow
  - `/api/hwpx/parse` 호출
  - `/api/hwpx/editor` 호출
  - `/convert-hwp-to-hwpx` 호출
  - download blob/raw report/draft JSON flow
  - filename sanitize 후보
  - inspection/live/dry-run report export 후보

## 3. Dirty Hunk 분류

P8D audit 결과, handler 본문은 다음 이유로 이번 단계 커밋 대상이 아니다.

- tracked dirty 대형 파일
- 500줄 이상 대형 handler
- 변경 규모가 매우 큼
- upload, conversion, editor, download, report 책임이 같은 파일에 혼재
- gate hunk만 안전하게 분리하기 전 별도 기준선 전략 필요

따라서 P8D에서는 `HwpxUploadHandler.java` 본문을 수정/커밋하지 않았다.

## 4. Gate 연결 가능 위치

| Gate | 연결 후보 |
|---|---|
| `FileTypeGate` | file input accept, `.hwpx`/`.hwp` 분기, `selectFile`/parse flow |
| `UploadSecurityGate` | filename header, `asciiSafeFileName`, upload size/filename 검증 후보 |
| `ExecutionLocationGate` | `.hwp` 감지, `/convert-hwp-to-hwpx` 호출, `X-Conversion-Gate` 처리 |
| `OutputArtifactGate` | `downloadBlob`, `downloadRawBlob`, draft/report export, `URL.createObjectURL` |

권장 다음 hunk:

1. `file_type_upload_gate`
2. `hwp_conversion_execution_gate`
3. `download_output_artifact_gate`

## 5. P8D Audit 결과

- 신규 스크립트: `scripts/audit_hwpx_upload_handler_split_readiness.py`
- 신규 테스트: `tests/test_hwpx_upload_handler_split_readiness.py`
- audit status: WARN
- findings: 9건
  - tracked dirty large handler
  - large handler
  - dirty hunk too large for direct commit
  - HWP conversion UI flow
  - `FileTypeGate` 직접 연결 없음
  - `UploadSecurityGate` 직접 연결 없음
  - `ExecutionLocationGate` 직접 연결 없음
  - `OutputArtifactGate` 직접 연결 없음
  - raw path candidate

## 6. 테스트 결과

| 항목 | 결과 |
|---|---|
| `python scripts/audit_hwpx_upload_handler_split_readiness.py` | WARN, 실행 PASS |
| `python -m pytest tests/test_hwpx_upload_handler_split_readiness.py -q` | PASS |
| `python scripts/audit_handler_gate_runtime_connections.py` | WARN, 실행 PASS |
| P1~P8C audit tests | PASS |
| `.\gradlew.bat tasks` | PASS |
| `.\gradlew.bat test` | PASS |
| working tree known-prefix quoted literal scan | 0건 |

## 7. 남은 WARN

1. `HwpxUploadHandler.java`는 아직 tracked dirty 대형 파일
2. gate 직접 연결은 아직 없음
3. `.hwp` conversion UI flow는 `ExecutionLocationGate` 기준으로 분리 필요
4. download/report export flow는 `OutputArtifactGate` 기준으로 분리 필요
5. HTML/UI와 API 호출 orchestration 분리는 P9 이후 필요

## 8. 수행하지 않은 작업 확인

- `HwpxUploadHandler.java` 본문 수정/커밋 없음
- 기존 dirty/untracked 삭제 없음
- git clean/reset/restore/checkout/stash 없음
- pull/push 없음
- remote/upstream 변경 없음
- DB write/schema 변경 없음
- 외부 브라우저 실행 없음
- secret 값 출력 없음
- endpoint path 변경 없음
- API 응답 key 변경 없음
- HWP/Hancom 직접 실행 추가 없음

## 9. 다음 단계

**A안. P8D 감사 완료.**

다음 단계는 P8E로 `HwpxUploadHandler`의 `file_type_upload_gate` hunk만 분리 가능한지 확인하는 것이 적절하다. 본문 커밋 전에는 반드시 hunk 단위 분리 가능성을 재검증해야 한다.

## 10. 최종 판정

WARN
