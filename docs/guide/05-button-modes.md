# 按钮模式

`DeviceButtonMode` （设备按钮模式）决定设备池在每次读取时如何交付按键与方向帽状态：是持续保留按住状态，还是交付一次后立即复位。枚举只有两个取值，定义见 `packages/fly_stick/src/utils.rs:265-270`。模式在创建设备池时通过 `btn_mode` 参数指定，也可以在运行中读写 `button_mode` 属性；它只改变上层看到的 `buttons` 与 `hats` 内容，不改变轴数据。

## 两种取值

- `Hold` （保持）：按键按住期间状态一直保留，松开后回到 0。
- `Trigger` （触发）：按键按下被交付一次，设备池随即把它复位为 0，之后的读取不再看到它。

枚举上的说明写在 `packages/fly_stick/src/utils.rs:255-264`。`Trigger` 的复位范围比字面含义更宽，除按键外还会清零方向帽，见下文「Trigger 同时清零方向帽」。

## 构造与切换

`DeviceButtonMode` 提供两个静态构造器和字符串构造：

```python
import fly_stick

trigger_mode = fly_stick.DeviceButtonMode.trigger()
hold_mode = fly_stick.DeviceButtonMode.hold()
trigger_mode = fly_stick.DeviceButtonMode("trigger")  # 与 trigger() 等价
```

`__new__(mode: str)` 只接受小写 `"trigger"` 与 `"hold"`，其它字符串抛出 `ValueError: Invalid button mode. Use 'trigger' or 'hold'.` （`packages/fly_stick/src/utils.rs:275-283`）；两个静态构造器分别返回对应取值（`packages/fly_stick/src/utils.rs:286-293`）。`repr()` 输出 `DeviceButtonMode.Trigger` 一类的名字，`str()` 输出 `Trigger` 或 `Hold` （`packages/fly_stick/src/utils.rs:295-307`）。

设备池的构造签名是 `PyDevicePool(device_descs={}, debounce_seconds=0.1, btn_mode=DeviceButtonMode.Hold)`，即不传 `btn_mode` 时按 `Hold` 工作（`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:21-32`）。运行中可以读取或改写 `pool.button_mode` （`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:103-120`）。

## 模式如何作用到读取结果

设备池维护两份寄存器：`input_register` 是设备池看到的最新状态，`last_input_register` 是上一次交付给调用方的状态（`packages/fly_stick/src/inner/device_pool.rs:29-38`）。两个读取入口对它们的使用方式不同：

- `fetch_nowait()` 先克隆 `input_register`，再把 `last_input_register` 无条件覆盖为同一份（`packages/fly_stick/src/inner/device_pool.rs:171-174`），随后按模式处理：`Trigger` 调用 `reset_trigger_register()`，`Hold` 什么都不做（`packages/fly_stick/src/inner/device_pool.rs:177-183`）。
- `fetch(timeout_seconds)` 只在 `input_register` 与 `last_input_register` 不相等时才更新后者、应用模式并返回（`packages/fly_stick/src/inner/device_pool.rs:231-248`）。

因此 `Hold` 下重复调用会持续拿到同一按键状态，`Trigger` 下该状态只出现一次。

## Trigger 同时清零方向帽

`reset_trigger_register()` 遍历所有设备寄存器，把所有按键与方向帽置 0，轴保持原值（`packages/fly_stick/src/inner/device_pool.rs:292-302`）。方向帽来自 `ABS_HAT0X` 与 `ABS_HAT0Y`，在 `get_state()` 中按轴值的符号取 `-1`、`0` 或 `1` （`packages/fly_stick/src/inner/joystick.rs:132-141`）。所以在 `Trigger` 模式下，方向帽的每次变化同样只交付一次；需要持续读取帽子状态时应使用 `Hold`。

## 去抖只作用于按键与方向帽

`debounce_seconds` 在构造时转成 `debounce_time = Duration::from_secs_f64(...)` （`packages/fly_stick/src/inner/device_pool.rs:99`）。监视循环里轴只要有事件就更新，不经过去抖（`packages/fly_stick/src/inner/device_pool.rs:444-448`）；按键与方向帽则先检查是否在描述中出现，再调用 `should_update_input()` （`packages/fly_stick/src/inner/device_pool.rs:451-457`、`:460-466`）。`should_update_input()` 按「设备 + code」分别记录上一次接受的时间，两次间隔小于 `debounce_time` 的更新被丢弃（`packages/fly_stick/src/inner/device_pool.rs:490-505`）。轴数据不受该时长影响。

`debounce_seconds` 默认为 0.1（`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:21-32`）。它同时决定按键的最小交付间隔：调大可以抑制抖动，但会丢掉更快的连续按键。

## 选择建议

- 一次性动作（开火、切换、边沿触发）用 `Trigger`，上层每读到一次 1 就处理一次。
- 需要持续按住的动作用 `Hold`，上层每次读取都能拿到当前状态。
- 需要连续读取方向帽时用 `Hold`，因为 `Trigger` 会把帽子开关一并清零。

示例 `packages/fly_stick/examples/btn_mode.py:87-90` 显式传入 `btn_mode=DeviceButtonMode.trigger()`；`packages/fly_stick/examples/device_pool.py:155` 只传描述与去抖，使用默认的 `Hold`。模型侧的接入示例同样使用默认模式，见 [在模型中接入操纵杆](/guide/components/fly_stick/06-model-integration)。
