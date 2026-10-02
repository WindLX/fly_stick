"""设备池入门示例：用 TOML 描述文件匹配设备，阻塞等待状态变化。

本示例演示 `PyDevicePool` 的基本用法：

1. `DeviceDescription.from_toml(profile)` 读取设备描述，默认是
   `devices/Thrustmaster/ta320.toml`，可用 `--profile` 覆盖；
2. `PyDevicePool({逻辑名: 描述})` 创建设备池，`await pool.reset()` 开始监控；
3. 循环 `await pool.fetch()`：没有新事件时它会等待，收到事件才返回。

`fetch()` 与 `fetch_nowait()` 的差别（后者由 `device_pool_block.py` 演示）：

- `await fetch(timeout_seconds=...)` 会等到状态变化；每轮都让出事件循环，
  适合「有输入才处理」的响应式主循环。指定 `--timeout` 后等待超时会抛
  `RuntimeError`，示例打印中文原因后结束，退出码仍为 0。
- `fetch_nowait()` 立即返回最近一次状态，不等待；设备池尚未 `reset()` 时抛
  `RuntimeError`。

设备池按 `info.name == desc.device_name` 精确匹配设备节点，匹配不上只提示不报错，
所以运行前要确认描述文件里的 `device_name` 与已连接设备的名称一致。

需要什么硬件：一个与所选描述文件 `device_name` 完全同名的操纵杆或手柄。没有设备、
名字不匹配或描述文件读不到时，示例打印中文原因后返回，退出码为 0。

怎么跑：

```bash
uv run python examples/device_pool.py
uv run python examples/device_pool.py --iterations 5 --timeout 0.5
uv run python examples/device_pool.py --profile devices/Thrustmaster/twcs.toml
```
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from fly_stick import (
    DeviceDescription,
    JoystickInfo,
    PyDevicePool,
    fetch_connected_joysticks,
)

DEFAULT_PROFILE = (
    Path(__file__).resolve().parents[1] / "devices" / "Thrustmaster" / "ta320.toml"
)
NO_DEVICE_REASON = (
    "没有找到可读的操纵杆设备；请确认设备已连接，"
    "并把当前用户加入 input 组或配置 udev 规则。"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。

    Args:
        argv: 参数字符串列表；为 `None` 时由 `argparse` 读取 `sys.argv`。

    Returns:
        argparse.Namespace: 含 `profile`、`logical_name`、`debounce`、
        `timeout` 与 `iterations` 的解析结果。
    """
    parser = argparse.ArgumentParser(description="用设备池阻塞读取操纵杆状态")
    parser.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE,
        help="设备描述 TOML 路径，默认包根 devices/Thrustmaster/ta320.toml",
    )
    parser.add_argument(
        "--logical-name",
        default=None,
        help="设备在池中的逻辑名，默认取描述文件名（不含扩展名）",
    )
    parser.add_argument(
        "--debounce",
        type=float,
        default=0.1,
        help="按键去抖时长，单位秒，默认 0.1",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="等待状态变化的最长秒数；不传则一直等待",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="取状态轮数；0 表示一直读取直到按 Ctrl+C，默认 0",
    )
    return parser.parse_args(argv)


def print_devices(devices: list[JoystickInfo]) -> None:
    """打印已连接设备，供用户核对描述文件里的 `device_name`。

    Args:
        devices: `fetch_connected_joysticks()` 返回的设备列表。
    """
    for device in devices:
        print(f"  {device.name}  {device.path}")


def load_profile(path: Path) -> DeviceDescription | None:
    """读取设备描述文件。

    Args:
        path: TOML 描述文件路径。

    Returns:
        DeviceDescription | None: 解析成功时返回描述；失败时打印中文原因并返回 `None`。
    """
    if not path.is_file():
        print(f"设备描述文件不存在：{path}")
        return None
    try:
        return DeviceDescription.from_toml(str(path))
    except ValueError as error:
        print(f"设备描述内容无法解析：{path}：{error}")
    except OSError as error:
        print(f"读取设备描述文件失败：{path}：{error}")
    return None


async def main(argv: list[str] | None = None) -> int:
    """运行设备池阻塞读取示例。

    Args:
        argv: 参数字符串列表；为 `None` 时由 `argparse` 读取 `sys.argv`。

    Returns:
        int: 退出码；没有可用设备或没有匹配到设备时同样返回 0。
    """
    args = parse_args(argv)

    description = load_profile(args.profile)
    if description is None:
        return 0

    devices = fetch_connected_joysticks()
    if not devices:
        print(NO_DEVICE_REASON)
        return 0
    if all(device.name != description.device_name for device in devices):
        print(f"没有找到名为 {description.device_name!r} 的设备；当前连接的有：")
        print_devices(devices)
        print("请连接对应设备，或用 --profile 指定匹配的描述文件。")
        return 0

    logical_name = args.logical_name or args.profile.stem
    pool = PyDevicePool(
        {logical_name: description},
        debounce_seconds=args.debounce,
    )
    matched = await pool.reset()
    if not matched:
        print("设备池没有匹配到任何设备，退出。")
        await pool.stop()
        return 0

    for name, (_description, info) in matched.items():
        print(f"已开始监控 {name} → {info.path} ({info.name})")

    rounds = 0
    try:
        while args.iterations <= 0 or rounds < args.iterations:
            # fetch 会阻塞到状态变化；指定 --timeout 后超时会抛 RuntimeError。
            states = await pool.fetch(timeout_seconds=args.timeout)
            for name, state in states.items():
                if state.axes or state.buttons or state.hats:
                    print(f"{name}: {state.to_dict()}")
            rounds += 1
    except KeyboardInterrupt:
        print("\n已停止监控。")
    except RuntimeError as error:
        print(f"等待状态变化失败：{error}")
    finally:
        # 库没有 close()，停止监控和释放设备统一用 stop()。
        await pool.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
