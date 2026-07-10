# fly-stick

一个基于 Rust 和 PyO3 构建的高性能 Python 库，专门用于处理游戏控制器（操纵杆/手柄）输入设备。该库使用 Linux evdev 接口提供低延迟的设备监控和状态读取能力，特别适用于飞行模拟器等实时输入场景。

## 特性

- 🎮 **多设备支持** - 同时监控多个游戏控制器设备
- ⚡ **高性能核心** - Rust 底层实现，提供毫秒级响应
- 🔄 **异步/非阻塞双模式** - 支持 `await fetch()` 与 `fetch_nowait()`
- 📊 **设备池管理** - 统一管理多设备，读取逻辑设备状态
- 🛠️ **TOML 配置** - 基于 TOML 的设备描述文件
- 🐍 **完整 Python API** - 直接从 `fly_stick` 包导入核心类型
- 🎯 **按钮模式控制** - 支持 `trigger` 与 `hold` 两种按钮处理模式
- 📈 **实时状态监控** - 轴、按钮、帽子开关状态实时更新
- 🛩️ **主动侧杆** - 通过 UDP 接收 SidestickTeensy 双杆遥测并发送飞机状态

## 安装

### 系统要求

- Linux 系统（依赖 evdev）
- Python 3.10+
- Rust（仅开发或源码构建时需要）

### 从 PYPI 下载

```bash
uv add fly-stick
```

### 从源码构建

```bash
# 克隆仓库
git clone https://github.com/WindLX/fly_stick.git
cd fly_stick

# 安装构建依赖
pip install maturin

# 构建并安装到当前 Python 环境
maturin develop
```

### 使用 uv（推荐）

```bash
uv sync
uv run maturin develop
```

## 快速开始

### 单设备监控

```python
import asyncio
import fly_stick


async def monitor_single_device():
    devices = fly_stick.fetch_connected_joysticks()
    if not devices:
        print("未找到设备")
        return

    dev = devices[0]
    joystick = fly_stick.PyJoystick(dev.path)

    print(f"监控设备: {dev.name} @ {dev.path}")

    while True:
        try:
            state = joystick.get_state()
            print(state.to_dict())
            await asyncio.sleep(0.01)
        except KeyboardInterrupt:
            break


asyncio.run(monitor_single_device())
```

### 设备池异步监控

```python
import asyncio
from fly_stick import PyDevicePool, DeviceDescription, DeviceButtonMode


async def monitor_device_pool():
    pool = PyDevicePool(
        device_descs={
            "ta320": DeviceDescription.from_toml("devices/Thrustmaster/ta320.toml"),
            "twcs": DeviceDescription.from_toml("devices/Thrustmaster/twcs.toml"),
        },
        debounce_seconds=0.1,
        btn_mode=DeviceButtonMode.hold(),
    )

    # 使用设备池前先初始化监控
    await pool.reset()

    print("开始监控设备池...")

    while True:
        try:
            states = await pool.fetch(timeout_seconds=1.0)
            for device_name, state in states.items():
                print(f"{device_name}: {state.to_dict()}")
        except KeyboardInterrupt:
            print("停止监控")
            await pool.stop()
            break


asyncio.run(monitor_device_pool())
```

### 设备池非阻塞读取

```python
import asyncio
from fly_stick import PyDevicePool, DeviceDescription


async def monitor_nowait():
    pool = PyDevicePool(
        device_descs={
            "ta320": DeviceDescription.from_toml("devices/Thrustmaster/ta320.toml"),
            "twcs": DeviceDescription.from_toml("devices/Thrustmaster/twcs.toml"),
        },
        debounce_seconds=0.1,
    )

    await pool.reset()

    try:
        while True:
            states = pool.fetch_nowait()
            for name, state in states.items():
                print(f"{name}: 轴={state.axes}, 按钮={state.buttons}, 帽子={state.hats}")
            await asyncio.sleep(0.01)
    except KeyboardInterrupt:
        await pool.stop()


asyncio.run(monitor_nowait())
```

### SidestickTeensy 主动侧杆

`ActiveSidestick` 是独立于 Linux evdev 设备池的 UDP 接口，只使用 ICC 通路，不会连接
SidestickTeensy 的 GUI/上位机端口。默认监听 `5406`（3 字节逻辑状态）和 `5407`
（48 字节电机状态），并向 Teensy `30.30.30.6:5405` 发送 `[AOA, elevator, aileron]`
飞机状态。所有数值均为弧度；线上的数值编码为大端 signed IQ24。

```python
import asyncio
from fly_stick import ActiveSidestick


async def main() -> None:
    stick = ActiveSidestick()
    await stick.start()
    try:
        state = await stick.fetch(timeout_seconds=1.0)
        if state.connected:
            print(state.stick_1.roll.position_rad)
            stick.send_aircraft_state(
                aoa_rad=0.0,
                elevator_rad=0.0,
                aileron_rad=0.0,
            )
    finally:
        await stick.stop()


asyncio.run(main())
```

`stick_1` 与 `stick_2` 分别对应固件的 `statebus1` 与 `statebus2`；每根杆包含 `roll` / `pitch` 的位置（rad）、速度（rad/s）和电流（A）。主动侧杆断链 100 ms 后， `state.stale` 变为真；固件同时退出 AP 反驱，但维持本地力梯度和侧杆联动。

## 设备配置

DevicePool 的设备配置使用 TOML 格式描述，此描述文件约束了哪些按键才会被监控和记录数据。例如 `devices/Thrustmaster/ta320.toml`：

```toml
device_name = "Thrustmaster T.A320 Copilot"
author = "WindLX"
created = "2025-01-14"
description = "Thrustmaster T.A320 Copilot Device Description File"

[[axes]]
code = 0
alias = "ABS_X"

[[axes]]
code = 1
alias = "ABS_Y"

[[buttons]]
code = 288
alias = "BTN_TRIGGER"

[[hats]]
code = 16
alias = "ABS_HAT0X"
```

### 配置文件说明

- `device_name`: 设备显示名称（用于匹配系统设备名）
- `author`: 配置文件作者（可选）
- `created`: 创建日期（可选）
- `description`: 设备描述（可选）
- `axes`: 轴配置列表，包含 `code` 与 `alias`
- `buttons`: 按钮配置列表，包含 `code` 与 `alias`
- `hats`: 帽子开关配置列表，包含 `code` 与 `alias`

## API 参考

### 核心函数

- `fetch_connected_joysticks()` - 获取当前连接的输入设备列表

### 核心类

- `PyJoystick(device_path)`
- `PyJoystick.get_state()`
- `PyDevicePool(device_descs, debounce_seconds=0.1, btn_mode=DeviceButtonMode.hold())`
- `PyDevicePool.reset()`
- `PyDevicePool.fetch(timeout_seconds=None)`
- `PyDevicePool.fetch_nowait()`
- `PyDevicePool.stop()`
- `PyDevicePool.devices`（属性）
- `PyDevicePool.debounce_time`（属性）
- `PyDevicePool.button_mode`（属性，可读写）

### 数据结构

- `JoystickInfo`（`path`, `name`）
- `JoystickState`（`axes`, `buttons`, `hats`）
- `JoystickState.to_dict()`
- `JoystickState.to_alias_dict(desc)`
- `JoystickState.get_alias_axes(desc)`
- `JoystickState.get_alias_buttons(desc)`
- `JoystickState.get_alias_hats(desc)`
- `DeviceDescription`
- `DeviceDescription.from_toml(toml_file)`
- `DeviceDescription.build_state()`
- `DeviceItem`
- `DeviceButtonMode.trigger()`
- `DeviceButtonMode.hold()`

> 注意：使用 `PyDevicePool.fetch()` 或 `fetch_nowait()` 前，需先调用 `await reset()`。

## 示例

项目包含多个示例文件：

- `examples/single_device.py` - 单设备异步监控
- `examples/multi_device.py` - 多设备异步监控
- `examples/device_pool.py` - 设备池非阻塞读取
- `examples/device_pool_block.py` - 设备池阻塞读取
- `examples/alias.py` - 按别名读取轴状态
- `examples/btn_mode.py` - 按钮触发模式示例

## 支持的设备

目前仓库内提供了以下设备描述文件：

- `devices/Thrustmaster/ta320.toml`
- `devices/Thrustmaster/twcs.toml`
- `devices/Thrustmaster/t16000m.toml`
- `devices/Thrustmaster/tca_qeng.toml`
- `devices/Thrustmaster/twcs_with_tfrp.toml`
- `devices/Microsoft X-Box 360/pad.toml`
- `devices/Microsoft X-Box 360/series_sx.toml`

### 设备映射图

项目提供了设备按键映射图：

- `figures/Thrustmaster_TA320_Copilot.drawio.png`
- `figures/Thrustmaster_TWCS_Throttle.drawio.png`
- `figures/Thrustmaster T.16000M.drawio.png`
- `figures/Thrustmaster T.Flight Rudder Pedals.drawio.png`
- `figures/Thrustmaster TCA Q-Eng 1&2.drawio.png`

## 开发

### 项目结构

```text
fly_stick/
├── src/
│   ├── lib.rs
│   ├── utils.rs
│   ├── inner/
│   │   ├── description.rs
│   │   ├── device_pool.rs
│   │   ├── joystick.rs
│   │   └── mod.rs
│   ├── wrapper/
│   │   ├── device_pool_wrapper.rs
│   │   ├── joystick_wrapper.rs
│   │   └── mod.rs
│   └── fly_stick/
│       ├── __init__.py
│       └── _core.pyi
├── examples/
├── devices/
├── figures/
├── Cargo.toml
└── pyproject.toml
```

### 构建与测试

```bash
# Rust 单元测试
cargo test

# Python 测试（如项目中提供测试用例）
pytest

# 构建发布 wheel
maturin build --release
```

## 性能特性

- **低延迟**: Rust 核心实现，输入处理延迟低
- **按钮模式控制**: 支持 Trigger/Hold 两种按钮语义
- **非阻塞读取**: 可使用 `fetch_nowait()` 做高频轮询
- **内存安全**: Rust 提供内存安全保障

## TODO

- [x] `alias` 支持
- [x] 按钮触发逻辑优化

## 许可证

本项目采用 MIT 许可证，详见 `LICENSE`。

## 贡献

欢迎提交 Issue 和 Pull Request。

建议在提交前完成：

1. 代码风格自检
2. 必要测试补充
3. 文档同步更新

## 作者

- **windlx** - 初始开发 - https://github.com/WindLX

---

*注意：该库当前仅支持 Linux（evdev）。未来可按需扩展到其他平台。*
