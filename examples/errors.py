"""异常解剖：把库里会抛出的错误逐类跑一遍。

覆盖 ``PyJoystick`` 打开设备的两类 ``OSError``（路径不存在、无读权限）、
``DeviceDescription.from_toml()`` 的 ``OSError`` 与 ``ValueError``、
``DeviceButtonMode("...")`` 的 ``ValueError``，以及未 ``reset()`` 或已 ``stop()``
时 ``fetch_nowait()`` 的 ``RuntimeError``。每个分支都打印中文说明。

不需要操纵杆；只有无读权限分支要求当前用户不是 root（root 会绕过权限位）。

运行方式：

```bash
uv run python examples/errors.py
```
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path

from fly_stick import DeviceButtonMode, DeviceDescription, PyDevicePool, PyJoystick

MISSING_DEVICE_PATH = "no-such-device-event0"
BROKEN_TOML = 'device_name = "未闭合\n'


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Returns:
        argparse.Namespace: 含 ``device`` 一项。
    """
    parser = argparse.ArgumentParser(
        description="逐类演示 fly_stick 的异常，并给出中文解释。"
    )
    parser.add_argument(
        "--device",
        type=Path,
        default=Path("/dev/input/event0"),
        help="额外尝试打开的真实设备节点路径。",
    )
    return parser.parse_args()


def first_line(error: ValueError) -> str:
    """取出解析错误消息的第一行。

    Args:
        error: ``from_toml()`` 抛出的解析异常。

    Returns:
        str: 消息中第一个非空行；消息为空时返回空字符串。
    """
    lines = [line for line in str(error).splitlines() if line.strip()]
    return lines[0] if lines else ""


def demo_missing_path() -> None:
    """打开不存在的设备路径，演示 ``FileNotFoundError``。"""
    print(f"[演示] 打开不存在的设备路径 {MISSING_DEVICE_PATH}：")
    try:
        PyJoystick(MISSING_DEVICE_PATH)
    except FileNotFoundError as error:
        print(f"  FileNotFoundError: {error}")


def demo_permission_denied(temp_dir: Path) -> None:
    """用权限位为 000 的临时文件演示 ``PermissionError``。

    Args:
        temp_dir: 存放临时文件的目录。
    """
    denied = temp_dir / "denied-event"
    denied.write_text("not a device", encoding="utf-8")
    denied.chmod(0o000)
    print(f"[演示] 打开无读权限的普通文件 {denied.name}：")
    try:
        PyJoystick(str(denied))
    except PermissionError as error:
        print(f"  PermissionError: {error}（当前用户读不到该文件）")
    except OSError as error:
        print(f"  {type(error).__name__}: {error}")
        print("  以 root 运行时权限位被绕过，会在设备探测阶段报这个错。")


def demo_from_toml_errors(temp_dir: Path) -> None:
    """演示 ``from_toml()`` 的缺失文件与 TOML 语法错两条分支。

    Args:
        temp_dir: 存放临时 TOML 文件的目录。
    """
    missing = temp_dir / "missing.toml"
    print(f"[演示] from_toml({missing.name})，文件不存在：")
    try:
        DeviceDescription.from_toml(str(missing))
    except OSError as error:
        print(f"  OSError: {error}")

    broken = temp_dir / "broken.toml"
    broken.write_text(BROKEN_TOML, encoding="utf-8")
    print(f"[演示] from_toml({broken.name})，TOML 语法错：")
    try:
        DeviceDescription.from_toml(str(broken))
    except ValueError as error:
        print(f"  ValueError: {first_line(error)}")


def demo_button_mode_error() -> None:
    """用非法字符串构造 ``DeviceButtonMode``，演示 ``ValueError``。"""
    print('[演示] DeviceButtonMode("press")：')
    try:
        DeviceButtonMode("press")
    except ValueError as error:
        print(f"  ValueError: {error}")
    print("  合法写法：", end="")
    print(f"{DeviceButtonMode('hold')!r} 或 {DeviceButtonMode('trigger')!r}")


def demo_device_node(device: Path) -> None:
    """尝试打开命令行指定的真实设备节点，并把 ``OSError`` 打印出来。

    Args:
        device: 设备节点路径。
    """
    print(f"[演示] 打开设备节点 {device}：")
    try:
        joystick = PyJoystick(str(device))
        state = joystick.get_state()
    except OSError as error:
        print(f"  {type(error).__name__}: {error}")
        return
    print(f"  打开成功；本轮 axes={dict(sorted(state.axes.items()))}")


async def demo_pool_states() -> None:
    """演示未 ``reset()`` 与已 ``stop()`` 时两个读取接口的差别。"""
    pool = PyDevicePool({})
    print("[演示] 未 reset() 就读取空设备池：")
    try:
        pool.fetch_nowait()
    except RuntimeError as error:
        print(f"  fetch_nowait() -> RuntimeError: {error}")
    before = await pool.fetch(timeout_seconds=0.1)
    print(f"  await pool.fetch() -> {before}（返回陈旧快照，不报错）")

    await pool.reset()
    print(f"[演示] reset() 之后：fetch_nowait() -> {pool.fetch_nowait()}")
    await pool.stop()

    print("[演示] stop() 之后：")
    try:
        pool.fetch_nowait()
    except RuntimeError as error:
        print(f"  fetch_nowait() -> RuntimeError: {error}")
    after = await pool.fetch(timeout_seconds=0.1)
    print(f"  await pool.fetch() -> {after}（同样是陈旧快照，不报错）")
    print("  空设备池返回 {}；匹配到设备时这里给出的是寄存器里的旧状态，仍不报错。")


def main() -> int:
    """解析参数并依次运行各异常演示。

    Returns:
        int: 进程退出码，恒为 0。
    """
    args = parse_args()
    demo_missing_path()
    with tempfile.TemporaryDirectory() as name:
        temp_dir = Path(name)
        demo_permission_denied(temp_dir)
        demo_from_toml_errors(temp_dir)
    demo_button_mode_error()
    demo_device_node(args.device)
    asyncio.run(demo_pool_states())
    print("全部演示结束：每类异常都已按中文说明处理，没有向用户抛 traceback。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
