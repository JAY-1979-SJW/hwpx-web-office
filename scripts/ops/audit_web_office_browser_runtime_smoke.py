"""WEB-OFFICE-BROWSER-RUNTIME-SMOKE-01 감사 스크립트.

frontend/web_office_viewer/ 의 RO-VIEW viewer 를 다음 방식으로 검증:
- 정적 http.server 띄워 index.html / payload.sample.json GET 200 확인
- node 로 runtime_smoke.mjs 실행해 HTML 획득 후 BeautifulSoup 파싱
- 4 영역 (toolbar/left/center/right) + paragraph/table/cell/merged 렌더
- input/textarea/contenteditable/save/apply 0건
- payload.sample.json sourceRef.sha256 / warnings / editable=false
- 원본 fixture HWPX sha/mtime 사전=사후

playwright/headless chrome 은 본 단지 환경 미설치이므로 사용하지 않는다.
"""
from __future__ import annotations
import hashlib
import json
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from bs4 import BeautifulSoup

PR = Path(__file__).resolve().parents[2]
VIEWER_DIR = PR / "frontend/web_office_viewer"
SAMPLE_JSON = VIEWER_DIR / "payload.sample.json"
RUNTIME_SMOKE_JS = VIEWER_DIR / "runtime_smoke.mjs"

FORBIDDEN_DOM_TOKENS = ["save", "apply", "edit-command"]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a, **kw):  # silence
        pass


def _serve(directory: Path, port: int) -> HTTPServer:
    class _H(_QuietHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)
    httpd = HTTPServer(("127.0.0.1", port), _H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def _http_get(url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def _render_via_node() -> tuple[str, int, str]:
    r = subprocess.run(
        ["node", str(RUNTIME_SMOKE_JS)],
        capture_output=True, text=True, timeout=30,
        encoding="utf-8")
    return r.stdout, r.returncode, r.stderr


def _resolve_source_hwpx_for_sha_check() -> Path | None:
    """sample 의 sourceRef.path 를 사용하되 절대/상대 처리."""
    if not SAMPLE_JSON.is_file():
        return None
    sample = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))
    p = sample.get("sourceRef", {}).get("path")
    if not p:
        return None
    pth = Path(p)
    if not pth.is_absolute():
        pth = PR / pth
    return pth if pth.is_file() else None


def audit() -> dict:
    findings: list[dict] = []

    if not SAMPLE_JSON.is_file():
        findings.append({"code": "PAYLOAD_SAMPLE_MISSING",
                                  "level": "FAIL",
                                  "detail": str(SAMPLE_JSON.relative_to(PR))})
        return {"task": "WEB-OFFICE-BROWSER-RUNTIME-SMOKE-01",
                    "verdict": "FAIL", "findings": findings}

    sample = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))
    if sample.get("editable") is not False:
        findings.append({"code": "SAMPLE_EDITABLE_NOT_FALSE",
                                  "level": "FAIL", "detail": None})
    if not sample.get("sourceRef", {}).get("sha256"):
        findings.append({"code": "SAMPLE_SOURCE_SHA_MISSING",
                                  "level": "FAIL", "detail": None})
    if "warnings" not in sample:
        findings.append({"code": "SAMPLE_WARNINGS_KEY_MISSING",
                                  "level": "FAIL", "detail": None})

    # 원본 HWPX sha/mtime baseline
    src_hwpx = _resolve_source_hwpx_for_sha_check()
    src_sha_before = _sha(src_hwpx) if src_hwpx else None
    src_mtime_before = src_hwpx.stat().st_mtime_ns if src_hwpx else None

    # 정적 server smoke
    port = _free_port()
    # index.html 의 fetch 경로는 ./payload.json 이므로 임시로 .sample 도
    # 같이 GET 해서 자원 가용성만 검증. payload.json 자체는 ignore 대상
    # — http.server 가 .sample.json 도 그대로 서빙.
    httpd = _serve(VIEWER_DIR, port)
    try:
        # 서버 기동 대기
        time.sleep(0.05)
        try:
            sc, body = _http_get(f"http://127.0.0.1:{port}/index.html")
            if sc != 200 or not body:
                findings.append({"code": "INDEX_HTML_GET_FAIL",
                                          "level": "FAIL",
                                          "detail": f"status={sc} bytes={len(body)}"})
        except Exception as e:
            findings.append({"code": "INDEX_HTML_GET_EXC",
                                      "level": "FAIL", "detail": str(e)[:200]})
        try:
            sc, body = _http_get(
                f"http://127.0.0.1:{port}/payload.sample.json")
            if sc != 200 or not body:
                findings.append({"code": "PAYLOAD_SAMPLE_GET_FAIL",
                                          "level": "FAIL",
                                          "detail": f"status={sc} bytes={len(body)}"})
            else:
                # 서버로 받은 JSON 도 유효해야 함
                obj = json.loads(body.decode("utf-8"))
                if obj.get("editable") is not False:
                    findings.append({"code": "SERVED_PAYLOAD_NOT_RO",
                                              "level": "FAIL", "detail": None})
        except Exception as e:
            findings.append({"code": "PAYLOAD_SAMPLE_GET_EXC",
                                      "level": "FAIL", "detail": str(e)[:200]})
    finally:
        httpd.shutdown()

    # node viewer 렌더링 + DOM 파싱
    html, rc, stderr = _render_via_node()
    if rc != 0 or not html:
        findings.append({"code": "NODE_SMOKE_FAIL", "level": "FAIL",
                                  "detail": f"rc={rc} stderr={stderr[:200]}"})
        soup = None
    else:
        soup = BeautifulSoup(html, "html.parser")

    dom_counts = {}
    if soup is not None:
        toolbar = soup.select(".wo-toolbar")
        left = soup.select(".wo-left-panel")
        center = soup.select(".wo-center")
        right = soup.select(".wo-right-panel")
        tables = soup.select("table.wo-table")
        paragraphs = soup.select(".wo-paragraph")
        cells = soup.select("td.wo-cell")
        merged = [c for c in cells
                          if c.has_attr("rowspan") or c.has_attr("colspan")]
        inputs = soup.find_all("input")
        textareas = soup.find_all("textarea")
        ce_true = [t for t in soup.find_all(attrs={"contenteditable": True})
                            if str(t.get("contenteditable", "")).lower() == "true"]
        # save/apply/edit-command 류 어트리뷰트 또는 텍스트
        buttons = soup.find_all("button")
        editable_false_count = len(soup.select('[data-editable="false"]'))

        dom_counts = {
            "toolbar": len(toolbar), "left": len(left),
            "center": len(center), "right": len(right),
            "tables": len(tables), "paragraphs": len(paragraphs),
            "cells": len(cells), "mergedCells": len(merged),
            "inputs": len(inputs), "textareas": len(textareas),
            "contentEditableTrue": len(ce_true),
            "buttons": len(buttons),
            "editableFalseAttrs": editable_false_count,
        }

        for label, count in (("toolbar", len(toolbar)),
                                              ("left", len(left)),
                                              ("center", len(center)),
                                              ("right", len(right))):
            if count < 1:
                findings.append({"code": f"{label.upper()}_MISSING",
                                          "level": "FAIL", "detail": None})
        if len(tables) < 1:
            findings.append({"code": "TABLE_NOT_RENDERED",
                                      "level": "FAIL", "detail": None})
        if len(paragraphs) < 1:
            findings.append({"code": "PARAGRAPH_NOT_RENDERED",
                                      "level": "FAIL", "detail": None})
        if len(cells) < 1:
            findings.append({"code": "CELL_NOT_RENDERED",
                                      "level": "FAIL", "detail": None})
        if len(merged) < 1:
            findings.append({"code": "MERGED_CELL_NOT_RENDERED",
                                      "level": "FAIL", "detail": None})

        if inputs:
            findings.append({"code": "INPUT_PRESENT",
                                      "level": "FAIL",
                                      "detail": f"{len(inputs)}"})
        if textareas:
            findings.append({"code": "TEXTAREA_PRESENT",
                                      "level": "FAIL",
                                      "detail": f"{len(textareas)}"})
        if ce_true:
            findings.append({"code": "CONTENTEDITABLE_TRUE_PRESENT",
                                      "level": "FAIL",
                                      "detail": f"{len(ce_true)}"})
        if buttons:
            findings.append({"code": "BUTTON_PRESENT",
                                      "level": "FAIL",
                                      "detail": f"{len(buttons)}"})
        if editable_false_count < 4:
            findings.append({"code": "EDITABLE_FALSE_UNDERCOUNT",
                                      "level": "FAIL",
                                      "detail": f"{editable_false_count}"})

        # 텍스트 컨텐츠 토큰 검사
        text = html.lower()
        for tok in FORBIDDEN_DOM_TOKENS:
            if tok in text:
                findings.append({"code": "FORBIDDEN_DOM_TEXT",
                                          "level": "FAIL", "detail": tok})

    # 원본 fixture 무변경
    if src_hwpx is not None and src_sha_before is not None:
        if _sha(src_hwpx) != src_sha_before:
            findings.append({"code": "SOURCE_SHA_CHANGED",
                                      "level": "FAIL", "detail": src_hwpx.name})
        if src_hwpx.stat().st_mtime_ns != src_mtime_before:
            findings.append({"code": "SOURCE_MTIME_CHANGED",
                                      "level": "FAIL", "detail": src_hwpx.name})

    # writer / output HWPX 생성 흔적 — 본 audit 가 만든 .hwpx 가 있어선 안 됨
    extra_hwpx = list(VIEWER_DIR.glob("*.hwpx"))
    if extra_hwpx:
        findings.append({"code": "UNEXPECTED_HWPX_OUTPUT",
                                  "level": "FAIL",
                                  "detail": [p.name for p in extra_hwpx]})

    verdict = "PASS" if not findings else "FAIL"
    return {
        "task": "WEB-OFFICE-BROWSER-RUNTIME-SMOKE-01",
        "sample": str(SAMPLE_JSON.relative_to(PR)),
        "sampleBytes": SAMPLE_JSON.stat().st_size,
        "documentId": sample.get("documentId"),
        "sourceSha": sample.get("sourceRef", {}).get("sha256"),
        "domCounts": dom_counts,
        "srcUnchanged": (src_sha_before is None
                                      or _sha(src_hwpx) == src_sha_before),
        "findings": findings,
        "verdict": verdict,
    }


def main() -> int:
    out = audit()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
