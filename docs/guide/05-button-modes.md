# 按钮模式

`DeviceButtonMode` 控制设备池如何呈现按键按下。它提供 `Hold` 与 `Trigger` 两种模式；方向帽不受按钮模式影响，始终保留当前方向。

## Hold：读取当前状态

```python
from fly_stick import DeviceButtonMode, DeviceDescription, PyDevicePool

pool = PyDevicePool(
    {"stick": DeviceDescription.from_toml("devices/Thrustmaster/t16000m.toml")}
)
```

默认模式是 `DeviceButtonMode.hold()`。按键按住期间快照值为 `1`，收到释放事件后变为 `0`；每次读取都反映当前状态。方向帽的 X/Y 方向值也会一直保留，直到收到中立值 `0`。

## Trigger：读取按下脉冲

```python
pool = PyDevicePool(device_descs, button_mode=DeviceButtonMode.trigger())
```

每个读取入口都有独立的按下进度。每个按钮从未按下转为按下时生成一个脉冲，该入口下次观察到时返回 `1`，随后返回 `0`。如果两次观察间同一按钮多次按下，脉冲合并为一个。按下与释放都发生在同一读取批次内时，Trigger 仍会交付按下脉冲。

这是一种按观察合并的输入语义，不是无限容量的逐事件队列；需要处理每次快速连按的应用应另外采集事件序列。方向帽继续返回持久方向状态，轴继续返回最新值。

## 去抖与模式切换

`debounce_seconds` 仅限制按键按下的最小间隔。按键释放立即接受，防止短按释放被去抖丢弃而遗留按住状态。轴与方向帽不去抖。evdev 的自动重复值会被忽略，不会伪装成释放。

构造参数名为 `button_mode`，与可读写属性同名；旧的 `btn_mode` 不再接受。运行时切换模式会同步各读取入口的脉冲计数，因此切换前的旧脉冲不会在新模式下重放，物理按键状态保持原样。Trigger/Hold 适合不同消费方式：飞行控制的持续轴和按钮用 Hold，一次性动作可用 Trigger。

模型实际使用设备池做连续操纵输入，示例见[模型接入](/guide/components/fly_stick/06-model-integration)；可运行的按钮模式对比见 `examples/btn_mode.py`。
