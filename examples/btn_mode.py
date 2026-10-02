"""演示 DeviceButtonMode 的 Hold 与 Trigger 语义差别。

本示例为同一台设备建立两个设备池：一个使用 Hold，一个使用 Trigger。按住设备上
的同一个按键，Hold 的按键状态在后续读取中保持为 1，Trigger 只在按下的那一轮交付
一次 1，下一次读取时已被清零。

需要硬件：一台 ``device_name`` 与描述文件匹配的操纵杆，且当前用户可读
``/dev/input/event*``。没有匹配设备时脚本打印提示并以退出码 0 结束。

运行方式：

```bash
uv run python examples/btn_mode.py --profile devices/Thrustmaster/ta320.toml
```
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from fly_stick import (
    DeviceButtonMode,
    DeviceDescription,
    PyDevicePool,
    fetch_connected_joysticks,
)

LOGICAL_NAME = "stick"
NO_DEVICE_HINT = (
    "没有找到与描述文件匹配的操纵杆设备；请确认设备已连接，"
    "并把当前用户加入 input 组或配置 udev 规则。"
)


def default_profile() -> Path:
    """返回包内默认设备描述文件的路径。

    Returns:
        Path: 包根目录下 ``devices/Thrustmaster/ta320.toml`` 的绝对路径。
    """
    root = Path(__file__).resolve().parents[1]
    return root / "devices" / "Thrustmaster" / "ta320.toml"


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Returns:
        argparse.Namespace: 含 ``profile``、``rounds``、``timeout`` 与 ``interval``。
    """
    parser = argparse.ArgumentParser(
        description="对比 DeviceButtonMode.Hold 与 Trigger 的按键语义。"
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=default_profile(),
        help="设备描述 TOML 路径（默认包内 Thrustmaster/ta320.toml）。",
    )
    parser.add_argument("--rounds", type=int, default=8, help="打印轮数。")
    parser.add_argument(
        "--timeout", type=float, default=0.2, help="每轮等待事件的上限秒数。"
    )
    parser.add_argument(
        "--interval", type=float, default=0.1, help="每轮之间的间隔秒数。"
    )
    return parser.parse_args()


def build_pools(desc: DeviceDescription) -> dict[str, PyDevicePool]:
    """按两种按键模式各建立一个设备池。

    Args:
        desc: 要监控的设备描述；两个池都按 ``LOGICAL_NAME`` 注册同一份描述。

    Returns:
        dict[str, PyDevicePool]: 模式名到设备池的映射。
    """
    return {
        "Hold": PyDevicePool(
            {LOGICAL_NAME: desc},
            debounce_seconds=0.05,
            button_mode=DeviceButtonMode.hold(),
        ),
        "Trigger": PyDevicePool(
            {LOGICAL_NAME: desc},
            debounce_seconds=0.05,
            button_mode=DeviceButtonMode.trigger(),
        ),
    }


async def run(profile: Path, rounds: int, timeout: float, interval: float) -> int:
    """逐轮打印两种模式下同一按键的读数。

    Args:
        profile: 设备描述 TOML 路径。
        rounds: 打印轮数。
        timeout: 每轮 ``fetch`` 等待事件的上限，单位秒。
        interval: 每轮之间的间隔，单位秒。

    Returns:
        int: 进程退出码；没有匹配设备时为 0。
    """
    desc = DeviceDescription.from_toml(str(profile))
    print(f"描述文件：{profile}")
    print(f"设备名：{desc.device_name!r}（作者 {desc.author}，创建 {desc.created}）")

    connected = fetch_connected_joysticks()
    matches = [info for info in connected if info.name == desc.device_name]
    if not matches:
        print(NO_DEVICE_HINT)
        print(f"当前枚举到的设备名：{[info.name for info in connected]}")
        return 0

    info = matches[0]
    print(f"匹配设备：{info.name}（{info.path}）")
    pools = build_pools(desc)
    print("按住设备上的任意按键，观察两种模式的差别；松开后两种模式都会回到 0。")

    try:
        await asyncio.gather(*(pool.reset() for pool in pools.values()))
        for index in range(1, rounds + 1):
            readings: list[str] = []
            for label, pool in pools.items():
                try:
                    states = await pool.fetch(timeout_seconds=timeout)
                    source = "fetch"
                except TimeoutError:
                    # 两个入口进度独立；nowait 仍可观察自己的脉冲。
                    states = pool.fetch_nowait()
                    source = "fetch_nowait"
                state = states.get(LOGICAL_NAME)
                # Rust 侧映射的迭代顺序不固定，排序后输出才可复现。
                buttons = (
                    dict(sorted(state.buttons.items())) if state is not None else {}
                )
                readings.append(f"{label}={buttons}（{source}）")
            print(f"第 {index} 轮  " + "  ".join(readings))
            await asyncio.sleep(interval)
    except KeyboardInterrupt:
        print("收到中断，停止设备池。")
    finally:
        await asyncio.gather(*(pool.stop() for pool in pools.values()))
    return 0


def main() -> int:
    """解析参数并运行示例。

    Returns:
        int: 进程退出码。
    """
    args = parse_args()
    return asyncio.run(run(args.profile, args.rounds, args.timeout, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
