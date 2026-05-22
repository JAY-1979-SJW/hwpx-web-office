# HWPX Reader P1C — Gradle 실행 및 패키징 이슈 분리

**작성일**: 2026-05-07  
**상태**: Known Issue (별도 처리 대상)  
**영향 범위**: 배포 단계 (개발/테스트 단계 무관)

## 개요

HWPX Reader Parser (P1C) 완료 기준은 **JUnit 통합 테스트 PASS**입니다.

다음 이슈들은 런타임 배포 단계에 해당하며, P1C 마감 기준에서 제외됩니다.

## 확인된 이슈

### Issue 1: ./gradlew run 인자 전달 문제

**현상**:
```bash
./gradlew run --args "serve 8080"
# 예상: EngineHttpServer port=8080 시작
# 실제: 인자 미전달, main() args[] 비어있음
```

**원인**: Gradle run task가 application 플러그인의 标准 방식(--args) 미지원 또는 구성 이슈

**영향**: ./gradlew run으로 서버 시작 불가 (수동 포트 설정 필요)

**해결 방법**: 별도 작업명 `HWPX-ENGINE-RUNTIME-PACKAGING-P1-GRADLE-RUN-FATJAR` 에서 처리

### Issue 2: fat-JAR 빌드 및 직접 실행 미검증

**현상**:
```bash
gradle jar  # fat-JAR 생성 시도
java -jar build/libs/*.jar serve 8080  # 실행 미검증
```

**원인**: build.gradle.kts에서 shadowJar 또는 fatJar 구성 없음

**영향**: 배포 패키징 방식 확정 필요

**대안**: 
- docker 컨테이너 배포 (현재 권장)
- gradle 래퍼 + shell script 배포
- Spring Boot style fat-JAR 빌드 구성 추가

## P1C 완료 기준 (이 이슈 제외)

✅ Parser JUnit 테스트 PASS (HwpxParserTest 6개)  
✅ HTTP Handler JUnit 테스트 PASS (ParseHwpxHandlerTest 4개)  
✅ 원문 순서 보존 PASS  
✅ 다중 섹션 PASS  
✅ 표 추출 PASS  
✅ 기존 회귀 없음  

**Gradle run/fat-JAR 문제는 P1C 마감을 차단하지 않음**

## 다음 단계

**작업명**: HWPX-ENGINE-RUNTIME-PACKAGING-P1-GRADLE-RUN-FATJAR

처리 항목:
1. ./gradlew run 인자 전달 수정
2. fat-JAR 빌드 구성 추가 (shadowJar 또는 gradle-shadow-plugin)
3. java -jar 직접 실행 검증
4. docker 배포 패키징 확인

예상 일정: P1C 마감 후 별도 진행
