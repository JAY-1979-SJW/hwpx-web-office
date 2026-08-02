"""AI 필드 해석 캐시 배치 — 문서별로 한 번 해석해 굳힌다.

지시(2026-08-01, 대표님): "개별 문서별로 파싱 로직하고 AI 분석하고 뭘
입력할지 최종 캐시로 저장하면 되잖아?"

왜 캐시인가
-----------
현재 런타임 AI 호출은 서식당 20~40초다. 사용자가 서식을 열 때마다 이걸
기다릴 수 없다. 문서에 종속된 해석(이 칸이 무엇을 요구하는가)은 사용자와
무관하게 불변이므로 **빌드타임에 한 번** 계산해 두면 런타임은 조회만 한다.

무엇을 저장하고 무엇을 저장하지 않는가
--------------------------------------
저장: isInput(진짜 입력칸인가) · semantic · profileKey · question · meaning
저장 안 함: **값**. 값은 사용자마다 다르고 개인정보다(§4). 캐시는
"어느 프로필 키가 이 칸에 들어가는가"까지만 굳히고, 실제 값은 런타임에
사용자 소스에서 채운다.

공사 규모 실측(2026-08-01)
--------------------------
해석 필요 서식 15,262건 · 직렬 ~112시간 · 8샤드 병렬 ~14시간.

안전 설계 (rebuild_form_derivations_batch 선례 계승)
----------------------------------------------------
- `forms` 를 건드리지 않는다. 스테이징 `ai_field_interpretation` 에만 쌓는다.
- 재개 가능 — 이미 쌓인 form_id 는 건너뛴다.
- 샤드 병렬(`--shard/--shards`), WAL + 짧은 트랜잭션(잠금 경합 회피).
- 반영은 별도 단계 `--promote` — 커버리지 게이트 미달이면 거부한다.
- 원본 HWPX 는 읽기만 한다.

사용
----
    python -m scripts.hwpx.web_office.build_ai_interpretation_cache --limit 20
    ... --shards 8 --shard 0        (8병렬 중 0번)
    ... --status
    ... --promote                   (승인 후에만)
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.hwpx.web_office.ai_doc_context import (  # noqa: E402
    build_context_fields)
from scripts.hwpx.web_office.ai_field_interpretation import (  # noqa: E402
    CLAUDE_MODEL, interpret_fields, should_demote, should_promote_to_user)

CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"
STAGING = "ai_field_interpretation"

# 건설·현장 서류 — 대표님 사업 축이라 우선 공사 대상(2026-08-01 지시).
# 카탈로그 실측: 이름에 이 신호가 있는 서식 1,774건(5.6%), 신청인칸
# 10,857개. 그중 검측요청서 38건은 전 칸이 관계자로 죽어 있었다.
CONSTRUCTION_DOC_RE = re.compile(
    r"(검측|시공|감리|공사|착공|준공|기성|공정|안전관리|품질관리"
    r"|자재승인|하도급|설계변경|현장대리인|건설기술|시방)")
FLUSH_EVERY = 10        # AI 호출이 느려 소량씩 — 중단돼도 잃는 게 적다

# promote 게이트 — 해석 성공률이 이 아래면 반영을 거부한다.
PROMOTE_MIN_OK_RATIO = 0.90

DDL = f"""
CREATE TABLE IF NOT EXISTS {STAGING}(
    form_id INTEGER PRIMARY KEY,
    status TEXT,
    model TEXT,
    field_count INTEGER,
    interpreted_count INTEGER,
    input_count INTEGER,
    not_input_count INTEGER,
    semantic_count INTEGER,
    author_count INTEGER,
    coverage REAL,
    interpretations TEXT,
    error TEXT,
    elapsed_sec REAL
);
"""

COLS = ["form_id", "status", "model", "field_count", "interpreted_count",
        "input_count", "not_input_count", "semantic_count", "author_count",
        "coverage", "interpretations", "error", "elapsed_sec"]

# 2차 독립 검증 결과(§4.6 두 신호) — 확신도 문턱을 대체한다.
VERIFY_TABLE = "ai_field_verification"
VERIFY_DDL = f"""
CREATE TABLE IF NOT EXISTS {VERIFY_TABLE}(
    form_id INTEGER PRIMARY KEY,
    status TEXT,
    model TEXT,
    verdicts TEXT,
    author_agreed TEXT,
    disagreed_count INTEGER,
    unverified_count INTEGER,
    agreement_rate REAL,
    error TEXT,
    elapsed_sec REAL
);
"""
VERIFY_COLS = ["form_id", "status", "model", "verdicts", "author_agreed",
               "disagreed_count", "unverified_count", "agreement_rate",
               "error", "elapsed_sec"]


def _log(m: str) -> None:
    print(m, flush=True)


def _connect() -> sqlite3.Connection:
    # isolation_level=None — 잠금 구간을 우리가 정한다. 샤드 병렬에서
    # 워커 하나가 AI 응답을 기다리며 쓰기 잠금을 붙들면 나머지가 전부
    # 죽는다(선례: rebuild_form_derivations_batch).
    con = sqlite3.connect(CATALOG, timeout=120, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=120000")
    return con


def _flush(con: sqlite3.Connection, pending: list[dict],
           retries: int = 10, table: str = STAGING,
           cols: list[str] | None = None) -> None:
    if not pending:
        return
    cols = cols or COLS
    sql = (f"INSERT OR REPLACE INTO {table}({', '.join(cols)}) "
           f"VALUES({', '.join('?' * len(cols))})")
    payload = [tuple(r.get(c) for c in cols) for r in pending]
    for attempt in range(retries):
        try:
            con.execute("BEGIN IMMEDIATE")
            con.executemany(sql, payload)
            con.execute("COMMIT")
            pending.clear()
            return
        except sqlite3.OperationalError as e:
            try:
                con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                raise
            time.sleep(0.4 * (attempt + 1))
    raise sqlite3.OperationalError("스테이징 쓰기 실패 — 잠김")


def _targets(con: sqlite3.Connection, limit: int, shard: int,
             shards: int, scope: str = "all",
             source_scope: str | None = None) -> list[tuple]:
    """공사 대상.

    scope='construction' — **이름** 키워드 필터(문서명에 '검측'·'공사' 등).
      카탈로그 전체가 대상이라 특정 이관·경로 범위를 안 가린다 — 다른
      배치(예: OneDrive 이관분 전용 실행)와 착각하기 쉽다(2026-08-02
      실사례: --scope construction 을 쓰다 의도와 다른 문서 집합을
      건드릴 뻔했다).
    source_scope — **경로** 필터(source_path 부분일치, 예: "onedrive_hwpx").
      "이 이관 범위만" 처럼 물리적 출처로 한정할 때 쓴다. scope 와 동시
      지정 가능(둘 다 만족해야 대상).

    우선순위는 **문서 내용**(파싱된 실제 applicant_count) 기준으로 죽은
    서식(신청인칸 0)을 먼저 돌린다 — 사용자가 지금 아예 못 쓰는 문서라
    효과가 가장 크고, 역할 교정 게이트가 '죽은 문서만' 적용되므로 위험도
    가장 낮다. 이름 키워드가 아니라 스키마 생성 단계가 이미 확정한 실제
    칸 구성을 근거로 삼는다.
    """
    done = {r[0] for r in con.execute(f"SELECT form_id FROM {STAGING}")}
    rows = con.execute(
        "SELECT form_id, source_path, input_schema, clean_name,"
        " COALESCE(name,''), COALESCE(applicant_count,0) FROM forms"
        " WHERE input_schema IS NOT NULL AND input_schema != ''"
        " ORDER BY form_id").fetchall()
    out = []
    for r in rows:
        form_id, source_path, _, clean_name, name, _ = r
        if form_id in done:
            continue
        if shards > 1 and form_id % shards != shard:
            continue
        if scope == "construction":
            label = f"{clean_name or ''} {name or ''}"
            if not CONSTRUCTION_DOC_RE.search(label):
                continue
        if source_scope and source_scope not in (source_path or ""):
            continue
        out.append(r)
    # 죽은 서식 우선(applicant_count 오름차순), 그 안에서는 form_id 순
    out.sort(key=lambda r: (r[5], r[0]))
    if limit:
        out = out[:limit]
    return [r[:4] for r in out]


def interpret_one(source_rel: str, schema_json: str, clean_name: str,
                  *, runner=None) -> dict:
    """서식 1건 해석. 원본은 읽기만 한다."""
    from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor

    res = load_hwpx_for_editor(
        {"operation": "HWPX_EDITOR_LOAD", "sourcePath": source_rel},
        project_root=PROJECT_ROOT)
    if res.get("verdict") != "PASS":
        return {"status": "LOAD_FAILED", "error": res.get("reason", "")}

    schema = json.loads(schema_json)
    # roles=None — 규칙이 매긴 역할과 무관하게 **전 입력칸**을 싣는다(§4.6).
    # 규칙이 AI 앞에서 자르면 검측요청서처럼 전 칸이 관계자로 판정된 문서를
    # AI 가 아예 못 본다(실측: 보이는 칸 0).
    fields = build_context_fields(schema, res["documentModel"],
                                  title=clean_name or "", roles=None)
    if not fields:
        return {"status": "NO_FIELDS", "field_count": 0}

    out = interpret_fields(fields, runner=runner)
    if not out.get("ok"):
        return {"status": "AI_FAILED", "error": out.get("error", ""),
                "field_count": len(fields)}
    return {
        "status": "OK",
        "field_count": len(fields),
        "interpreted_count": len(out["interpretations"]),
        "input_count": out["inputCount"],
        "not_input_count": out["notInputCount"],
        "semantic_count": out["semanticCount"],
        "author_count": out["authorCount"],
        "coverage": out["coverage"],
        "interpretations": json.dumps(out["interpretations"],
                                      ensure_ascii=False),
    }


def run(limit: int = 0, shard: int = 0, shards: int = 1,
        scope: str = "all", source_scope: str | None = None,
        promote_on_pass: bool = False) -> None:
    con = _connect()
    con.execute(DDL)
    targets = _targets(con, limit, shard, shards, scope, source_scope)
    _log(f"대상 {len(targets)}건 (shard {shard}/{shards}, scope={scope},"
         f" sourceScope={source_scope or '-'}, model={CLAUDE_MODEL})")
    pending: list[dict] = []
    t0 = time.time()
    for n, (form_id, source_path, schema_json, clean_name) in enumerate(
            targets, 1):
        t1 = time.time()
        try:
            r = interpret_one(source_path, schema_json, clean_name)
        except Exception as exc:  # noqa: BLE001
            r = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"[:200]}
        r["form_id"] = form_id
        r["model"] = CLAUDE_MODEL
        r["elapsed_sec"] = round(time.time() - t1, 1)
        pending.append(r)
        if len(pending) >= FLUSH_EVERY:
            _flush(con, pending)
            done = n
            rate = (time.time() - t0) / done
            _log(f"[{done}/{len(targets)}] {rate:.1f}s/건 "
                 f"· 남은 예상 {(len(targets) - done) * rate / 3600:.1f}시간")
    _flush(con, pending)
    _log(f"완료 {len(targets)}건 / {time.time() - t0:.0f}s")
    con.close()
    if promote_on_pass:
        # 대표님 지시(2026-08-01): 게이트 통과 시 자동 반영.
        # promote() 안의 성공률 게이트가 미달이면 스스로 거부하므로
        # '무조건 반영'이 아니다 — 통과했을 때만 넘어간다.
        _log("--- 게이트 통과 시 자동 반영 ---")
        promote()


def verify(limit: int = 0, shard: int = 0, shards: int = 1) -> None:
    """2차 독립 검증 — 이미 해석된 서식을 다른 각도로 다시 판정한다.

    1차 판정을 검증자에게 보여주지 않는다(앵커링 차단). 일치 대조는
    프로그램이 한다 — `ai_field_verification.agreement`.
    """
    from scripts.hwpx.web_office.ai_field_verification import (
        CLAUDE_MODEL as V_MODEL, verify_fields)
    from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor

    con = _connect()
    con.execute(DDL)
    con.execute(VERIFY_DDL)
    done = {r[0] for r in con.execute(f"SELECT form_id FROM {VERIFY_TABLE}")}
    # 되살림 후보(죽은 서식 · 보호구역 아님)를 먼저 검증한다 — 살아있는
    # 서식이나 대장·발급증서는 어차피 역할이 안 바뀌므로 검증해도 반영에
    # 영향이 없다. 앞선 표본 12건이 전부 비후보라 되살림 0 으로 나왔다.
    from scripts.hwpx.web_office.ai_field_interpretation import (
        ROLE_PROTECTED_DOCTYPES, ROLE_PROTECTED_KINDS)
    rows = con.execute(
        f"SELECT s.form_id, s.interpretations, f.source_path, f.clean_name,"
        f" f.input_schema, COALESCE(f.applicant_count,0),"
        f" COALESCE(f.doc_type,''), COALESCE(f.form_kind,'')"
        f" FROM {STAGING} s JOIN forms f ON f.form_id=s.form_id"
        f" WHERE s.status='OK' AND s.interpretations IS NOT NULL"
        f" ORDER BY s.form_id").fetchall()

    def _is_candidate(r) -> bool:
        return (r[5] == 0 and r[6] not in ROLE_PROTECTED_DOCTYPES
                and r[7] not in ROLE_PROTECTED_KINDS)

    pool = [r for r in rows
            if r[0] not in done and (shards <= 1 or r[0] % shards == shard)]
    pool.sort(key=lambda r: (0 if _is_candidate(r) else 1, r[0]))
    cand = sum(1 for r in pool if _is_candidate(r))
    _log(f"  (되살림 후보 {cand} / 전체 {len(pool)} — 후보 우선)")
    targets = [r[:5] for r in pool]
    if limit:
        targets = targets[:limit]
    _log(f"검증 대상 {len(targets)}건 (shard {shard}/{shards}, model={V_MODEL})")

    pending: list[dict] = []
    t0 = time.time()
    for n, (form_id, interp_json, source_path, clean_name,
            schema_json) in enumerate(targets, 1):
        t1 = time.time()
        rec: dict = {"form_id": form_id, "model": V_MODEL}
        try:
            res = load_hwpx_for_editor(
                {"operation": "HWPX_EDITOR_LOAD", "sourcePath": source_path},
                project_root=PROJECT_ROOT)
            if res.get("verdict") != "PASS":
                rec.update({"status": "LOAD_FAILED"})
            else:
                fields = build_context_fields(
                    json.loads(schema_json), res["documentModel"],
                    title=clean_name or "", roles=None)
                interp = json.loads(interp_json)
                out = verify_fields(fields, interp)
                if not out.get("ok"):
                    rec.update({"status": "AI_FAILED",
                                "error": out.get("error", "")})
                else:
                    ag = out["agreement"]
                    rec.update({
                        "status": "OK",
                        "verdicts": json.dumps(out["verdicts"],
                                               ensure_ascii=False),
                        "author_agreed": json.dumps(ag["authorAgreed"],
                                                    ensure_ascii=False),
                        "disagreed_count": len(ag["disagreed"]),
                        "unverified_count": len(ag["unverified"]),
                        "agreement_rate": ag["agreementRate"],
                    })
        except Exception as exc:  # noqa: BLE001
            rec.update({"status": "ERROR",
                        "error": f"{type(exc).__name__}: {exc}"[:200]})
        rec["elapsed_sec"] = round(time.time() - t1, 1)
        pending.append(rec)
        if len(pending) >= FLUSH_EVERY:
            _flush(con, pending, table=VERIFY_TABLE, cols=VERIFY_COLS)
            rate = (time.time() - t0) / n
            _log(f"[{n}/{len(targets)}] {rate:.1f}s/건 · 남은 예상 "
                 f"{(len(targets) - n) * rate / 3600:.1f}시간")
    _flush(con, pending, table=VERIFY_TABLE, cols=VERIFY_COLS)
    _log(f"완료 {len(targets)}건 / {time.time() - t0:.0f}s")
    con.close()


def status() -> None:
    con = _connect()
    con.execute(DDL)
    total = con.execute(
        "SELECT COUNT(*) FROM forms WHERE input_schema IS NOT NULL"
        " AND input_schema != ''").fetchone()[0]
    rows = con.execute(
        f"SELECT status, COUNT(*) FROM {STAGING} GROUP BY status").fetchall()
    staged = sum(n for _, n in rows)
    _log(f"대상 {total} · 스테이징 {staged} ({staged / total * 100:.1f}%)")
    for st, n in rows:
        _log(f"  {st}: {n}")
    agg = con.execute(
        f"SELECT SUM(field_count), SUM(interpreted_count), SUM(input_count),"
        f" SUM(not_input_count), SUM(semantic_count), AVG(elapsed_sec)"
        f" FROM {STAGING} WHERE status='OK'").fetchone()
    if agg and agg[0]:
        fc, ic, inp, notinp, sem, el = agg
        _log(f"  칸 {fc} · 해석 {ic} ({ic / fc * 100:.1f}%)"
             f" · 입력칸 {inp} · 입력칸아님(오염제거) {notinp}"
             f" · semantic {sem} ({sem / fc * 100:.1f}%)"
             f" · 평균 {el:.1f}s/건")
    con.close()


def promote() -> None:
    """해석을 forms.input_schema 에 반영. 게이트 미달이면 거부.

    반영 규칙:
      · 강등(role='noise')은 `should_demote` 가 허락할 때만 — AI 와 규칙이
        **둘 다** 입력칸이 아니라고 할 때. AI 단독 판정은 파일럿에서 정상
        입력칸의 15.8% 를 죽였다(오탐은 오염 잔존보다 해롭다).
      · semantic 이 비어있던 칸만 AI 태그로 채운다(기존 태그 불변).
      · aiMeaning/aiQuestion/aiProfileKey 를 필드에 덧붙인다.
    """
    con = _connect()
    con.execute(DDL)
    rows = con.execute(
        f"SELECT status, COUNT(*) FROM {STAGING} GROUP BY status").fetchall()
    staged = sum(n for _, n in rows)
    ok = dict(rows).get("OK", 0)
    if not staged:
        _log("REJECTED: 스테이징이 비었다")
        return
    ratio = ok / staged
    if ratio < PROMOTE_MIN_OK_RATIO:
        _log(f"REJECTED: 해석 성공률 {ratio:.1%}"
             f" < 게이트 {PROMOTE_MIN_OK_RATIO:.0%}")
        return

    # 2차 검증 결과 — 있으면 확신도 문턱 대신 이걸 둘째 신호로 쓴다(§4.6).
    con.execute(VERIFY_DDL)
    verified_by_form: dict[int, set[str]] = {}
    for fid, agreed in con.execute(
            f"SELECT form_id, author_agreed FROM {VERIFY_TABLE}"
            f" WHERE status='OK' AND author_agreed IS NOT NULL"):
        try:
            verified_by_form[fid] = set(json.loads(agreed))
        except Exception:      # noqa: BLE001
            pass
    if verified_by_form:
        _log(f"2차 검증 반영 — 검증된 서식 {len(verified_by_form)}건"
             f" (확신도 문턱 대신 두 판정 일치를 씀)")

    updated = 0
    demoted = 0
    tagged = 0
    revived = 0
    revived_forms = 0
    pending: list[tuple] = []
    for form_id, interp_json in con.execute(
            f"SELECT form_id, interpretations FROM {STAGING}"
            f" WHERE status='OK' AND interpretations IS NOT NULL"):
        row = con.execute(
            "SELECT input_schema, doc_type, form_kind, applicant_count"
            " FROM forms WHERE form_id=?", (form_id,)).fetchone()
        if not row or not row[0]:
            continue
        schema = json.loads(row[0])
        doc_type, form_kind, app_before = row[1] or "", row[2] or "", row[3] or 0
        by_key = {i["key"]: i for i in json.loads(interp_json)}
        agreed = verified_by_form.get(form_id)
        revived_here = 0
        for f in schema:
            it = by_key.get(f.get("paragraphId"))
            if not it:
                continue
            # 라벨은 스키마 것이 원본이다 — 캐시 항목에 없어도 규칙 검사가
            # 무력화되면 안 된다(라벨이 비면 규칙이 항상 통과시켜 버린다).
            judged = {**it, "label": it.get("label") or f.get("label") or "",
                      "ruleRole": it.get("ruleRole") or f.get("role") or ""}
            if f.get("role") == "applicant" and should_demote(judged):
                f["role"] = "noise"
                demoted += 1
            # 역할 교정 — 통째로 죽은 문서(신청인칸 0)만 되살린다(§4.6).
            elif f.get("role") == "office" and should_promote_to_user(
                    judged, doc_type=doc_type, form_kind=form_kind,
                    form_applicant_count=app_before,
                    verified=(it.get("key") in agreed
                              if agreed is not None else None)):
                f["role"] = "applicant"
                revived_here += 1
            if not (f.get("semantic") or "").strip() and it["semantic"]:
                f["semantic"] = it["semantic"]
                tagged += 1
            if it.get("meaning"):
                f["aiMeaning"] = it["meaning"]
            if it.get("question"):
                f["aiQuestion"] = it["question"]
            if it.get("profileKey"):
                f["aiProfileKey"] = it["profileKey"]
        inputs = [f for f in schema if f.get("role") != "noise"]
        app = sum(1 for f in inputs if f.get("role") == "applicant")
        pending.append((json.dumps(schema, ensure_ascii=False), len(inputs),
                        app, len(inputs) - app, form_id))
        updated += 1
        revived += revived_here
        if revived_here:
            revived_forms += 1

    for i in range(0, len(pending), 200):
        chunk = pending[i:i + 200]
        con.execute("BEGIN IMMEDIATE")
        con.executemany(
            "UPDATE forms SET input_schema=?, input_count=?,"
            " applicant_count=?, office_count=? WHERE form_id=?", chunk)
        con.execute("COMMIT")
    _log(f"PROMOTED: 서식 {updated} · 오염제거(noise 강등) {demoted}"
         f" · semantic 신규부여 {tagged}"
         f" · 역할교정(죽은 서식 되살림) {revived}칸/{revived_forms}서식")
    con.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--promote", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="2차 독립 검증(확신도 문턱 대체)")
    ap.add_argument("--scope", choices=("all", "construction"), default="all",
                    help="construction = 문서명 키워드 필터(건설·현장)")
    ap.add_argument("--source-scope", default=None,
                    help="source_path 부분일치 필터(예: onedrive_hwpx)"
                        " — 특정 이관·경로 범위로 한정할 때. --scope 와 별개")
    ap.add_argument("--promote-on-pass", action="store_true",
                    help="공사 후 게이트 통과 시 자동 반영")
    a = ap.parse_args()
    if a.status:
        status()
    elif a.verify:
        verify(limit=a.limit, shard=a.shard, shards=a.shards)
    elif a.promote:
        promote()
    else:
        run(limit=a.limit, shard=a.shard, shards=a.shards, scope=a.scope,
            source_scope=a.source_scope, promote_on_pass=a.promote_on_pass)


if __name__ == "__main__":
    main()
