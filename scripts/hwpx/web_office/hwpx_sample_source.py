"""HWPX 표본 해석기 — 테스트·감리가 쓸 실제 서식 파일 한 건을 고른다.

배경(실측으로 확인된 결함):
    저장·verify7 테스트 26건과 감리 13종이 전부 표본을 찾지 못해 조용히
    건너뛰고 있었다. 표본을 data/recognition_corpus/corpus.sqlite3 에서만
    찾는데 그 DB 가 존재하지 않는다. 파일 개수만 보면 검증된 것처럼 보이지만
    실제로는 저장 경로가 한 번도 돌지 않았다.

    지금은 카탈로그(data/drafts/form_library/catalog.sqlite)에 채움가능
    서식이 33,604건 있으므로 레거시 DB 가 없으면 여기서 고른다.

선택은 반드시 결정적이어야 한다 — 실행할 때마다 다른 파일을 쓰면 실패가
재현되지 않는다. 그래서 form_id 오름차순 첫 적합 파일을 쓴다.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LEGACY_DB = PROJECT_ROOT / "data" / "recognition_corpus" / "corpus.sqlite3"
CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"

SIZE_MIN, SIZE_MAX = 30_000, 80_000


def from_legacy_corpus() -> Path | None:
    """구 corpus DB 에서 fillable_form 1건 (있으면 기존 동작 그대로 유지)."""
    if not LEGACY_DB.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{LEGACY_DB}?mode=ro", uri=True, timeout=30)
        row = conn.execute(
            """
            SELECT d.source_path FROM hwpx_documents d
            JOIN document_classifications c ON c.document_id = d.document_id
            WHERE d.inventory_status='FOUND'
              AND c.document_type='fillable_form'
              AND d.file_size BETWEEN ? AND ?
            ORDER BY d.first_seen_at LIMIT 1
            """, (SIZE_MIN, SIZE_MAX)).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    p = PROJECT_ROOT / row[0]
    return p if p.is_file() else None


def catalog_candidates(limit: int = 400) -> list[Path]:
    """카탈로그의 채움가능 서식 — 프로젝트 내부 경로·크기 조건 충족분."""
    if not CATALOG.is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True, timeout=30)
        rows = conn.execute(
            "SELECT source_path FROM forms "
            "WHERE status='OK' AND fillable=1 AND source_path LIKE 'data/%' "
            "ORDER BY form_id").fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    out: list[Path] = []
    for (rel,) in rows:
        p = PROJECT_ROOT / rel
        try:
            if p.is_file() and SIZE_MIN <= p.stat().st_size <= SIZE_MAX:
                out.append(p)
        except OSError:
            continue
        if len(out) >= limit:
            break
    return out


def resolve_sample() -> Path | None:
    """구조 요구 없는 표본 — 유효한 HWPX 파일 하나."""
    legacy = from_legacy_corpus()
    if legacy is not None:
        return legacy
    cands = catalog_candidates(limit=1)
    return cands[0] if cands else None


def resolve_sample_with_cells(
        required: tuple[tuple[int, int], ...] = ((3, 0), (4, 0)),
        table_id: str = "t_s0_000") -> Path | None:
    """지정한 표·셀 좌표를 실제로 가진 표본.

    셀 저장 테스트/감리는 좌표를 직접 집는다. 좌표가 없는 서식을 꽂으면
    저장 결함이 아니라 StopIteration 으로 죽으므로 존재를 확인한 파일만
    돌려준다.
    """
    legacy = from_legacy_corpus()
    if legacy is not None:
        return legacy
    try:
        from scripts.hwpx.web_office.ro_view_importer import (
            import_hwpx_as_ro_view)
    except ImportError:
        return None
    for path in catalog_candidates():
        try:
            doc = import_hwpx_as_ro_view(path)
        except Exception:  # noqa: BLE001 — 표본 탐색이라 개별 실패는 건너뛴다
            continue
        have = {(c.row, c.col) for c in doc.cells if c.tableId == table_id}
        if all(rc in have for rc in required):
            return path
    return None
