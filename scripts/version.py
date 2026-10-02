"""统一的版本管理脚本：查看、校验与更新 fly_stick 的四处版本源。

版本源为 Cargo.toml 的 ``package.version``、Cargo.lock 中 ``fly_stick`` 的版本、
pyproject.toml 的 ``project.version`` 与 uv.lock 中 ``fly-stick`` 的版本。
本项目没有 Deno、pnpm 与 package.json 版本面，脚本会显式报告该事实。

用法：
    python scripts/version.py show [--json]
    python scripts/version.py check [--expect VERSION]
    python scripts/version.py set VERSION [--dry-run] [--no-locks]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

#: 本地 Rust crate 名，对应 Cargo.toml 与 Cargo.lock。
CARGO_PACKAGE = "fly_stick"
#: 本地 Python 发行包名，对应 pyproject.toml 与 uv.lock。
UV_PACKAGE = "fly-stick"
#: 四处版本源相对仓库根的路径与字段位置。
_SOURCE_EDITORS: tuple[tuple[str, str, str], ...] = (
    ("Cargo.toml", "package", "version"),
    ("pyproject.toml", "project", "version"),
)
#: 两个锁文件中本地包记录的位置。
_LOCK_EDITORS: tuple[tuple[str, str], ...] = (
    ("Cargo.lock", CARGO_PACKAGE),
    ("uv.lock", UV_PACKAGE),
)
#: 探测 JS/Deno/pnpm 版本面时检查的仓库根文件。
_JS_FACE_NAMES: tuple[str, ...] = (
    "package.json",
    "deno.json",
    "deno.jsonc",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
)
#: CI 工作流里识别的工具 pin；顺序即 ``show`` 的展示顺序。
_TOOL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("python", re.compile(r"uv python install\s+(\S+)")),
    ("uv", re.compile(r"astral-sh/setup-uv@(\S+)")),
    ("rust", re.compile(r"dtolnay/rust-toolchain@(\S+)")),
    ("maturin", re.compile(r"pyo3/maturin-action@(\S+)", re.IGNORECASE)),
    ("just", re.compile(r"cargo install just(?:\s+--version\s+(\S+))?")),
    ("node", re.compile(r"actions/setup-node@(\S+)|node-version:\s*(\S+)")),
)
#: TOML 表头匹配，用于定位 ``[package]`` / ``[project]`` 等区块。
_SECTION_HEADER = re.compile(r"^\s*\[([^\[\]]+)\]\s*$")
#: 语义化版本匹配，允许前导 ``v`` 与预发布/构建元数据。
_SEMVER = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?P<pre>-[0-9A-Za-z.-]+)?(?P<build>\+[0-9A-Za-z.-]+)?$"
)
#: ``--no-locks`` 时提示手动同步锁文件。
_NO_LOCKS_HINT = (
    "已跳过锁文件（--no-locks）：请手动运行 cargo metadata --format-version 1 "
    ">/dev/null 与 uv lock 同步 Cargo.lock / uv.lock。"
)


class VersionError(Exception):
    """版本源缺失、格式错误或命令行输入非法。"""


@dataclass(frozen=True)
class SourceReading:
    """单个版本源的读取结果。

    Attributes:
        path: 相对仓库根的路径。
        key: 版本字段在文件中的位置描述。
        versions: 该文件中本地包的全部版本记录，按出现顺序排列。
    """

    path: str
    key: str
    versions: tuple[str, ...]


@dataclass(frozen=True)
class ToolPin:
    """CI 工作流中固定的一项工具版本。

    Attributes:
        name: 工具名，如 ``python``、``uv``。
        version: pin 到的版本；工作流未固定版本时为 ``None``。
        source: 形如 ``.github/workflows/ci.yml:19`` 的来源；未发现时为 ``""``。
    """

    name: str
    version: str | None
    source: str


def _read_text(path: Path) -> str:
    """读取 UTF-8 文本文件。

    Args:
        path: 目标文件路径。

    Returns:
        文件全文。

    Raises:
        VersionError: 文件不存在或不可读。
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise VersionError(f"无法读取 {path.name}: {error}") from error


def _load_toml(path: Path) -> object:
    """读取并解析一个 TOML 文件。

    Args:
        path: TOML 文件路径。

    Returns:
        解析得到的 TOML 文档对象。

    Raises:
        VersionError: 文件不可读或不是合法 TOML。
    """
    text = _read_text(path)
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise VersionError(f"{path.name} 不是合法 TOML: {error}") from error


def _dig_str(document: object, keys: Sequence[str], where: str) -> str:
    """按字段路径从 TOML 文档中取出一个字符串。

    Args:
        document: TOML 文档对象。
        keys: 逐级字段名。
        where: 出错信息中显示的来源描述。

    Returns:
        字段的字符串值。

    Raises:
        VersionError: 路径不存在或取值不是字符串。
    """
    current: object = document
    location = "/".join(keys)
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            raise VersionError(f"{where} 缺少字段 {location}")
        current = current[key]
    if not isinstance(current, str):
        raise VersionError(f"{where} 的字段 {location} 不是字符串")
    return current


def _locked_versions(
    document: object, package_name: str, where: str
) -> tuple[str, ...]:
    """收集锁文件 ``[[package]]`` 数组中本地包的全部版本记录。

    Args:
        document: 锁文件 TOML 文档对象。
        package_name: 目标包名。
        where: 出错信息中显示的来源描述。

    Returns:
        按出现顺序排列的版本字符串元组。

    Raises:
        VersionError: 缺少 ``package`` 数组、记录不是表或缺少版本字段。
    """
    if not isinstance(document, dict):
        raise VersionError(f"{where} 顶层不是表")
    packages = document.get("package")
    if not isinstance(packages, list):
        raise VersionError(f"{where} 缺少 [[package]] 数组")
    versions: list[str] = []
    for entry in packages:
        if not isinstance(entry, dict):
            raise VersionError(f"{where} 存在非表的 [[package]] 记录")
        if entry.get("name") != package_name:
            continue
        version = entry.get("version")
        if not isinstance(version, str):
            raise VersionError(f"{where} 中 {package_name} 缺少 version 字段")
        versions.append(version)
    return tuple(versions)


def read_sources(root: Path) -> tuple[SourceReading, ...]:
    """读取全部四处版本源。

    Args:
        root: 仓库根目录。

    Returns:
        四个版本源的读取结果，顺序为 Cargo.toml、Cargo.lock、pyproject.toml、uv.lock。

    Raises:
        VersionError: 任一文件缺失、无法解析或字段类型非法。
    """
    cargo_toml = _load_toml(root / "Cargo.toml")
    cargo_lock = _load_toml(root / "Cargo.lock")
    pyproject = _load_toml(root / "pyproject.toml")
    uv_lock = _load_toml(root / "uv.lock")
    return (
        SourceReading(
            path="Cargo.toml",
            key="package.version",
            versions=(_dig_str(cargo_toml, ("package", "version"), "Cargo.toml"),),
        ),
        SourceReading(
            path="Cargo.lock",
            key=f"package[name={CARGO_PACKAGE}].version",
            versions=_locked_versions(cargo_lock, CARGO_PACKAGE, "Cargo.lock"),
        ),
        SourceReading(
            path="pyproject.toml",
            key="project.version",
            versions=(_dig_str(pyproject, ("project", "version"), "pyproject.toml"),),
        ),
        SourceReading(
            path="uv.lock",
            key=f"package[name={UV_PACKAGE}].version",
            versions=_locked_versions(uv_lock, UV_PACKAGE, "uv.lock"),
        ),
    )


def collect_tool_pins(root: Path) -> tuple[ToolPin, ...]:
    """从 ``.github/workflows/`` 提取只读的工具版本 pin。

    Args:
        root: 仓库根目录。

    Returns:
        每个已识别工具一条记录；未在任何工作流中声明的工具版本为 ``None``。
    """
    workflow_dir = root / ".github" / "workflows"
    workflows = sorted(workflow_dir.glob("*.y*ml")) if workflow_dir.is_dir() else []
    texts = {path.name: (path.read_text(encoding="utf-8"), path) for path in workflows}
    pins: list[ToolPin] = []
    for name, pattern in _TOOL_PATTERNS:
        found: ToolPin | None = None
        for filename, (text, _) in texts.items():
            match = pattern.search(text)
            if match is None:
                continue
            groups: tuple[str | None, ...] = match.groups()
            version = next((value for value in groups if value is not None), None)
            line = text.count("\n", 0, match.start()) + 1
            found = ToolPin(
                name=name,
                version=version,
                source=f".github/workflows/{filename}:{line}",
            )
            break
        pins.append(
            found if found is not None else ToolPin(name=name, version=None, source="")
        )
    return tuple(pins)


def detect_javascript_faces(root: Path) -> tuple[str, ...]:
    """探测仓库根是否存在 JS/Deno/pnpm 版本面文件。

    Args:
        root: 仓库根目录。

    Returns:
        实际存在的版本面文件名元组；本项目预期为空。
    """
    return tuple(name for name in _JS_FACE_NAMES if (root / name).exists())


def normalize_version(raw: str) -> str:
    """把用户输入规范化为语义化版本字符串。

    Args:
        raw: 原始版本输入，允许带前导 ``v``。

    Returns:
        去掉前导 ``v`` 后的 ``X.Y.Z[-pre][+build]`` 字符串。

    Raises:
        VersionError: 输入不是合法语义化版本。
    """
    match = _SEMVER.match(raw.strip())
    if match is None:
        raise VersionError(f"{raw!r} 不是合法版本号，应形如 1.2.3 或 v1.2.3")
    return (
        f"{match.group('major')}.{match.group('minor')}.{match.group('patch')}"
        f"{match.group('pre') or ''}{match.group('build') or ''}"
    )


def _distinct_versions(sources: Sequence[SourceReading]) -> tuple[str, ...]:
    """汇总所有版本源中出现过的不同版本值。

    Args:
        sources: 版本源读取结果。

    Returns:
        按首次出现顺序排列的不同版本文本元组。
    """
    distinct: list[str] = []
    for source in sources:
        for version in source.versions:
            if version not in distinct:
                distinct.append(version)
    return tuple(distinct)


def _reference_version(sources: Sequence[SourceReading]) -> str | None:
    """取基准版本，优先使用 Cargo.toml 的单条记录。

    Args:
        sources: 版本源读取结果。

    Returns:
        第一个只有单条记录的版本源取值；都不满足时为 ``None``。
    """
    for source in sources:
        if len(source.versions) == 1:
            return source.versions[0]
    return None


def _is_consistent(sources: Sequence[SourceReading]) -> bool:
    """判断四处版本源是否各恰好一条记录且取值一致。

    Args:
        sources: 版本源读取结果。

    Returns:
        完全一致时为 ``True``。
    """
    if any(len(source.versions) != 1 for source in sources):
        return False
    return len(_distinct_versions(sources)) == 1


def _display_versions(source: SourceReading) -> str:
    """把版本源的记录渲染成一行可读文本。

    Args:
        source: 单个版本源的读取结果。

    Returns:
        缺失时为 ``缺失``，否则为逗号分隔的版本列表。
    """
    if not source.versions:
        return "缺失"
    return ", ".join(source.versions)


def _source_status(source: SourceReading, reference: str | None) -> str:
    """给出单个版本源相对基准的状态标签。

    Args:
        source: 单个版本源的读取结果。
        reference: 基准版本，可能为 ``None``。

    Returns:
        状态标签：``一致``、``不匹配``、``缺失`` 或 ``记录重复``。
    """
    if not source.versions:
        return "缺失"
    if len(source.versions) != 1:
        return "记录重复"
    if reference is not None and source.versions[0] != reference:
        return "不匹配"
    return "一致"


def _format_versions(sources: Sequence[SourceReading]) -> str:
    """把全部版本源压成 ``路径=版本`` 的一行摘要。

    Args:
        sources: 版本源读取结果。

    Returns:
        逗号分隔的 ``路径=版本`` 文本。
    """
    return ", ".join(f"{source.path}={_display_versions(source)}" for source in sources)


def run_show(root: Path, *, as_json: bool) -> int:
    """执行 ``show`` 子命令：只读打印版本源、工具版本与 JS 版本面。

    Args:
        root: 仓库根目录。
        as_json: 为 ``True`` 时输出 JSON。

    Returns:
        退出码，恒为 0。
    """
    sources = read_sources(root)
    tools = collect_tool_pins(root)
    faces = detect_javascript_faces(root)
    reference = _reference_version(sources)
    consistent = _is_consistent(sources)
    if as_json:
        payload: dict[str, object] = {
            "consistent": consistent,
            "version": reference,
            "sources": [
                {
                    "path": source.path,
                    "key": source.key,
                    "versions": list(source.versions),
                    "status": _source_status(source, reference),
                }
                for source in sources
            ],
            "tools": [
                {"name": pin.name, "version": pin.version, "source": pin.source}
                for pin in tools
            ],
            "javascript_faces": list(faces),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    lines = ["版本源（只读）"]
    lines.extend(
        f"  {source.path:<16}{source.key:<40}{_display_versions(source):<16}"
        f"{_source_status(source, reference)}"
        for source in sources
    )
    if consistent:
        lines.append(f"状态：四处版本一致，当前版本 {reference}")
    else:
        lines.append("状态：版本源不一致，或存在缺失/重复记录：")
        lines.append(f"  {_format_versions(sources)}")
    lines.append("")
    lines.append("工具版本（只读，来源 .github/workflows/）")
    if tools:
        lines.extend(
            f"  {pin.name:<10}{(pin.version or '未固定'):<18}"
            f"{pin.source or '未在任何 workflow 中声明'}"
            for pin in tools
        )
    else:
        lines.append("  未发现任何工具版本 pin。")
    lines.append("")
    if faces:
        lines.append(f"发现 JS/Deno/pnpm 版本面：{', '.join(faces)}（本脚本不覆盖）。")
    else:
        lines.append(
            "本项目没有 Deno/pnpm/package.json 版本面"
            "（未发现 package.json、deno.json* 或 pnpm-lock.yaml）。"
        )
    print("\n".join(lines))
    return 0


def run_check(root: Path, *, expect: str | None) -> int:
    """执行 ``check`` 子命令：校验四处版本源一致且各恰好一条记录。

    Args:
        root: 仓库根目录。
        expect: 期望版本，可为 ``None``；非空时允许带前导 ``v``。

    Returns:
        一致时返回 0 并打印一行结果；否则打印差异到 stderr 并返回 1。

    Raises:
        VersionError: ``expect`` 不是合法语义化版本。
    """
    expected = normalize_version(expect) if expect is not None else None
    sources = read_sources(root)
    problems: list[str] = []
    for source in sources:
        if len(source.versions) != 1:
            problems.append(
                f"{source.path} 应恰好包含一条本地包记录，"
                f"实际 {len(source.versions)} 条"
            )
    distinct = _distinct_versions(sources)
    if len(distinct) != 1:
        problems.append(f"四处版本不一致：{_format_versions(sources)}")
    elif expected is not None and distinct[0] != expected:
        problems.append(f"期望版本 {expected}，实际 {distinct[0]}")
    if problems:
        print("版本检查失败：", file=sys.stderr)
        for source in sources:
            print(f"  {source.path}  {_display_versions(source)}", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"版本一致：{distinct[0]}")
    return 0


def _replace_section_key(
    text: str, section: str, key: str, value: str
) -> tuple[str, bool]:
    """替换 TOML 文本中某个表内某个字符串键的值。

    Args:
        text: 原始 TOML 文本。
        section: 表名，如 ``package``。
        key: 键名，如 ``version``。
        value: 新的字符串值。

    Returns:
        ``(新文本, 是否发生替换)``；未找到目标字段时新文本与原文相同。
    """
    lines = text.split("\n")
    assignment = re.compile(rf'^(\s*{re.escape(key)}\s*=\s*)"[^"]*"(.*)$')
    current = ""
    for index, line in enumerate(lines):
        header = _SECTION_HEADER.match(line)
        if header is not None:
            current = header.group(1).strip()
            continue
        if current != section:
            continue
        replaced, count = assignment.subn(rf'\g<1>"{value}"\g<2>', line, count=1)
        if count:
            lines[index] = replaced
            return "\n".join(lines), True
    return text, False


def _replace_lock_version(text: str, package_name: str, value: str) -> tuple[str, bool]:
    """替换锁文件 ``[[package]]`` 记录中本地包的 ``version`` 字段。

    Args:
        text: 原始锁文件文本。
        package_name: 目标包名。
        value: 新的版本字符串。

    Returns:
        ``(新文本, 是否发生替换)``；未找到目标记录时新文本与原文相同。
    """
    lines = text.split("\n")
    name_pattern = re.compile(r'^name\s*=\s*"([^"]*)"\s*$')
    version_pattern = re.compile(r'^version\s*=\s*"[^"]*"\s*$')
    current: str | None = None
    for index, line in enumerate(lines):
        if line.strip() == "[[package]]":
            current = None
            continue
        name_match = name_pattern.match(line)
        if name_match is not None and current is None:
            current = name_match.group(1)
            continue
        if current == package_name and version_pattern.match(line) is not None:
            lines[index] = f'version = "{value}"'
            return "\n".join(lines), True
    return text, False


def run_set(root: Path, raw_version: str, *, dry_run: bool, no_locks: bool) -> int:
    """执行 ``set`` 子命令：同步更新源文件与（可选）锁文件中的版本。

    Args:
        root: 仓库根目录。
        raw_version: 目标版本，允许带前导 ``v``。
        dry_run: 为 ``True`` 时只列出将变化的文件。
        no_locks: 为 ``True`` 时跳过两个锁文件并提示手动同步。

    Returns:
        目标版本已生效或写入成功时返回 0；输入非法时返回 2。

    Raises:
        VersionError: 目标字段缺失，或无法读取待更新文件。
    """
    try:
        version = normalize_version(raw_version)
    except VersionError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    planned: dict[str, str] = {}
    for relative, section, key in _SOURCE_EDITORS:
        text = _read_text(root / relative)
        updated, replaced = _replace_section_key(text, section, key, version)
        if not replaced:
            raise VersionError(f"{relative} 的 [{section}] 缺少 {key} 字段")
        if updated != text:
            planned[relative] = updated
    if not no_locks:
        for relative, package in _LOCK_EDITORS:
            text = _read_text(root / relative)
            updated, replaced = _replace_lock_version(text, package, version)
            if not replaced:
                raise VersionError(f"{relative} 缺少本地包 {package} 的 version 记录")
            if updated != text:
                planned[relative] = updated
    if not planned:
        print(f"version already set to {version}")
        if no_locks:
            print(_NO_LOCKS_HINT)
        return 0
    if dry_run:
        print(f"[dry-run] 版本将更新为 {version}，涉及 {len(planned)} 个文件：")
        for relative in planned:
            print(f"  {relative}")
        if no_locks:
            print(_NO_LOCKS_HINT)
        return 0
    for relative, updated in planned.items():
        (root / relative).write_text(updated, encoding="utf-8")
    print(f"版本已更新为 {version}，涉及 {len(planned)} 个文件：")
    for relative in planned:
        print(f"  {relative}")
    print("建议的后续命令：")
    print("  cargo metadata --format-version 1 >/dev/null")
    print("  uv lock")
    if no_locks:
        print(_NO_LOCKS_HINT)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。

    Args:
        无。

    Returns:
        带 ``show`` / ``check`` / ``set`` 三个子命令的解析器。
    """
    parser = argparse.ArgumentParser(
        prog="version.py",
        description="查看、校验与更新 fly_stick 的四处版本源。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    show = subparsers.add_parser("show", help="只读列出版本源与工具版本 pin")
    show.add_argument("--json", action="store_true", help="以 JSON 输出")
    check = subparsers.add_parser("check", help="校验四处版本源一致")
    check.add_argument(
        "--expect", metavar="VERSION", default=None, help="期望版本，可带前导 v"
    )
    setter = subparsers.add_parser("set", help="更新四处版本源")
    setter.add_argument("version", metavar="VERSION", help="目标版本，可带前导 v")
    setter.add_argument("--dry-run", action="store_true", help="只列出将变化的文件")
    setter.add_argument("--no-locks", action="store_true", help="跳过两个锁文件")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    Args:
        argv: 命令行参数，``None`` 时读取 ``sys.argv``。

    Returns:
        进程退出码。
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        if args.command == "show":
            return run_show(root, as_json=bool(args.json))
        if args.command == "check":
            return run_check(root, expect=args.expect)
        return run_set(
            root,
            args.version,
            dry_run=bool(args.dry_run),
            no_locks=bool(args.no_locks),
        )
    except VersionError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
