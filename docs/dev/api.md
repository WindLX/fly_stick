# 接口参考

`fly_stick` 的公开面是八个对象：`src/fly_stick/__init__.py:7-16` 从编译扩展 `fly_stick._core` 导入，并由同文件的 `__all__`（`:18-27`）对外声明。签名与逐成员说明写在与扩展同名的类型存根 `packages/fly_stick/src/fly_stick/_core.pyi` 里，逐条列表见 [API 参考](/api/fly_stick/)；本章说明这些对象各承担什么、怎么组合，以及读签名时要注意的边界。

## 公开对象

| 对象 | 存根位置 | 职责 |
| --- | --- | --- |
| `fetch_connected_joysticks()` | `_core.pyi:108` | 枚举当前可读的输入设备，返回 `JoystickInfo` 列表；打不开的节点直接跳过。 |
| `JoystickInfo` | `_core.pyi:7` | 设备的 `path` 与 `name`，枚举结果的元素，不手工构造。 |
| `JoystickState` | `_core.pyi:27` | 一次读取的结果：`axes`、`buttons`、`hats` 三个 `code → 值` 映射；`to_dict()` 直接取映射，其余方法按设备描述投影成别名键。 |
| `DeviceButtonMode` | `_core.pyi:127` | 按键语义：`Trigger` 命中即复位，`Hold` 保持到释放；用 `DeviceButtonMode("trigger")` 或 `DeviceButtonMode("hold")` 构造。 |
| `DeviceItem` | `_core.pyi:184` | 描述文件里的一条「别名 → code」条目。 |
| `DeviceDescription` | `_core.pyi:204` | 一份 TOML 设备描述；`from_toml()` 读取文件，`build_state()` 生成全零状态。 |
| `PyJoystick` | `_core.pyi:286` | 单个设备对象，`get_state()` 返回这次调用读到的事件。 |
| `PyDevicePool` | `_core.pyi:323` | 多设备状态池：`reset()` 启动监控，`fetch_nowait()` 与 `fetch()` 取状态，`stop()` 停止。 |

## 组合方式

单设备用 `PyJoystick`：拿 `fetch_connected_joysticks()` 返回的 `path` 构造，轮询 `get_state()`。需要阻塞等待或同时管理多个设备时用 `PyDevicePool`：把「逻辑名 → `DeviceDescription`」交给构造函数，`reset()` 之后按逻辑名取 `JoystickState`。

别名投影需要描述对象本身：`state.get_alias_axes(desc)` 把 `code → 值` 换成 `别名 → 值`，没写 `alias` 的条目保留数字字符串键。想枚举描述声明的全部输入项，取 `DeviceDescription.build_state()` 生成零状态的键集合即可。

按键语义在池的构造函数里选定，运行时可读可写 `pool.button_mode`；去抖窗口用 `pool.debounce_time` 读取。设备清单用 `pool.devices` 查看，键是逻辑名，值是描述对象与 `JoystickInfo` 的组合。

```python
import asyncio

from fly_stick import DeviceButtonMode, DeviceDescription, PyDevicePool


async def main() -> None:
    desc = DeviceDescription.from_toml("devices/Thrustmaster/t16000m.toml")
    pool = PyDevicePool(device_descs={"stick": desc}, btn_mode=DeviceButtonMode.trigger())
    if "stick" not in await pool.reset():
        return
    state = pool.fetch_nowait()["stick"]
    print(state.get_alias_axes(desc))
    await pool.stop()


asyncio.run(main())
```

## 读签名时的边界

- 存根给出声明，行为细节以 `src/` 的 Rust 实现为准：设备池没有 `close()`，`stop()` 是唯一停止入口；停止后 `fetch_nowait()` 抛 `RuntimeError`，而 `fetch()` 返回最后一次快照。
- 轴取值 `[-1, 1]` 且不参与去抖；按键 `0/1`、帽 `-1/0/1` 参与去抖，细节见 [按键模式](/guide/components/fly_stick/05-button-modes)。
- `DeviceItem` 与 `DeviceDescription` 的位置参数在 Rust 侧没有默认值，实例化时要写全，字段见 [设备描述契约](/dev/components/fly_stick/03-device-description-contract)。

## 继续阅读

- 单个设备与池的调用路径：[架构与分层](/dev/components/fly_stick/01-architecture)
- 池的行为与失败路径：[实现细节](/dev/components/fly_stick/02-implementation)
- 改动公开面要同步哪些文件：[扩展点](/dev/components/fly_stick/04-extending)
