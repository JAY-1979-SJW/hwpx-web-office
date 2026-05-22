# HWPX P3D G2B Real Sample Discovery

## 기준

- P3C: CLOSED / PASS
- P3D audit: WARN
- WARN 원인: 실제 공고문 HWPX 샘플 0건
- local HEAD: `595b2a427abfc6c76c48f90caab9c386626536ed`
- github/main HEAD: `595b2a427abfc6c76c48f90caab9c386626536ed`
- server HEAD: `595b2a427abfc6c76c48f90caab9c386626536ed`

## G2B DB 후보

- DB: `/home/ubuntu/app/g2b/db/g2b_bid.db`
- table: `bid_notice_cnstwk`
- 전체 공사 입찰공고: `905`
- 소방 관련 후보: `41`
- server git status: clean

## 수집/확인 방식

- 서버 DB는 read-only로만 조회했다.
- 서버 G2B 웹 접속은 수행하지 않았다.
- 서버 `/tmp` CSV는 read-only로 로컬 임시 폴더에 복사했다.
- G2B 공개 상세 URL 접근은 로컬 PC에서만 수행했다.
- 로그인, 인증서, 비밀번호, OTP, 투찰, 전자서명, 제출, 세션/쿠키 추출은 수행하지 않았다.
- 다운로드 샘플과 중간 CSV는 `tmp/p3d_g2b_hwpx_discovery/` 하위에만 생성했다.

## 후보 CSV

### 서버 CSV

- `/tmp/g2b_bid_notice_fire_candidates_20260508.csv`
- header + data 41 lines

### 로컬 임시 CSV

- `tmp/p3d_g2b_hwpx_discovery/g2b_bid_notice_fire_candidates_20260508.csv`
- rows: `41`
- empty detail URL: `0`

## URL 접근성 결과

로컬 PC에서 41개 G2B 상세 URL에 대해 HTTP GET 접근성을 확인했다.
샌드박스 네트워크에서는 connection refused가 발생했으나, 권한 상승 컨텍스트에서는 41건 모두 HTTP 200으로 접근됐다.

| result | count |
| --- | ---: |
| PUBLIC_PAGE_ATTACHMENT_HINT | 0 |
| PUBLIC_PAGE_NO_ATTACHMENT_HINT | 41 |
| AUTH_REQUIRED_OR_BLOCKED | 0 |
| HTTP_ERROR | 0 |
| ERROR | 0 |

정적 HTML 응답에는 첨부파일, HWPX, HWP, download 링크 힌트가 확인되지 않았다.
상세 페이지가 동적 렌더링 또는 별도 API 호출로 첨부 영역을 구성할 가능성이 있다.

## 첨부 후보 결과

정적 HTML의 `href`/`src`에서 HWPX/HWP/download/file/attach/atch 후보를 추출했다.

| kind | count |
| --- | ---: |
| HWPX_HINT | 0 |
| HWP_HINT | 0 |
| ATTACH_HINT | 0 |
| TEXT_HINT_NO_LINK | 0 |
| ERROR | 0 |

직접 다운로드 가능한 HWPX/HWP 링크는 확인되지 않았다.

## 다운로드 결과

다운로드 대상 후보 URL이 없어 실제 다운로드는 수행되지 않았다.

| result | count |
| --- | ---: |
| DOWNLOADED_HWPX | 0 |
| DOWNLOADED_HWP | 0 |
| NOT_HWPX_ZIP | 0 |
| HTTP_ERROR | 0 |
| ERROR | 0 |

## HWP 처리 원칙

P3D 파서는 HWPX 기준으로 진행한다.
공개 첨부에서 HWP만 확보되는 경우에는 HWP를 HWPX로 변환한 뒤 HWPX parser에 투입한다.

이번 실행에서는 HWP 파일도 확보되지 않아 변환은 수행하지 않았다.
로컬 변환 도구 확인 결과 다음 명령은 현재 PATH에서 확인되지 않았다.

- `soffice`
- `libreoffice`
- `hwp5txt`
- `hwp5proc`
- Python package `pyhwp`

따라서 다음 단계에서 HWP만 확보될 경우, 사용자 승인 하에 변환 도구를 확정해야 한다.
가능한 경로는 한컴/LibreOffice/pyhwp 등이며, 변환 산출물은 `tmp/p3d_g2b_hwpx_discovery/downloads` 또는 별도 임시 폴더에 두고 git에는 추가하지 않는다.

## 확보 샘플

확보된 HWPX 샘플은 없다.

| file | bid_no | title | size | zip_check |
| --- | --- | --- | ---: | --- |
| N/A | N/A | N/A | 0 | N/A |

## 남은 문제

- G2B 정적 상세 URL에서는 첨부 링크가 노출되지 않았다.
- G2B 상세 페이지가 JavaScript 또는 내부 API로 첨부 목록을 로딩할 가능성이 있다.
- 직접 HWPX/HWP URL이 없으므로 자동 다운로드를 진행할 수 없다.
- 실제 샘플 확보를 위해 로컬 브라우저 user-present 방식 확인이 필요하다.
- HWP만 확보될 경우 HWPX 변환 도구 확정이 필요하다.

## 다음 단계

1. 로컬 브라우저 user-present 방식으로 소방 후보 상세 페이지의 첨부 영역을 확인한다.
2. 로그인, 인증서, 투찰, 전자서명 없이 공개 첨부만 다운로드한다.
3. HWPX는 그대로 P3D 샘플로 사용한다.
4. HWP만 있으면 HWPX로 변환한 뒤 parser에 투입한다.
5. 실제 HWPX 샘플 3건 이상 확보 후 P3D batch quality audit을 실행한다.

## 최종 판정

WARN

G2B 소방 후보 41건의 공개 상세 URL은 로컬 PC에서 HTTP 200으로 접근됐지만, 정적 HTML에서 첨부/HWP/HWPX 링크가 노출되지 않았다.
실제 HWPX 샘플은 0건 확보됐다.
P3D는 구현 단계로 넘어가지 말고 로컬 브라우저 user-present 방식으로 공개 첨부 파일을 먼저 확보해야 한다.
