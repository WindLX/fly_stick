"""纯数据示例：构造 DeviceDescription、零状态与 from_toml 的错误分支。

本示例不打开任何设备，只操作设备描述对象：用 ``DeviceItem(code, alias)`` 拼出一份
描述，查看 ``build_state()`` 的零状态和 ``to_alias_dict()`` 的别名映射，再用临时
文件制造 ``from_toml()`` 的两类失败（``OSError`` 与 ``ValueError``）。

不需要硬件，任何环境都能跑完并返回退出码 0。

运行方式：

```bash
uv run python examples/describe_device.py --profile devices/Thrustmaster/ta320.toml
```
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from fly_stick import DeviceDescription, DeviceItem, JoystickInfo

BROKEN_TOML = 'device_name = "未闭合\n'


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
        argparse.Namespace: 含 ``profile`` 一项。
    """
    parser = argparse.ArgumentParser(
        description="不碰硬件，演示设备描述的构造、零状态与解析错误。"
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=default_profile(),
        help="额外加载一份真实描述文件（默认包内 Thrustmaster/ta320.toml）。",
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


def sorted_by_code(values: dict[int, float | int]) -> dict[int, float | int]:
    """按 code 排序后返回同一份映射，保证输出可复现。

    Args:
        values: 硬件 code 到数值的映射。

    Returns:
        dict[int, float | int]: 按 code 升序排列的新字典。
    """
    return {key: values[key] for key in sorted(values)}


def sorted_by_alias(values: dict[str, float | int]) -> dict[str, float | int]:
    """按键名排序后返回同一份映射，保证输出可复现。

    Args:
        values: 别名或 code 字符串到数值的映射。

    Returns:
        dict[str, float | int]: 按键名升序排列的新字典。
    """
    return {key: values[key] for key in sorted(values)}


def demo_constructor_defaults() -> None:
    """演示描述、输入项与设备信息构造器的可选参数。"""
    # 三个构造器都允许省略可选参数，这里先确认默认值，后续演示才有对照。
    desc = DeviceDescription(device_name="自定义设备")
    item = DeviceItem(0)
    info = JoystickInfo("/dev/input/event0", "自定义设备")
    print("[构造器默认值]")
    print(f"  DeviceDescription: {desc.device_name!r}, path={desc.device_path!r}")
    print(f"  DeviceItem: code={item.code}, alias={item.alias!r}")
    print(f"  JoystickInfo: {info.name!r} @ {info.path}")


def build_demo_description() -> DeviceDescription:
    """用七个位置参数构造一份演示描述。

    Returns:
        DeviceDescription: 含两个轴、两个按键与一个帽开关的演示描述；轴 code 1
        与按键 code 300 故意不给别名，用来观察 ``str(code)`` 回退。
    """
    # 位置参数依次是名称、作者、创建日期与说明，随后是轴、按键、帽开关三份列表。
    return DeviceDescription(
        "演示用摇杆",
        "示例作者",
        "2026-01-01",
        "仅用于演示对象构造，不打开任何设备。",
        [DeviceItem(0, "roll"), DeviceItem(1, None)],
        [DeviceItem(288, "trigger"), DeviceItem(300, None)],
        [DeviceItem(16, "pov_x")],
    )


def print_zero_state(desc: DeviceDescription) -> None:
    """打印 ``build_state()`` 的零状态与两种字典视图。

    Args:
        desc: 待取零状态的设备描述。
    """
    # 零状态覆盖描述里声明的全部 code；两种视图只差键的类型。
    state = desc.build_state()
    plain = {kind: sorted_by_code(values) for kind, values in state.to_dict().items()}
    aliased = {
        kind: sorted_by_alias(values)
        for kind, values in state.to_alias_dict(desc).items()
    }
    print("[build_state() 零状态，全部声明项都补 0]")
    print(f"  to_dict()           = {plain}")
    print(f"  to_alias_dict()     = {aliased}")
    print(f"  get_alias_axes()    = {sorted_by_alias(state.get_alias_axes(desc))}")
    print(f"  get_alias_buttons() = {sorted_by_alias(state.get_alias_buttons(desc))}")
    print(f"  get_alias_hats()    = {sorted_by_alias(state.get_alias_hats(desc))}")
    print("  注意 code 1 与 code 300 没有别名，键是 '1' 与 '300'。")


def demo_from_toml(profile: Path) -> None:
    """加载一份真实描述文件并打印摘要。

    Args:
        profile: TOML 描述文件路径。
    """
    # 两类失败分开捕获：文件读不到是 OSError，TOML 内容不合法是 ValueError。
    try:
        desc = DeviceDescription.from_toml(str(profile))
    except OSError as error:
        print(f"[from_toml] 读取 {profile} 失败：{type(error).__name__}: {error}")
        return
    except ValueError as error:
        print(f"[from_toml] 解析 {profile} 失败：{first_line(error)}")
        return
    print(f"[from_toml] {profile}")
    print(f"  device_name={desc.device_name!r}")
    print(f"  author={desc.author!r} created={desc.created!r}")
    print(f"  axes={len(desc.axes)} buttons={len(desc.buttons)} hats={len(desc.hats)}")


def demo_from_toml_errors(temp_dir: Path) -> None:
    """用临时文件演示 ``from_toml()`` 的缺失文件、语法错误与空文件三条分支。

    Args:
        temp_dir: 存放临时 TOML 文件的目录。
    """
    # 第一条分支用不存在的路径触发文件读取错误。
    missing = temp_dir / "missing.toml"
    print(f"[预期异常] from_toml({missing.name})，文件不存在：")
    try:
        DeviceDescription.from_toml(str(missing))
    except OSError as error:
        print(f"  {type(error).__name__}: {error}")

    # 第二条分支写一段未闭合的字符串，触发 TOML 语法解析错误。
    broken = temp_dir / "broken.toml"
    broken.write_text(BROKEN_TOML, encoding="utf-8")
    print(f"[预期异常] from_toml({broken.name})，TOML 语法错：")
    try:
        DeviceDescription.from_toml(str(broken))
    except ValueError as error:
        print(f"  ValueError: {first_line(error)}")

    # 第三条分支说明空文件是合法输入，字段全部取默认值。
    minimal = temp_dir / "minimal.toml"
    minimal.write_text("", encoding="utf-8")
    desc = DeviceDescription.from_toml(str(minimal))
    print("[预期结果] from_toml(minimal.toml)，空文件不报错：")
    print(f"  device_name={desc.device_name!r} axes={len(desc.axes)}")


def main() -> int:
    """解析参数并依次运行各个纯数据演示。

    Returns:
        int: 进程退出码，恒为 0。
    """
    args = parse_args()
    # 三段演示依次是：构造器默认值、内存构造的零状态、真实文件与临时文件的解析。
    demo_constructor_defaults()
    desc = build_demo_description()
    print(f"[内存构造] device_name={desc.device_name!r}")
    print(f"  author={desc.author!r} created={desc.created!r}")
    print(f"  axes={len(desc.axes)} buttons={len(desc.buttons)} hats={len(desc.hats)}")
    print_zero_state(desc)
    demo_from_toml(args.profile)
    # 临时目录在 with 退出时自动清理，示例不留下任何文件。
    with tempfile.TemporaryDirectory() as name:
        demo_from_toml_errors(Path(name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
