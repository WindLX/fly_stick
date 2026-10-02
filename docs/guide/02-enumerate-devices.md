# 枚举设备与读取单个设备

这一章先用 `fetch_connected_joysticks()` 找出可用的设备节点，再用 `PyJoystick` 读取单个设备的轴、按键与帽开关。多设备合并、去抖与按键语义见 [设备池](/guide/components/fly_stick/04-device-pool)。

## 枚举当前可读的设备

```python
import fly_stick

for info in fly_stick.fetch_connected_joysticks():
    print(info.path, info.name)
```

`fetch_connected_joysticks()` 是 Rust 侧函数（`packages/fly_stick/src/utils.rs:239-253`）：它调用 `evdev::enumerate()`，把每个设备的路径转成字符串、把设备名读成字符串，装进 `JoystickInfo`。

返回的 `JoystickInfo` 只有两个只读属性（`packages/fly_stick/src/utils.rs:8-15`，字段标注 `#[pyo3(get)]`，没有 setter）：

| 字段   | 内容                                 |
| ------ | ------------------------------------ |
| `path` | 设备节点路径，如 `/dev/input/event3` |
| `name` | 设备名；读取失败时为 `"Unknown"`     |

`path` 由 `path.to_string_lossy()` 得到（`packages/fly_stick/src/utils.rs:246`），`name` 由 `device.name().unwrap_or("Unknown")` 得到（`packages/fly_stick/src/utils.rs:247`）。该类没有 `#[new]`，Python 侧无法自己构造，只能由这个函数产生。

枚举不会只挑手柄：`evdev::enumerate()` 扫描 `/dev/input` 下所有以 `event` 开头的节点，逐个尝试打开，打不开的直接跳过（evdev 0.13.2 的 `src/raw_stream.rs:736-763`，版本由 `packages/fly_stick/Cargo.toml:18` 锁定）。所以键盘、鼠标一类的设备名也会出现在结果里，需要按 `name` 自行筛选。

## 读不到设备时的表现

权限不足不会抛异常，而是让设备从结果里消失。`/dev/input/event*` 通常是 `root:input` 加 `rw-rw----`，能不能打开由 `Device::open` 决定（`packages/fly_stick/src/inner/joystick.rs:48`）；枚举阶段遇到打不开的节点就跳过（`packages/fly_stick/src/utils.rs:241`）。对比节点数与枚举结果可以确认这一点：

```bash
ls /dev/input/event* | wc -l
python -c "import fly_stick; print(len(fly_stick.fetch_connected_joysticks()))"
```

用户不在 `input` 组时，节点数会明显多于枚举结果，差值就是当前用户读不到的设备。常见做法是把用户加入 `input` 组（重新登录后生效），或为设备写 udev 规则。

## 打开单个设备节点

`PyJoystick` 的构造函数只接受一个设备路径字符串（`packages/fly_stick/src/wrapper/joystick_wrapper.rs:13-16`）：

```python
from fly_stick import PyJoystick, fetch_connected_joysticks

infos = fetch_connected_joysticks()
if not infos:
    raise SystemExit("没有可读的输入设备")

joystick = PyJoystick(infos[0].path)
state = joystick.get_state()
print(state.axes, state.buttons, state.hats)
```

`device_path` 参数要求 `str`，传 `JoystickInfo` 对象会被拒绝。打开失败按 `std::io::Error` 的种类映射为 Python 异常：路径不存在是 `FileNotFoundError`，权限不足是 `PermissionError`，两者都是 `OSError` 的子类（`packages/fly_stick/src/inner/joystick.rs:47-51` 返回 `Result`，`packages/fly_stick/src/wrapper/joystick_wrapper.rs:14` 用 `?` 直接传播，PyO3 0.28.2 的 `src/err/impls.rs:46-65` 完成映射）。读取过程中的失败则被显式包装成 `IOError`，消息前缀是 `Failed to get joystick state: ` （`packages/fly_stick/src/wrapper/joystick_wrapper.rs:19-25`）。

## get_state() 返回的是本次调用收到的事件

这是最容易误用的地方：`get_state()` 把本次 `fetch_events()` 收到的事件整理成状态返回（`packages/fly_stick/src/inner/joystick.rs:108-161`），只含这一轮变化的 code。

- 每次调用都新建 `axes`、`buttons`、`hats` 三个映射（`packages/fly_stick/src/inner/joystick.rs:109-111`），只填入本次事件命中的 code。
- 设备静止时返回三个空字典。实机连续调用三次得到的是 `{'axes': {}, 'buttons': {}, 'hats': {}}`：没有事件不算错误，`WouldBlock` 被吞掉（`packages/fly_stick/src/inner/joystick.rs:148-150`）。
- 设备以非阻塞模式打开（`packages/fly_stick/src/inner/joystick.rs:51`），调用不会等待事件。

数值规则（`packages/fly_stick/src/inner/joystick.rs:113-146`）：

| 输入   | 键                           | 值                            |
| ------ | ---------------------------- | ----------------------------- |
| 轴     | 轴 code（`u16`）             | 归一化到 `[-1, 1]`            |
| 按键   | 按键 code（`u16`）           | 按下为 `1`，否则 `0`          |
| 帽开关 | `ABS_HAT0X`/`ABS_HAT0Y` code | 负为 `-1`，正为 `1`，零为 `0` |

轴归一化公式是 `(value - min) / (max - min) * 2 - 1` （`packages/fly_stick/src/inner/joystick.rs:128-129`）。只有设备能力里登记过的 code 会被接收：轴与帽来自 `get_absinfo()`，其中 `ABS_HAT0X`/`ABS_HAT0Y` 归入帽、其余归入轴（`packages/fly_stick/src/inner/joystick.rs:58-68`），按键来自 `supported_keys()` （`packages/fly_stick/src/inner/joystick.rs:71-75`）。

既然每次调用都是新对象，想要"当前完整状态"就得在 Python 侧自己累积：把每次非空的键值合并进一个长期字典。仓库示例正是这样写的—— `packages/fly_stick/examples/single_device.py:148-155` 每 0.02 秒调用一次 `get_state()`，只在 `axes or buttons or hats` 非空时打印。

`JoystickState` 的 `axes`、`buttons`、`hats` 属性同样只读（`packages/fly_stick/src/utils.rs:36-43`），每次访问返回的是按当前内容新建的字典，改写它不会影响对象内部。要读可读名字，可用 `to_dict()` （`packages/fly_stick/src/utils.rs:86-111`）或按别名取值的 `to_alias_dict()`、`get_alias_axes()` 等方法（`packages/fly_stick/src/utils.rs:140-202`），别名的定义见[设备描述](/guide/components/fly_stick/03-device-description)。

## 如何挑选设备

- 用 `info.path` 打开设备，用 `info.name` 判断型号。取不到名字时是 `"Unknown"` （`packages/fly_stick/src/utils.rs:247`），不要把它当匹配键。
- 两个同型号手柄的 `name` 相同而 `path` 不同；按 `name` 匹配只能命中第一个，设备池的匹配规则见[设备池](/guide/components/fly_stick/04-device-pool)。
- 想把裸 code 变成可读名字，就为设备写一份 `DeviceDescription`，再用别名读取，见[设备描述](/guide/components/fly_stick/03-device-description)。

## 相关页面

- [设备描述](/guide/components/fly_stick/03-device-description)
- [设备池](/guide/components/fly_stick/04-device-pool)
- [模型集成](/guide/components/fly_stick/06-model-integration)
- [排障](/guide/components/fly_stick/07-troubleshooting)
