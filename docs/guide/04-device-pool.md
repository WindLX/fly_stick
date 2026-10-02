# 设备池：PyDevicePool

`PyDevicePool` 把逻辑设备名映射到设备完整快照。每个池由一个异步监视任务读取所有设备；`fetch()` 等待新事件，`fetch_nowait()` 读取最新快照。

## 匹配并启动设备

```python
import asyncio

from fly_stick import DeviceDescription, PyDevicePool


async def main() -> None:
    description = DeviceDescription.from_toml("devices/Thrustmaster/t16000m.toml")
    pool = PyDevicePool({"stick": description}, debounce_seconds=0.02)
    try:
        devices = await pool.reset()
        print(devices["stick"][1].path)
        states = await pool.fetch(timeout_seconds=1.0)
        print(states["stick"].get_alias_axes(description))
    finally:
        await pool.stop()


asyncio.run(main())
```

构造只保存配置。每次 `reset()` 都重新枚举设备，按名称精确匹配；描述有 `device_path` 时还要求路径相同。名称不匹配时抛 `LookupError`，名称匹配多台设备时抛 `ValueError`，重复路径或无效配置也抛 `ValueError`。`reset()` 会先打开全部匹配设备，全部成功后才启动监视；任一打开失败会抛 `OSError`、释放已打开句柄并让整个池保持停止。

成功时 `reset()` 返回逻辑设备名到 `(DeviceDescription, JoystickInfo)` 的映射；空配置成功返回 `{}`。

调用 `reset()` 前，`fetch()` 与 `fetch_nowait()` 都抛 `RuntimeError`。设备热插拔后再次调用 `reset()` 会重新枚举并匹配；运行中不会自动重连。

异步方法可以直接 `await pool.reset()`、`await pool.fetch()` 和 `await pool.stop()`。若需在后台调度 `fetch()`，使用 `asyncio.ensure_future(pool.fetch())`；PyO3 返回的是 `asyncio.Future`，不能传给只接受 coroutine 的 `asyncio.create_task()`。

## 完整快照与两种读取入口

`PyJoystick.get_state()` 返回本次收到的事件差分；设备池将这些差分合并为完整快照。轴、按键、方向帽在初始快照中包含描述声明的全部 code；任何一台设备出现状态变化，返回值都包含所有逻辑设备的快照。

`fetch_nowait()` 每次都返回最新快照。`await fetch(timeout_seconds=None)` 等待输入变化，`None` 表示一直等待，数值超时抛 `TimeoutError`。两种入口各自保留读取进度，交替使用不会消费对方尚未观察的变化。

每个池同一时刻只允许一个 `fetch()` 等待；并行的第二个 `fetch()` 立即抛 `RuntimeError`。等待可取消，取消后可再次调用。`fetch_nowait()` 与等待中的 `fetch()` 可并行读取。`stop()` 会唤醒等待者，使它们以 `RuntimeError` 退出。

设备发生读取故障时，整个池停止，所有设备句柄被释放，等待中的读取抛 `OSError`。修复设备或权限后，显式调用 `reset()` 恢复。

## 按键、方向帽与去抖

默认 `button_mode=DeviceButtonMode.hold()`：按键与方向帽保持物理状态，直到收到释放或回中事件。`DeviceButtonMode.trigger()` 为每个读取入口记录按下脉冲；每次按下在该入口被观察一次，两次读取间的多次按下合并为一个脉冲。方向帽始终保持方向状态，不随 Trigger 清零。轴始终是持久状态。

`debounce_seconds` 只抑制过快的按键按下；按键释放立即接受，方向帽和轴不去抖。evdev 自动重复事件不会被解释成释放。见[按钮模式](/guide/components/fly_stick/05-button-modes)。

模式可用构造参数 `button_mode` 指定，也可通过 `pool.button_mode` 切换。切换时会丢弃旧的 Trigger 脉冲进度，不会修改真实按键状态。

## 停止与恢复

`await pool.stop()` 是唯一停止入口。它取消并等待监视任务结束，任务退出后设备文件句柄已释放。`stop()` 可重复调用；停止后所有读取抛 `RuntimeError`。再次 `reset()` 会重新枚举、验证并打开全部设备。

使用 `try/finally` 确保任务取消或异常时仍会停止池。异常原因见[排障](/guide/components/fly_stick/07-troubleshooting)。
