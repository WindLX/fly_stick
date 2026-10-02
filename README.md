# fly_stick

Real-time joystick input for FlyRuler simulations, built on Linux evdev.

`fly_stick` 把 Linux 下的飞行手柄接进 FlyRuler：Rust 与 PyO3 负责打开 `/dev/input/event*`、维护事件状态机与按键去抖，Python 侧暴露设备对象、TOML 设备描述与多设备状态池。

## 能做什么

- 枚举系统里可读的输入设备，拿到设备节点路径与名称。
- 读取单个设备的轴、按键与帽开关：轴归一到 `[-1, 1]`，按键 0/1，帽 -1/0/1。
- 用 TOML 描述文件给每个数值码起别名，按别名而不是裸数值码取值。
- 用一个设备池同时管理多个设备，按逻辑名取状态，并选择 `Hold` 或 `Trigger` 按键语义。

本包不包含飞行器模型、控制器或可视化。把轴映射成模型输入的做法见 `models/fr_gtm/examples/fly_stick_gtm.py` 与 `models/fr_f16/examples/fly_stick_f16.py`。

## 安装

```bash
pip install fly-stick
```

发行名是 `fly-stick`，导入名是 `fly_stick`。wheel 由 maturin 构建，只发布 Linux 平台产物；需要 Python 3.12+，wheel 为 abi3 产物。

在源码仓库里开发时，用本目录的 justfile 同步依赖并安装扩展模块：

```bash
cd packages/fly_stick
just setup
```

## 快速开始

```python
from fly_stick import PyJoystick, fetch_connected_joysticks

for info in fetch_connected_joysticks():
    print(info.path, info.name)

joystick = PyJoystick("/dev/input/event3")
print(joystick.get_state().axes)
```

`get_state()` 返回的是本次调用读到的事件，设备静止时三个映射为空。多设备与别名用法见设备池示例：

```python
import asyncio

from fly_stick import DeviceDescription, PyDevicePool


async def main() -> None:
    desc = DeviceDescription.from_toml("devices/Thrustmaster/t16000m.toml")
    pool = PyDevicePool(device_descs={"stick": desc})
    if "stick" not in await pool.reset():
        return
    state = pool.fetch_nowait()["stick"]
    print(state.get_alias_axes(desc).get("ABS_X"))
    await pool.stop()


asyncio.run(main())
```

## 示例

`examples/` 按由简到繁排列，包含枚举设备、多设备、设备池的阻塞与非阻塞读取、按键模式、别名、设备描述构造与异常解剖；无硬件时也能跑通其中三个。阅读顺序与运行命令见 `examples/README.md`。

## 文档与开发

- 用户手册：`docs/guide/` —— 安装、设备枚举、设备描述、设备池、按键模式、模型接入与排障。
- 开发者手册：`docs/dev/` —— 架构分层、实现细节、设备描述契约、扩展方式与接口参考。
- 接口声明：`src/fly_stick/_core.pyi` 是全部公开类型的签名与说明，`examples/` 里的可运行脚本是配套样例。
- 命令以 `just --list` 为准：`just setup`、`just fmt`、`just check`、`just test`、`just build`、`just pre-commit`；单项排障入口是私有 recipe（`just _test-rust`、`just _test-python`），不在列表里。
