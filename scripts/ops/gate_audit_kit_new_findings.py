#!/usr/bin/env python3
"""audit-kit 신규 위반 차단 — 기준 트리와 PR 트리의 finding 을 비교해 "이번 PR 로 늘어난" 것만 실패시킨다.

기준선 숫자를 저장하지 않는다: 비교 대상은 매번 같은 환경에서 새로 잰 기준 트리(병합 대상 브랜치 끝)이므로
올려서 통과시킬 숫자가 없다. 키는 (도구, 규칙, 파일) 별 건수라 줄 번호 이동은 무시한다.

판정(파일별):
  - 기준보다 늘었으면 위반. 기준에 없던 파일은 0 에서 시작한다.
  - 이름 바꿈·이동: 기준 트리에서 사라진 파일의 건수를 (도구, 규칙) 별 "비워진 몫"으로 모아 두고,
    새로 생긴 파일의 증가분만 그 몫만큼 흡수한다(총합이 늘지 않으면 통과). 기존 파일의 증가는 흡수하지 않는다.
출력은 규칙·파일·건수뿐이며 finding 메시지는 출력하지 않는다.

사용: python scripts/ops/gate_audit_kit_new_findings.py --base-tree <기준 트리> --head-tree <PR 트리> --kit <audit-kit 실행 파일>
종료코드: 0 통과 / 1 신규 위반 / 2 audit-kit 실행·결과 읽기 실패(통과로 간주하지 않는다).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

IGNORED_SEVERITY = "ignore"
RUN_TIMEOUT_S = 1200
MAX_LISTED = 50

Key = tuple[str, str, str]  # (도구, 규칙, 파일)


def count_findings(findings: list[dict[str, Any]]) -> Counter[Key]:
    """무시(ignore) 등급을 뺀 finding 을 (도구, 규칙, 파일) 별로 센다. 경로 구분자는 '/' 로 맞춘다."""
    counts: Counter[Key] = Counter()
    for item in findings:
        if item.get("severity") == IGNORED_SEVERITY:
            continue
        file_name = str(item.get("file") or "").replace("\\", "/")
        counts[(str(item.get("tool", "")), str(item.get("rule", "")), file_name)] += 1
    return counts


def compare_counts(
    base: Counter[Key],
    head: Counter[Key],
    removed_files: set[str],
    added_files: set[str],
) -> list[tuple[Key, int, int]]:
    """위반 목록 [(키, 기준 건수, PR 건수)] 을 키 순으로 돌려준다. 비어 있으면 통과.

    removed_files: 기준 트리에는 있고 PR 트리에는 없는 파일. added_files: 그 반대.
    """
    freed: Counter[tuple[str, str]] = Counter()
    for (tool, rule, file_name), count in base.items():
        if file_name in removed_files:
            freed[(tool, rule)] += count
    violations: list[tuple[Key, int, int]] = []
    for key in sorted(head):
        tool, rule, file_name = key
        increase = head[key] - base.get(key, 0)
        if increase <= 0:
            continue
        if file_name in added_files:
            absorbed = min(increase, freed[(tool, rule)])
            freed[(tool, rule)] -= absorbed
            increase -= absorbed
        if increase > 0:
            violations.append((key, base.get(key, 0), head[key]))
    return violations


def rule_totals(counts: Counter[Key]) -> Counter[tuple[str, str]]:
    totals: Counter[tuple[str, str]] = Counter()
    for (tool, rule, _file), count in counts.items():
        totals[(tool, rule)] += count
    return totals


def _finding_files(counts: Counter[Key]) -> set[str]:
    return {file_name for (_tool, _rule, file_name) in counts if file_name}


def changed_file_sets(base_tree: Path, head_tree: Path, base: Counter[Key], head: Counter[Key]) -> tuple[set[str], set[str]]:
    """(removed_files, added_files) — finding 에 나온 파일 중 한쪽 트리에만 존재하는 것."""
    removed = {f for f in _finding_files(base) if not (head_tree / f).exists()}
    added = {f for f in _finding_files(head) if not (base_tree / f).exists()}
    return removed, added


def _newest_report(tree: Path, std: bool, before: set[Path]) -> Path:
    reports = tree / "audit-reports"
    fresh = [p for p in reports.glob("*/findings.json") if p not in before and p.parent.name.startswith("std_") == std]
    if not fresh:
        raise RuntimeError(f"audit-kit 결과(findings.json)가 생기지 않았습니다: {'std' if std else 'run'}")
    return max(fresh, key=lambda p: p.stat().st_mtime)


def measure_tree(kit: str, tree: Path) -> Counter[Key]:
    """audit-kit run(테스트 단계 제외) 과 std 를 각각 돌려 finding 건수를 모은다. 실패는 예외로 올린다."""
    total: Counter[Key] = Counter()
    for std in (False, True):
        before = set((tree / "audit-reports").glob("*/findings.json"))
        command = [kit, "std" if std else "run", "--path", str(tree), "--solo", "--fail-on", "never"]
        if not std:
            command.append("--no-tests")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RUN_TIMEOUT_S,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"audit-kit {'std' if std else 'run'} 종료코드 {result.returncode} ({tree.name})")
        report = _newest_report(tree, std, before)
        total += count_findings(json.loads(report.read_text(encoding="utf-8"))["findings"])
    return total


def render(
    base: Counter[Key], head: Counter[Key], violations: list[tuple[Key, int, int]]
) -> str:
    base_totals, head_totals = rule_totals(base), rule_totals(head)
    lines = ["audit-kit 규칙별 총합 (기준 -> PR):"]
    for tool_rule in sorted(set(base_totals) | set(head_totals)):
        before, after = base_totals[tool_rule], head_totals[tool_rule]
        if before != after:
            lines.append(f"  {tool_rule[0]}/{tool_rule[1]}: {before} -> {after} ({after - before:+d})")
    lines.append(f"  전체: {sum(base_totals.values())} -> {sum(head_totals.values())}")
    if violations:
        lines.append(f"신규 위반 {len(violations)}건 (도구/규칙, 파일, 기준 -> PR):")
        for (tool, rule, file_name), before, after in violations[:MAX_LISTED]:
            lines.append(f"  {tool}/{rule} {file_name or '(파일 없음)'} {before} -> {after}")
        if len(violations) > MAX_LISTED:
            lines.append(f"  ... 외 {len(violations) - MAX_LISTED}건")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--head-tree", required=True, type=Path)
    parser.add_argument("--kit", required=True, help="audit-kit 실행 파일 경로")
    args = parser.parse_args(argv)
    try:
        base = measure_tree(args.kit, args.base_tree)
        head = measure_tree(args.kit, args.head_tree)
    except (RuntimeError, OSError, subprocess.TimeoutExpired, KeyError, json.JSONDecodeError) as exc:
        print(f"FAIL(측정 실패): {type(exc).__name__}: {exc}")
        return 2
    removed, added = changed_file_sets(args.base_tree, args.head_tree, base, head)
    violations = compare_counts(base, head, removed, added)
    print(render(base, head, violations))
    print("PASS: 신규 위반 없음" if not violations else "FAIL: 이번 변경으로 audit-kit finding 이 늘었습니다")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
