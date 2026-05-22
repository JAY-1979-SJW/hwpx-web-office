# 한컴 개발자센터 HWP -> HWPX 변환 소스/API 확인

확인일: 2026-05-13

## 확인 범위

- 한컴 개발자센터 문서 변환 API
- 한컴 개발자센터 오픈 소스 목록
- 한컴디벨로퍼 포럼의 HWP -> HWPX 변환 관련 답변
- 로컬 변환 라우터 상태

## 공식 개발자센터 확인 결과

한컴 개발자센터의 `한컴 통합문서뷰어 > 문서 변환 API`에는 HWP -> HWPX 변환 API가 문서화되어 있다. 포럼 공개 예시 기준 호출 형태는 다음과 같다.

```python
response = requests.get(
    f"{BASE_URL}/hwp/hwp2hwpx",
    params={"file_path": result_key},
    cookies=cookies,
)
result = response.json()
```

다만 이 API는 라이선스에 따라 제공 여부가 갈린다. 실제 포럼 사례에서는 `F051`, `LICENSE_INVALID` 응답이 발생했고, 한컴 측 답변은 보유 라이선스에 따라 제공 API가 다를 수 있으므로 지원센터를 통해 라이선스를 확인하라는 내용이다.

## 오픈 소스 확인 결과

개발자센터의 오픈 소스 목록에는 HWP -> HWPX 변환기 소스가 직접 제공되지는 않는다. 확인된 항목은 다음 성격이다.

- `hwpx-owpml-model`: OWPML/HWPX 구조 모델
- `metatag-ex`: HWPX 메타태그 추출
- `dvc`: HWPX 유효성 검사
- `hwpx-contents-extract`: HWPX 내용 추출 예제

즉 한컴 공식 오픈 소스는 HWPX 처리/검증/추출 쪽이고, HWP 바이너리에서 HWPX로 변환하는 공개 소스는 개발자센터 오픈 소스 목록에는 보이지 않는다.

## 별도 공개 Java 변환 라이브러리

공식 한컴 개발자센터 오픈 소스는 아니지만, 공개 Java 라이브러리 `neolord0/hwp2hwpx`가 있다. README 기준 사용 흐름은 다음과 같다.

```java
HWPFile fromFile = HWPReader.fromFile(InputFilePath);
HWPXFile toFile = Hwp2Hwpx.toHWPX(fromFile);
HWPXWriter.toFilepath(toFile, OutputFilePath);
```

이 라이브러리는 `hwplib`, `hwpxlib` 및 한컴이 공개한 HWP 5.0/OWPML 문서를 기반으로 한다.

## 로컬 라우터 상태

로컬 라우터 점검 결과는 `tmp/hancom_devcenter_hwp2hwpx_check/router_preflight.json`에 저장했다.

요약:

- `standalone`: 사용 가능, 검증됨. 단, 텍스트 중심 HWPX 재구성이라 원본 레이아웃 보존은 제한됨.
- `official_converter`: `HwpConverter.exe` 후보는 있으나 공식 HWPX Converter Add-in 설치 증거가 없어 실행 불가.
- `sdk`: Hwp SDK는 라이선스/설치 확인 필요.
- `com`: HWP Open은 가능하나 HWPX SaveAs 타임아웃으로 차단.
- `local_gui`: 저장 대화상자 탐지 실패로 차단.
- `user_present`: 수동 fallback 가능하지만 무인 배치 변환 경로는 아님.

## 결론

개발자센터에서 확인 가능한 HWP -> HWPX 경로는 소스 코드가 아니라 `통합문서뷰어 DocsConverter API` 계약이다. 핵심 엔드포인트는 공개 예시 기준 `/hwp/hwp2hwpx`이며, 사용 가능 여부는 라이선스에 묶인다.

현재 이 저장소의 안정적인 자동 경로는 `scripts/hwpx/hwp_to_hwpx_standalone.py`의 독립 변환기다. 공식 한컴 품질/레이아웃 보존 경로를 쓰려면 다음 중 하나가 필요하다.

1. 통합문서뷰어 라이선스에서 `/hwp/hwp2hwpx` 사용 가능 여부 확인
2. 공식 HWPX Converter Add-in 설치 후 로컬 `official_converter` 재탐지
3. Hwp SDK 라이선스/샘플 API 확보 후 `sdk` provider 구현

## 참고 링크

- 한컴 개발자센터 문서 변환 API: https://developer.hancom.com/docsconverter/guide/api
- 한컴 개발자센터 변환 모듈/API: https://developer.hancom.com/docsconverter/guide/api/module
- 한컴 개발자센터 오픈 소스: https://developer.hancom.com/opensources
- 한컴 FAQ HWPX 변환기: https://www2.hancom.com/support/faqCenter/faq/detail/3128
- 포럼 HWP -> HWPX API 라이선스 오류: https://forum.developer.hancom.com/t/hwp-hwpx-api/2980
- 포럼 HWP 포맷 Export 지원 범위: https://forum.developer.hancom.com/t/hwp-hwpx/3017
- 공개 Java hwp2hwpx: https://github.com/neolord0/hwp2hwpx
