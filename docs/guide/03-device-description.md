# 设备描述：DeviceItem 与 DeviceDescription

设备描述把一台操纵杆的名称、可选 evdev 路径与输入布局写成 TOML 或 Python 对象。设备池每次 `reset()` 都重新枚举设备，并用描述匹配物理设备。

## 输入项

`DeviceItem` 由硬件 code 和可选 alias 组成。别名省略时，转换后的字典使用十进制 code 字符串。

```python
from fly_stick import DeviceItem

roll = DeviceItem(0, "ABS_X")
unaliased = DeviceItem(1)
```

轴、按键、方向帽各自要求 code 唯一；有效别名键也必须唯一。空白别名无效。校验在 Python 构造、TOML 加载和设备池构造时执行。

## DeviceDescription

```python
from fly_stick import DeviceDescription, DeviceItem

description = DeviceDescription(
    device_name="Thrustmaster T.16000M",
    device_path="/dev/input/event3",  # 可省略；同名设备有多个时必须指定
    axes=[DeviceItem(0, "ABS_X"), DeviceItem(1, "ABS_Y")],
    buttons=[DeviceItem(288, "BTN_TRIGGER")],
    hats=[DeviceItem(16, "ABS_HAT0X"), DeviceItem(17, "ABS_HAT0Y")],
)
```

`device_name` 缺省为 `"Unknown Device"`；`author`、`created`、`description`、`device_path` 缺省为 `None`；三个输入列表缺省为空列表。构造器和 TOML 解析都会拒绝重复 code、重复有效 alias key、空名称或空路径。

TOML 的 `device_path` 可用于同名设备消歧：

```toml
device_name = "Thrustmaster T.16000M"
device_path = "/dev/input/event3"
author = "WindLX"

[[axes]]
code = 0
alias = "ABS_X"

[[buttons]]
code = 288
alias = "BTN_TRIGGER"
```

省略 `device_path` 时，`reset()` 要求恰好有一台设备名称精确匹配；没有匹配会抛 `LookupError`，同名设备有多个会抛 `ValueError` 并要求补路径。两个逻辑设备不能指向同一设备节点。

## 初始快照与别名

`description.build_state()` 为每个声明的 code 建立零值。设备池以此为初始快照；后续事件只更新命中的项。`PyJoystick.get_state()` 则返回本次读取到的事件差分，所以静止时映射为空。

```python
state = description.build_state()
print(state.axes, state.buttons, state.hats)
print(state.get_alias_axes(description))
```

无 alias 的输入项以 `str(code)` 为键。每类输入独立校验 alias key，因此轴和按键可以各自使用同一个别名。

## 错误

`DeviceDescription.from_toml(path)` 在文件不可读时抛 `OSError`；TOML 格式错误或描述校验失败时抛 `ValueError`。字段类型错误、缺少必需的 code、重复 code 和重复 alias 都在启动设备池之前报告。

仓库自带的控制器配置位于 `devices/`。Xbox 控制器 profile 中 code 2 映射 `ABS_Z`，code 5 映射 `ABS_RZ`。
