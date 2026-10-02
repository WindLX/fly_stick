# 设备描述：DeviceItem 与 DeviceDescription

设备描述（device description）把一台操纵杆的输入布局写成数据：有哪些轴、按键与帽开关，各自的 evdev 数值码和别名是什么。设备池用描述建立初始状态、做别名映射并按 `device_name` 匹配设备，它本身不打开设备。

## DeviceItem：一个输入项

| 属性    | 类型          | 含义                            |
| ------- | ------------- | ------------------------------- |
| `code`  | `int`         | evdev 数值码，如 `0`（`ABS_X`） |
| `alias` | `str \| None` | 别名，不设时传 `None`           |

```python
from fly_stick import DeviceItem
trigger = DeviceItem(288, "BTN_TRIGGER")
raw = DeviceItem(300, None)
```

两个字段都只有 `#[pyo3(get)]` （`packages/fly_stick/src/inner/description.rs:36-40`），Python 侧赋值抛 `AttributeError`。`#[new] fn new(code: u16, alias: Option<String>)` （`packages/fly_stick/src/inner/description.rs:62-65`）没配 `#[pyo3(signature = ...)]`，`Option<String>` 在 Python 中仍是必填参数，`DeviceItem(288)` 抛 `TypeError: ... missing 1 required positional argument: 'alias'`；`packages/fly_stick/src/fly_stick/_core.pyi:195` 标了默认值 `None`，与实现不一致。

## DeviceDescription：整台设备

| 字段 | 类型 | 缺省 |
| --- | --- | --- |
| `device_name` | `str` | `"Unknown Device"` |
| `author` / `created` / `description` | `str \| None` | `None` |
| `axes` / `buttons` / `hats` | `list[DeviceItem]` | 空列表 |

`device_name` 的默认值来自 `default_device_name()` （`packages/fly_stick/src/inner/description.rs:120-122`）：serde 由 `#[serde(default = "default_device_name")]` 触发，构造函数遇到 `None` 时同样替换（`packages/fly_stick/src/inner/description.rs:100-101`、`:161`）。七个属性都只读（`packages/fly_stick/src/inner/description.rs:100-117`）。构造函数有七个关键字参数，都要显式传入：

```python
desc = DeviceDescription(
    device_name="Thrustmaster T.16000M", author="WindLX", created="2025-06-16",
    description=None, axes=[DeviceItem(0, "ABS_X")],
    buttons=[DeviceItem(288, "BTN_TRIGGER")], hats=[],
)
```

`#[new]` （`packages/fly_stick/src/inner/description.rs:150-159`）同样没有 `#[pyo3(signature = ...)]`：即使 `packages/fly_stick/src/fly_stick/_core.pyi:238-247` 列出默认值，省略参数仍抛 `DeviceDescription.__new__() missing 6 required positional arguments`。不需要的元信息显式传 `None`，或改用 `from_toml()`。

## TOML 格式与示例

顶层写 `device_name`、`author`、`description` 等元信息，`[[axes]]`、`[[buttons]]`、`[[hats]]` 列出输入项，每项 `code` 必填、`alias` 可省略。

```toml
device_name = "Thrustmaster T.16000M"
author = "WindLX"
description = "Thrustmaster T.16000M Device Description File"
[[axes]]
code = 0
alias = "ABS_X"
[[buttons]]
code = 288
alias = "BTN_TRIGGER"
[[hats]]
code = 16
alias = "ABS_HAT0X"
```

与 `packages/fly_stick/devices/Thrustmaster/t16000m.toml:1-26` 一致；该文件里 `code = 300`、`301`、`302` 三项没有 `alias` （`packages/fly_stick/devices/Thrustmaster/t16000m.toml:72-80`），这是合法写法。

仓库自带 7 份描述：`packages/fly_stick/devices/Microsoft X-Box 360/` 下的 `pad.toml`、`series_sx.toml`，以及 `packages/fly_stick/devices/Thrustmaster/` 下的 `t16000m.toml`、`ta320.toml`、`tca_qeng.toml`、`twcs.toml`、`twcs_with_tfrp.toml`；它们的 `device_name` 必须与枚举出的设备名精确一致。

serde 的缺省规则：`device_name`、`axes`、`buttons`、`hats` 有默认值；`author`、`created`、`description` 是 `Option<T>`，缺省即 `None`。空文件也能解析成默认描述，`device_name` 取 `"Unknown Device"` （`packages/fly_stick/src/inner/description.rs:351-366`）。

## from_toml() 的两类失败

静态方法 `DeviceDescription.from_toml(toml_file)` （`packages/fly_stick/src/fly_stick/_core.pyi:260-274`）：

```python
desc = DeviceDescription.from_toml("devices/Thrustmaster/t16000m.toml")
```

| 现象         | 异常         | 触发点                    |
| ------------ | ------------ | ------------------------- |
| 文件读不到   | `OSError`    | `fs::read_to_string` 失败 |
| 内容解析失败 | `ValueError` | `toml::from_str` 失败     |

两处都用 `PyErr` 直接抛出，底层文本原样透传：路径不存在时是 `No such file or directory (os error 2)`，TOML 写错时是带行列号的 `TOML parse error`，漏写 `code` 时报 `missing field 'code'` （`packages/fly_stick/src/inner/description.rs:180-183`）。校验只到语法与类型：`code` 填成设备上不存在的数值不会被拒绝，池运行时也只更新描述里声明过的输入（`packages/fly_stick/src/inner/device_pool.rs:442-467`）。

## build_state() 与 to_dict()

`build_state()` 按描述里声明过的 code 造一份全零状态；轴写 `0.0`，按键与帽开关写 `0`，键就是 `code` （`packages/fly_stick/src/inner/description.rs:191-207`）。

```python
state = desc.build_state()   # axes/buttons/hats 全为零，键就是 code
```

`JoystickState` 的三个字段都是 `dict[int, ...]`，只带 getter（`packages/fly_stick/src/utils.rs:36-43`）：读到的是一份普通字典，改写它不会影响 Rust 侧状态。`to_dict()` 是 `JoystickState` 的方法，把同一份数据转成按类别分组的字典（`packages/fly_stick/src/utils.rs:86-111`），`packages/fly_stick/examples/device_pool.py:175` 就打印 `state.to_dict()`。

## 别名的作用

别名让读取端写 `axes["ABS_X"]` 而不是 `axes[0]`。规则集中在 `find_by_alias()` （`packages/fly_stick/src/utils.rs:207-222`）：有 `alias` 时用别名作键，没有时用 `item.code.to_string()` 作键（`packages/fly_stick/src/utils.rs:210-219`），且只有该 `code` 出现在传入的状态字典里才产生键值对（`packages/fly_stick/src/utils.rs:211`、`:217`）；映射结果只包含命中的键，状态里没有的输入项不会以零值补齐。

重复别名则相反：同一别名后出现的项覆盖先出现的项（`packages/fly_stick/src/utils.rs:209-220`）。`packages/fly_stick/devices/Microsoft X-Box 360/series_sx.toml` 里 `code = 2` （`:16`）与 `code = 5` （`:28`）都叫 `ABS_RZ`，映射后只剩一个键。

`get_alias_axes()`、`get_alias_buttons()`、`get_alias_hats()` 与 `to_alias_dict()` 都走这套规则（`packages/fly_stick/src/utils.rs:140-202`）；池场景下的读取方式见 [设备池](/guide/components/fly_stick/04-device-pool)，底层实现见 [fly_stick 实现](/dev/components/fly_stick/02-implementation)。
