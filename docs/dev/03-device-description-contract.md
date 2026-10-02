# 设备描述契约

设备描述（device description）是"逻辑输入名 → 硬件 code"的映射表，用 TOML 文件书写、由 `serde` 反序列化进 `DeviceDescription`。本章说明这份文件被接受的范围、缺省值、校验边界以及仓库现有描述的现状。所有路径相对仓库根，同一文件重复引用只写文件名与行号。

## TOML 形状

顶层是四个元数据字段加三个可选的数组表：

```toml
device_name = "Thrustmaster T.A320 Copilot"
author = "WindLX"
created = "2025-06-14"
description = "Thrustmaster T.A320 Copilot Device Description File"

# Axes
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

`code` 是 u16，取 evdev 的原生编号；`alias` 是可读名字，省略时该输入只能用数字 code 引用。上面示例的前 9 行照抄 `packages/fly_stick/devices/Thrustmaster/ta320.toml:1-9`；`[[buttons]]` 与 `[[hats]]` 两段是按同一形状补的示意，该文件里它们出现在更后面。

## 反序列化规则

结构体的 derive 在 `packages/fly_stick/src/inner/description.rs:68-69`，字段级规则如下（行号同文件）：

| 字段 | 类型 | 缺失时 | 依据 |
| --- | --- | --- | --- |
| `device_name` | `String` | `"Unknown Device"` | `:100-102,120-122` |
| `author` | `Option<String>` | `None` | `:103-104` |
| `created` | `Option<String>` | `None` | `:105-106` |
| `description` | `Option<String>` | `None` | `:107-108` |
| `axes` | `Vec<DeviceItem>` | 空列表 | `:109-111` |
| `buttons` | `Vec<DeviceItem>` | 空列表 | `:112-114` |
| `hats` | `Vec<DeviceItem>` | 空列表 | `:115-117` |
| `DeviceItem.code` | `u16` | 必填 | `:36-37` |
| `DeviceItem.alias` | `Option<String>` | `None` | `:39-40` |

只有 `device_name` 用 `#[serde(default = "default_device_name")]` 绑定函数（`:100-102`），`axes`/`buttons`/`hats` 用 `#[serde(default)]` （`:109,112,115`）；`author`/`created`/`description` 没有显式属性，靠 serde 在字段缺失时给 `Option` 取 `None` 的默认行为。整个结构体没有 `deny_unknown_fields`，因此多写的键被忽略而不是报错。

Python 侧直接构造走的是同一个结构：`DeviceDescription(...)` 的 `#[new]` （`:150-175`）在 `device_name` 为 `None` 时套用默认名（`:161`），三个列表为 `None` 时用 `unwrap_or_default()` （`:165-167`）。七个字段都带 `#[pyo3(get)]` （`:100-118`），Python 只能读不能改。

## 校验边界

反序列化只覆盖 TOML 的语法与类型两层，`toml::from_str` 的失败统一变成 `ValueError` （`packages/fly_stick/src/inner/description.rs:182-183`）。它不做这些检查：

- 不检查 `code` 是否是真实的 evdev code，也不检查它在目标设备上是否存在。
- 不检查同一列表内的重复 `code`，也不检查 `alias` 是否重复或为空串。
- 不读取 min/max 之类的额外键，未知键被静默忽略。
- `code` 写成负数或大于 65535 的整数会在类型转换阶段失败，同样落入 `ValueError`。

`build_state()` （`packages/fly_stick/src/inner/description.rs:191-207`）按列表生成零值状态：轴写 `0.0`、按键写 `0`、帽写 `0` （`:197-206`）。它用 `HashMap` 的 `insert` 建键，同一列表里重复的 `code` 会折叠成一个键；轴、按键、帽是三张独立的 map，同一个数字 code 出现在不同类型里互不冲突。池的初始寄存器与 `reset()` 都调用这个方法（`packages/fly_stick/src/inner/device_pool.rs:88-91,271-280`）。

## 两种失败

`DeviceDescription.from_toml(path)` 按失败原因给出两种异常（`packages/fly_stick/src/inner/description.rs:179-185`）：

| 情况                    | 位置       | 异常         |
| ----------------------- | ---------- | ------------ |
| 文件不存在或读不到      | `:180-181` | `OSError`    |
| TOML 语法或字段类型错误 | `:182-183` | `ValueError` |

Rust 侧的内部入口是 `from_toml_rust` （`:212-216`），它把错误保持为 `Box<dyn std::error::Error>`，只用于测试与 Rust 调用方，不暴露给 Python。

## 设备名如何被使用

池按 `info.name == desc.device_name` 做精确字符串比较（`packages/fly_stick/src/inner/device_pool.rs:73`），取第一个命中的物理设备并从候选列表移除（`:82-85`）。由此产生两条契约：

- 比对的是内核上报的名字，大小写、空格、连字符都必须逐字节一致；名字不符时只写一条日志（`:76-79`），不抛异常。
- 两个逻辑名指向同一个 `device_name` 时，只有遍历中先遇到的那个能绑定设备，另一个被跳过。`device_descs` 是 `HashMap` （`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:24`），其迭代顺序在进程内不保证，因此"哪一个逻辑名拿到设备"也不确定。

仓库里有一对真实例子：`packages/fly_stick/devices/Thrustmaster/twcs.toml` 与 `packages/fly_stick/devices/Thrustmaster/twcs_with_tfrp.toml` 的 `device_name` 都是 `"Thrustmaster TWCS Throttle"` （两者都在文件第 1 行），同时把两者注册进一个池时只会有一个被绑定。两份描述的区别在于 `twcs_with_tfrp.toml` 把 T.Flight 脚舵的轴也并了进来。

## `devices/` 目录现状

`packages/fly_stick/devices/` 下现有 7 份描述，下列路径省略该前缀，末尾数字依次是轴/按键/帽的数量：

- `Microsoft X-Box 360/pad.toml` — `Microsoft X-Box 360 pad`：7/11/2
- `Microsoft X-Box 360/series_sx.toml` — `Microsoft Xbox Series S|X Controller`：6/12/2
- `Thrustmaster/t16000m.toml` — `Thrustmaster T.16000M`：4/16/2
- `Thrustmaster/ta320.toml` — `Thrustmaster T.A320 Copilot`：4/17/2
- `Thrustmaster/tca_qeng.toml` — `Thrustmaster TCA Q-Eng 1&2`：2/8/0
- `Thrustmaster/twcs.toml` — `Thrustmaster TWCS Throttle`：3/13/4
- `Thrustmaster/twcs_with_tfrp.toml` — `Thrustmaster TWCS Throttle`：6/13/4

描述里可以有注释行，位置不限，`tca_qeng.toml` 就在 `[[axes]]` 与 `code` 之间插了说明方向的注释（该文件第 8、13 行）。增删一份描述、以及如何确认设备名，见 [扩展与维护](/dev/components/fly_stick/04-extending)。
