"""演示 PyDevicePool 的生命周期与可调参数。

依次展示描述与设备匹配、``debounce_time`` 与 ``button_mode`` 属性、未 ``reset()``
时两个读取入口都抛 ``RuntimeError``、``reset()``
的返回值、运行时切换按键模式，以及 ``stop()`` 之后两个读取接口的行为。

需要硬件：匹配的设备越多观察越完整；没有匹配设备时池是空的，生命周期流程仍会完整
执行并以退出码 0 结束。

运行方式：

```bash
uv run python examples/pool_lifecycle.py --profile devices/Thrustmaster/ta320.toml
```
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from fly_stick import DeviceButtonMode, DeviceDescription, PyDevicePool

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
        argparse.Namespace: 含 ``profile``、``debounce``、``mode`` 与 ``timeout``。
    """
    parser = argparse.ArgumentParser(
        description="演示设备池的构造、reset、读取、模式切换与 stop 生命周期。"
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=default_profile(),
        help="设备描述 TOML 路径（默认包内 Thrustmaster/ta320.toml）。",
    )
    parser.add_argument(
        "--debounce", type=float, default=0.1, help="按键去抖时长，单位秒。"
    )
    parser.add_argument(
        "--mode",
        choices=("hold", "trigger"),
        default="hold",
        help="初始按键模式；脚本运行中会切到另一种模式。",
    )
    parser.add_argument(
        "--timeout", type=float, default=0.2, help="每次阻塞读取的等待上限秒数。"
    )
    return parser.parse_args()


def print_pool_summary(pool: PyDevicePool) -> None:
    """打印设备池的设备匹配、去抖时长与按键模式。

    Args:
        pool: 待检查的设备池；设备匹配在 ``reset()`` 中完成。
    """
    devices = pool.devices
    print(f"  pool.devices       = {sorted(devices)}")
    # 每项是逻辑名到 (设备描述, 设备信息) 的映射，reset() 之后才有内容。
    for logical in sorted(devices):
        matched_desc, info = devices[logical]
        print(f"    {logical}: {matched_desc.device_name!r} @ {info.path}")
    print(f"  pool.debounce_time = {pool.debounce_time}")
    print(f"  pool.button_mode   = {pool.button_mode!r}")


async def run(profile: Path, debounce: float, mode: str, timeout: float) -> int:
    """按顺序演示设备池的构造、启动、读取、切换与停止。

    Args:
        profile: 设备描述 TOML 路径。
        debounce: 按键去抖时长，单位秒。
        mode: 初始按键模式，``hold`` 或 ``trigger``。
        timeout: 每次阻塞读取的等待上限，单位秒。

    Returns:
        int: 进程退出码，恒为 0。
    """
    desc = DeviceDescription.from_toml(str(profile))
    # 构造只登记描述、去抖时长与初始按键模式；设备匹配在 reset() 中完成。
    pool = PyDevicePool(
        {LOGICAL_NAME: desc},
        debounce_seconds=debounce,
        button_mode=DeviceButtonMode(mode),
    )
    print(f"描述设备：{desc.device_name!r}（逻辑名 {LOGICAL_NAME}）")
    print("[构造完成，尚未 reset()]")
    print_pool_summary(pool)
    # 记录是否已正常 stop，供 finally 判断要不要兜底清理。
    stopped = False

    try:
        print("[未 reset() 时读取]")
        # 未启动时两个读取入口都必须抛 RuntimeError，这里各演示一次。
        try:
            await pool.fetch(timeout_seconds=timeout)
        except RuntimeError as error:
            print(f"  await pool.fetch() -> RuntimeError: {error}")
        try:
            pool.fetch_nowait()
        except RuntimeError as error:
            print(f"  fetch_nowait() -> RuntimeError: {error}")

        print("[await pool.reset()]")
        # reset() 重新枚举、唯一匹配并预打开设备，返回「逻辑名 -> (描述, 设备信息)」。
        devices = await pool.reset()
        print(f"  reset() 返回 {len(devices)} 个逻辑设备")
        for logical in sorted(devices):
            matched_desc, info = devices[logical]
            print(f"    {logical}: {matched_desc.device_name!r} @ {info.path}")
        # 启动之后 fetch_nowait() 才可用，返回值是各设备的完整快照。
        print(f"  fetch_nowait() 此时可用：{sorted(pool.fetch_nowait())}")
        if not devices:
            # 描述为空是合法输入，只是没有任何逻辑设备可监控。
            print("设备描述为空；没有注册逻辑设备。")

        # button_mode 是运行时可写属性，切换后立即影响后续读取的按键语义。
        switched = "trigger" if mode == "hold" else "hold"
        pool.button_mode = DeviceButtonMode(switched)
        print("[运行时切换按键模式]")
        print(f"  pool.button_mode = {pool.button_mode!r}")

        # stop() 等待监控任务退出并释放设备；停止后再读取只抛 RuntimeError。
        await pool.stop()
        stopped = True
        print("[await pool.stop()]")
        try:
            pool.fetch_nowait()
        except RuntimeError as error:
            print(f"  fetch_nowait() -> RuntimeError: {error}")
        try:
            await pool.fetch(timeout_seconds=timeout)
        except RuntimeError as error:
            print(f"  await pool.fetch() -> RuntimeError: {error}")
    except (LookupError, OSError, ValueError) as error:
        print(f"设备池启动失败：{type(error).__name__}: {error}")
    except KeyboardInterrupt:
        print("收到中断，停止设备池。")
    finally:
        # 启动失败或中途异常时兜底停止，避免监控任务与设备句柄残留。
        if not stopped:
            await pool.stop()

    print("提示：stop() 等待监控任务退出并释放所有设备；reset() 会重新枚举并匹配设备。")
    return 0


def main() -> int:
    """解析参数并运行示例。

    Returns:
        int: 进程退出码。
    """
    args = parse_args()
    return asyncio.run(run(args.profile, args.debounce, args.mode, args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
