#!/usr/bin/env python3
"""Run a small OpenHWP Rust probe against local HWP files.

The probe is intentionally external to the main converter. It lets the Python
pipeline compare pyhwp/hwp5proc signals with OpenHWP parsing signals without
making Rust a hard runtime dependency for normal conversion.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_TOOLCHAIN = "stable-x86_64-pc-windows-gnu"
DEFAULT_TARGET_DIR = Path("C:/tmp/openhwp_probe_target")
DEFAULT_WORK_DIR = Path("tmp/openhwp_rust_probe")
DEFAULT_OPENHWP_ROOT = Path("tmp/oss_openhwp")


PROBE_MAIN_RS = r'''
use std::env;
use std::fs;
use std::path::PathBuf;

use hwp::HwpDocument;

fn fnv1a64(bytes: &[u8]) -> u64 {
    let mut hash: u64 = 0xcbf29ce484222325;
    for byte in bytes {
        hash ^= *byte as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    hash
}

fn json_escape(value: &str) -> String {
    let mut out = String::with_capacity(value.len() + 8);
    for ch in value.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            c if c < '\u{20}' => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

fn main() {
    let path = match env::args_os().nth(1) {
        Some(value) => PathBuf::from(value),
        None => {
            println!("{{\"status\":\"FAIL\",\"error\":\"INPUT_MISSING\"}}");
            std::process::exit(2);
        }
    };
    let bytes = match fs::read(&path) {
        Ok(value) => value,
        Err(err) => {
            println!(
                "{{\"status\":\"FAIL\",\"error\":\"READ_FAILED\",\"message\":\"{}\",\"input\":\"{}\"}}",
                json_escape(&err.to_string()),
                json_escape(&path.display().to_string())
            );
            std::process::exit(1);
        }
    };
    match HwpDocument::from_bytes(&bytes) {
        Ok(doc) => {
            let text = doc.extract_text();
            let text_head: String = text.chars().take(400).collect();
            let text_tail_vec: Vec<char> = text.chars().rev().take(400).collect();
            let text_tail: String = text_tail_vec.into_iter().rev().collect();
            println!(
                concat!(
                    "{{",
                    "\"status\":\"PASS\",",
                    "\"input\":\"{}\",",
                    "\"version\":\"{}\",",
                    "\"section_count\":{},",
                    "\"paragraph_count\":{},",
                    "\"text_length\":{},",
                    "\"text_line_count\":{},",
                    "\"text_fnv1a64\":\"{:016x}\",",
                    "\"text_tail\":\"{}\",",
                    "\"text_head\":\"{}\"",
                    "}}"
                ),
                json_escape(&path.display().to_string()),
                json_escape(&doc.version().to_string()),
                doc.section_count(),
                doc.paragraph_count(),
                text.chars().count(),
                text.lines().count(),
                fnv1a64(text.as_bytes()),
                json_escape(&text_tail),
                json_escape(&text_head)
            );
        }
        Err(err) => {
            println!(
                "{{\"status\":\"FAIL\",\"error\":\"PARSE_FAILED\",\"message\":\"{}\",\"input\":\"{}\"}}",
                json_escape(&format!("{:?}", err)),
                json_escape(&path.display().to_string())
            );
            std::process::exit(1);
        }
    }
}
'''.strip() + "\n"


def cargo_toml(openhwp_root: Path) -> str:
    hwp_crate = (openhwp_root / "crates" / "hwp").expanduser().resolve()
    crate_path = str(hwp_crate).replace("\\", "/")
    return (
        "[package]\n"
        'name = "openhwp_probe"\n'
        'version = "0.1.0"\n'
        'edition = "2024"\n'
        "\n"
        "[dependencies]\n"
        f'hwp = {{ path = "{crate_path}" }}\n'
    )


def write_if_changed(path: Path, content: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def ensure_probe_project(work_dir: Path, openhwp_root: Path) -> Path:
    work_dir = work_dir.expanduser().resolve()
    openhwp_root = openhwp_root.expanduser().resolve()
    if not (openhwp_root / "crates" / "hwp" / "Cargo.toml").exists():
        raise FileNotFoundError(f"OpenHWP hwp crate not found: {openhwp_root}")
    write_if_changed(work_dir / "Cargo.toml", cargo_toml(openhwp_root))
    write_if_changed(work_dir / "src" / "main.rs", PROBE_MAIN_RS)
    return work_dir / "Cargo.toml"


def run_probe(
    input_path: Path,
    *,
    openhwp_root: Path = DEFAULT_OPENHWP_ROOT,
    work_dir: Path = DEFAULT_WORK_DIR,
    target_dir: Path = DEFAULT_TARGET_DIR,
    cargo: Path | None = None,
    toolchain: str = DEFAULT_TOOLCHAIN,
    timeout_sec: int = 180,
) -> dict[str, Any]:
    manifest = ensure_probe_project(work_dir, openhwp_root)
    cargo_path = cargo or Path(os.environ.get("CARGO", "")) or None
    if not cargo_path or str(cargo_path) == ".":
        cargo_path = Path.home() / ".cargo" / "bin" / "cargo.exe"
    command = [
        str(cargo_path),
        f"+{toolchain}",
        "run",
        "--quiet",
        "--manifest-path",
        str(manifest),
        "--",
        str(input_path.expanduser().resolve()),
    ]
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(target_dir.expanduser().resolve())
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        env=env,
    )
    stdout = (proc.stdout or "").strip()
    try:
        payload = json.loads(stdout.splitlines()[-1]) if stdout else {}
    except json.JSONDecodeError:
        payload = {"status": "FAIL", "error": "INVALID_PROBE_JSON", "stdout_tail": stdout[-2000:]}
    payload["returncode"] = proc.returncode
    payload["command"] = command
    payload["stderr_tail"] = (proc.stderr or "")[-4000:]
    if proc.returncode != 0 and payload.get("status") == "PASS":
        payload["status"] = "FAIL"
        payload["error"] = "PROBE_PROCESS_FAILED"
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--openhwp-root", type=Path, default=DEFAULT_OPENHWP_ROOT)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--cargo", type=Path)
    parser.add_argument("--toolchain", default=DEFAULT_TOOLCHAIN)
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--out-json", type=Path)
    args = parser.parse_args(argv)

    report = run_probe(
        args.input,
        openhwp_root=args.openhwp_root,
        work_dir=args.work_dir,
        target_dir=args.target_dir,
        cargo=args.cargo,
        toolchain=str(args.toolchain),
        timeout_sec=int(args.timeout_sec),
    )
    if args.out_json:
        resolved = args.out_json.expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
