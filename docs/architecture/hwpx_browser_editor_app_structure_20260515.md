# HWPX Browser Editor App Structure

**버전:** P13A  
**날짜:** 2026-05-15  
**상태:** CONFIRMED

---

## 1. 전체 레이어 구조

```
┌─────────────────────────────────────────────────┐
│  UI Layer (Browser)                              │
│  HwpxUploadPageScripts / Styles / View           │
│  → command JSON 생성 / result 표시               │
│  금지: XML/ZIP 직접 조작, raw path, engine 호출  │
└────────────────┬────────────────────────────────┘
                 │ HTTP POST (JSON / multipart)
┌────────────────▼────────────────────────────────┐
│  Web API Handler Layer                           │
│  HwpxEditorApiHandler / HwpxUploadHandler /      │
│  ParseHwpxHandler / ConvertHwpToHwpxHandler 등   │
│  → HTTP request/response 변환, 분기 routing      │
│  금지: engine 직접 조작, business rule 구현       │
└───┬──────────────────────────┬──────────────────┘
    │ command dispatch          │ upload/parse flow
┌───▼──────────────┐   ┌───────▼──────────────────┐
│ UseCase Layer    │   │ UseCase Layer             │
│ HwpxEditorCmd   │   │ HwpxUploadParseUseCase    │
│ UseCase          │   │ HwpxDownloadExportUseCase │
│ → command 흐름  │   │ → parse/download 흐름     │
└───┬──────────────┘   └───────────────────────────┘
    │
┌───▼──────────────────────────────────────────────┐
│  Validation / Gate Layer                         │
│  HwpxEditorValidationGate                        │
│  FileTypeGate / UploadSecurityGate               │
│  ExecutionLocationGate / OutputArtifactGate      │
│  → command 허용 여부, raw path, secret 차단      │
│  금지: 실제 HWPX 수정, side effect               │
└───┬──────────────────────────────────────────────┘
    │ (P14에서 연결)
┌───▼──────────────────────────────────────────────┐
│  Engine Adapter Layer (P14 이후 연결)            │
│  PythonScriptBridge / HwpToHwpxCliBridge         │
│  → HWPX engine 호출 감싸는 adapter               │
│  금지: UI/API 직접 의존, raw path 외부 노출      │
└───┬──────────────────────────────────────────────┘
    │
┌───▼──────────────────────────────────────────────┐
│  Infra / File Storage Layer                      │
│  archiveOutput / Files.* / reports/hwpx-editor   │
│  → artifact 저장, export, temp file              │
│  금지: raw path UI 노출, secret 로그              │
└──────────────────────────────────────────────────┘
```

---

## 2. 레이어별 파일 목록

### UI Layer
| 파일 | 역할 |
|------|------|
| HwpxUploadPageScripts.java (SCRIPT_1~5) | JS 로직: state, gate policy, command dispatch |
| HwpxUploadPageStyles.java | CSS + HTML 구조 |
| HwpxUploadPageView.java | 페이지 조립 |
| HwpxUploadPageGatePolicy.java | 브라우저 gate policy JSON 생성 |

### Web API Handler Layer
| 파일 | 역할 |
|------|------|
| HwpxEditorApiHandler.java | command dispatch + upload/archive/download |
| HwpxUploadHandler.java | 파일 업로드 (parse 전) |
| ParseHwpxHandler.java | HWPX parse 실행 |
| ConvertHwpToHwpxHandler.java | HWP → HWPX 변환 |
| EngineHttpServer.java | endpoint 등록 |

### UseCase Layer
| 파일 | 역할 |
|------|------|
| HwpxEditorCommandUseCase.java | command 실행 흐름 (validate → dry/apply) |
| HwpxEditorCommandResult.java | command 실행 결과 모델 |
| HwpxUploadParseUseCase.java | 파일 업로드 → parse 흐름 |
| HwpxDownloadExportUseCase.java | download/export 흐름 |
| HwpxUploadParseResult.java | parse 결과 모델 |
| HwpxDownloadExportResult.java | download 결과 모델 |

### Validation / Gate Layer
| 파일 | 역할 |
|------|------|
| HwpxEditorValidationGate.java | command schema, raw path, secret, allowed type 검증 |
| HwpxEditorValidationResult.java | validation 결과 모델 |
| FileTypeGate.java | 파일 확장자 gate |
| UploadSecurityGate.java | 업로드 보안 gate |
| ExecutionLocationGate.java | 실행 위치 gate (USER_PRESENT vs SERVER) |
| OutputArtifactGate.java | 출력 artifact gate |
| GateResult.java | gate 공통 결과 모델 |

### Domain / Command Model Layer
| 파일 | 역할 |
|------|------|
| HwpxEditorCommand.java | command 요청 모델 |
| ApiResponseMeta.java | schemaVersion, engineVersion, requestId |
| DocumentParseResponse.java | parse 응답 모델 |
| ParseMeta.java / ParseResult.java | parse 결과 |

### Engine Adapter Layer (P14 이후 연결)
| 파일 | 역할 |
|------|------|
| PythonScriptBridge.java | Python engine 호출 |
| HwpToHwpxCliBridge.java | HWP → HWPX CLI 호출 |
| HwpToHwpxRouterBridge.java | 변환 방식 routing |

### Infra / File Storage Layer
| 파일 | 역할 |
|------|------|
| HwpxEditorApiHandler#archiveOutput() | artifact 저장 |
| HwpxEditorApiHandler#archiveRoot() | 저장 경로 결정 |
| HwpxDownloadExportUseCase | download export 흐름 |

### Audit / Test Layer
| 파일 | 역할 |
|------|------|
| scripts/audit_*.py | 구조/API/UI/gate 자동 감사 |
| tests/test_*.py | audit 결과 pytest 고정 |
| src/test/java/ | Java 단위/통합 테스트 |

---

## 3. 의존 방향 규칙

```
UI → (HTTP only) → Handler → UseCase → Gate → Model
                           ↘ EngineAdapter (P14)
                             ↘ Infra
```

역방향 금지:
- Gate → Handler 금지
- Model → UseCase/Handler 금지
- UseCase → HTTP 금지
- EngineAdapter → UI 금지

---

## 4. 거대 파일 현황

| 파일 | 라인 수 | 분리 필요 여부 |
|------|---------|--------------|
| HwpxUploadPageScripts.java | ~2700 | P14 이후 SCRIPT_5 분리 검토 |
| HwpxEditorApiHandler.java | ~520 | command/archive 책임 혼재 — 향후 분리 검토 |
| InspectionPageHandler.java | ~640 | 별도 앱 영역 |

---

## 5. P13 적용 기준

- UI Layer: command dispatch 함수 추가 완료 (P13 완료)
- Handler Layer: JSON branch + usecase wiring 완료 (P13 완료)
- UseCase Layer: APPLY_DEFERRED 반환 (P13 범위)
- Gate Layer: 검증 완료 (P12 완료)
- Engine Adapter: 미연결 (P14 이후)
- Infra: 변경 없음

## 6. P14 이월 항목

- `ApplyEngine` 실제 구현체 연결
- server-side artifactId 반환 (parse 응답에 포함)
- sessionArtifactId → server artifactId 교체
- actual apply 실행 (dryRun=false 경로)
