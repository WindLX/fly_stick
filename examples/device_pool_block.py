"""仿真循环示例：在每个控制周期里非阻塞取设备状态。

本示例与 `device_pool.py` 同构，区别在取状态的方式：这里用
`pool.fetch_nowait()`，它立即返回各设备最近一次的状态，不等待输入，
因此不会拖住控制周期。

适用场景：飞行仿真、控制器或游戏主循环这类按固定周期推进的代码 ——
每个周期读一次输入、算一次控制量，绝不能在读设备上阻塞。

`fetch_nowait()` 与 `await pool.fetch()` 的差别（后者见 `device_pool.py`）：

- `fetch_nowait()` 不阻塞；设备池尚未 `reset()` 时抛 `RuntimeError`。
- `await fetch(timeout_seconds=...)` 会等到状态变化或超时，超时抛 `TimeoutError`。
- 两个 API 的读取进度独立，混用不会消费对方的变化。

设备池按名称唯一匹配设备；同名设备多个时需要在描述文件指定 `device_path`。
匹配失败由 `reset()` 抛出 `LookupError` 或 `ValueError`。

需要什么硬件：一个与所选描述文件 `device_name` 完全同名的操纵杆或手柄。没有设备、
名字不匹配或描述文件读不到时，示例打印中文原因后返回，退出码为 0。

怎么跑：

```bash
uv run python examples/device_pool_block.py
uv run python examples/device_pool_block.py --period 0.01 --iterations 500
uv run python examples/device_pool_block.py --profile devices/Thrustmaster/twcs.toml
```
"""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from fly_stick import (
    DeviceDescription,
    JoystickInfo,
    JoystickState,
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
        `period` 与 `iterations` 的解析结果。
    """
    parser = argparse.ArgumentParser(description="在固定周期循环里非阻塞读取操纵杆状态")
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
        # 去抖只作用于按键按下的那一个边沿；轴、帽开关与按键释放不受影响。
        help="按键去抖时长，单位秒，默认 0.1",
    )
    parser.add_argument(
        "--period",
        type=float,
        default=0.02,
        help="控制周期，单位秒，默认 0.02（50 Hz）",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="控制周期数；0 表示一直运行直到按 Ctrl+C，默认 0",
    )
    return parser.parse_args(argv)


def print_devices(devices: list[JoystickInfo]) -> None:
    """打印已连接设备，供用户核对描述文件里的 `device_name`。

    Args:
        devices: `fetch_connected_joysticks()` 返回的设备列表。
    """
    # 枚举包含键盘、鼠标等非操纵杆节点，打印全名便于和描述文件的 device_name 核对。
    for device in devices:
        print(f"  {device.name}  {device.path}")


def load_profile(path: Path) -> DeviceDescription | None:
    """读取设备描述文件。

    Args:
        path: TOML 描述文件路径。

    Returns:
        DeviceDescription | None: 解析成功时返回描述；失败时打印中文原因并返回 `None`。
    """
    # 文件缺失与内容解析失败分开提示，方便区分路径写错和 TOML 写错。
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
    """运行固定周期非阻塞读取示例。

    Args:
        argv: 参数字符串列表；为 `None` 时由 `argparse` 读取 `sys.argv`。

    Returns:
        int: 退出码；没有可用设备或没有匹配到设备时同样返回 0。
    """
    args = parse_args(argv)

    # 先读描述、再枚举设备，把「描述读不到」和「设备对不上」分成两条提示。
    description = load_profile(args.profile)
    if description is None:
        return 0

    devices = fetch_connected_joysticks()
    if not devices:
        print(NO_DEVICE_REASON)
        return 0
    # 预检只按名称比对；真正的唯一匹配与打开由 reset() 完成。
    if all(device.name != description.device_name for device in devices):
        print(f"没有找到名为 {description.device_name!r} 的设备；当前连接的有：")
        print_devices(devices)
        print("请连接对应设备，或用 --profile 指定匹配的描述文件。")
        return 0

    # 逻辑名默认取描述文件名，池内各设备用逻辑名区分。
    logical_name = args.logical_name or args.profile.stem
    # 构造阶段只登记描述；设备在 reset() 中才被打开和监控。
    pool = PyDevicePool(
        {logical_name: description},
        debounce_seconds=args.debounce,
    )
    try:
        # reset() 重新枚举、按名称唯一匹配并全量预打开，失败时整池保持停止。
        matched = await pool.reset()
    except (LookupError, OSError, ValueError) as error:
        print(f"设备池启动失败：{type(error).__name__}: {error}")
        return 0

    # matched 的每一项是「逻辑名 -> (设备描述, 设备信息)」。
    for name, (_description, info) in matched.items():
        print(f"已开始监控 {name} → {info.path} ({info.name})")
    print(f"控制周期 {args.period:g} 秒；按 Ctrl+C 停止。")

    rounds = 0
    # 用单调时钟累加目标时刻，避免每轮的实际耗时逐渐累积成周期漂移。
    next_tick = time.monotonic()
    # 缓存上一周期的快照，用于把完整快照差分成变化事件。
    previous: dict[str, JoystickState] = {}
    try:
        while args.iterations <= 0 or rounds < args.iterations:
            # 仿真循环里绝不能等待设备：立即取最近状态，再补齐本周期剩余时间。
            states = pool.fetch_nowait()
            for name, state in states.items():
                # fetch_nowait 返回完整快照，比较上一周期就能只看变化。
                if previous.get(name) != state:
                    print(f"{name}: {state.to_dict()}")
                    previous[name] = state
            rounds += 1
            next_tick += args.period
            # 本周期已经超时就立即继续，不睡眠，让循环尽量追上目标频率。
            await asyncio.sleep(max(0.0, next_tick - time.monotonic()))
    except KeyboardInterrupt:
        print("\n已停止监控。")
    except (OSError, RuntimeError) as error:
        print(f"设备池停止读取：{error}")
    finally:
        # 停止监控并等待设备句柄释放。
        await pool.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
