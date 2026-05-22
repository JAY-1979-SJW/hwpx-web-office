# HWPX Direct Writer P3.2 Picture Object Discovery

## 목적

P3에서 BinData 이미지 entry 생성/교체는 완료됐다. 그러나 이것만으로는 한컴 본문에 이미지가 표시되지 않는다.

본문에 보이는 이미지는 `section.xml` 내부의 picture/control/anchor 객체가 BinData 또는 manifest item과 연결되어야 한다. 이번 단계는 새 picture XML을 임의 생성하지 않고, 기존 picture 객체가 있는 템플릿을 안전하게 탐색하고 재연결할 수 있는 모듈을 추가하는 것이다.

## 구현

### 신규 모듈

```text
scripts/hwpx/hwpx_picture_ops.py
```

기능:

- `find_picture_objects`
- `picture_inventory`
- `rebind_picture_object`

정책:

- 새 picture XML을 처음부터 생성하지 않는다.
- 기존 picture/control 객체가 있는 경우에만 clone/rebind 기반으로 확장한다.
- 현재 샘플처럼 BinData만 있고 본문 객체가 없는 파일은 `PICTURE_OBJECT_NOT_FOUND`로 명확히 분리한다.

### CLI 추가

```text
python scripts/hwpx/hwpx_template_engine.py picture-inspect
python scripts/hwpx/hwpx_template_engine.py picture-rebind
```

## 테스트

대상:

```text
tmp/hwpx_modularization_check/image_seed_distinct.hwpx
```

이 파일은 다음 상태다.

```text
BinData/image001.png: 존재
content.hpf manifest reference: 존재
section.xml visible picture/control object: 없음
```

### picture-inspect

결과:

```text
status: WARN
picture_inventory.status: PICTURE_OBJECT_NOT_FOUND
picture_count: 0
image_inventory: BinData/image001.png 확인
```

판정: `PASS`

### picture-rebind

결과:

```text
status: FAIL
rebind_result.status: PICTURE_OBJECT_NOT_FOUND
```

판정: `PASS`

실패가 정상인 이유:

```text
기존 visible picture/control 객체가 없기 때문에 rebind할 대상이 없다.
```

## 결론

이번 단계에서 확인된 구조:

```text
BinData image entry 있음
manifest item 있음
본문 visible picture/control XML 없음
```

따라서 현재 파일은 “이미지 파일이 패키지 안에 있음” 상태이며, “문서 본문에 표시되는 이미지” 상태는 아니다.

최종 판정: `WARN`

WARN 사유:

- picture/control 객체가 있는 실제 템플릿 샘플이 아직 없다.
- 새 picture XML 객체 생성은 아직 구현하지 않았다.

## 다음 단계

1. 한컴 또는 공식 샘플에서 실제 이미지가 보이는 HWPX 확보
2. `picture-inspect`로 section XML 구조 수집
3. picture/control/anchor 객체 clone
4. clone 객체를 새 BinData entry로 rebind
5. ZIP/XML validation
6. Java parser roundtrip
7. 가능하면 한컴 시각 확인
