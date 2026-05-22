# HWPX Open Source Tooling Feasibility

## 목적

HWPX 문서를 직접 작성하고 서식 변환하는 오픈소스를 조사해, 우리 프로젝트에서 도구로 개발 가능한지 판단했다.

## 결론

HWPX-first 문서 작성 도구는 개발 가능하다. 다만 HWP 바이너리를 안정적으로 HWPX로 변환하는 문제와, HWPX를 새로 생성/편집/서식 변환하는 문제는 분리해야 한다.

추천 방향:

1. HWPX 문서 작성/템플릿/서식 변환은 `pyhwpxlib` 또는 자체 XML/ZIP writer 기반으로 PoC
2. HWPX 분석/검증은 기존 parser와 `python-hwpx`/`pyhwpxlib`의 validator 아이디어 참고
3. HWP -> HWPX 변환은 `hwp2hwpx` Java 계열 또는 공식 HWPX Converter/SDK를 별도 provider로 유지
4. 상용/업무 사용 가능성은 라이선스 검토 후 결정

## 공식 포맷 근거

한컴은 HWPX를 OWPML 기반의 XML 패키지 포맷으로 설명한다. 한컴테크 문서와 한컴 다운로드 센터의 HWP/OWPML 자료에 따르면 HWPX는 ZIP 내부에 XML 구성요소를 가진 개방형 문서 포맷이며, OWPML/HWP 공개 자료를 통해 구현 근거를 확보할 수 있다.

자료:

- https://tech.hancom.com/hwpxformat/
- https://www.hancom.com/support/downloadCenter/hwpOwpml

## 후보별 평가

| 후보 | 용도 | 장점 | 제약 | 판정 |
| --- | --- | --- | --- | --- |
| `pyhwpxlib` | HWPX 생성/편집/Markdown 변환/CLI | 문서 작성 CLI가 풍부하고 Apache-2.0/BSL 구조로 명시됨 | BSL 조건 때문에 상용/6인 이상 사용은 별도 확인 필요 | 1순위 PoC 후보 |
| `python-hwpx` | HWPX 읽기/편집/생성/검증 | 순수 Python, CLI/검증/템플릿 분석 제공 | NonCommercial 라이선스라 업무 제품 의존성은 위험 | 참고/검증 후보 |
| `neolord0/hwpxlib` | Java HWPX read/write | Apache 계열 생태계, HWPX read/write 직접 지원 | Java 통합 필요 | 서버/엔진 후보 |
| `neolord0/hwp2hwpx` | HWP -> HWPX 변환 | Apache-2.0, `hwplib` + `hwpxlib` 기반 변환 코드 | 변환 품질/복잡 문서 검증 필요 | HWP 변환 PoC 후보 |
| `pyhwpx` | 한컴 COM 자동화 wrapper | HwpObject/HAction 호출을 Python화 | 한컴 설치/Windows/COM 필요, 현재 SaveAs blocked와 같은 문제 가능 | fallback |
| `megahwpx` | JS HWPX <-> JSON | JSON 변환 컨셉 유용 | 성숙도/라이선스/기능 검증 필요 | 보류 |
| `kordoc` 등 parser | HWP/HWPX -> Markdown | 추출/분석에 유용 | 작성/서식 생성보다는 parser 중심 | 분석 보조 |

## 가장 현실적인 개발 경로

### 1단계: HWPX writer adapter

목표:

- 새 `.hwpx` 문서 생성
- 제목/문단/글머리표
- 표 생성
- 기본 글자 크기/굵게/색상
- 간단한 header/footer
- ZIP 구조 및 XML 존재 검증

권장 구현:

- `scripts/hwpx/hwpx_writer_adapter.py`
- provider: `pyhwpxlib` 우선, 실패 시 자체 minimal writer
- 출력은 `tmp/hwpx_writer_poc/`

성공 기준:

- 한컴에서 열리는 HWPX 생성
- ZIP 검증
- XML 구조 검증
- 기존 parser로 텍스트 추출 가능

### 2단계: Markdown/HTML -> HWPX 변환

목표:

- Markdown heading, paragraph, list, table, code block을 HWPX로 변환
- 공고문/보고서 템플릿 생성에 사용

참고:

- `pyhwpxlib`는 Markdown/HTML/TXT -> HWPX 변환 CLI와 CSS -> HWPX mapping을 제공한다고 설명한다.

### 3단계: HWPX template fill

목표:

- 기존 HWPX 템플릿 unpack
- placeholder/필드 유사 구조 탐색
- 값 치환
- repack
- page guard / package validation

### 4단계: HWP -> HWPX provider 분리

목표:

- `hwp2hwpx` Java converter PoC
- 공식 HWPX Converter Add-in provider
- Hwp SDK provider
- 변환 품질 audit

## 라이선스 판단

- `python-hwpx`: PyPI 기준 NonCommercial. 제품/업무 자동화의 직접 의존성으로는 부적합하다.
- `pyhwpxlib`: PyPI metadata는 Apache-2.0으로 표시되지만 본문은 일부 BSL 1.1 조건을 설명한다. 실제 사용 전 repository의 `LICENSE.md`를 확인해야 한다.
- `hwp2hwpx` / `hwpxlib`: GitHub에서 Apache-2.0으로 표시된다. HWP 변환 엔진 후보로 검토 가치가 크다.

## 권장 의사결정

바로 도입할 후보:

- `pyhwpxlib` 기반 HWPX 작성 PoC
- `hwp2hwpx` 기반 HWP -> HWPX 변환 PoC

참고하되 직접 의존 보류:

- `python-hwpx`는 NonCommercial 조건 때문에 구조/검증 아이디어 참고용
- `pyhwpx`는 COM wrapper라 현재 한컴 SaveAs timeout 문제를 근본 해결하지 못할 가능성이 큼

## 다음 작업

1. `pyhwpxlib` 설치 없이 repository/API 조사 후 라이선스 확인
2. 격리된 PoC에서 `document new`, `text add`, `style add`, `table add`, `convert markdown` 검증
3. 생성 HWPX를 기존 parser로 round-trip 검증
4. 한컴 GUI에서 수동 open 확인
5. `hwp2hwpx` Java PoC로 작은 HWP 1건 변환 가능성 확인

## 최종 판정

`PASS_WITH_LICENSE_REVIEW`

HWPX 문서 작성/서식 변환 도구는 오픈소스 기반으로 개발 가능하다. 단, 상용/업무 사용을 고려하면 라이선스 검토가 선행되어야 하며, HWP -> HWPX 변환은 HWPX writer와 별도 provider로 분리해야 한다.
