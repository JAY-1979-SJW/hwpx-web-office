"""서식 카탈로그 검색·매칭 — 로컬 SQLite 지식베이스 조회.

기능:
- search(query): 이름/종류/법정번호 텍스트 검색.
- match_form(fingerprint, field_labels): 업로드된 서식이 카탈로그의 어떤 서식인지
  분류. ① 구조지문 완전일치 → 강한 매칭 ② 필드 라벨 겹침(Jaccard) → 유사 매칭.
- stats(): 카탈로그 통계.

읽기 전용 — 카탈로그 빌드가 진행 중이어도 조회 가능.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


# 도메인 카테고리 — 서식 이름 키워드 기반 분류
DOMAIN_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("건축", ("건축", "가설건축", "착공", "사용승인", "대수선")),
    ("건설", ("건설", "공사", "도급", "감리", "시공", "엔지니어링")),
    ("소방", ("소방", "화재", "방화", "소방시설")),
    ("가스", ("가스", "액화석유", "고압가스", "도시가스")),
    ("전기·정보통신", ("전기", "정보통신", "통신")),
    ("환경", ("환경", "폐기물", "오염", "대기", "수질")),
    ("안전·보건", ("안전", "보건", "산업재해", "재해예방")),
    ("품질·검사", ("품질", "시험", "점검", "검사", "성적서")),
    ("등록·인허가", ("등록증", "허가", "신고", "지정", "승인", "면허")),
    ("세무·회계", ("세무", "소득", "부가가치", "결산", "회계")),
]


def _domain_of(name: str) -> list[str]:
    return [d for d, kws in DOMAIN_RULES if any(w in name for w in kws)]


def categories() -> dict[str, Any]:
    """도메인별 서식 수 — 카테고리 브라우즈용."""
    if not catalog_ready():
        return {"ready": False, "categories": []}
    try:
        con = _con()
        names = [r[0] for r in con.execute("SELECT name FROM forms WHERE status='OK'")]
        con.close()
        counts = {d: 0 for d, _ in DOMAIN_RULES}
        for nm in names:
            for d in _domain_of(nm):
                counts[d] += 1
        cats = [{"domain": d, "count": counts[d]} for d, _ in DOMAIN_RULES if counts[d] > 0]
        cats.sort(key=lambda c: -c["count"])
        return {"ready": True, "categories": cats}
    except sqlite3.Error as e:
        return {"ready": False, "categories": [], "error": str(e)[:120]}


def by_category(domain: str, *, limit: int = 40) -> dict[str, Any]:
    """도메인 카테고리 서식 목록 — 키워드 OR 조건으로 조회."""
    if not catalog_ready():
        return {"ready": False, "results": []}
    kws = next((k for d, k in DOMAIN_RULES if d == domain), None)
    if not kws:
        return {"ready": True, "domain": domain, "results": []}
    try:
        con = _con()
        clause = " OR ".join("name LIKE ?" for _ in kws)
        params = [f"%{k}%" for k in kws] + [limit]
        rows = con.execute(
            f"SELECT form_id,form_type,statute_no,name,field_count,table_count,cell_count "
            f"FROM forms WHERE status='OK' AND ({clause}) "
            f"ORDER BY (statute_no != '') DESC, field_count DESC LIMIT ?", params).fetchall()
        results = []
        for r in rows:
            labels = [x[0] for x in con.execute(
                "SELECT label FROM fields WHERE form_id=? LIMIT 12", (r["form_id"],))]
            results.append({"formId": r["form_id"], "formType": r["form_type"],
                            "statuteNo": r["statute_no"], "name": r["name"],
                            "fieldCount": r["field_count"], "tableCount": r["table_count"],
                            "cellCount": r["cell_count"], "sampleFields": labels})
        con.close()
        return {"ready": True, "domain": domain, "results": results}
    except sqlite3.Error as e:
        return {"ready": False, "results": [], "error": str(e)[:120]}


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "")


def catalog_ready() -> bool:
    return CATALOG.exists()


def stats() -> dict[str, Any]:
    if not catalog_ready():
        return {"ready": False, "total": 0}
    try:
        con = _con()
        total = con.execute("SELECT COUNT(*) FROM forms").fetchone()[0]
        ok = con.execute("SELECT COUNT(*) FROM forms WHERE status='OK'").fetchone()[0]
        statute = con.execute("SELECT COUNT(*) FROM forms WHERE statute_no != ''").fetchone()[0]
        fields = con.execute("SELECT COUNT(*) FROM fields").fetchone()[0]
        con.close()
        return {"ready": True, "total": total, "parsed": ok,
                "statuteForms": statute, "totalFields": fields}
    except sqlite3.Error as e:
        return {"ready": False, "total": 0, "error": str(e)[:120]}


def search(query: str, *, limit: int = 20) -> dict[str, Any]:
    """이름/종류/법정번호 텍스트 검색."""
    if not catalog_ready():
        return {"ready": False, "results": []}
    q = (query or "").strip()
    if not q:
        return {"ready": True, "results": []}
    try:
        con = _con()
        like = f"%{q}%"
        rows = con.execute(
            "SELECT form_id,form_type,statute_no,name,field_count,table_count,cell_count "
            "FROM forms WHERE status='OK' AND (name LIKE ? OR form_type LIKE ? OR statute_no LIKE ?) "
            "ORDER BY (statute_no != '') DESC, field_count DESC LIMIT ?",
            (like, like, like, limit),
        ).fetchall()
        results = []
        for r in rows:
            labels = [x[0] for x in con.execute(
                "SELECT label FROM fields WHERE form_id=? LIMIT 12", (r["form_id"],))]
            results.append({
                "formId": r["form_id"], "formType": r["form_type"],
                "statuteNo": r["statute_no"], "name": r["name"],
                "fieldCount": r["field_count"], "tableCount": r["table_count"],
                "cellCount": r["cell_count"], "sampleFields": labels,
            })
        con.close()
        return {"ready": True, "query": q, "results": results}
    except sqlite3.Error as e:
        return {"ready": False, "results": [], "error": str(e)[:120]}


def match_form(*, fingerprint: str | None = None,
               field_labels: list[str] | None = None,
               limit: int = 5) -> dict[str, Any]:
    """업로드 서식을 카탈로그와 대조 → 후보 목록(분류).

    Returns: {ready, exactMatch?, candidates:[{formId,name,statuteNo,overlap,jaccard,...}]}
    """
    if not catalog_ready():
        return {"ready": False, "candidates": []}
    field_labels = field_labels or []
    norm_labels = {_norm(l) for l in field_labels if _norm(l)}
    try:
        con = _con()
        result: dict[str, Any] = {"ready": True, "candidates": []}

        # ① 구조지문 완전일치
        if fingerprint:
            rows = con.execute(
                "SELECT form_id,name,statute_no,field_count FROM forms "
                "WHERE status='OK' AND fingerprint=? LIMIT 3", (fingerprint,)).fetchall()
            if rows:
                result["exactMatch"] = [{"formId": r["form_id"], "name": r["name"],
                                          "statuteNo": r["statute_no"],
                                          "fieldCount": r["field_count"]} for r in rows]

        # ② 필드 라벨 겹침(Jaccard) — 유사 서식 순위
        if norm_labels:
            # 후보 폼별 겹침 수 집계
            overlap: dict[int, int] = {}
            # 라벨 정규화 대조를 위해 전체 fields 스캔(카탈로그 규모상 허용;
            # 커지면 정규화 컬럼+인덱스로 최적화)
            for fid, lab in con.execute("SELECT form_id,label FROM fields"):
                if _norm(lab) in norm_labels:
                    overlap[fid] = overlap.get(fid, 0) + 1
            if overlap:
                top = sorted(overlap.items(), key=lambda x: -x[1])[:limit * 3]
                cands = []
                for fid, ov in top:
                    r = con.execute(
                        "SELECT name,statute_no,form_type,field_count FROM forms WHERE form_id=?",
                        (fid,)).fetchone()
                    if not r:
                        continue
                    denom = len(norm_labels) + (r["field_count"] or 0) - ov
                    jac = ov / denom if denom > 0 else 0.0
                    cands.append({
                        "formId": fid, "name": r["name"], "statuteNo": r["statute_no"],
                        "formType": r["form_type"], "overlap": ov,
                        "jaccard": round(jac, 3), "fieldCount": r["field_count"],
                    })
                cands.sort(key=lambda c: (-c["overlap"], -c["jaccard"]))
                result["candidates"] = cands[:limit]

        con.close()
        return result
    except sqlite3.Error as e:
        return {"ready": False, "candidates": [], "error": str(e)[:120]}


def form_fields(form_id: int) -> dict[str, Any]:
    """특정 서식의 전체 입력 필드."""
    if not catalog_ready():
        return {"ready": False, "fields": []}
    try:
        con = _con()
        r = con.execute("SELECT name,statute_no,form_type FROM forms WHERE form_id=?",
                        (form_id,)).fetchone()
        if not r:
            con.close()
            return {"ready": True, "fields": [], "error": "FORM_NOT_FOUND"}
        labels = [x[0] for x in con.execute(
            "SELECT label FROM fields WHERE form_id=?", (form_id,))]
        con.close()
        return {"ready": True, "formId": form_id, "name": r["name"],
                "statuteNo": r["statute_no"], "formType": r["form_type"], "fields": labels}
    except sqlite3.Error as e:
        return {"ready": False, "fields": [], "error": str(e)[:120]}
