"""单个操纵杆的最小示例：枚举设备、打开一个、循环读取状态。

本示例演示 `fly_stick` 的最短使用路径：

1. `fetch_connected_joysticks()` 枚举 `/dev/input/event*` 下的全部输入节点；
2. 按序号选出一个设备路径；
3. `PyJoystick(path)` 打开它，循环调用 `get_state()`。

关键语义：`get_state()` 返回的是**本次调用期间收到的事件**，不是设备的完整快照。
静止时 `axes`、`buttons`、`hats` 都是空字典，所以本示例只在有事件的那一轮打印。

需要什么硬件：一个能被 evdev 识别的操纵杆或手柄（例如 `/dev/input/event3`）。
没有设备、序号越界或没有读权限时，示例打印中文原因后返回，退出码为 0；
`--list` 只枚举设备、不打开设备，因此不受权限影响。

怎么跑：

```bash
uv run python examples/single_device.py --list
uv run python examples/single_device.py
uv run python examples/single_device.py --index 1 --iterations 200
```
"""

from __future__ import annotations

import argparse
import time

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
        argparse.Namespace: 含 `list`、`index` 与 `iterations` 的解析结果。
    """
    parser = argparse.ArgumentParser(description="读取单个操纵杆设备的状态")
    parser.add_argument(
        "--list",
        action="store_true",
        help="只列出枚举到的输入设备后退出，不打开任何设备",
    )
    parser.add_argument(
        "--index",
        type=int,
        default=0,
        help="要打开的设备序号（见 --list 输出），默认 0",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="读取轮数；0 表示一直读取直到按 Ctrl+C，默认 0",
    )
    return parser.parse_args(argv)


def print_devices(devices: list[JoystickInfo]) -> None:
    """按序号打印已枚举的设备。

    Args:
        devices: `fetch_connected_joysticks()` 返回的设备列表。
    """
    # 列表顺序就是 --index 的取值顺序，先打印出来方便用户选号。
    # 枚举结果包含键盘、鼠标等非操纵杆节点，型号要按 name 自行辨认。
    print(f"共枚举到 {len(devices)} 个输入设备（含非操纵杆节点）：")
    for index, device in enumerate(devices):
        print(f"  [{index}] {device.name}  {device.path}")


def list_devices() -> int:
    """枚举并打印输入设备，不打开任何设备节点。

    Returns:
        int: 恒为 0，表示正常结束。
    """
    # --list 分支只枚举不打开，因此不受设备读权限影响。
    devices = fetch_connected_joysticks()
    if not devices:
        print(NO_DEVICE_REASON)
        return 0
    print_devices(devices)
    return 0


def open_device(info: JoystickInfo) -> PyJoystick | None:
    """打开一个设备节点。

    注意 `PyJoystick` 只接受字符串路径，`JoystickInfo` 不能直接传入。

    Args:
        info: 由 `fetch_connected_joysticks()` 返回的设备信息。

    Returns:
        PyJoystick | None: 打开成功时返回设备对象；失败时打印中文原因并返回 `None`。
    """
    try:
        return PyJoystick(info.path)
    except PermissionError:
        # 无读权限最常见，提示指向 input 组与 udev 规则这两条修复路径。
        print(
            f"没有读取 {info.path} 的权限；请把当前用户加入 input 组或配置 udev 规则。"
        )
    except FileNotFoundError:
        print(f"设备节点 {info.path} 不存在，可能已被拔出。")
    except OSError as error:
        print(f"打开设备 {info.path} 失败：{error}")
    return None


def main(argv: list[str] | None = None) -> int:
    """运行单设备示例。

    Args:
        argv: 参数字符串列表；为 `None` 时由 `argparse` 读取 `sys.argv`。

    Returns:
        int: 退出码；没有可用设备、序号越界或读取失败同样返回 0。
    """
    args = parse_args(argv)
    # --list 是最安全的入口：只枚举设备名与路径，不占用设备节点。
    if args.list:
        return list_devices()

    devices = fetch_connected_joysticks()
    if not devices:
        print(NO_DEVICE_REASON)
        return 0
    print_devices(devices)

    # 越界序号属于用户输入错误，打印可用范围后正常退出。
    if not 0 <= args.index < len(devices):
        print(f"序号 {args.index} 超出范围；可用序号为 0 到 {len(devices) - 1}。")
        return 0

    info = devices[args.index]
    # 打开失败时 open_device() 已经打印中文原因，这里只需结束示例。
    joystick = open_device(info)
    if joystick is None:
        return 0

    print(f"已打开 {info.name} ({info.path})；按 Ctrl+C 停止。")
    # 先把「空字典表示本轮没有新事件」讲清楚，读者才不会把静止误判成故障。
    print("提示：某一轮 get_state() 返回空字典，表示该轮没有收到新事件。")

    rounds = 0
    try:
        # 循环条件同时覆盖「固定轮数」和「读到 Ctrl+C」两种用法。
        while args.iterations <= 0 or rounds < args.iterations:
            state = joystick.get_state()
            # get_state() 是事件差分：静止时三个映射都为空，因此只在有事件时打印。
            if state.axes or state.buttons or state.hats:
                print(f"axes={state.axes} buttons={state.buttons} hats={state.hats}")
            rounds += 1
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\n已停止读取。")
    except OSError as error:
        print(f"读取设备失败：{error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
