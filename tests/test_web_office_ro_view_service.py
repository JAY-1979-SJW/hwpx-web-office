"""WEB-OFFICE-RO-VIEW 렌더 서비스(scripts/hwpx/web_office/service.py) 계약 테스트.

기준서: docs/specs/2026-09-24_hwpx_33to02_merge_phase1_spec.md 검증 기준 3.

FastAPI 가 설치되어 있지 않으면 skip 이 아니라 실패로 보고한다(기준서 명시).
"""
from __future__ import annotations
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from fastapi.testclient import TestClient  # noqa: E402 — 설치 안 되면 실패로 보고

from scripts.hwpx.web_office.service import app  # noqa: E402
from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view,
)

FORM_57 = PR / "tests/fixtures/form_57.hwpx"

client = TestClient(app)


def test_health_endpoint_ok():
    resp = client.get("/health")
    assert resp.status_code == 200


def test_render_hwpx_returns_html_fragment_with_expected_table_count():
    doc = import_hwpx_as_ro_view(FORM_57)
    expected_table_blocks = len([b for b in doc.blocks if b.type == "table"])
    assert expected_table_blocks == 2

    with FORM_57.open("rb") as fh:
        resp = client.post(
            "/render-hwpx",
            files={"file": ("form_57.hwpx", fh, "application/octet-stream")},
        )
    assert resp.status_code == 200
    body = resp.text
    assert "<html" not in body
    assert body.count("<table") == expected_table_blocks
