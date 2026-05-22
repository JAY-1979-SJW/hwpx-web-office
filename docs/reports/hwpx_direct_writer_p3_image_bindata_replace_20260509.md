# HWPX Direct Writer P3 Image BinData Replace

## 목적

HWPX direct writer/editor에서 한컴 실행 없이 기존 HWPX 내부의 `BinData` 이미지 파일을 교체할 수 있는지 검증한다.

이번 P3는 새 이미지 객체를 생성하는 단계가 아니다. 기존 HWPX 템플릿에 이미 존재하는 이미지 참조 구조를 유지한 채, 해당 `BinData` 파일만 교체하는 방식으로 제한했다.

## 기준

- 기준 HEAD: `5f7fd8d1b7185a12c89fadb537ae2fe194d266c4`
- 한컴 실행: 없음
- 한컴 COM/GUI 사용: 없음
- HWP 변환: 없음
- 원본 HWPX 수정: 없음
- tmp 산출물 stage: 없음

## 구현

### `hwpx_image_ops.py`

P3 이후 이미지 관련 로직을 별도 모듈로 분리했다.

역할:

- 이미지 확장자 및 media type 정의
- `BinData` 이미지 entry 탐색
- 이미지 inventory 생성
- XML reference count 계산
- 기존 이미지 data 교체
- `BinData` 이미지 data 추가
- `Contents/content.hpf` manifest item 보강 시도

`hwpx_writer_adapter.py`는 기존 public method를 유지하고, 내부 구현만 `hwpx_image_ops.py`로 위임한다.

### `hwpx_writer_adapter.py`

추가 기능:

- `list_images()`
- `replace_image(image_index, replacement_path)`
- `replace_image_by_entry(entry_name, replacement_path)`

이미지 inventory 필드:

- `index`
- `entry_name`
- `extension`
- `size`
- `sha256`
- `referenced_by_xml`
- `reference_count`

교체 검증 필드:

- `old_size`
- `new_size`
- `old_sha256`
- `new_sha256`
- `hash_changed`
- `xml_refs_before`
- `xml_refs_after`
- `xml_refs_preserved`

### `hwpx_template_engine.py`

추가 CLI:

```text
image-seed
image-replace
```

지원 옵션:

```text
--template
--output
--image-index
--image-entry
--replacement
--validate
--report-json
```

규칙:

- `image-seed`는 기존 HWPX 패키지에 `BinData` 이미지 entry를 추가
- `--image-index`와 `--image-entry` 중 하나만 허용
- replacement 파일이 없으면 `REPLACEMENT_NOT_FOUND`
- 기존 `BinData` 이미지가 없으면 `IMAGE_NOT_FOUND`
- 기존 이미지와 replacement 확장자가 다르면 `IMAGE_EXTENSION_MISMATCH`
- `image-replace`는 XML 참조 변경을 하지 않음

## 이미지 템플릿 탐색 결과

repo 및 tmp 전체의 HWPX를 조사했지만, `BinData/` 하위에 이미지 확장자를 가진 HWPX 후보를 찾지 못했다.

```text
non-tmp image_template_candidates: 0
all image_template_candidates: 0
```

따라서 실제 `IMAGE_REPLACE_PASS` 케이스는 이번 환경에서 실행할 수 없었다.

이후 사용자 지시에 따라, 시각 표시 객체 생성이 아닌 **패키지 내부 `BinData` 이미지 entry 생성** 방식으로 seed HWPX를 만들어 교체 파이프라인을 검증했다.

## 테스트

### replacement PNG 생성

외부 라이브러리 없이 1x1 PNG 2개를 생성했다.

```text
tmp/hwpx_image_replace_poc/seed_marker.png
size: 69 bytes

tmp/hwpx_image_replace_poc/replacement_marker.png
size: 69 bytes
```

### image seed 생성

대상:

```text
smoke-test.hwpx
```

명령:

```text
python scripts/hwpx/hwpx_template_engine.py image-seed --template smoke-test.hwpx --output tmp\hwpx_image_replace_poc\image_seed.hwpx --image tmp\hwpx_image_replace_poc\seed_marker.png --image-entry BinData/image001.png --validate --report-json tmp\hwpx_image_replace_poc\image_seed_report.json
```

결과:

```text
status: PASS
entry: BinData/image001.png
seed image sha256: b1ff9c8ea3a780bad09b346c423d2d0e46815926879b18e841d928376a946640
ZIP/XML validation: PASS
```

판정:

```text
IMAGE_BINDATA_ADD_PASS
```

주의:

```text
이 seed는 패키지 내부 BinData entry를 추가한 것이다.
HWPX 본문에 실제로 보이는 anchored picture XML 객체를 생성한 것은 아니다.
```

### image replace 실행

명령:

```text
python scripts/hwpx/hwpx_template_engine.py image-replace --template tmp\hwpx_image_replace_poc\image_seed.hwpx --output tmp\hwpx_image_replace_poc\image_replaced.hwpx --image-index 0 --replacement tmp\hwpx_image_replace_poc\replacement_marker.png --validate --report-json tmp\hwpx_image_replace_poc\image_replace_report.json
```

결과:

```text
status: PASS
entry: BinData/image001.png
old sha256: b1ff9c8ea3a780bad09b346c423d2d0e46815926879b18e841d928376a946640
new sha256: fce481932ea5d07a91c7991c09fdadb4bf78f9b4cc8f927188384231f9d12679
hash_changed: true
xml_refs_preserved: true
ZIP/XML validation: PASS
```

판정:

```text
IMAGE_REPLACE_PASS
```

### Failure Case A: 이미지 없는 HWPX

명령:

```text
python scripts/hwpx/hwpx_template_engine.py image-replace --template smoke-test.hwpx --output tmp\hwpx_image_replace_poc\fail_no_image.hwpx --image-index 0 --replacement tmp\hwpx_image_replace_poc\replacement_marker.png --validate --report-json tmp\hwpx_image_replace_poc\fail_no_image_report.json
```

결과:

```text
status: FAIL
replace_result.status: IMAGE_NOT_FOUND
image_count: 0
output created: false
```

판정:

```text
PASS as failure handling
```

### Failure Case B: replacement 파일 없음

명령:

```text
python scripts/hwpx/hwpx_template_engine.py image-replace --template smoke-test.hwpx --output tmp\hwpx_image_replace_poc\fail_missing_replacement.hwpx --image-index 0 --replacement tmp\hwpx_image_replace_poc\not_exists.png --validate --report-json tmp\hwpx_image_replace_poc\fail_missing_replacement_report.json
```

결과:

```text
status: FAIL
error: REPLACEMENT_NOT_FOUND
output created: false
```

판정:

```text
PASS as failure handling
```

## Java Parser Roundtrip

대상:

```text
tmp/hwpx_image_replace_poc/image_replaced.hwpx
```

결과:

```text
parse_status: PASS
paragraph_count: 1
table_count: 0
semantic_sections_count: 0
extracted_fields_count: 0
diagnostics_exists: true
quality_score: 7
```

Log4j file appender 권한 경고가 출력됐지만 parser 결과 JSON은 정상 생성됐다.

## 결과

```text
P3 status: PASS_WITH_LIMITATION
```

성공한 것:

- 이미지 처리 모듈화 (`hwpx_image_ops.py`)
- 이미지 inventory API 구현
- 기존 이미지 BinData 교체 API 구현
- `image-seed` CLI 구현
- `image-replace` CLI 구현
- replacement PNG 생성
- package-level `BinData` 이미지 entry 생성
- `BinData` 이미지 교체
- hash 변경 확인
- XML refs 유지 확인
- ZIP/XML validation
- Java parser roundtrip
- `IMAGE_NOT_FOUND` 실패 케이스 처리
- `REPLACEMENT_NOT_FOUND` 실패 케이스 처리
- 실패 시 output HWPX 미생성 확인

미완료:

- 한컴 시각 확인
- 본문에 보이는 anchored picture XML 객체 생성
- 기존 이미지 참조가 있는 실제 템플릿에서의 교체

## 제한

- 기존 이미지 참조가 있는 HWPX 템플릿이 필요하다.
- 이번 단계는 `BinData` entry 생성/교체까지만 지원한다.
- 본문에 실제 표시되는 새 이미지 객체 생성은 아직 미구현이다.
- 이미지 배치, 크기, anchor 변경은 후속 단계다.

## 다음 단계

1. 이미지가 포함된 HWPX 템플릿 확보
2. `image-replace` 실제 교체 실행
3. ZIP/XML validation
4. Java parser roundtrip
5. P4: 그래프 PNG 생성 후 기존 이미지 자리 교체
6. 후속: 새 이미지 객체 생성 구조 분석
