# HWPX Engine Docker Runtime 구성 문서

작성일: 2026-05-07  
상태: P1J 배포 준비 완료  
목표: Docker 기반 HWPX 파싱 엔진 실행 구조 구성

---

## 1. 개요

HWPX Reader Java 공통 엔진을 Docker 컨테이너로 패키징하여, 운영 환경에서 격리된 실행 환경을 제공합니다.

**핵심 원칙:**
- 원본 HWPX 샘플 파일은 Docker 이미지에 포함하지 않음
- 비밀번호, API 키, 인증서 등은 이미지에 포함하지 않음
- TABLE_NOT_VERIFIED 제한 유지
- Parser 코드 변경 없음
- API 응답 key 변경 없음

---

## 2. Dockerfile 구조

파일: `Dockerfile.hwpx-engine`

### 2.1 Multi-stage Build
- **Stage 1 (Build):** JDK 21 기반, Gradle `installDist` 실행
- **Stage 2 (Runtime):** JRE 21 기반, 최소화된 이미지

### 2.2 보안 설정
- Non-root user (`appuser`, UID 1000) 사용
- 불필요한 빌드 캐시 제외 (.gradle, build/)
- 샘플 파일 및 증거 자료 제외

### 2.3 진입점 (ENTRYPOINT)
```bash
/opt/office-analysis-engine/bin/office-analysis-engine serve 8080
```

---

## 3. 빌드 명령

### 3.1 Docker 이미지 빌드

```bash
docker build -f Dockerfile.hwpx-engine -t office-analysis-engine-hwpx:test .
```

**빌드 결과:**
- 이미지명: `office-analysis-engine-hwpx:test`
- JRE 21 기반
- 크기: 약 300-400MB (JRE + 컴파일된 엔진)

### 3.2 원본 샘플 미포함 확인

빌드 후, 이미지 내 샘플 파일 미포함 확인:
```bash
docker inspect office-analysis-engine-hwpx:test | grep -i sample
# 결과: 없음 (제외됨)
```

---

## 4. Foreground 실행 명령

### 4.1 기본 실행 (포트 8080)

```bash
docker run --rm -p 8080:8080 office-analysis-engine-hwpx:test
```

**출력:**
```
office-analysis-engine listening on http://0.0.0.0:8080
```

### 4.2 다른 포트 매핑 (예: 8081)

```bash
docker run --rm -p 8081:8080 office-analysis-engine-hwpx:test
```

**주의:**
- 포트 8080이 이미 사용 중이면 `-p` 플래그로 다른 호스트 포트 지정
- 백그라운드 실행(`-d` 플래그)은 권장하지 않음 (배포 준비 단계에서는 foreground로 테스트)

---

## 5. Docker Compose를 이용한 실행

파일: `docker-compose.hwpx-engine.yml`

### 5.1 빌드 및 실행

```bash
docker-compose -f docker-compose.hwpx-engine.yml up
```

**동작:**
- 이미지 빌드
- 포트 8080 노출
- healthcheck 10초 간격으로 /health 확인
- restart policy: unless-stopped

### 5.2 중지

```bash
docker-compose -f docker-compose.hwpx-engine.yml down
```

---

## 6. Health Check

### 6.1 컨테이너 내부에서 확인

```bash
curl http://localhost:8080/health
```

**응답:**
```
office-analysis-engine ok
```

### 6.2 호스트에서 확인

```bash
curl http://localhost:8080/health
```

---

## 7. /parse-hwpx Smoke 테스트

### 7.1 파일 준비

HWPX 샘플 파일이 필요합니다. 호스트에서 다음 명령으로 테스트:

```bash
curl -X POST http://localhost:8080/parse-hwpx \
  -F "file=@/path/to/sample.hwpx"
```

**응답 (성공):**
```json
{
  "errors": [],
  "warnings": [],
  "tables": [
    {
      "sheetName": "...",
      "sheetIndex": 0,
      "status": "OK",
      "cells": [ ... ]
    }
  ],
  "meta": {
    "fileName": "sample.hwpx",
    "fileType": "hwpx",
    "parseTime": 1234,
    "parser": "HwpxParser"
  }
}
```

### 7.2 Invalid ZIP 테스트 (Negative Smoke)

```bash
echo "not a zip file" | curl -X POST http://localhost:8080/parse-hwpx \
  -F "file=@-" 2>&1
```

**기대 응답:**
- HTTP 400 또는 error 필드 포함
- 샘플이 거부되었음을 명시

---

## 8. 포트 정책

| 환경 | 포트 | 용도 |
|------|------|------|
| 개발 | 8080 | 로컬 테스트 |
| docker-compose | 8080 | 포트 포워딩 |
| 다중 인스턴스 | 8081+ | 추가 포트 매핑 |

---

## 9. 샘플 파일 및 보안 원칙

### 9.1 원본 샘플 미포함

- `.dockerignore`에 `samples/`, `*.hwpx`, `*.hwp` 기록
- 빌드 시 이미지에 포함되지 않음
- 운영 환경에서는 별도 마운트 또는 API 요청으로 처리

### 9.2 비밀 정보 미포함

- `*.pem`, `secrets/`, `.env` 제외
- ANTHROPIC_API_KEY는 컨테이너 환경변수로 전달 (필요시)

### 9.3 TABLE_NOT_VERIFIED 제한 유지

- Parser 코드 미변경
- API 응답 key 미변경
- Docker 이미지는 기존 엔진 기능 그대로 제공

---

## 10. 운영 배포 전 확인사항

체크리스트:

- [ ] Docker 이미지 빌드 성공 (크기 300-400MB 범위)
- [ ] Foreground 실행 시 포트 8080 정상 수신
- [ ] `/health` 응답 "office-analysis-engine ok"
- [ ] `/parse-hwpx` 샘플 파일 파싱 성공
- [ ] Invalid ZIP 파일 거부 확인
- [ ] 이미지 내 원본 샘플 파일 미포함 확인
- [ ] healthcheck 설정 정상 작동
- [ ] 컨테이너 종료 후 정리 (--rm 플래그 사용)

---

## 11. 금지사항

다음은 운영 배포 전까지 수행하지 마세요:

- ❌ 원본 HWPX 샘플 파일을 이미지에 포함
- ❌ 비밀번호, API 키, 인증서를 Dockerfile에 하드코딩
- ❌ 운영 환경의 compose 파일을 이 파일로 교체
- ❌ Parser 코드 수정
- ❌ API 응답 key 변경
- ❌ P2 기능(표 처리) 구현 추가
- ❌ 백그라운드로 자동 실행 설정 (배포 준비 단계에서는 foreground)

---

## 12. 문제 해결

### 포트 충돌
```bash
# 8080 포트 사용 중인 경우
docker run --rm -p 8081:8080 office-analysis-engine-hwpx:test
```

### 이미지 크기 확인
```bash
docker images office-analysis-engine-hwpx:test
```

### 빌드 캐시 초기화
```bash
docker build --no-cache -f Dockerfile.hwpx-engine -t office-analysis-engine-hwpx:test .
```

---

## 13. 참조

- Dockerfile: `Dockerfile.hwpx-engine`
- Docker Compose: `docker-compose.hwpx-engine.yml`
- .dockerignore: `.dockerignore`
- HWPX Parser: `src/main/java/com/haehan/engine/hwpx/HwpxParser.java`
- HTTP Server: `src/main/java/com/haehan/engine/http/EngineHttpServer.java`
- API Contract: `src/main/java/com/haehan/engine/contract/`

---

## 14. 버전 정보

- Java: 21 (OpenJDK, eclipse-temurin)
- Gradle: 8.x (Wrapper)
- TABLE_NOT_VERIFIED 제한: 유지됨
- P1I 클라이언트 API smoke: PASS
