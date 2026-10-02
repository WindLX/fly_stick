"""统一版本管理脚本的行为回归测试。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "version.py"


def run_version(*args: str) -> subprocess.CompletedProcess[str]:
    """运行版本管理脚本并捕获输出。

    Args:
        *args: 传给脚本的子命令与选项。

    Returns:
        已完成进程的结果，包含返回码、stdout 与 stderr。
    """
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_show_lists_every_source_and_the_absent_js_faces() -> None:
    """``show`` 覆盖四处版本源，并显式报告没有 JS/Deno/pnpm 版本面。"""
    result = run_version("show")
    assert result.returncode == 0
    for path in ("Cargo.toml", "Cargo.lock", "pyproject.toml", "uv.lock"):
        assert path in result.stdout
    assert "本项目没有 Deno/pnpm/package.json 版本面" in result.stdout
    assert "工具版本" in result.stdout


def test_show_json_reports_consistent_sources() -> None:
    """``show --json`` 输出可解析且四个版本源状态一致。"""
    result = run_version("show", "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    assert payload["consistent"] is True
    sources = payload["sources"]
    assert isinstance(sources, list)
    statuses = {item["status"] for item in sources if isinstance(item, dict)}
    assert statuses == {"一致"}


def test_check_accepts_current_version() -> None:
    """``check`` 在四处版本一致时成功并只打印一行。"""
    result = run_version("check")
    assert result.returncode == 0
    assert result.stdout.startswith("版本一致：")
    assert result.stderr == ""


def test_check_rejects_wrong_expected_version() -> None:
    """``check --expect`` 与当前版本不符时退出 1 并向 stderr 打印差异。"""
    result = run_version("check", "--expect", "9.9.9")
    assert result.returncode == 1
    assert "9.9.9" in result.stderr
    assert result.stdout == ""


def test_set_current_version_is_a_noop() -> None:
    """``set`` 目标版本已生效时打印提示且不改动文件。"""
    current = run_version("check").stdout.strip().removeprefix("版本一致：")
    cargo_before = (ROOT / "Cargo.toml").read_text(encoding="utf-8")
    result = run_version("set", current)
    assert result.returncode == 0
    assert result.stdout == f"version already set to {current}\n"
    assert (ROOT / "Cargo.toml").read_text(encoding="utf-8") == cargo_before


def test_set_dry_run_lists_files_without_writing() -> None:
    """``set --dry-run`` 列出将变化的四个文件但不写入。"""
    before = {
        name: (ROOT / name).read_text(encoding="utf-8")
        for name in ("Cargo.toml", "Cargo.lock", "pyproject.toml", "uv.lock")
    }
    result = run_version("set", "9.9.9", "--dry-run")
    assert result.returncode == 0
    for name in before:
        assert name in result.stdout
        assert (ROOT / name).read_text(encoding="utf-8") == before[name]


def test_set_rejects_invalid_semver() -> None:
    """``set`` 对非法版本号退出 2 且不写入任何文件。"""
    cargo_before = (ROOT / "Cargo.toml").read_text(encoding="utf-8")
    result = run_version("set", "not-a-version")
    assert result.returncode == 2
    assert "not-a-version" in result.stderr
    assert (ROOT / "Cargo.toml").read_text(encoding="utf-8") == cargo_before
