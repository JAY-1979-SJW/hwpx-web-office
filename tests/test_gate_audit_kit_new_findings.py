"""audit-kit 신규 위반 차단 비교(gate_audit_kit_new_findings) 시험 — 가짜 findings 와 임시 폴더만 쓴다(audit-kit 실행 없음)."""

from __future__ import annotations

import tomllib
from collections import Counter
from pathlib import Path

from scripts.ops import gate_audit_kit_new_findings as gate

ROOT = Path(__file__).resolve().parents[1]


def _f(rule: str, file_name: str, tool: str = "ruff", severity: str = "improve") -> dict[str, str]:
    return {"tool": tool, "rule": rule, "file": file_name, "severity": severity, "message": "비출력 문구"}


def _cmp(base: list[dict[str, str]], head: list[dict[str, str]], removed: set[str] | None = None, added: set[str] | None = None):
    return gate.compare_counts(gate.count_findings(base), gate.count_findings(head), removed or set(), added or set())


def test_count_findings_skips_ignored_and_normalizes_separators() -> None:
    counts = gate.count_findings([_f("F401", "a\\b.py"), _f("F401", "a/b.py"), _f("F401", "a/b.py", severity="ignore")])
    assert counts == Counter({("ruff", "F401", "a/b.py"): 2})


def test_increase_fails_and_equal_or_decrease_passes() -> None:
    base = [_f("F401", "a.py"), _f("F401", "a.py")]
    assert _cmp(base, base) == []
    assert _cmp(base, [_f("F401", "a.py")]) == []
    assert _cmp(base, []) == []
    assert _cmp(base, base + [_f("F401", "a.py")]) == [(("ruff", "F401", "a.py"), 2, 3)]


def test_other_rule_or_tool_in_same_file_is_a_new_finding() -> None:
    base = [_f("F401", "a.py")]
    assert _cmp(base, base + [_f("E402", "a.py")]) == [(("ruff", "E402", "a.py"), 0, 1)]
    assert _cmp(base, base + [_f("F401", "a.py", tool="std-ruff")]) == [(("std-ruff", "F401", "a.py"), 0, 1)]


def test_new_file_starts_from_zero() -> None:
    base = [_f("F401", "a.py")]
    assert _cmp(base, base, added={"new.py"}) == []
    assert _cmp(base, base + [_f("F401", "new.py")], added={"new.py"}) == [(("ruff", "F401", "new.py"), 0, 1)]


def test_fixing_one_file_does_not_excuse_a_new_finding_in_another_existing_file() -> None:
    base = [_f("F401", "a.py"), _f("F401", "a.py"), _f("F401", "b.py")]
    head = [_f("F401", "b.py"), _f("F401", "b.py")]
    assert _cmp(base, head) == [(("ruff", "F401", "b.py"), 1, 2)]


def test_rename_is_judged_by_rule_total_for_added_files_only() -> None:
    base = [_f("F401", "old.py"), _f("F401", "old.py"), _f("E402", "old.py")]
    moved = [_f("F401", "moved.py"), _f("F401", "moved.py"), _f("E402", "moved.py")]
    # 이름만 바뀐 경우: 총합이 같으니 통과
    assert _cmp(base, moved, removed={"old.py"}, added={"moved.py"}) == []
    # 옮기면서 한 건 늘었으면 그 한 건만 위반
    assert _cmp(base, moved + [_f("F401", "moved.py")], removed={"old.py"}, added={"moved.py"}) == [
        (("ruff", "F401", "moved.py"), 0, 3)
    ]
    # 비워진 몫은 같은 (도구, 규칙) 의 새 파일에만 쓰이고 다른 규칙·기존 파일의 증가는 흡수하지 않는다
    other_rule = [_f("F401", "moved.py")] * 2 + [_f("E402", "moved.py")] + [_f("E741", "moved.py")]
    assert _cmp(base, other_rule, removed={"old.py"}, added={"moved.py"}) == [(("ruff", "E741", "moved.py"), 0, 1)]
    existing = [_f("F401", "keep.py")]
    assert _cmp(base + existing, [_f("F401", "keep.py")] * 2, removed={"old.py"}) == [(("ruff", "F401", "keep.py"), 1, 2)]


def test_changed_file_sets_uses_tree_existence(tmp_path: Path) -> None:
    base_tree, head_tree = tmp_path / "base", tmp_path / "head"
    for tree, names in ((base_tree, ["gone.py", "same.py"]), (head_tree, ["same.py", "fresh.py"])):
        for name in names:
            (tree / name).parent.mkdir(parents=True, exist_ok=True)
            (tree / name).write_text("x = 1\n", encoding="utf-8")
    base = gate.count_findings([_f("F401", "gone.py"), _f("F401", "same.py")])
    head = gate.count_findings([_f("F401", "fresh.py"), _f("F401", "same.py")])
    assert gate.changed_file_sets(base_tree, head_tree, base, head) == ({"gone.py"}, {"fresh.py"})


def test_render_lists_rule_totals_and_never_prints_messages() -> None:
    base = gate.count_findings([_f("F401", "a.py")])
    head = gate.count_findings([_f("F401", "a.py"), _f("F401", "b.py")])
    violations = gate.compare_counts(base, head, set(), set())
    text = gate.render(base, head, violations)
    assert "ruff/F401: 1 -> 2 (+1)" in text
    assert "ruff/F401 b.py 0 -> 1" in text
    assert "비출력 문구" not in text


def test_main_fails_closed_when_audit_kit_cannot_run(tmp_path: Path, capsys) -> None:
    code = gate.main(["--base-tree", str(tmp_path), "--head-tree", str(tmp_path), "--kit", str(tmp_path / "missing-kit")])
    assert code == 2
    assert "FAIL(측정 실패)" in capsys.readouterr().out


def test_layer_contracts_are_defined_for_both_import_notations() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["importlinter"]
    contracts = config["contracts"]
    assert sorted(c["containers"][0] for c in contracts) == ["hwpx", "scripts.hwpx"]
    assert all(c["type"] == "layers" for c in contracts)
    assert contracts[0]["layers"] == contracts[1]["layers"]
    assert set(config["root_packages"]) == {"hwpx", "scripts"}
