# HWPX Audit Scripts

HWPX Reader P1F/P1G 검증 결과를 재실행 가능한 감사 스크립트로 자동화합니다.

## 목적

- 27개 실제 HWPX 샘플 자동 감사
- API 계약 검증
- 텍스트 품질 검사
- 보안 방어 확인
- 사람이 읽을 수 있는 MD 리포트 + 기계가 읽을 수 있는 JSON 리포트 생성
- 향후 Docker/클라이언트 연동 전 재사용 가능한 스크립트 고정

## 스크립트 목록

### 1. `audit_hwpx_samples.py`
**목적**: 샘플 인벤토리 자동 생성

**기능**:
- .hwpx 파일 자동 검색 (samples/, docs/samples/, src/test/resources/ 등)
- SHA256 해시 계산 (파일 무결성 검증)
- 파일 메타데이터 수집 (크기, 수정 시간)
- fixture vs real sample 자동 분류
- 중복 파일 감지

**사용법**:
```bash
python3 scripts/hwpx/audit_hwpx_samples.py --sample-root . --out-dir docs/reports/hwpx_audit
```

**출력**:
- `docs/reports/hwpx_audit/inventories/hwpx_sample_inventory_latest.json` (JSON)
- `docs/reports/hwpx_audit/inventories/hwpx_sample_inventory_latest.md` (Markdown)

---

### 2. `smoke_hwpx_api.py`
**목적**: /parse-hwpx API를 모든 샘플로 테스트

**기능**:
- 샘플 파일을 API에 POST
- HTTP status, response JSON 검증
- API 계약 v1.0 (14개 필수 키) 검증
- 텍스트 품질 지표 수집:
  - fullText 길이
  - 한글 문자 수
  - 깨진 문자 (replacement char)
  - XML 잔여 (<hp:, <hs: 등)
  - 제어 문자
- 민감정보 마스킹 (preview 최대 300자)
- 샘플별 summary + batch summary 생성

**사용법**:
```bash
python3 scripts/hwpx/smoke_hwpx_api.py \
  --base-url http://127.0.0.1:8080 \
  --inventory docs/reports/hwpx_audit/inventories/hwpx_sample_inventory_latest.json \
  --out-dir docs/reports/hwpx_audit
```

**출력**:
- `docs/reports/hwpx_audit/evidence/{run_id}/batch_summary.json` (배치 결과)
- `docs/reports/hwpx_audit/evidence/{run_id}/*.summary.json` (샘플별 결과)
- `docs/reports/hwpx_audit/evidence/latest_batch_summary.json` (최신 배치)

---

### 3. `verify_hwpx_evidence.py`
**목적**: 생성된 evidence 교차 검증

**기능**:
- inventory, batch summary, 개별 sample summary 일관성 확인
- SHA256 일치 여부 검증
- 파싱 결과 완전성 확인
- API 계약 준수 검증
- 최종 PASS/WARN/FAIL 판정

**사용법**:
```bash
python3 scripts/hwpx/verify_hwpx_evidence.py \
  --inventory docs/reports/hwpx_audit/inventories/hwpx_sample_inventory_latest.json \
  --batch-summary docs/reports/hwpx_audit/evidence/latest_batch_summary.json \
  --sample-dir docs/reports/hwpx_audit/evidence/20260507_182925 \
  --out-dir docs/reports/hwpx_audit/summaries
```

**출력**:
- `docs/reports/hwpx_audit/summaries/hwpx_evidence_verification_latest.json`
- `docs/reports/hwpx_audit/summaries/hwpx_evidence_verification_latest.md`

---

### 4. `test_hwpx_security.py`
**목적**: 보안 방어 테스트

**테스트**:
1. Invalid ZIP (not ZIP format) → 거부 확인
2. Non-HWPX ZIP (valid ZIP, no HWPX structure) → 거부 확인
3. Empty file → 거부 확인

**기능**:
- 테스트용 임시 파일 자동 생성
- API 응답 ok=false 확인
- HTTP 400 에러 반환 확인
- 서버 500 에러 방지 확인

**사용법**:
```bash
python3 scripts/hwpx/test_hwpx_security.py \
  --base-url http://127.0.0.1:8080 \
  --out-dir docs/reports/hwpx_audit/evidence
```

**출력**:
- `docs/reports/hwpx_audit/evidence/negative_smoke_summary.json`
- `docs/reports/hwpx_audit/evidence/negative_smoke_summary.md`

---

### 5. `run_hwpx_full_audit.sh`
**목적**: 모든 감사 스크립트 통합 실행

**순서**:
1. Git 상태 기록
2. HWPX 테스트 실행 (21/21)
3. 빌드 (HWPX 관련만)
4. 샘플 인벤토리 생성
5. 서버 health 확인
6. API smoke 테스트 (27/27 샘플)
7. 보안 방어 테스트 (3/3)
8. Evidence 검증
9. 최종 리포트 생성
10. Git 상태 기록

**사용법**:
```bash
bash scripts/hwpx/run_hwpx_full_audit.sh
```

**환경 변수**:
- `BASE_URL`: API base URL (기본: http://127.0.0.1:8080)
- `SAMPLE_ROOT`: 샘플 검색 root (기본: .)
- `INCLUDE_FIXTURES`: fixture 포함 여부 (기본: false)

**예시**:
```bash
BASE_URL=http://example.com:8080 bash scripts/hwpx/run_hwpx_full_audit.sh
```

---

## 실행 순서

### 터미널 1: 샘플 인벤토리 생성 (서버 불필요)
```bash
python3 scripts/hwpx/audit_hwpx_samples.py
```

### 터미널 2: 서버 실행 (foreground)
```bash
./gradlew run --args "serve 8080"
```

### 터미널 3: 전체 감사 실행 (서버 필수)
```bash
bash scripts/hwpx/run_hwpx_full_audit.sh --base-url http://127.0.0.1:8080
```

또는 개별 스크립트 실행:
```bash
python3 scripts/hwpx/smoke_hwpx_api.py --base-url http://127.0.0.1:8080
python3 scripts/hwpx/test_hwpx_security.py --base-url http://127.0.0.1:8080
python3 scripts/hwpx/verify_hwpx_evidence.py
```

---

## 디렉터리 구조

```
scripts/hwpx/
  ├── audit_hwpx_samples.py         (샘플 인벤토리)
  ├── smoke_hwpx_api.py              (API 테스트)
  ├── verify_hwpx_evidence.py         (Evidence 검증)
  ├── test_hwpx_security.py           (보안 테스트)
  ├── run_hwpx_full_audit.sh          (통합 실행)
  └── README.md                       (이 파일)

docs/reports/hwpx_audit/
  ├── inventories/                    (샘플 인벤토리)
  │   ├── hwpx_sample_inventory_latest.json
  │   └── hwpx_sample_inventory_latest.md
  ├── evidence/                       (API 응답 evidence)
  │   ├── {run_id}/
  │   │   ├── batch_summary.json
  │   │   └── *.summary.json
  │   ├── latest_batch_summary.json
  │   ├── negative_smoke_summary.json (보안 테스트)
  │   └── negative_smoke_summary.md
  ├── summaries/                      (최종 리포트)
  │   ├── hwpx_evidence_verification_latest.json
  │   ├── hwpx_evidence_verification_latest.md
  │   ├── p1_existing_artifact_audit_20260507.json
  │   └── p1_existing_artifact_audit_20260507.md
  ├── logs/                           (실행 로그)
  │   ├── audit_hwpx_samples_*.log
  │   ├── smoke_hwpx_api_*.log
  │   ├── test_hwpx_security_*.log
  │   ├── verify_hwpx_evidence_*.log
  │   ├── hwpx_tests.log
  │   ├── build.log
  │   ├── git_status_before.log
  │   ├── git_status_after.log
  │   └── git_log.log
  └── README.md                       (이 문서)
```

---

## PASS/WARN/FAIL 기준

### Sample Inventory (audit_hwpx_samples.py)
- **PASS**: real sample >= 1, 모든 파일 SHA256 생성됨
- **WARN**: fixture와 real 분류 불명확
- **FAIL**: real sample = 0, SHA256 누락

### API Smoke Test (smoke_hwpx_api.py)
- **PASS**: 모든 샘플 HTTP 200, ok=true, errorCount=0
- **WARN**: 일부 샘플 warning 있음
- **FAIL**: 샘플 파싱 실패, HTTP 에러, ok=false

### Evidence Verification (verify_hwpx_evidence.py)
- **PASS**: 모든 검증 통과, 경고 없음
- **WARN**: table sample 없음 (expected), 기타 경고
- **FAIL**: count mismatch, 파싱 오류, SHA256 불일치

### Security Test (test_hwpx_security.py)
- **PASS**: 3/3 negative test 통과 (모두 거부됨)
- **WARN**: HTTP status 부분 부정확
- **FAIL**: invalid zip 통과, 500 에러 발생

---

## 주의사항

### Python은 파싱을 하지 않는다
- Python 스크립트는 orchestration, hash 계산, API 호출만 수행
- 실제 HWPX 파싱은 Java engine의 /parse-hwpx API만 사용
- HWP 포맷 직접 파싱 구현 금지

### 원본 샘플 파일
- samples/*.hwpx는 커밋하지 않음 (원본 보존)
- evidence/*.summary.json은 커밋 대상 (재검증 가능)

### 민감정보 마스킹
- fullText preview는 최대 300자로 제한
- 한글 문서라 개인정보 노출 위험 있으므로 마스킹 필요
- 로그 파일에 secret/password 없음 확인

### 재실행성
- 스크립트는 멱등성(idempotent) 보장
- 같은 샘플로 여러 번 실행 가능
- timestamp를 filename에 포함하여 버전 관리

---

## 문제해결

### 서버가 실행 중이 아님
별도 터미널에서 foreground로 실행하세요:
```bash
./gradlew run --args "serve 8080"
```
또는:
```bash
./gradlew bootRun
```

### 샘플을 찾을 수 없음
```bash
python3 scripts/hwpx/audit_hwpx_samples.py --sample-root /path/to/samples
```

### API 응답이 느림
- 네트워크 지연 확인
- 서버 리소스 확인
- timeout 기본값: 10초 (조정 가능)

---

## 기준선

- P1C (a2c584d): HWPX reader validation
- P1 (d3f6b2e): runtime packaging
- P1D (dfa2c6d): API contract freeze
- P1E (1ddb151): P1 closeout audit
- P1F (89d3ec4): MIME validation fix
- P1G (174d8ab): P1G closeout audit

---

## 다음 단계

- **P2**: 표 처리 개선 (rowspan/colspan)
- **P2**: 이미지 처리
- **P2**: 성능 최적화
- **DEPLOYMENT**: Docker, K8s 통합

---

**작성**: 2026-05-07  
**상태**: READY FOR PRODUCTION
