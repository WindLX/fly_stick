"""演示设备描述里的别名与按别名取键的接口。

别名写在描述文件的每个输入项上。状态对象提供 ``to_alias_dict()`` 与
``get_alias_axes()`` / ``get_alias_buttons()`` / ``get_alias_hats()``，把 evdev
code 换成别名。没有别名的输入项用 code 的字符串形式作键。

``PyJoystick.get_state()`` 只返回本次调用收到的事件，所以别名映射里只出现本轮
命中的键；设备池的状态寄存器相反，它由 ``build_state()`` 初始化，包含描述里声明的
全部 code，池读取的别名映射总是覆盖所有已声明的键。

需要硬件：一台 ``device_name`` 与描述文件匹配的操纵杆。没有匹配设备时会在打印别名
表之后退出，退出码 0。

运行方式：

```bash
uv run python examples/alias.py --profile devices/Thrustmaster/ta320.toml
```
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from fly_stick import (
    DeviceDescription,
    JoystickState,
    PyJoystick,
    fetch_connected_joysticks,
)

NO_DEVICE_HINT = (
    "没有找到与描述文件匹配的操纵杆设备；请确认设备已连接，"
    "并把当前用户加入 input 组或配置 udev 规则。"
)


def default_profile() -> Path:
    """返回包内默认设备描述文件的路径。

    Returns:
        Path: 包根目录下 ``devices/Thrustmaster/ta320.toml`` 的绝对路径。
    """
    # 默认路径由脚本自身位置推出，因此从任意工作目录运行都能找到描述文件。
    root = Path(__file__).resolve().parents[1]
    return root / "devices" / "Thrustmaster" / "ta320.toml"


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Returns:
        argparse.Namespace: 含 ``profile``、``rounds`` 与 ``interval``。
    """
    parser = argparse.ArgumentParser(
        description="演示别名映射与 to_alias_dict/get_alias_* 的取键规则。"
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=default_profile(),
        help="设备描述 TOML 路径（默认包内 Thrustmaster/ta320.toml）。",
    )
    parser.add_argument("--rounds", type=int, default=10, help="读取轮数。")
    parser.add_argument(
        "--interval", type=float, default=0.2, help="每轮之间的间隔秒数。"
    )
    return parser.parse_args()


def sorted_by_alias(values: dict[str, float | int]) -> dict[str, float | int]:
    """按别名键排序后返回同一份映射，保证输出可复现。

    Args:
        values: 别名或 code 字符串到数值的映射。

    Returns:
        dict[str, float | int]: 按键名升序排列的新字典。
    """
    return {key: values[key] for key in sorted(values)}


def print_alias_table(desc: DeviceDescription) -> None:
    """打印描述文件里每个输入项的 code 与别名对应关系。

    Args:
        desc: 待打印的设备描述。
    """
    for kind, items in (
        ("axes", desc.axes),
        ("buttons", desc.buttons),
        ("hats", desc.hats),
    ):
        print(f"[{kind}] 共 {len(items)} 项")
        for item in items:
            # 没有别名的输入项在别名映射里回退成 code 的字符串形式。
            if item.alias is None:
                print(f"  code {item.code:<4} -> 无别名，键为 {str(item.code)!r}")
            else:
                print(f"  code {item.code:<4} -> {item.alias!r}")


def print_alias_state(
    desc: DeviceDescription, state: JoystickState, index: int
) -> None:
    """打印一轮状态的两类别名视图。

    Args:
        desc: 提供 code 到别名映射的设备描述。
        state: 本轮由 ``get_state()`` 得到的状态。
        index: 轮次序号，从 1 开始。
    """
    # get_state() 是事件差分：本轮没有任何事件时三个映射都为空。
    if not (state.axes or state.buttons or state.hats):
        print(f"第 {index} 轮：本次调用没有收到事件，三个映射都是空的。")
        return
    # 一次取四种视图：to_alias_dict() 按种类分组，三个 get_alias_*() 直接给单类。
    aliases = state.to_alias_dict(desc)
    axes = state.get_alias_axes(desc)
    buttons = state.get_alias_buttons(desc)
    hats = state.get_alias_hats(desc)
    print(f"第 {index} 轮 本轮命中的键：")
    # 排序后打印，抵消 Rust 侧映射不固定的迭代顺序。
    for kind in ("axes", "buttons", "hats"):
        print(f"  to_alias_dict[{kind!r}] = {sorted_by_alias(aliases[kind])}")
    print(f"  get_alias_axes()    = {sorted_by_alias(axes)}")
    print(f"  get_alias_buttons() = {sorted_by_alias(buttons)}")
    print(f"  get_alias_hats()    = {sorted_by_alias(hats)}")


def run(profile: Path, rounds: int, interval: float) -> int:
    """打印别名表，并逐轮打印设备本轮命中的别名映射。

    Args:
        profile: 设备描述 TOML 路径。
        rounds: 读取轮数。
        interval: 每轮之间的间隔，单位秒。

    Returns:
        int: 进程退出码；没有匹配设备或设备不可读时为 0。
    """
    desc = DeviceDescription.from_toml(str(profile))
    print(f"描述文件：{profile}")
    print(f"设备名：{desc.device_name!r}（作者 {desc.author}，创建 {desc.created}）")
    # 先打印完整对照表；别名映射里只会出现本轮命中的键，需要对照表才能还原全貌。
    print_alias_table(desc)

    # 名称唯一匹配失败不报错，打印别名表后正常退出。
    connected = fetch_connected_joysticks()
    matches = [info for info in connected if info.name == desc.device_name]
    if not matches:
        print(f"\n{NO_DEVICE_HINT}")
        print(f"当前枚举到的设备名：{[info.name for info in connected]}")
        return 0

    info = matches[0]
    print(f"\n匹配设备：{info.name}（{info.path}）")
    print("请拨动任一根轴或按下按钮；每轮只显示本次事件命中的别名键。")
    try:
        # PyJoystick 只接受字符串路径。
        joystick = PyJoystick(info.path)
    except OSError as error:
        print(f"打开 {info.path} 失败：{type(error).__name__}: {error}")
        print(NO_DEVICE_HINT)
        return 0

    try:
        # 逐轮读取；每轮的 get_state() 与上一轮互不累积。
        for index in range(1, rounds + 1):
            print_alias_state(desc, joystick.get_state(), index)
            time.sleep(interval)
    except OSError as error:
        print(f"读取设备失败：{type(error).__name__}: {error}")
        return 0
    except KeyboardInterrupt:
        print("收到中断，退出。")
        return 0
    return 0


def main() -> int:
    """解析参数并运行示例。

    Returns:
        int: 进程退出码。
    """
    args = parse_args()
    return run(args.profile, args.rounds, args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
