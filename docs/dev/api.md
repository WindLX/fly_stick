# 接口参考

`fly_stick` 导出设备枚举、单设备事件读取、设备描述和多设备状态池。签名与逐成员 docstring 位于 `src/fly_stick/_core.pyi`；自动 API 页面提供完整参数和类型。

## 公开对象

| 对象 | 职责 |
| --- | --- |
| `fetch_connected_joysticks()` | 返回当前枚举设备的 `JoystickInfo(path, name)` 列表。 |
| `JoystickInfo` | 设备路径和系统名称，可由调用方构造。 |
| `JoystickState` | 轴、按键、方向帽映射；单设备读取给事件差分，设备池给完整快照。 |
| `PyJoystick` | 打开一个设备；`get_state()` 同步读取当前读取批次的事件差分。 |
| `DeviceItem` | 一个分类内的 code 与可选 alias。 |
| `DeviceDescription` | 设备名、可选路径与轴/按键/帽布局；可从 TOML 或 Python 构造。 |
| `DeviceButtonMode` | 设备池的 Hold/Trigger 按键呈现模式。 |
| `PyDevicePool` | 重新枚举、匹配并监视多设备，提供快照读取。 |

## 组合方式

单设备调用 `PyJoystick(path).get_state()` 获取本次事件；需要保留状态时由调用方合并差分。设备池内部完成该合并：构造时提供逻辑名到描述的字典，`await pool.reset()` 重新枚举并打开全部设备，随后用 `pool.fetch_nowait()` 或 `await pool.fetch()` 读取完整快照，最后 `await pool.stop()` 等待设备释放。

```python
import asyncio

from fly_stick import DeviceButtonMode, DeviceDescription, PyDevicePool


async def main() -> None:
    desc = DeviceDescription.from_toml("devices/Thrustmaster/t16000m.toml")
    pool = PyDevicePool(
        device_descs={"stick": desc},
        button_mode=DeviceButtonMode.hold(),
    )
    try:
        devices = await pool.reset()
        state = await pool.fetch(timeout_seconds=1.0)
        print(devices["stick"][1].path, state["stick"].get_alias_axes(desc))
    finally:
        await pool.stop()


asyncio.run(main())
```

`fetch()` 与 `fetch_nowait()` 有独立读取进度，混用不会消费对方的变化。Trigger 每个入口单独观察脉冲；多次未观察的按下合并为一个。一个池同时只允许一个阻塞 `fetch()`，取消它会释放等待槽。超时抛 `TimeoutError`。

`reset()`、`fetch()` 和 `stop()` 可直接 `await`。它们由 PyO3 返回 `asyncio.Future`；若要用任务调度 `fetch()`，使用 `asyncio.ensure_future(pool.fetch())`，不要传给只接受 coroutine 的 `asyncio.create_task()`。

## 错误类别

| 情况                                | Python 异常              |
| ----------------------------------- | ------------------------ |
| 描述没有匹配设备                    | `LookupError`            |
| 名称歧义、重复设备路径或无效描述    | `ValueError`             |
| 设备打开或运行中读取失败            | `OSError`                |
| 池未运行或已有另一个 `fetch()` 等待 | `RuntimeError`           |
| `fetch()` 超时                      | `TimeoutError`           |
| TOML 文件读失败 / 内容无效          | `OSError` / `ValueError` |

设备读取错误会停止整个池并释放全部设备；需显式 `reset()` 恢复。单个设备名不匹配不会部分启动池。
