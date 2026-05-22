# HWPX Browser Editor Module Boundary Rules

**버전:** P13A  
**날짜:** 2026-05-15  
**상태:** CONFIRMED — audit gate로 강제됨

---

## 1. UI Layer 규칙

**허용:**
- command JSON 생성 (buildEditorCommand)
- JSON POST fetch to `/api/hwpx/editor`
- result 표시 (renderEditorCommandResult)
- state machine (IDLE / UPLOADING / READY / EDITING / ...)

**금지:**
- HWPX XML/ZIP 직접 읽기/쓰기
- raw filesystem path 전달
- engine(Python/Java) 직접 호출
- secret/token/password/session/cookie 포함 payload
- artifactId 없이 command 생성 (validateDocument 제외)

**허용 파일 패턴:** `http/HwpxUploadPage*.java`

**금지 코드 패턴:**
- `BinData/` (command dispatch 영역)
- `Contents/` (command dispatch 영역)
- `C:\\` / `/home/` / `/var/` (raw path)
- `password` / `secret` / `token` (payload key)

---

## 2. Web API Handler Layer 규칙

**허용:**
- HTTP request 파싱 (multipart / JSON)
- content-type 기반 분기
- UseCase 호출
- response 직렬화
- error key 반환 (`error`, `message`, `status`)

**금지:**
- HWPX engine 직접 수정 (PythonScriptBridge 직접 호출 → EngineAdapter로 이동 예정)
- business rule 직접 구현
- UI state 판단
- ValidationGate 우회

**허용 파일 패턴:** `http/*Handler.java`

**금지 코드 패턴:**
- Handler에서 `HwpxEditorValidationGate.validate()` 호출 없이 command 처리
- Handler에서 `Files.write()` + HWPX 경로

---

## 3. UseCase Layer 규칙

**허용:**
- command 실행 흐름 조정
- ValidationGate 호출
- ApplyEngine 호출 (P14)
- result 모델 생성

**금지:**
- `import com.haehan.engine.http.*`
- `import com.sun.net.httpserver.*`
- raw filesystem path 외부 노출
- UI 표현 로직

**허용 파일 패턴:** `usecase/Hwpx*.java`

**금지 코드 패턴:**
- `HttpExchange` / `HttpHandler` import
- `exchange.send*`

---

## 4. Validation / Gate Layer 규칙

**허용:**
- command schema 검증 (commandType, target, payload, artifactId)
- raw path 탐지
- secret key 탐지
- allowed command allowlist 검사
- dryRun 파라미터 검증

**금지:**
- 실제 HWPX 파일 수정
- side effect (Files.write, ProcessBuilder, Runtime.exec, HttpClient)
- 네트워크 I/O
- DB write

**허용 파일 패턴:** `gate/Hwpx*.java`, `gate/*Gate.java`

**금지 코드 패턴:**
- `Files.write` (gate 파일 내)
- `ProcessBuilder` (gate 파일 내)
- `Runtime.exec` (gate 파일 내)
- `HttpClient` (gate 파일 내)

---

## 5. Domain / Command Model Layer 규칙

**허용:**
- 순수 data model
- @SerializedName GSON 어노테이션
- 불변 필드 / 레코드

**금지:**
- `import com.haehan.engine.http.*`
- `import com.sun.net.httpserver.*`
- `import java.nio.file.*` (model에서)
- 비즈니스 로직 직접 구현

**허용 파일 패턴:** `contract/*.java`

---

## 6. Engine Adapter Layer 규칙 (P14 이후)

**허용:**
- Python/CLI engine 실행
- 실행 결과 래핑
- 임시 파일 관리

**금지:**
- UI 직접 의존
- HTTP 직접 의존
- raw path UI 노출

**허용 파일 패턴:** `hwp/*.java`

---

## 7. Infra / File Storage Layer 규칙

**허용:**
- artifact 저장 (reports/hwpx-editor/)
- 설정 기반 경로 (`hwpx.editor.output.dir` system property)
- SHA256 검증

**금지:**
- raw path UI/API 응답 노출 (guardedArtifactRef 사용)
- secret 로그 출력

---

## 8. Audit / Test Layer 규칙

**허용:**
- read-only 코드 검사
- pytest assert
- Java JUnit 검사
- JSON 보고서 생성

**금지:**
- 운영 파일 write
- 외부 서버 접속
- DB write
- HWP/Hancom 직접 실행

---

## 9. 의존 방향 요약

| From → To | 허용 | 비고 |
|-----------|------|------|
| UI → Handler | ✅ (HTTP) | |
| Handler → UseCase | ✅ | |
| Handler → Gate | ✅ (직접 gate 필요 시) | |
| UseCase → Gate | ✅ | |
| UseCase → EngineAdapter | ✅ (P14) | |
| Gate → Model | ✅ | |
| Model → 어디든 | ❌ | model은 의존 없음 |
| UseCase → HTTP | ❌ | 금지 |
| Gate → EngineAdapter | ❌ | |
| EngineAdapter → UI | ❌ | |

---

## 10. audit gate 참조

- `scripts/audit_hwpx_editor_architecture_gate.py` — 위 규칙 자동 검증
- `tests/test_hwpx_editor_architecture_gate.py` — pytest 고정
