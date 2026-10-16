"""공용 검사 함수(ops_common_checks) 계약 시험 — 임시 폴더·임시 git 저장소만 사용한다."""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ops import classify_hwpx_repo_inventory as inventory
from scripts.ops import ops_common_checks as occ

MODULE_REL = "scripts/ops/ops_common_checks.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _repo_with(tmp_path: Path, files: dict[str, str]) -> str:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for rel, text in files.items():
        (tmp_path / rel).write_text(text, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()


# --- no_leak -----------------------------------------------------------------


def test_01_no_leak_true_without_match() -> None:
    assert occ.no_leak("hello", re.compile("zzz"), re.compile("qqq")) is True


def test_02_no_leak_false_when_any_pattern_matches() -> None:
    assert occ.no_leak("hello zzz", re.compile("qqq"), re.compile("zzz")) is False


def test_03_no_leak_without_patterns_raises() -> None:
    # 패턴 없이 부르면 통과(True)가 아니라 실패 - 정규식을 빠뜨린 교체가 검사를 조용히 끄지 못한다.
    with pytest.raises(ValueError):
        occ.no_leak("anything")


# --- safe_write_json ----------------------------------------------------------


def test_04_safe_write_json_writes_when_clean(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    occ.safe_write_json(out, {"a": "한글"}, lambda t: True, "unsafe")
    assert out.read_text(encoding="utf-8") == '{\n  "a": "한글"\n}'


def test_05_safe_write_json_refuses_leak_and_does_not_echo_value(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    secret_like = "zz-marker-value"
    with pytest.raises(ValueError) as exc:
        occ.safe_write_json(out, {"k": secret_like}, lambda t: secret_like not in t, "FAIL_UNSAFE_REPORT")
    assert str(exc.value) == "FAIL_UNSAFE_REPORT: r.json"
    assert secret_like not in str(exc.value)
    assert not out.exists()


@pytest.mark.parametrize("bad", [None, "not-callable", 0])
def test_05b_safe_write_json_requires_callable_leak_check(tmp_path: Path, bad: object) -> None:
    out = tmp_path / "r.json"
    with pytest.raises(TypeError):
        occ.safe_write_json(out, {"a": 1}, bad, "unsafe")  # type: ignore[arg-type]
    assert not out.exists()


# --- check_locked_files -------------------------------------------------------


def test_06_locked_file_unchanged_has_no_findings(tmp_path: Path) -> None:
    base = _repo_with(tmp_path, {"a.txt": "one\n"})
    assert occ.check_locked_files(["a.txt"], base, tmp_path) == []


def test_07_locked_file_changed_is_fail(tmp_path: Path) -> None:
    base = _repo_with(tmp_path, {"a.txt": "one\n"})
    (tmp_path / "a.txt").write_text("two\n", encoding="utf-8")
    assert occ.check_locked_files(["a.txt"], base, tmp_path) == [
        {"code": "LOCKED_FILE_CHANGED", "level": "FAIL", "detail": "a.txt"}
    ]


def test_08_bad_baseline_is_warn_rc(tmp_path: Path) -> None:
    _repo_with(tmp_path, {"a.txt": "one\n"})
    found = occ.check_locked_files(["a.txt"], "no-such-rev", tmp_path)
    assert [f["code"] for f in found] == ["GIT_DIFF_RC"]
    assert found[0]["level"] == "WARN"


@pytest.mark.parametrize(
    "exc",
    [FileNotFoundError("git"), subprocess.TimeoutExpired(cmd="git", timeout=1)],
)
def test_09_git_unavailable_or_timeout_is_warn_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise exc

    monkeypatch.setattr(occ.subprocess, "run", boom)
    found = occ.check_locked_files(["a.txt"], "HEAD", tmp_path)
    assert [f["code"] for f in found] == ["GIT_DIFF_FAILED"]
    assert found[0]["level"] == "WARN"


def test_09b_rc_failure_code_default_keeps_git_diff_rc(tmp_path: Path) -> None:
    _repo_with(tmp_path, {"a.txt": "one\n"})
    explicit = occ.check_locked_files(["a.txt"], "no-such-rev", tmp_path, rc_failure_code="GIT_DIFF_RC")
    assert explicit == occ.check_locked_files(["a.txt"], "no-such-rev", tmp_path)


def test_09c_rc_failure_code_changes_only_the_code(tmp_path: Path) -> None:
    _repo_with(tmp_path, {"a.txt": "one\n"})
    default = occ.check_locked_files(["a.txt"], "no-such-rev", tmp_path)
    custom = occ.check_locked_files(["a.txt"], "no-such-rev", tmp_path, rc_failure_code="GIT_DIFF_FAILED")
    assert [f["code"] for f in custom] == ["GIT_DIFF_FAILED"]
    assert [{k: v for k, v in f.items() if k != "code"} for f in custom] == [
        {k: v for k, v in f.items() if k != "code"} for f in default
    ]


def test_09d_rc_failure_code_is_keyword_only(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        occ.check_locked_files(["a.txt"], "HEAD", tmp_path, 20, "GIT_DIFF_FAILED")  # type: ignore[misc]


def test_09e_rc_failure_code_does_not_affect_changed_or_clean(tmp_path: Path) -> None:
    base = _repo_with(tmp_path, {"a.txt": "one\n", "b.txt": "one\n"})
    (tmp_path / "a.txt").write_text("two\n", encoding="utf-8")
    assert occ.check_locked_files(["b.txt", "a.txt"], base, tmp_path, rc_failure_code="GIT_DIFF_FAILED") == [
        {"code": "LOCKED_FILE_CHANGED", "level": "FAIL", "detail": "a.txt"}
    ]


# rc≠0 코드로 GIT_DIFF_FAILED 를 쓰던 감사 3개 - 보고서에 찍히는 이 문자열이 바뀌지 않게 고정한다.
_B_AUDITS = [
    "audit_web_office_para_adapter_applycharpr",
    "audit_web_office_para_edit_e2e_integration",
    "audit_web_office_para_readback_parser",
]


@pytest.mark.parametrize("name", _B_AUDITS)
def test_09f_b_group_audits_report_git_diff_failed_on_rc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    import importlib

    mod = importlib.import_module("scripts.ops." + name)
    _repo_with(tmp_path, {"a.txt": "one\n"})
    monkeypatch.setattr(mod, "PR", tmp_path)
    monkeypatch.setattr(mod, "BASELINE_COMMIT", "no-such-rev")
    monkeypatch.setattr(mod, "LOCKED_FILES", ["a.txt"])
    assert mod._check_locked_files() == [
        {"code": "GIT_DIFF_FAILED", "level": "WARN", "detail": "a.txt: rc=128"}
    ]


# --- check_audit_no_writer_calls --------------------------------------------------


def test_09g_no_writer_calls_requires_both_arguments(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("", encoding="utf-8")
    with pytest.raises(TypeError):
        occ.check_audit_no_writer_calls()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        occ.check_audit_no_writer_calls(f)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        occ.check_audit_no_writer_calls(symbols=["a"])  # type: ignore[call-arg]


def test_09h_no_writer_calls_reports_matches_in_symbol_order(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("b_call()\nzzz\na_call()\n", encoding="utf-8")
    expected = [
        {"code": "AUDIT_FORBIDDEN_WRITER_CALL", "level": "FAIL", "detail": "a_call"},
        {"code": "AUDIT_FORBIDDEN_WRITER_CALL", "level": "FAIL", "detail": r"b_call\("},
    ]
    assert occ.check_audit_no_writer_calls(f, ["a_call", r"b_call\(", "absent"]) == expected
    assert occ.check_audit_no_writer_calls(str(f), ("a_call", r"b_call\(")) == expected  # str 경로·튜플도 같은 결과
    assert occ.check_audit_no_writer_calls(f, []) == []
    assert occ.check_audit_no_writer_calls(f, ["absent"]) == []


def test_09i_no_writer_calls_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        occ.check_audit_no_writer_calls(tmp_path / "nope.py", ["a"])


def _no_writer_audits() -> list[str]:
    names = []
    for p in sorted((ROOT / "scripts" / "ops").glob("*.py")):
        if re.search(r"^def _check_audit_no_writer_calls\(", p.read_text(encoding="utf-8"), re.M):
            names.append(p.stem)
    return names


def _symbols_of(mod: object) -> tuple[str, list[str]]:
    found = [k for k in ("FORBIDDEN_AUDIT_WRITER_SYMBOLS", "FORBIDDEN_WRITER_SYMBOLS") if hasattr(mod, k)]
    assert len(found) == 1
    return found[0], list(getattr(mod, found[0]))


def _realize(sym: str) -> str:
    cand = re.sub(r"\\(.)", r"\1", sym)
    return cand if re.search(sym, cand) else sym


def test_09j_every_no_writer_audit_delegates_with_own_file_and_own_constant() -> None:
    names = _no_writer_audits()
    assert len(names) >= 20
    for name in names:
        src = (ROOT / "scripts" / "ops" / (name + ".py")).read_text(encoding="utf-8")
        m = re.search(r"return occ\.check_audit_no_writer_calls\(__file__, (FORBIDDEN_\w+)\)", src)
        assert m, name  # 자기 복사본을 다시 만들지 않고 공용 함수로 위임한다


@pytest.mark.parametrize("name", _no_writer_audits())
def test_09k_no_writer_audit_uses_its_own_symbol_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    import importlib

    mod = importlib.import_module("scripts.ops." + name)
    const, mine = _symbols_of(mod)
    other_const = "FORBIDDEN_WRITER_SYMBOLS" if const == "FORBIDDEN_AUDIT_WRITER_SYMBOLS" else "FORBIDDEN_AUDIT_WRITER_SYMBOLS"
    other = [
        s
        for n in _no_writer_audits()
        for s in (_symbols_of(importlib.import_module("scripts.ops." + n))[1])
        if other_const in vars(importlib.import_module("scripts.ops." + n))
    ]
    cases = {
        "empty": "",
        "mine_all": "\n".join(_realize(s) for s in mine),
        "other_group_all": "\n".join(_realize(s) for s in other),
    }
    for label, text in cases.items():
        f = tmp_path / f"{label}.py"
        f.write_text(text, encoding="utf-8")
        monkeypatch.setattr(mod, "__file__", str(f))
        expected = [
            {"code": "AUDIT_FORBIDDEN_WRITER_CALL", "level": "FAIL", "detail": s} for s in mine if re.search(s, text)
        ]
        assert mod._check_audit_no_writer_calls() == expected, (name, label)
    # 자기 목록의 심볼은 전부 잡힌다(= 빈 결과로 무력화되지 않았다)
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "mine_all.py"))
    assert [d["detail"] for d in mod._check_audit_no_writer_calls()] == [s for s in mine if re.search(s, cases["mine_all"])]
    assert mine
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "does_not_exist.py"))
    with pytest.raises(FileNotFoundError):
        mod._check_audit_no_writer_calls()


def test_09l_the_two_audit_groups_keep_different_symbol_values() -> None:
    import importlib

    by_const: dict[str, set[str]] = {}
    for n in _no_writer_audits():
        const, syms = _symbols_of(importlib.import_module("scripts.ops." + n))
        by_const.setdefault(const, set()).add("\n".join(syms))
    # 두 상수는 값이 서로 다르고 각 그룹 안에서는 값이 하나로 같다 - 합치면 검사 강도가 바뀐다.
    assert set(by_const) == {"FORBIDDEN_AUDIT_WRITER_SYMBOLS", "FORBIDDEN_WRITER_SYMBOLS"}
    assert all(len(v) == 1 for v in by_const.values())
    assert by_const["FORBIDDEN_AUDIT_WRITER_SYMBOLS"] != by_const["FORBIDDEN_WRITER_SYMBOLS"]


# --- 이름이 감사 수집 패턴에 섞이지 않는다 ---------------------------------------


def test_10_module_name_is_not_collected_as_audit_or_gate() -> None:
    name = Path(MODULE_REL).name
    # 감사 스크립트를 세거나 모으는 파일 이름 패턴(audit_*.py / gate_*.py)에 걸리지 않는다.
    assert not fnmatch.fnmatch(name, "audit_*.py")
    assert not fnmatch.fnmatch(name, "gate_*.py")
    # 분류기의 이름 토큰(audit_/gate_ 등)에도 걸리지 않는다 - 분류는 아래 정확한 경로 규칙이 정한다.
    lowered = MODULE_REL.lower()
    assert not any(tok in lowered for tok in ("audit_", "gate_", "verify_", "build_", "classify_"))


def test_11_module_has_no_audit_entrypoint() -> None:
    # 라이브러리라서 main/audit 진입점이 없다 — 있으면 감사로 오인된다.
    assert not hasattr(occ, "main")
    assert not hasattr(occ, "audit")


def test_12_classification_is_pinned_to_exact_path_and_name_only() -> None:
    # 새 공용 모듈은 정확한 경로 규칙으로 감사 지원 모듈(AUDIT_GATE/closeout_security)이 된다.
    assert inventory.classify_path(MODULE_REL) == ("AUDIT_GATE", "closeout_security", "keep_gate_audit")
    assert inventory.classify_path("tests/test_ops_common_checks.py")[1] == "closeout_security"
    # 넓은 접두사로 번지지 않는다 - 다른 ops_common_* 파일은 자동 편입되지 않는다.
    other = inventory.classify_path("scripts/ops/ops_common_other.py")
    assert other[0] != "AUDIT_GATE" and other[1] == "unassigned"


# --- 소함수 7종의 공용 구현 (P4-4b) -------------------------------------------


@pytest.mark.parametrize("ok", [True, 1, "x", [0]])
def test_13a_check_result_pass_has_no_fail_code(ok: object) -> None:
    got = occ.check_result("C1", "설명", ok, "FC")  # type: ignore[arg-type]
    assert got == {"code": "C1", "desc": "설명", "status": "PASS", "failCode": None}


@pytest.mark.parametrize("ok", [False, 0, "", None])
def test_13b_check_result_fail_carries_fail_code_only_when_given(ok: object) -> None:
    assert occ.check_result("C1", "d", ok, "FC")["failCode"] == "FC"  # type: ignore[arg-type]
    assert occ.check_result("C1", "d", ok)["failCode"] is None  # type: ignore[arg-type]
    assert occ.check_result("C1", "d", ok)["status"] == "FAIL"  # type: ignore[arg-type]


def test_13c_load_json_file_none_or_empty_is_none_and_errors_propagate(tmp_path: Path) -> None:
    good = tmp_path / "ok.json"
    good.write_text('["a", "b"]', encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    assert occ.load_json_file(None) is None
    assert occ.load_json_file("") is None
    assert occ.load_json_file(str(good)) == ["a", "b"]
    with pytest.raises(FileNotFoundError):
        occ.load_json_file(str(tmp_path / "missing.json"))
    with pytest.raises(ValueError):  # JSONDecodeError 는 ValueError 의 하위
        occ.load_json_file(str(bad))


def test_13d_missing_phrase_findings_keeps_phrase_order_and_code() -> None:
    got = occ.missing_phrase_findings("alpha 한글", ["zzz", "alpha", "qqq", "한글"], "MISSING")
    assert got == [
        {"code": "MISSING", "level": "FAIL", "detail": "zzz"},
        {"code": "MISSING", "level": "FAIL", "detail": "qqq"},
    ]
    assert occ.missing_phrase_findings("anything", [], "MISSING") == []


@pytest.mark.parametrize(
    ("rc", "exc", "expected"),
    [
        (0, None, True),
        (1, None, False),
        (127, None, False),
        (None, FileNotFoundError("node"), False),
        (None, subprocess.TimeoutExpired(["node"], 10), False),
    ],
)
def test_13e_node_available_maps_run_outcomes_to_bool(
    monkeypatch: pytest.MonkeyPatch, rc: int | None, exc: Exception | None, expected: bool
) -> None:
    calls: list[tuple] = []

    def fake_run(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        if exc is not None:
            raise exc
        return type("R", (), {"returncode": rc})()

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert occ.node_available() is expected
    assert calls[0][0] == (["node", "--version"],)
    assert calls[0][1]["timeout"] == 10


def test_13f_node_available_does_not_swallow_other_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> object:
        raise PermissionError("x")

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(PermissionError):
        occ.node_available()


def _fake_paragraph(
    kind: str | None = "cell", pp: int = 1, runs: bool = True, cp: int = 1, text: str | None = "ab"
) -> object:
    import types

    run_list = [types.SimpleNamespace(charPrIDRef=cp)] if runs else []
    return types.SimpleNamespace(
        containerScope={"kind": kind} if kind else None, parPrIDRef=pp, runs=run_list, text=text
    )


def test_13g_pick_cell_paragraph_takes_first_qualifying_cell_paragraph() -> None:
    import types

    first, second = _fake_paragraph(text="first"), _fake_paragraph(text="second")
    assert occ.pick_cell_paragraph(types.SimpleNamespace(paragraphs=[first, second])) is first
    skipped = [
        _fake_paragraph(kind="body"),
        _fake_paragraph(text="a"),
        _fake_paragraph(text=None),
        _fake_paragraph(pp=0),
        _fake_paragraph(runs=False),
        _fake_paragraph(cp=0),
        _fake_paragraph(kind=None),
    ]
    assert occ.pick_cell_paragraph(types.SimpleNamespace(paragraphs=skipped)) is None
    assert occ.pick_cell_paragraph(types.SimpleNamespace(paragraphs=[skipped[0], second])) is second


def test_13h_sha256_file_matches_hashlib_and_missing_file_raises(tmp_path: Path) -> None:
    import hashlib

    f = tmp_path / "h.bin"
    f.write_bytes(b"hello\x00world\n" * 100)
    assert occ.sha256_file(f) == hashlib.sha256(f.read_bytes()).hexdigest()
    with pytest.raises(FileNotFoundError):
        occ.sha256_file(tmp_path / "missing.bin")


_SMALL_HELPER_CALLS = {
    "_check": "occ.check_result(code, desc, ok, fail_code)",
    "_load_decisions": "occ.load_json_file(path)",
    "_load_paths": "occ.load_json_file(path)",
    "_missing_phrase_findings": "occ.missing_phrase_findings(src, phrases, code)",
    "_node_ok": "occ.node_available()",
    "_pick_paragraph": "occ.pick_cell_paragraph(doc)",
}


def _delegating_helpers() -> dict[str, list[str]]:
    """scripts/ops 의 최상위 함수 중 본문이 `return occ.<공용 함수>(...)` 한 문장인 것을 이름별로 모은다."""
    import ast

    found: dict[str, list[str]] = {}
    for path in sorted((ROOT / "scripts" / "ops").glob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.FunctionDef):
                continue
            has_doc = (
                bool(node.body)
                and isinstance(node.body[0], ast.Expr)
                and isinstance(getattr(node.body[0], "value", None), ast.Constant)
            )
            body = node.body[1:] if has_doc else node.body
            if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
                continue
            call = ast.unparse(body[0].value)
            if node.name == "_sha":
                expected = f"occ.sha256_file({node.args.args[0].arg})"
            else:
                expected = _SMALL_HELPER_CALLS.get(node.name)
            if expected is not None and call == expected:
                found.setdefault(node.name, []).append(path.name)
    return found


def test_13i_small_helpers_stay_delegated_to_the_shared_implementation() -> None:
    found = _delegating_helpers()
    # 이 PR 에서 위임한 개수 아래로 줄면(복사본이 다시 생기면) 실패한다.
    minimum = {
        "_check": 4,
        "_sha": 7,
        "_pick_paragraph": 3,
        "_missing_phrase_findings": 5,
        "_node_ok": 6,
        "_load_decisions": 2,
        "_load_paths": 3,
    }
    for name, count in minimum.items():
        assert len(found.get(name, [])) >= count, (name, found.get(name))


_PREFIX_PROBE = """
import ast, pathlib, sys
bad = []
for p in sorted(pathlib.Path(sys.argv[1]).glob('*.py')):
    t = ast.parse(p.read_text(encoding='utf-8'))
    idx = next((i for i, n in enumerate(t.body) if isinstance(n, ast.ImportFrom) and n.module == 'scripts.ops'
                and any(a.name == 'ops_common_checks' for a in n.names)), None)
    if idx is None:
        continue
    saved = list(sys.path)
    for k in [k for k in sys.modules if k == 'scripts' or k.startswith('scripts.')]:
        del sys.modules[k]
    try:
        exec(compile(ast.Module(body=t.body[:idx + 1], type_ignores=[]), str(p), 'exec'),
             {'__file__': str(p), '__name__': 'x'})
    except BaseException as e:
        bad.append(p.name + ':' + type(e).__name__)
    sys.path[:] = saved
print('BAD=' + ','.join(bad))
"""


def test_13j_every_file_importing_occ_can_resolve_it_from_a_foreign_cwd(tmp_path: Path) -> None:
    # 감사 스크립트는 직접 실행되므로, occ import 앞에서 sys.path 에 저장소 루트가 들어가야 한다.
    # import 앞까지의 최상위 문장만 새 인터프리터에서 실행해(감사 본문은 실행하지 않는다) 확인한다.
    r = subprocess.run(
        [sys.executable, "-I", "-c", _PREFIX_PROBE, str(ROOT / "scripts" / "ops")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert r.returncode == 0, r.stderr[-300:]
    assert r.stdout.strip() == "BAD=", r.stdout[-300:]
