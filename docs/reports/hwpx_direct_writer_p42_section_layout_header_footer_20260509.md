# HWPX Direct Writer P42 Section Layout Header Footer

## 목적

멀티 섹션 HWPX 생성 이후 각 섹션에 서로 다른 용지 설정, 머리말, 꼬리말, 시작 쪽 번호를 적용할 수 있는지 검증했다.

이번 단계는 한컴 실행 없이 HWPX ZIP/XML을 직접 수정하는 direct writer 기능 확장이다.

## 구현

### Composer

- `page_layouts` 배열 지원 추가
- `page_numberings` 배열 지원 추가
- 기존 단일 `page_layout`, `page_numbering` 입력과 호환 유지
- visible header/footer 텍스트를 expected value 검증 대상에 자동 포함

### Schema

- 단일/배열 레이아웃 스펙 검증 분리
- 단일/배열 page numbering 스펙 검증 분리
- `page_layouts`, `page_numberings` count 반영

### Audit

- 섹션별 page layout inspect 결과 추가
- 섹션별 page numbering inspect 결과 추가
- manifest/spine/preview/metadata/section 검증과 함께 확인 가능

### Regression

새 golden profile을 추가했다.

```text
section_layout_header_footer
```

검증 내용:

- section count 3
- section 0 portrait layout
- section 1 landscape layout
- section 2 portrait layout
- section별 startNum 생성
- section별 visible header/footer text 생성
- strict package audit PASS

## 직접 Compose 검증

대상:

```text
tmp/hwpx_p42_section_layout/section_layout_header_footer_direct.hwpx
```

결과:

```text
compose status: PASS
schema status: PASS
sections: 3
page_layout count: 3
page_numbering count: 3
missing expected values: []
warnings: []
```

Strict audit:

```text
status: PASS
section_entries: 3
manifest_spine: PASS
metadata: PASS
preview_text: PASS
sections_inspect: PASS
page_layouts: PASS, PASS, PASS
page_numberings: PASS, PASS, PASS
```

## Regression Suite

명령:

```text
python scripts/hwpx/hwpx_compose_regression.py run --template smoke-test.hwpx --out-dir tmp/hwpx_p42_section_layout_regression --strict
```

결과:

```text
status: PASS
profile_count: 5
pass_count: 5
warn_count: 0
fail_count: 0
```

Profile 결과:

| Profile | Result |
| --- | --- |
| metadata_text_table | PASS |
| page_header_footer | PASS |
| image_chart | PASS |
| multi_section | PASS |
| section_layout_header_footer | PASS |

## Java Parser Roundtrip

대상:

```text
tmp/hwpx_p42_section_layout/section_layout_header_footer_direct.hwpx
tmp/hwpx_p42_section_layout_regression/section_layout_header_footer.hwpx
```

결과:

| File | Parse | Paragraphs | Tables | Diagnostics | Quality | Missing Expected |
| --- | --- | ---: | ---: | --- | ---: | --- |
| section_layout_header_footer_direct.hwpx | PASS | 6 | 0 | true | 7 | 0 |
| section_layout_header_footer.hwpx | PASS | 6 | 0 | true | 7 | 0 |

Java 실행 중 기존과 동일하게 Log4j rolling file appender 권한 경고가 출력됐지만, `HwpxParser.parse()` 결과는 모두 PASS였다.

## 제한

- 현재 visible header/footer는 정적 텍스트 기반이다.
- native dynamic page field는 아직 guard 상태로 유지한다.
- 한컴 GUI 시각 확인은 수행하지 않았다.

## 결론

P42 판정:

```text
PASS
```

HWPX direct writer는 이제 다음 범위를 지원한다.

```text
multi-section generation
section-specific page layout
section-specific visible header/footer
section-specific start page numbering
strict package audit
regression suite coverage
Java parser roundtrip
```

## 다음 단계

1. P43: DocumentBuilder multi-section API 정리
2. P44: section-aware image/table placement regression
3. P45: API layer compose endpoint hardening
