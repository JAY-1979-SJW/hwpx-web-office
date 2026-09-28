#!/usr/bin/env python3
"""Post-commit devlog writer.

Default behavior writes change history and devlog files only. It never creates
an additional commit unless ALLOW_POST_COMMIT_AUTO_COMMIT=1 is explicitly set.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
DIFF_MAX_CHARS = 8000
AUTO_COMMIT_ENV = "ALLOW_POST_COMMIT_AUTO_COMMIT"
KNOWN_SECRET_PREFIXES = ("s" + "k-", "gh" + "p_", "AI" + "za")
SECRET_LITERAL_RE = re.compile(
    r'"(?:' + "|".join(re.escape(prefix) for prefix in KNOWN_SECRET_PREFIXES) + r')[^"\r\n]*"'
)


def run(cmd: list[str], cwd=None) -> str:
    return subprocess.check_output(cmd, text=True, encoding="utf-8", cwd=cwd).strip()


def mask_secret_literals(text: str) -> str:
    return SECRET_LITERAL_RE.sub('"[REDACTED_SECRET]"', text or "")


def auto_commit_enabled(env: dict[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    return values.get(AUTO_COMMIT_ENV) == "1"


def commit_generated_devlog(repo: Path, devlog_path: Path, jsonl_path: Path, commit_hash: str) -> bool:
    if not auto_commit_enabled():
        print(f"[post-commit] auto commit disabled; set {AUTO_COMMIT_ENV}=1 to opt in")
        return False

    subprocess.run(["git", "add", str(devlog_path), str(jsonl_path)], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", f"docs: devlog {commit_hash}"], cwd=repo, check=True)
    print(f"[post-commit] docs: devlog {commit_hash} auto commit complete")
    return True


def generate_devlog_claude(
    commit_msg: str,
    commit_body: str,
    changed_files: list[str],
    diff_text: str,
    date_str: str,
    author: str,
    branch: str,
    commit_hash: str,
) -> str:
    files_md = "\n".join(f"- `{f}`" for f in changed_files)
    prompt = f"""git diff and the commit message are provided below.
Write a concise Korean development log in Markdown only.
Do not include secrets, credentials, tokens, cookies, or session values.

Commit message: {commit_msg}
Commit body: {commit_body or "(none)"}
Changed files:
{files_md}

Diff:
{diff_text}

# {commit_msg}

- 작업일시: {date_str}
- 작업자: {author}
- 관련 브랜치: {branch}
- 관련 커밋: {commit_hash}

## 목표

## 수정 파일

{files_md}

## 변경 이유

## 검증 결과

## 다음 단계
"""
    prompt = mask_secret_literals(prompt)
    result = subprocess.run(
        ["claude", "-p", prompt, "--allowedTools", ""],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "claude CLI error")
    return mask_secret_literals(result.stdout.strip())


def make_stub(
    commit_msg: str,
    changed_files: list[str],
    date_str: str,
    author: str,
    branch: str,
    commit_hash: str,
) -> str:
    files_md = "\n".join(f"- `{f}`" for f in changed_files)
    return mask_secret_literals(
        f"""# {commit_msg}

- 작업일시: {date_str}
- 작업자: {author}
- 관련 브랜치: {branch}
- 관련 커밋: {commit_hash}

## 목표

확인 필요

## 수정 파일

{files_md}

## 변경 이유

확인 필요

## 검증 결과

확인 필요

## 다음 단계

- 확인 필요
"""
    )


def claude_available() -> bool:
    try:
        subprocess.run(["claude", "--version"], capture_output=True, timeout=5)
        return True
    except Exception:  # noqa: BLE001 -- 이 단계만 기록 후 계속
        return False


def main():
    repo = Path(run(["git", "rev-parse", "--show-toplevel"]))
    commit_msg = run(["git", "log", "-1", "--pretty=%s"])

    if commit_msg.startswith("docs: devlog"):
        sys.exit(0)

    commit_hash = run(["git", "rev-parse", "--short", "HEAD"])
    commit_body = run(["git", "log", "-1", "--pretty=%b"])
    author = run(["git", "config", "user.name"])
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    raw_files = run(["git", "diff-tree", "--no-commit-id", "-r", "--name-only", "HEAD"])
    changed_files = [f for f in raw_files.splitlines() if f]

    now = datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")

    entry = {
        "timestamp": timestamp,
        "task_name": mask_secret_literals(commit_msg),
        "changed_files": changed_files,
        "summary": mask_secret_literals(commit_body.replace("\n", " ").strip() if commit_body else commit_msg),
        "result": "ok",
        "commit_hash": commit_hash,
        "notes": "",
    }

    jsonl_path = repo / "logs" / "change_history.jsonl"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    existing = jsonl_path.read_text(encoding="utf-8") if jsonl_path.exists() else ""
    with Path(jsonl_path).open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if existing:
            f.write(existing)
    print(f"[post-commit] change_history.jsonl <- {commit_hash}  {commit_msg}")

    devlog_dir = repo / "docs" / "devlog"
    devlog_dir.mkdir(parents=True, exist_ok=True)
    devlog_path = devlog_dir / f"{date_str}-{commit_hash}.md"

    if claude_available():
        try:
            diff_text = run(["git", "show", "--no-color", "-p", "HEAD"])
            diff_text = mask_secret_literals(diff_text)
            if len(diff_text) > DIFF_MAX_CHARS:
                diff_text = diff_text[:DIFF_MAX_CHARS] + "\n... (truncated)"
            print("[post-commit] writing devlog with Claude Code...")
            content = generate_devlog_claude(
                mask_secret_literals(commit_msg),
                mask_secret_literals(commit_body),
                changed_files,
                diff_text,
                date_str,
                author,
                branch,
                commit_hash,
            )
        except Exception as exc:  # noqa: BLE001 -- 이 단계만 기록 후 계속
            print(f"[post-commit] Claude failed ({exc}); writing stub", file=sys.stderr)
            content = make_stub(mask_secret_literals(commit_msg), changed_files, date_str, author, branch, commit_hash)
    else:
        print("[post-commit] claude CLI unavailable; writing stub", file=sys.stderr)
        content = make_stub(mask_secret_literals(commit_msg), changed_files, date_str, author, branch, commit_hash)

    content = mask_secret_literals(content)
    devlog_path.write_text(content, encoding="utf-8", newline="\n")
    print(f"[post-commit] devlog -> docs/devlog/{devlog_path.name}")
    commit_generated_devlog(repo, devlog_path, jsonl_path, commit_hash)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- 이 단계만 기록 후 계속
        print(f"[post-commit] warning: {exc}", file=sys.stderr)
        sys.exit(0)
