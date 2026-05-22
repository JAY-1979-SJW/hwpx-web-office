# HWPX Direct Writer P3.3 Picture Clone Rebind

## 목적

P3.2에서 visible picture/control 객체 탐색과 rebind 기능을 추가했다.

이번 단계는 실제 이미지가 보이는 HWPX 템플릿을 확보했을 때, 기존 picture 객체를 clone하고 새 BinData entry로 연결하는 기능을 추가하는 것이다.

## 구현

### 모듈

```text
scripts/hwpx/hwpx_picture_ops.py
```

추가 기능:

```text
clone_picture_object
```

동작:

```text
1. 기존 visible picture/control 객체 탐색
2. 대상 picture 객체 deep clone
3. clone 내부 이미지 참조 attribute를 새 BinData entry 또는 manifest id로 rebind
4. 원본 picture 객체 바로 뒤에 삽입
5. XML 저장
```

주의:

```text
새 picture XML을 처음부터 생성하지 않는다.
기존 한컴이 만든 picture/control/anchor 구조를 clone하는 방식만 허용한다.
```

### CLI

```text
python scripts/hwpx/hwpx_template_engine.py picture-clone-rebind
```

옵션:

```text
--template
--output
--picture-index
--image-entry
--manifest-id
--validate
--report-json
```

## 테스트

현재 사용 가능한 샘플:

```text
tmp/hwpx_modularization_check/image_seed_distinct.hwpx
```

이 파일 상태:

```text
BinData/image001.png 있음
content.hpf manifest item 있음
visible picture/control 객체 없음
```

따라서 clone 성공 테스트는 아직 불가능하다.

실행 결과:

```text
status: FAIL
clone_result.status: PICTURE_OBJECT_NOT_FOUND
picture_count: 0
```

판정:

```text
failure path PASS
```

## 결론

기능 구현은 완료됐다.

현재 성공 조건:

```text
visible picture/control 객체가 있는 HWPX 템플릿 필요
```

현재 판정: `WARN`

WARN 사유:

```text
성공 케이스를 검증할 visible picture template이 아직 없다.
```

## 다음 단계

1. 한컴에서 이미지 1개가 실제로 보이는 HWPX 템플릿 생성
2. `picture-inspect`로 객체 구조 확인
3. `image-seed`로 새 BinData 추가
4. `picture-clone-rebind`로 새 이미지 객체 삽입
5. ZIP/XML validation
6. Java parser roundtrip
7. 한컴 시각 확인
