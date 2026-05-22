# HWPX P3D G2B Local Browser Attachment Discovery

## 기준

- local HEAD: `c2f3b8d7eeafa3215baf5659c0c787f2aebdae85`
- github/main HEAD: `c2f3b8d7eeafa3215baf5659c0c787f2aebdae85`
- G2B 소방 후보: `41`
- 선행 결과: 정적 HTML 첨부 링크 `0`

## 수행 원칙

- 로컬 PC 브라우저 기준으로만 확인했다.
- 서버에서 G2B 웹 접속은 수행하지 않았다.
- 서버 브라우저 자동화는 수행하지 않았다.
- 로그인, 인증서, 비밀번호, OTP, 투찰, 전자서명, 제출, 신청은 수행하지 않았다.
- 쿠키, session, token 추출은 수행하지 않았다.
- DB write, schema 변경, 운영 데이터 수정은 수행하지 않았다.
- 다운로드 파일과 probe 결과는 `tmp/p3d_g2b_hwpx_discovery/` 하위에만 보관했다.

## 브라우저 확인 방식

Python Playwright를 사용해 로컬 Chromium 브라우저를 실행했다.
후보 41건을 한 건씩 직렬로 열고, 페이지 로딩 후 DOM 텍스트와 링크/버튼 텍스트를 검사했다.

검사 기준은 다음과 같다.

- 첨부, 파일, 다운로드, 공고서 텍스트
- HWPX/HWP 텍스트 또는 URL
- 로그인, 인증서, 공동인증, 금융인증, 보안프로그램, 비밀번호, CAPTCHA 문구

명확한 공개 HWPX/HWP 직접 URL만 다운로드 대상으로 삼았다.
불명확한 버튼 클릭, 로그인/인증/투찰/제출 관련 클릭은 수행하지 않았다.

## 브라우저 확인 결과

| result | count |
| --- | ---: |
| ATTACHMENT_UI_FOUND | 0 |
| HWPX_CANDIDATE_FOUND | 0 |
| HWP_CANDIDATE_FOUND | 0 |
| DOWNLOAD_CANDIDATE_FOUND | 0 |
| NO_ATTACHMENT_UI | 0 |
| AUTH_OR_SECURITY_BLOCKED | 41 |
| ERROR | 0 |

41건 모두 페이지 DOM에 인증/보안 관련 문구가 확인되어 `AUTH_OR_SECURITY_BLOCKED`로 분류했다.
후보 링크 수는 모든 건에서 `0`이었다.

## 다운로드 결과

| result | count |
| --- | ---: |
| HWPX | 0 |
| HWP | 0 |
| 기타 | 0 |
| 실패 | 0 |

다운로드 가능한 직접 HWPX/HWP URL이 없어 다운로드는 수행되지 않았다.

## 확보 샘플 목록

| file | bid_no | title | format | size |
| --- | --- | --- | --- | ---: |
| N/A | N/A | N/A | N/A | 0 |

## 남은 문제

- 로컬 브라우저 기준에서도 공개 첨부 링크가 DOM에 노출되지 않았다.
- 41건 모두 인증/보안 관련 문구로 차단 분류됐다.
- 자동화로 첨부 UI에 접근하기 어렵다.
- 실제 파일 확보는 사용자가 직접 브라우저에서 공개 첨부를 확인하는 user-present 수동 절차가 필요하다.
- HWP만 확보될 경우 HWPX 변환 경로를 별도 확정해야 한다.

## 다음 단계

1. 사용자가 로컬 브라우저에서 G2B 상세 페이지를 직접 열고 공개 첨부 영역을 확인한다.
2. 로그인/인증/투찰/전자서명 없이 접근 가능한 파일만 다운로드한다.
3. HWPX 파일은 그대로 P3D batch quality audit에 사용한다.
4. HWP 파일만 확보되면 HWPX 변환 도구를 확정한 뒤 변환본으로 파싱한다.
5. HWPX 3건 이상 확보 후 P3D batch quality audit을 실행한다.

## 최종 판정

WARN

로컬 브라우저 자동화 기준으로 G2B 소방 후보 41건을 모두 확인했으나, 모든 건이 인증/보안 관련 차단 상태로 분류됐다.
HWPX/HWP 샘플은 확보하지 못했다.
다음 단계는 자동화가 아니라 사용자 직접 브라우저 확인을 통한 공개 첨부 파일 확보다.
