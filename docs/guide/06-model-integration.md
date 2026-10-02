# 在模型中接入操纵杆

`packages/fly_stick` 只负责把设备状态读成 Python 字典，怎样映射成模型输入由各自的示例脚本决定。仓库里有两个可直接参照的接入点：

- `models/fr_gtm/examples/fly_stick_gtm.py`
- `models/fr_f16/examples/fly_stick_f16.py`

两者结构一致：解析命令行、打开设备与 profile、在仿真回调里读取输入、把命令写进模型输入。`fly_stick` 与 `fly_ruler_proto_python` 都是可选依赖，脚本只在真正需要时才导入（`models/fr_gtm/examples/fly_stick_gtm.py:1-24`）。

## 运行方式

`models/fr_gtm/justfile:23-26` 的 `just setup-stick` 以可编辑模式安装两个包并做导入检查，`models/fr_gtm/justfile:105-107` 的 `just example-fly-stick` 运行示例；`models/fr_f16/justfile:23-26`、`:107-109` 提供同名配方。不接硬件时可以跑免依赖冒烟：

```bash
uv run python examples/fly_stick_gtm.py --dry-run --no-stick --no-proto
```

`--dry-run` 会把 `no_stick`、`no_proto`、`no_save` 一并置真（`models/fr_gtm/examples/fly_stick_gtm.py:428-433`）。

## 打开设备与加载 profile

`_open_stick()` 完成设备池的创建（`models/fr_gtm/examples/fly_stick_gtm.py:402-418`）：

- 默认 profile 是脚本同目录下的 `fly_stick_profiles/t16000m.toml` （`models/fr_gtm/examples/fly_stick_gtm.py:54-56`），由 `--profile` 覆盖。
- `DeviceDescription.from_toml(str(args.profile))` 读取设备描述（`models/fr_gtm/examples/fly_stick_gtm.py:406`）。
- `PyDevicePool(device_descs={args.logical_name: desc}, debounce_seconds=0.02)` （`models/fr_gtm/examples/fly_stick_gtm.py:407-410`）：描述以逻辑名 `stick` 为键，去抖 0.02 秒；未传 `button_mode`，因此按 `Hold` 工作，见 [按钮模式](/guide/components/fly_stick/05-button-modes)。
- `await pool.reset()` 重新枚举、匹配并启动全部设备；成功时返回逻辑名到 `(DeviceDescription, JoystickInfo)` 的映射。当前模型示例不需要这个返回值。未匹配设备由 `reset()` 抛 `LookupError`；无需手工检查 key 或先停止池（`models/fr_gtm/examples/fly_stick_gtm.py:412`）。

设备池按 `device_name` 与设备名精确相等匹配，细节见 [设备池](/guide/components/fly_stick/04-device-pool)。

## 在回调里读取输入

输入回调用 `fetch_nowait()` 取当前状态，再按逻辑名取出该设备的状态字典（`models/fr_gtm/examples/fly_stick_gtm.py:498-499`）：

```python
state = None if pool is None else pool.fetch_nowait().get(args.logical_name)
axes, buttons = _read_alias_input(state, desc)
```

`_read_alias_input()` 只认识几个别名（`models/fr_gtm/examples/fly_stick_gtm.py:202-220`）：轴取 `ABS_X`、`ABS_Y`、`ABS_RZ`、`ABS_THROTTLE`，按键取 `BTN_TRIGGER`，缺失的轴留 `None`，数值经 `_clip_unit()` 限幅到 `[-1, 1]` （`models/fr_gtm/examples/fly_stick_gtm.py:73-78`）。别名与 code 的对应关系来自 profile 的 `[[axes]]` / `[[buttons]]` 小节，`get_alias_axes()` 与 `get_alias_buttons()` 只会交出这次读取命中的键（`packages/fly_stick/src/utils.rs`）。

## StickAxes 是纯数据类

`models/fr_gtm/src/fr_gtm/stick_input.py:5` 定义 `STICK_VISUAL_MODEL_ID = "boeing_737_800"`，`:9-23` 定义不可变的 `StickAxes(roll, pitch, yaw, throttle)`：字段都有默认值，`throttle` 允许 `None` 表示该设备没有油门轴。它不带任何合并或换算逻辑。`models/fr_f16/examples/fly_stick_f16.py:53-69` 在自己的脚本里另外定义了 `StickAxes`、`StickButtons`、`GearToggle` 三个数据类，字段含义相同。

## 从轴到模型输入

映射集中在示例脚本里，分三步：

1. 限幅与死区：`_clip_unit()` 把值压到 `[-1, 1]` （`models/fr_gtm/examples/fly_stick_gtm.py:73-78`），`_deadband()` 把阈值内的值归零，阈值外按剩余行程线性缩放（`models/fr_gtm/examples/fly_stick_gtm.py:81-86`）。
2. `map_stick_to_command()` 把轴转成 `[升降舵, 副翼, 方向舵, 油门]` （`models/fr_gtm/examples/fly_stick_gtm.py:89-144`）：横滚、俯仰、偏航按 `invert_*` 决定符号，过死区后与对应舵面限幅相乘；油门取 `nominal_throttle`，或在有油门轴时按 `(轴值 + 1) * 50` 映射到 `0..100`。
3. `build_input()` 把命令铺进模型输入向量：`Root::u` 是四元命令，`Root::d` 是 4 个零，`Root::n` 是 21 个零，共 29 个元素（`models/fr_gtm/examples/fly_stick_gtm.py:147-164`）。

F-16 示例的差别主要在油门：它把 `[-1, 1]` 先映射到 `[0, 1]`，再插值到 `thrust_cmd_limit_bottom..thrust_cmd_limit_top` （`models/fr_f16/examples/fly_stick_f16.py:107-115`）。按键只用来做边沿检测，例如 `buttons.trigger and not gear.last_trigger` 切换起落架（`models/fr_f16/examples/fly_stick_f16.py:438-447`）。

## profile 文件

两个示例各带一份 `t16000m.toml` （92 行），内容只有 `created` 与 `description` 两行不同。顶层字段为 `device_name`、`author`、`created`、`description`，输入项写在 `[[axes]]`、`[[buttons]]`、`[[hats]]` 小节中，每项 `code` 必填、`alias` 可选；没有 `alias` 的项在别名字典里以十进制 code 字符串为键（`packages/fly_stick/src/utils.rs`）。字段语义见[设备描述](/guide/components/fly_stick/03-device-description)。

## 收尾

示例在 `finally` 块里保存记录、`await pool.stop()` 并关闭协议客户端（`models/fr_gtm/examples/fly_stick_gtm.py:594-602`）。设备池没有 `close()`，停止方式是 `stop()`；异常与收尾细节见[故障处理](/guide/components/fly_stick/07-troubleshooting)。
