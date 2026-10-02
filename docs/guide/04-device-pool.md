# 设备池：PyDevicePool

`PyDevicePool` 把多台设备聚合成一张「逻辑名 → 状态」的表：每个逻辑名配一份 [设备描述](/guide/components/fly_stick/03-device-description)，池按 `device_name` 匹配设备；匹配成功后每台设备有一个后台任务，每 10 ms 读一次并写进共享寄存器（`packages/fly_stick/src/inner/device_pool.rs:470`）。

## 创建与设备匹配

```python
from fly_stick import DeviceDescription, PyDevicePool

desc = DeviceDescription.from_toml("devices/Thrustmaster/t16000m.toml")
pool = PyDevicePool({"stick": desc}, debounce_seconds=0.1)
```

三个参数见 `packages/fly_stick/src/wrapper/device_pool_wrapper.rs:21-32`：`device_descs` 缺省空字典，`debounce_seconds` 缺省 `0.1`，`btn_mode` 缺省 `DeviceButtonMode.Hold`；类型声明见 `packages/fly_stick/src/fly_stick/_core.pyi:360-373`。池只在本进程内使用，生命周期与这个 Python 对象一致。

匹配在构造时一次做完（`packages/fly_stick/src/inner/device_pool.rs:64-85`）：枚举出设备后按 `info.name == desc.device_name` 精确比较（`:73`），不做大小写转换或模糊匹配；一台物理设备只分给一个逻辑名，命中后立刻从可用列表移除（`:82-85`）；没有匹配到时只写 `warn!("Device '{}' not found", ...)` （`:76-79`），不抛异常。枚举只发生在构造时，`reset()` 不会重新枚举。

两台同名设备配两个逻辑名时各得一台：两个逻辑名都用 `packages/fly_stick/devices/Microsoft X-Box 360/series_sx.toml`，分别绑到 `/dev/input/event3` 与 `/dev/input/event259`；同一份描述注册两次而机器上只有一台时，第二个逻辑名匹配失败。

## 属性

| 属性            | 类型                                                | 可写 |
| --------------- | --------------------------------------------------- | ---- |
| `devices`       | `dict[str, tuple[DeviceDescription, JoystickInfo]]` | 否   |
| `debounce_time` | `float`                                             | 否   |
| `button_mode`   | `DeviceButtonMode`                                  | 是   |

`devices` 给出匹配成功的逻辑名及 `(设备描述, 设备信息)`，其中的 `path` 是设备节点（`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:122-129`）。`debounce_time` 只有getter（`:94-101`），要换值就重建池；`button_mode` 可随时赋值（`:112-120`）；释放只用 `await pool.stop()`，池没有 `close()`。

## reset() 与停止

`await pool.reset()` 是必走的一步，不调用它 `fetch_nowait()` 会直接报错。它依次停掉现有后台任务（`packages/fly_stick/src/inner/device_pool.rs:376-380`）、用每份描述的 `build_state()` 重写寄存器并把「最后输入」同步成同一份（`:271-280`，即回到全 `0`）、清空去抖计时（`:137-140`）、重新起后台任务（`:315-319`），最后返回匹配到的逻辑名映射（`:134-143`）。

返回的映射与 `pool.devices` 是同一批逻辑名，没匹配上的不在里面。设备在这里才被打开：后台任务调用 `Joystick::new(device_path)`，失败只写 `warn!` 并结束该设备任务（`:421-427`）。

`await pool.stop()` 只把运行标志置 `false` 并通知后台任务退出（`:524-526`、`:376-387`），两个方法都可重复调用，都有「已是目标状态就直接返回」的判断。清理挂在 `stop()` 上，`Drop` 里没有实际逻辑（`:529-537`），别靠对象回收来停任务。

## fetch_nowait() 与 await fetch()

| 方法 | 调用方式 | 运行前提 | 失败 |
| --- | --- | --- | --- |
| `fetch_nowait()` | 同步 | 必须已 `reset()` | 未运行抛 `RuntimeError` |
| `await fetch(timeout_seconds=None)` | 协程 | 无 | 超时抛 `RuntimeError` |

`fetch_nowait()` 在 Rust 侧是同步函数，包装层用 `block_on` 驱动（`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:43-59`）；未运行时底层返回 `"Device monitoring is not running. Call reset() first."` （`packages/fly_stick/src/inner/device_pool.rs:161-164`），包装层转成 `RuntimeError`。

`await pool.fetch()` 是协程，`timeout_seconds=None` 表示一直等；检查间隔 10 ms（`packages/fly_stick/src/inner/device_pool.rs:256`），超时抛 `RuntimeError: Fetch operation timed out` （`:250-254`）。池未运行时不报错，直接把当前寄存器交出来（`:215-219`），这一点与 `fetch_nowait()` 不对称。

两个方法共用同一份「最后输入」寄存器：`fetch_nowait()` 返回前把它更新成刚拿到的快照（`:171-174`），相当于消费掉这次变化；`await fetch()` 只在当前寄存器与「最后输入」不同时才返回（`:231-248`），相同就继续每 10 ms 检查直到超时。先 `fetch_nowait()` 再马上 `await fetch(timeout_seconds=...)` 等不到刚刚那次输入，容易误判成「设备没响应」；同一个循环里只用一种读法。返回的字典覆盖所有逻辑名，任何一台设备有变化都会让它返回全部设备的状态。

## Trigger 模式会清空按键与帽

`DeviceButtonMode.Trigger` 下，两个读取方法都在返回前清空寄存器里的按键与帽开关（`:176-184`、`:237-248`），只清 `buttons` 与 `hats`，不碰 `axes` （`:292-302`）。于是按键值每次都是本次新发生的按下，下一次读又变回 `0`；`DeviceButtonMode.Hold` 保持上次的值直到下一次变化。模式可在构造时给，也可运行中用 `pool.button_mode = ...` 切换。

## 去抖

去抖只作用于按键与帽开关，轴每次采样都直接写入（`packages/fly_stick/src/inner/device_pool.rs:444-448`）。`should_update_input()` 按该设备的更新时间比较：间隔小于 `debounce_time` 就丢弃，否则记录当前时刻并接受（`:490-505`）；按键与帽开关共用一张 `device_times` 表，code 相同的两者会互相压制，`debounce_seconds` 默认 `0.1`。

## 读取别名

逻辑名对应的描述决定别名：拿到状态后用 `get_alias_axes()`、`get_alias_buttons()`、`get_alias_hats()` 或 `to_alias_dict()` 转成以别名为键的字典，传入的描述要与该逻辑名一致（`packages/fly_stick/src/utils.rs:140-202`）。`find_by_alias` 只把状态里出现的 code 变成条目（`:207-222`）：设备池的状态在构造时按描述调 `build_state()` 播种（`packages/fly_stick/src/inner/device_pool.rs:88-91`），所以池路径拿到的别名映射包含描述里声明的全部输入项；单设备 `get_state()` 只带这次调用读到的事件，映射里也只有这次命中的 code。规则见 [设备描述](/guide/components/fly_stick/03-device-description)，`packages/fly_stick/examples/alias.py:117` 是 `state.get_alias_axes(desc)` 的用法。

## 完整示例

```python
import asyncio

from fly_stick import DeviceDescription, PyDevicePool


async def main() -> None:
    desc = DeviceDescription.from_toml("devices/Thrustmaster/t16000m.toml")
    pool = PyDevicePool({"stick": desc})
    devices = await pool.reset()
    try:
        while True:
            states = await pool.fetch(timeout_seconds=1.0)
            info = devices["stick"][1]
            print(info.path, states["stick"].get_alias_axes(desc))
    finally:
        await pool.stop()


asyncio.run(main())
```

`timeout_seconds` 到点会抛 `RuntimeError`，示例让它冒泡给调用方。`packages/fly_stick/examples/device_pool.py` 用 `--profile` 指定描述路径（缺省 `devices/Thrustmaster/ta320.toml`，`:46-48`），读取前先判断文件是否存在（`:117-119`）；阻塞式读法见 `:172`，非阻塞式见 `packages/fly_stick/examples/device_pool_block.py:175`。

## 常见现象

| 现象 | 先查 |
| --- | --- |
| `fetch_nowait()` 抛 `RuntimeError` | 是否 `await pool.reset()` 过 |
| `await fetch()` 一直超时 | 是否与 `fetch_nowait()` 混用；设备是否真在产生输入 |
| `pool.devices` 少于预期 | `device_name` 拼写、同名设备已被别的逻辑名占用 |
| 按键读不到第二次 | `button_mode` 是否为 `Trigger` |
