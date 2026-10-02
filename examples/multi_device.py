"""多设备示例：按名称挑选若干设备，在同一循环里分别读取状态。

本示例演示同时监控多个操纵杆：

1. `fetch_connected_joysticks()` 枚举设备；
2. `--name` 可重复传入设备名来挑选设备，不传时取前两个可用设备；
3. 给每个设备各开一个 `PyJoystick`，每轮循环打印各自收到的事件。

每个 `get_state()` 只返回该设备本轮收到的事件，设备之间互不影响；同一手柄可能
对应多个 `event` 节点，同名设备会按枚举顺序分别打开、分别打印。

需要什么硬件：至少一个能被 evdev 识别的操纵杆或手柄。没有设备、请求的名字都
匹配不上、或设备打不开时，示例打印中文原因并跳过，最终退出码为 0。

怎么跑：

```bash
uv run python examples/multi_device.py
uv run python examples/multi_device.py --iterations 200
uv run python examples/multi_device.py --name "Thrustmaster T.A320 Copilot"
uv run python examples/multi_device.py --name "Thrustmaster T.16000M"
```
"""

from __future__ import annotations

import argparse
import asyncio

from fly_stick import JoystickInfo, PyJoystick, fetch_connected_joysticks

NO_DEVICE_REASON = (
    "没有找到可读的操纵杆设备；请确认设备已连接，"
    "并把当前用户加入 input 组或配置 udev 规则。"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。

    Args:
        argv: 参数字符串列表；为 `None` 时由 `argparse` 读取 `sys.argv`。

    Returns:
        argparse.Namespace: 含 `name` 与 `iterations` 的解析结果。
    """
    parser = argparse.ArgumentParser(description="在同一循环里读取多个操纵杆的状态")
    parser.add_argument(
        "--name",
        action="append",
        default=[],
        metavar="NAME",
        help="要监控的设备名，可重复传入；不传时取前两个可用设备",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="循环轮数；0 表示一直读取直到按 Ctrl+C，默认 0",
    )
    return parser.parse_args(argv)


def print_devices(devices: list[JoystickInfo]) -> None:
    """按序号打印已枚举的设备。

    Args:
        devices: `fetch_connected_joysticks()` 返回的设备列表。
    """
    print(f"共枚举到 {len(devices)} 个输入设备（含非操纵杆节点）：")
    for index, device in enumerate(devices):
        print(f"  [{index}] {device.name}  {device.path}")


def select_devices(devices: list[JoystickInfo], names: list[str]) -> list[JoystickInfo]:
    """按名称挑选设备；未指定名称时取前两个。

    Args:
        devices: 已枚举的设备列表。
        names: 请求的设备名；为空时返回前两个设备。

    Returns:
        list[JoystickInfo]: 选中的设备；同名设备按枚举顺序取尚未使用的第一个。
    """
    if not names:
        return devices[:2]

    selected: list[JoystickInfo] = []
    used_paths: set[str] = set()
    for name in names:
        match = next(
            (
                device
                for device in devices
                if device.name == name and device.path not in used_paths
            ),
            None,
        )
        if match is None:
            print(f"没有找到名为 {name!r} 的设备，已跳过。")
            continue
        used_paths.add(match.path)
        selected.append(match)
    return selected


def open_devices(
    devices: list[JoystickInfo],
) -> list[tuple[JoystickInfo, PyJoystick]]:
    """依次打开设备，打不开的设备打印中文原因后跳过。

    Args:
        devices: 要打开的设备列表。

    Returns:
        list[tuple[JoystickInfo, PyJoystick]]: 成功打开的 `(设备信息, 设备对象)`。
    """
    opened: list[tuple[JoystickInfo, PyJoystick]] = []
    for info in devices:
        try:
            opened.append((info, PyJoystick(info.path)))
        except PermissionError:
            print(f"没有读取 {info.path} 的权限，已跳过。")
        except FileNotFoundError:
            print(f"设备节点 {info.path} 不存在，已跳过。")
        except OSError as error:
            print(f"打开设备 {info.path} 失败，已跳过：{error}")
    return opened


async def monitor(
    opened: list[tuple[JoystickInfo, PyJoystick]], iterations: int
) -> int:
    """在同一个循环里轮流读取每个设备的状态。

    Args:
        opened: `(设备信息, 设备对象)` 列表。
        iterations: 循环轮数；0 表示一直运行直到按 Ctrl+C。

    Returns:
        int: 恒为 0，表示正常结束。
    """
    label_width = max(len(info.name) for info, _ in opened)
    rounds = 0
    try:
        while iterations <= 0 or rounds < iterations:
            for info, joystick in opened:
                state = joystick.get_state()
                if state.axes or state.buttons or state.hats:
                    print(
                        f"{info.name:<{label_width}} "
                        f"axes={state.axes} buttons={state.buttons} "
                        f"hats={state.hats}"
                    )
            rounds += 1
            await asyncio.sleep(0.02)
    except KeyboardInterrupt:
        print("\n已停止读取。")
    except OSError as error:
        print(f"读取设备失败：{error}")
    return 0


async def main(argv: list[str] | None = None) -> int:
    """运行多设备示例。

    Args:
        argv: 参数字符串列表；为 `None` 时由 `argparse` 读取 `sys.argv`。

    Returns:
        int: 退出码；没有可用设备或没有选中设备时同样返回 0。
    """
    args = parse_args(argv)

    devices = fetch_connected_joysticks()
    if not devices:
        print(NO_DEVICE_REASON)
        return 0
    print_devices(devices)

    selected = select_devices(devices, args.name)
    if not selected:
        print("没有选中任何设备；请用 --name 指定上面列出的设备名。")
        return 0

    opened = open_devices(selected)
    if not opened:
        print("选中的设备都打不开，退出。")
        return 0

    print(f"已打开 {len(opened)} 个设备；按 Ctrl+C 停止。")
    return await monitor(opened, args.iterations)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
