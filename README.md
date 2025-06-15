# fly-stick

一个基于 Rust 和 PyO3 构建的高性能 Python 库，专门用于处理游戏控制器（操纵杆/手柄）输入设备。该库使用 Linux evdev 接口提供低延迟的设备监控和状态读取功能，特别适用于飞行模拟器控制设备。

## 特性

- 🎮 **多设备支持** - 同时监控多个游戏控制器设备
- ⚡ **高性能核心** - 基于 Rust 的底层实现，提供毫秒级响应
- 🔄 **异步/同步双模式** - 支持异步和同步设备状态获取
- 📊 **设备池管理** - 统一管理多设备，自动处理设备连接状态
- 🛠️ **TOML 配置** - 基于 TOML 的设备配置描述文件
- 🐍 **完整 Python API** - 易用的 Python 接口
- 🎯 **防抖动处理** - 内置按钮和输入防抖动机制
- 📈 **实时状态监控** - 轴、按钮、帽子开关的实时状态更新

## 安装

### 系统要求

- Linux 系统（依赖 evdev 接口）
- Python 3.10+
- Rust 1.70+（仅开发时需要）

### 从源码构建

```bash
# 克隆仓库
git clone https://github.com/WindLX/fly_stick.git
cd fly_stick

# 安装构建依赖
pip install maturin

# 构建和安装
maturin develop
```

### 使用 uv（推荐）

```bash
# 使用 uv 包管理器
uv sync
uv run maturin develop
```

## 快速开始

### 单设备监控

```python
import asyncio
import fly_stick

async def monitor_single_device():
    # 获取连接的设备
    devices = fly_stick.fetch_connected_devices()
    if not devices:
        print("未找到设备")
        return

    device_path, device_name = devices[0]
    joystick = fly_stick.PyJoystick(device_path)

    print(f"监控设备: {device_name}")

    while True:
        try:
            # 获取设备状态 (axes, buttons, hats)
            state = joystick.get_state()
            axes = state.axes
            buttons = state.buttons  
            hats = state.hats
            
            if axes or buttons or hats:
                print(f"轴: {axes}, 按钮: {buttons}, 帽子开关: {hats}")
            
            await asyncio.sleep(0.01)
        except KeyboardInterrupt:
            break

asyncio.run(monitor_single_device())
```

### 设备池异步监控

```python
import asyncio
from fly_stick import DevicePool

async def monitor_device_pool():
    # 使用设备描述文件初始化设备池
    pool = DevicePool(
        device_desc_files=[
            "devices/thrustmaster/ta320.toml",
            "devices/thrustmaster/twcs.toml"
        ],
        debounce_time=0.1  # 100ms 防抖动时间
    )

    print("开始监控设备池...")

    while True:
        try:
            # 异步获取所有设备状态
            states = await pool.fetch(timeout=1.0)
            if states:
                for device_name, device_state in states.items():
                    print(f"{device_name}: {device_state}")
        except KeyboardInterrupt:
            print("停止监控")
            break

asyncio.run(monitor_device_pool())
```

### 设备池同步使用

```python
from fly_stick import DevicePool

# 初始化设备池
pool = DevicePool(
    device_desc_files=["devices/thrustmaster/ta320.toml"],
    debounce_time=0.1
)

# 同步获取设备状态
while True:
    try:
        states = pool.fetch_nowait()
        if states:
            for device_name, state in states.items():
                print(f"{device_name}: 轴={state['axes']}, 按钮={state['buttons']}")
    except KeyboardInterrupt:
        break
```

## 设备配置

设备配置使用 TOML 格式描述。例如 [devices/thrustmaster/ta320.toml](devices/thrustmaster/ta320.toml)：

```toml
device_name = "Thrustmaster T.A320 Copilot"
author = "WindLX"
created = "2025-01-14"
description = "Thrustmaster T.A320 Copilot Device Description File"

# 轴配置 (模拟输入)
[[axes]]
code = 0
alias = "ABS_X"

[[axes]]
code = 1  
alias = "ABS_Y"

[[axes]]
code = 5
alias = "ABS_RZ"

# 按钮配置
[[buttons]]
code = 288
alias = "BTN_TRIGGER"

[[buttons]]
code = 289
alias = "BTN_THUMB"

[[buttons]]
code = 290
alias = "BTN_THUMB2"

# 帽子开关配置 (方向键)
[[hats]]
code = 16
alias = "ABS_HAT0X"

[[hats]]
code = 17
alias = "ABS_HAT0Y"
```

### 配置文件说明

- `device_name`: 设备显示名称
- `author`: 配置文件作者
- `created`: 创建日期
- `description`: 设备描述
- `axes`: 轴配置列表，包含 code（evdev 代码）和 alias（别名）
- `buttons`: 按钮配置列表
- `hats`: 帽子开关配置列表

## API 参考

### 核心函数

- [`fetch_connected_devices()`](src/utils.rs) - 获取所有连接的游戏控制器设备
- [`PyJoystick(device_path)`](src/wrapper/joystick_wrapper.rs) - 创建操纵杆实例
- [`PyJoystick.get_state()`](src/wrapper/joystick_wrapper.rs) - 获取设备当前状态

### 设备池类

- [`DevicePool`](src/fly_stick/device_pool.py) - 多设备管理器
- [`DevicePool.fetch(timeout)`](src/fly_stick/device_pool.py) - 异步获取设备状态
- [`DevicePool.fetch_nowait()`](src/fly_stick/device_pool.py) - 同步获取设备状态
- [`DevicePool.reset()`](src/fly_stick/device_pool.py) - 重置设备池状态

### 设备描述

- [`DeviceDescription`](src/inner/description.rs) - 设备配置描述类
- [`DeviceItem`](src/inner/description.rs) - 设备项配置
- [`DeviceDescription.from_toml_rust(path)`](src/inner/description.rs) - 从 TOML 文件加载配置

### 数据结构

- [`JoystickState`](src/utils.rs) - 操纵杆状态，包含 axes、buttons、hats
- [`JoystickInfo`](src/utils.rs) - 操纵杆信息，包含路径和名称

## 示例

项目包含多个示例文件：

- [examples/single_device.py](examples/single_device.py) - 单设备异步监控
- [examples/multi_device.py](examples/multi_device.py) - 多设备监控
- [examples/device_pool.py](examples/device_pool.py) - 同步设备池使用
- [examples/device_pool_block.py](examples/device_pool_block.py) - 阻塞式设备池使用

## 支持的设备

目前已测试的设备：

- **Thrustmaster T.A.320 Copilot** - 空客 A320 副驾驶侧杆
- **Thrustmaster TWCS Throttle** - 推力控制系统

配置文件位于 [devices/thrustmaster/](devices/thrustmaster/) 目录：
- [devices/thrustmaster/ta320.toml](devices/thrustmaster/ta320.toml)
- [devices/thrustmaster/twcs.toml](devices/thrustmaster/twcs.toml)

### 设备映射图

项目提供了详细的设备按键映射图：
- [Thrustmaster T.A320 Copilot 映射图](figures/Thrustmaster_TA320_Copilot.drawio.png)
- [Thrustmaster TWCS Throttle 映射图](figures/Thrustmaster_TWCS_Throttle.drawio.png)

## 开发

### 项目结构

```
fly_stick/
├── src/
│   ├── lib.rs                  # Rust 模块入口
│   ├── utils.rs                # 工具函数
│   ├── inner/                  # 核心实现
│   │   ├── description.rs      # 设备描述
│   │   ├── device_pool.rs      # 设备池实现  
│   │   ├── joystick.rs         # 操纵杆实现
│   │   └── mod.rs              # 模块声明
│   ├── wrapper/                # Python 包装器
│   │   ├── device_pool_wrapper.rs
│   │   └── joystick_wrapper.rs
│   └── fly_stick/              # Python 包
│       ├── __init__.py         # 包初始化
│       ├── device_pool.py      # 设备池 Python 接口
│       └── device_description.py # 设备描述 Python 接口
├── examples/                   # 示例代码
├── devices/                    # 设备配置文件
├── figures/                    # 文档图片和映射图
├── Cargo.toml                  # Rust 项目配置
└── pyproject.toml              # Python 项目配置
```

### 构建要求

- **Rust 1.70+** - 核心库实现
- **Python 3.10+** - Python 接口
- **maturin** - Python 扩展构建工具
- **Linux evdev** - 设备输入接口

### 开发依赖

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
cargo test
pytest

# 构建发布版本
maturin build --release
```

### 添加新设备支持

1. 使用 `fetch_connected_devices()` 获取设备信息
2. 创建设备的 TOML 配置文件
3. 测试设备输入映射
4. 添加到 [devices/](devices/) 目录

## 性能特性

- **低延迟**: 基于 Rust 的核心实现，提供毫秒级响应
- **防抖动**: 内置按钮防抖动机制，避免误触发
- **非阻塞**: evdev 非阻塞模式，不会阻塞主线程
- **内存安全**: Rust 的内存安全保证，避免内存泄漏

## 许可证

本项目采用 [MIT 许可证](LICENSE)。

## 贡献

欢迎提交 Issue 和 Pull Request！

请确保：
1. 代码遵循项目风格
2. 添加必要的测试
3. 更新相关文档

## 作者

- **windlx** - *初始开发* - [windlx](https://github.com/WindLX)

---

*注意：此库目前仅支持 Linux 系统，因为它依赖于 evdev 接口。未来可能会添加对其他平台的支持。*