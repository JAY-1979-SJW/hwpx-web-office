# Web Office Viewer — 브라우저 Runtime Smoke 가이드

> 공정명: WEB-OFFICE-BROWSER-RUNTIME-SMOKE-01
> 기준 HEAD: `9818fc2`
> 분류: §11-1 ⑤ 감리검사 (runtime smoke)
> 본 문서는 RO-VIEW 프로토타입을 실제 브라우저 또는 headless 환경에서
> 검증하는 절차를 정착시킨다. 편집/save/writer/output 은 일절 없다.

---

## 1. 산출물

- `frontend/web_office_viewer/payload.sample.json` — 0018 샘플로 빌드한
  read-only RenderPayload (sourceRef.sha256 포함, editable=false 고정)
- `frontend/web_office_viewer/index.html` — fetch("./payload.json") 또는
  `?fixture=payload.sample.json` 로 fixture 로드
- `frontend/web_office_viewer/runtime_smoke.mjs` — node 단독 smoke
- `scripts/ops/audit_web_office_browser_runtime_smoke.py` — 정적 server +
  DOM 검증 감사
- `tests/test_web_office_browser_runtime_smoke.py` — 계약 잠금

---

## 2. 실 브라우저에서 보는 방법 (수동)

```bash
# 1) 같은 디렉토리에 payload.sample.json 을 payload.json 으로 복사
cd frontend/web_office_viewer
cp payload.sample.json payload.json    # PowerShell: Copy-Item

# 2) 정적 서버 띄우기 (Python 기본)
python -m http.server 8765

# 3) 브라우저에서 열기
#    http://localhost:8765/
```

`index.html` 은 `fetch("./payload.json")` 로 fixture 를 로드하고
`renderPayloadToHTML(payload)` 결과를 `#root` 에 마운트한다.

> 주의: `payload.json` 은 .gitignore 처리될 가능성이 있어 본 단지는
> `payload.sample.json` 으로 영구 보관한다. 수동 smoke 전에 복사하거나
> `index.html` 내부의 fetch 경로를 `./payload.sample.json` 으로 임시
> 수정한다. (편집 commit 은 금지)

---

## 3. 자동 smoke (node 단독)

```bash
node frontend/web_office_viewer/runtime_smoke.mjs
```

`payload.sample.json` 을 viewer_core 로 렌더하고 HTML 을 stdout 으로
출력한다. JS 실행만 검증한다.

---

## 4. 자동 smoke (정적 server + DOM 파싱)

```bash
python scripts/ops/audit_web_office_browser_runtime_smoke.py
```

내부에서 수행:

1. `http.server` 를 `frontend/web_office_viewer` 위에 띄움 (랜덤 포트)
2. `GET /index.html` 응답 200 + Content-Length>0
3. `GET /payload.sample.json` 응답 200 + 유효 JSON + editable=false +
   sourceRef.sha256 존재 + warnings 키 존재
4. `node runtime_smoke.mjs` 실행 → HTML 획득 → BeautifulSoup 파싱
5. DOM 검증:
   - `.wo-toolbar` / `.wo-left-panel` / `.wo-center` / `.wo-right-panel`
     각 1개 이상
   - `<table class="wo-table">` ≥ 1
   - `.wo-paragraph` ≥ 1
   - `<td class="wo-cell">` ≥ 1
   - rowspan 또는 colspan 속성 ≥ 1 (병합 셀)
   - `<input>` / `<textarea>` / `contenteditable="true"` 0건
   - save/apply 류 버튼 0건 (`button[onclick]` 자체 0건)
   - `data-editable="false"` 다수 부착
6. 원본 HWPX sha256/mtime 사전=사후 동일

---

## 5. 검증 항목 매핑 (시방서 ↔ 산출물)

| 시방서 검증 | 산출물 |
|-------------|--------|
| payload.json fetch 가능 | `http.server` GET 200 (audit step 3) |
| index.html smoke PASS | GET 200 + bytes>0 |
| paragraph 렌더 | `.wo-paragraph` count ≥1 |
| table/cell 렌더 | `<table>` + `<td.wo-cell>` count ≥1 |
| merged cell 렌더 | rowspan/colspan attr ≥1 |
| read-only DOM | input/textarea/contenteditable=true 0건 |
| edit/save/apply 요소 | save/apply/onclick 0건 |
| writer/output 생성 | 본 공정 파일·실행 결과로 .hwpx 0건 |
| 원본 HWPX 무변경 | sha256/mtime 사전=사후 게이트 |
| audit PASS | `verdict=="PASS"` |
| pytest PASS | 계약 테스트 전부 |
| git diff --check | clean |

---

## 6. 안전장치

- **JS 실행 방식**: node 또는 브라우저. Python urllib 만으로는 fetch().then()
  의 결과를 검증할 수 없으므로, audit 은 viewer_core 를 node 로 호출해
  HTML 을 별도 얻어 DOM 파싱한다. http.server smoke 는 자원 수령
  (200 + payload 유효성) 만 검증한다.
- **수동 smoke 시 복사본 사용**: `payload.json` 은 ignore 대상. 수동
  smoke 후 복사본은 폐기. 영구 fixture 는 `payload.sample.json` 만.
- **Playwright**: 본 단지 PC 에 chrome-headless-shell 바이너리 부재.
  설치는 별도 ops 공정으로 분리. 본 공정은 BeautifulSoup + node 조합
  으로 시방서 검증 완료.

---

*생성: WEB-OFFICE-BROWSER-RUNTIME-SMOKE-01 (2026-05-20)*

> **저장소 분리 기준**: e04d325 (hwpx-web-office 신규 저장소 초기 커밋, 2026-05-22)
