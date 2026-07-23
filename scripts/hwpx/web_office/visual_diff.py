"""WEB-OFFICE-VISUAL-DIFF — M0 검증 하네스 (지시문 8장).

한컴 실렌더 PNG(이미 확보된 truth 캐시)를 기준 이미지로 삼아, 브라우저에
띄운 좌표 렌더러 출력을 페이지 단위로 스크린샷 → 픽셀 diff 계산한다.

지시문 원칙 준수:
  - 완료 기준은 "diff 비율 X% 이하"(육안 확인 아님)
  - 기준 이미지는 한컴 실제 렌더(truth cache) — 별도 준비 불필요(이미 존재)
  - Playwright/pixelmatch 대신 이 저장소 기존 스택(CDP+PIL+numpy)으로 동일
    기능(스크린샷·diff%·diff 하이라이트 이미지) 구현 — 신규 툴체인 미도입

read-only — 원본 무수정. 서버(uvicorn)와 CDP(headless chrome)가 떠 있어야
동작한다(사용법: run_diff(cdp_port, http_base, source_path, out_dir)).
"""
from __future__ import annotations

import base64
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    import numpy as np
    from PIL import Image
    _DEPS_OK = True
except Exception:  # noqa: BLE001
    _DEPS_OK = False

DIFF_THRESHOLD = 24          # 0-255 채널차 — 이 이상이면 '다른 픽셀'
PASS_DIFF_PCT = 1.0          # 완료 기준(9장 M7): 페이지당 diff < 1%
STRUCT_PASS_PCT = 1.0        # 구조 diff 합격선(9장 M7 갱신) — 이 이하면 통과


class _CDP:
    """최소 CDP 클라이언트 — websocket 1개 세션 재사용."""

    def __init__(self, port: int):
        import websocket  # 지연 임포트(선택 의존성)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
        tab = json.load(urllib.request.urlopen(req, timeout=10))
        self.ws = websocket.create_connection(
            tab["webSocketDebuggerUrl"], timeout=120)
        self._id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps(
            {"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                return msg.get("result", {})

    def navigate(self, url: str) -> None:
        self.call("Page.enable")
        self.call("Runtime.enable")
        self.call("Page.navigate", {"url": url})

    def eval_js(self, expr: str) -> Any:
        r = self.call("Runtime.evaluate",
                       {"expression": expr, "returnByValue": True})
        return r.get("result", {}).get("value")

    def screenshot_png(self) -> bytes:
        data = self.call("Page.captureScreenshot", {"format": "png"})["data"]
        return base64.b64decode(data)

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass


def _wait_loaded(cdp: _CDP, timeout_s: int = 240) -> str:
    """좌표 레이아웃 로드 완료까지 대기 — **자체 렌더링**(우리 텍스트·테두리)
    상태를 캡처한다. truth 배경 모드(한컴 PNG 그대로 표시)로 대체될 때까지
    기다리면 '한컴 사진을 CSS 배경으로 되돌려 보여준 것 vs 그 사진 자체'를
    비교하는 순환 검증이 된다(남는 차이는 브라우저 이미지 리스케일 아티팩트
    일 뿐, 우리 엔진의 진짜 정합도가 아님). 이 하네스가 재려는 것은 지시문
    M3/M4 목표 그대로 — **자체 계산 레이아웃**이 한컴 실제 배치와 얼마나
    맞는가이므로, probeTruth 의 비동기 배경 전환 이전 상태를 그대로 쓴다."""
    for _ in range(timeout_s):
        st = cdp.eval_js(
            "(document.querySelector('.wo-status')||{}).textContent||''")
        if st and ("품질" in st or "실패" in st):
            return st
        time.sleep(1)
    return ""


def _page_diff(expected: "Image.Image", actual: "Image.Image"
               ) -> tuple[float, "Image.Image"]:
    """두 PNG 픽셀 diff% + 하이라이트 이미지.

    리사이즈 금지 — 텍스트가 대부분인 문서 페이지는 1px 리사이즈만으로도
    글자 가장자리 전체가 블러돼(재표본화) 거의 모든 글자가 '다른 픽셀'로
    오탐된다(실사례: 793x1122→794x1123 리사이즈로 diff 7%대 허위 발생).
    크롭 단계에서 이미 expected 와 정확히 같은 픽셀 크기로 잘라야 한다."""
    w, h = expected.size
    if actual.size != (w, h):
        # 리샘플 없는 캔버스 정합 — 부족분은 흰 배경으로 패딩, 여유분은 절삭.
        # (1px 리사이즈조차 텍스트 가장자리를 블러시켜 대량 오탐을 만든다.)
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        canvas.paste(actual.convert("RGB"), (0, 0))
        actual = canvas
    a = np.asarray(expected.convert("RGB"), dtype=np.int16)
    b = np.asarray(actual.convert("RGB"), dtype=np.int16)
    diff = np.abs(a - b).max(axis=2)
    bad = diff > DIFF_THRESHOLD
    pct = round(100.0 * bad.sum() / bad.size, 3)
    overlay = np.asarray(expected.convert("RGB")).copy()
    overlay[bad] = [255, 0, 0]
    struct_pct = _struct_diff_pct(expected, actual)
    return pct, struct_pct, Image.fromarray(overlay)


STRUCT_BIN_CUTOFF = 128      # 이진화 임계(휘도 0-255) — 이보다 어두우면 잉크
STRUCT_DILATE_PX = 1         # 이진화 후 각 잉크 화소를 이만큼 팽창(1px 잔여
# 정렬 오차 흡수) — 그래도 남는 불일치만 실제 구조 결함으로 카운트.


def _struct_diff_pct(expected: "Image.Image", actual: "Image.Image") -> float:
    """구조 diff — 양쪽을 흑/백으로 이진화한 뒤 비교한 diff%.

    지시문 8.2 완료기준 갱신 — 순수 픽셀 diff(위 pct)는 폰트 힌팅·안티앨리
    어싱 차이만으로도 5~20%까지 오르내려(실측: 별지5 행별 5~18%) fixture
    마다 "몇 %면 통과인가"를 매번 재판단해야 했다.
    시도 1(가우시안 블러)·시도 2(블록 다운샘플 평균)는 둘 다 실패했다 —
    텍스트는 고주파 콘텐츠라 스무딩 계열은 미세한 1px 정렬차를 상쇄시키기
    는커녕 더 넓은 영역으로 번지게 해 diff%를 오히려 올렸다(6.6%→9~15%,
    실측 확인). 이진화는 다르다 — AA 의 회색 중간값을 흑/백 중 하나로
    강제 수렴시키므로, 같은 글자가 1px 안팎으로 어긋나 있어도 이진화 후엔
    대부분 같은 칸에서 만난다. 그래도 남는 불일치(팽창 후에도 어긋남)만
    누락·오배치 같은 진짜 구조 결함이다."""
    e = np.asarray(expected.convert("L")) < STRUCT_BIN_CUTOFF
    a = np.asarray(actual.convert("L")) < STRUCT_BIN_CUTOFF
    h, w = e.shape
    a = a[:h, :w] if a.shape[0] >= h and a.shape[1] >= w else np.pad(
        a, ((0, max(0, h - a.shape[0])), (0, max(0, w - a.shape[1]))))
    d = STRUCT_DILATE_PX
    if d > 0:
        ep = np.pad(e, d, constant_values=False)
        ap = np.pad(a, d, constant_values=False)
        e_dil = np.zeros_like(e)
        a_dil = np.zeros_like(a)
        for dy in range(-d, d + 1):
            for dx in range(-d, d + 1):
                e_dil |= ep[d + dy:d + dy + h, d + dx:d + dx + w]
                a_dil |= ap[d + dy:d + dy + h, d + dx:d + dx + w]
    else:
        e_dil, a_dil = e, a
    # 팽창된 서로의 잉크 영역과 전혀 안 겹치는 잉크만 '진짜 다름'
    bad = (e & ~a_dil) | (a & ~e_dil)
    return round(100.0 * bad.sum() / bad.size, 3)


def run_diff(cdp_port: int, http_base: str, source_rel: str,
             truth_dir: Path, out_dir: Path,
             page_w_css: int = 1400) -> dict[str, Any]:
    """fixture 1건 시각 회귀 — 반환: {path, pages, perPage:[{page,diffPct}], ok}."""
    if not _DEPS_OK:
        return {"path": source_rel, "ok": False, "error": "MISSING_DEPS"}
    truths = sorted(truth_dir.glob("p*.png"),
                     key=lambda p: int(p.stem[1:]))
    if not truths:
        return {"path": source_rel, "ok": False, "error": "NO_TRUTH_CACHE"}
    out_dir.mkdir(parents=True, exist_ok=True)

    cdp = _CDP(cdp_port)
    try:
        url = (f"{http_base}/web-office/weboffice.html#load="
               + urllib.parse.quote(source_rel, safe=""))
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": page_w_css, "height": 1400,
            "deviceScaleFactor": 1, "mobile": False})
        # truth-page 요청 자체를 차단 — probeTruth() 는 로컬 캐시라 매우
        # 빨라(수십ms) 경쟁으로 자체 렌더링 캡처를 보장할 수 없다. 요청을
        # 실패시켜 app.mjs 의 실패 폴백(truthBase=null 유지)을 강제한다 —
        # 이 하네스가 재려는 것은 '한컴 사진 되돌려 보여주기'가 아니라
        # 우리 엔진의 자체 계산 레이아웃이므로 truth 배경은 애초에 필요없다.
        cdp.call("Network.enable")
        cdp.call("Network.setBlockedURLs",
                 {"urls": ["*truth-page*"]})
        cdp.navigate(url)
        status = _wait_loaded(cdp)
        time.sleep(0.3)   # DOM reflow 안정화
        n_pages = cdp.eval_js(
            "document.querySelectorAll('.co-page').length") or 0
        own_render = cdp.eval_js(
            "document.querySelectorAll('.co-line').length > 0")

        per_page = []
        for i, truth_png in enumerate(truths):
            if i >= n_pages:
                per_page.append({"page": i + 1, "diffPct": 100.0,
                                  "note": "PAGE_MISSING_IN_VIEWER"})
                continue
            rect = cdp.eval_js(
                f"(()=>{{const p=document.querySelectorAll('.co-page')[{i}];"
                "const r=p.getBoundingClientRect();"
                "return {x:r.left,y:r.top,w:r.width,h:r.height};})()")
            if not rect or rect["w"] <= 0:
                per_page.append({"page": i + 1, "diffPct": 100.0,
                                  "note": "NO_RECT"})
                continue
            cdp.call("Emulation.setDeviceMetricsOverride", {
                "width": page_w_css,
                "height": int(rect["y"] + rect["h"] + 20),
                "deviceScaleFactor": 1, "mobile": False})
            png_bytes = cdp.screenshot_png()
            full = Image.open(__import__("io").BytesIO(png_bytes))
            expected0 = Image.open(truth_png)
            # round() 사용(int truncation 은 최대 1px 원점 오차) + expected
            # 의 정확한 픽셀 크기로 잘라 _page_diff 의 패딩/절삭 분기를 최소화.
            x0, y0 = round(rect["x"]), round(rect["y"])
            crop = full.crop((x0, y0, x0 + expected0.width,
                               y0 + expected0.height))
            pct, struct_pct, overlay = _page_diff(expected0, crop)
            diff_path = out_dir / f"p{i+1}_diff.png"
            overlay.save(diff_path)
            per_page.append({"page": i + 1, "diffPct": pct,
                              "structDiffPct": struct_pct,
                              "diffImage": str(diff_path)})
        # 합격 기준(9장 M7 갱신) — 구조 diff(AA 노이즈 제거) 기준으로 판정.
        # 순수 픽셀 diff(diffPct)는 참고용 — 폰트 힌팅만으로 5~20% 오르내려
        # fixture 마다 통과선을 따로 잡아야 했다.
        ok = bool(per_page) and all(
            p.get("structDiffPct", 100.0) <= STRUCT_PASS_PCT
            for p in per_page)
        return {"path": source_rel, "pages": n_pages, "status": status,
                "ownRender": own_render, "perPage": per_page, "ok": ok}
    finally:
        cdp.close()
