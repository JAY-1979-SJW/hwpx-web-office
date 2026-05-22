# HWPX Direct Writer P24-2 Header Footer Body Discovery

## 목적

P24에서 쪽 번호 메타데이터 제어는 구현했지만, 실제 문서에 보이는 머리말/꼬리말 본문 객체 생성은 구조 샘플이 필요하다. 이번 단계는 HWPX 패키지에서 visible header/footer/master page 구조를 탐색하는 전용 도구를 추가하고, 현재 로컬 샘플 상태를 확인하는 것이다.

## 구현

```text
scripts/hwpx/hwpx_header_footer_discovery.py
```

기능:

- HWPX ZIP 순회
- header/footer/master 관련 entry 탐색
- master page / header/footer object 관련 XML term 탐색
- JSON/CSV discovery report 생성

탐색 term:

```text
<hm:
<hp:masterPage
masterPageCnt="1"
masterPageCnt="2"
headerIDRef
footerIDRef
<hp:header
<hp:footer
pageNumCtrl
```

## 실행

```text
python scripts/hwpx/hwpx_header_footer_discovery.py --root . --out-json tmp/hwpx_p24_header_footer_discovery/discovery.json --out-csv tmp/hwpx_p24_header_footer_discovery/discovery.csv
```

## 결과

```text
status: WARN
file_count: 29
found_count: 0
```

현재 repo 샘플 기준으로 실제 visible header/footer/master page 구조는 발견되지 않았다. 일부 샘플의 `Contents/header.xml`에는 `hm` namespace 선언이 있지만, 실제 `hm:*` element나 `headerIDRef`/`footerIDRef` 연결 구조는 없다.

## 판정

```text
P24_2_HEADER_FOOTER_BODY_DISCOVERY: WARN
```

구조가 없는 상태에서 임의 XML을 생성하면 한컴 호환성을 보장하기 어렵다. 따라서 visible header/footer body 생성은 실제 머리말/꼬리말이 포함된 HWPX fixture 확보 후 진행한다.

## 결론

- 쪽 번호 메타데이터: P24에서 구현 완료
- visible header/footer body: 구조 샘플 없음
- 이번 단계: discovery tool 구현 완료
- 다음 개발: 구조 샘플 확보 또는 다른 완전 구현 영역으로 진행

## 다음 단계

1. 머리말/꼬리말이 들어간 HWPX fixture 확보
2. `hm:*` / `headerIDRef` / `footerIDRef` 구조 분석
3. 기존 구조 clone 기반 header/footer text 생성
4. ZIP/XML validation
5. Java parser roundtrip
6. 가능하면 한컴 시각 확인
