# fly_stick 示例

这里的示例按「由简到繁」排成一个阅读顺序：从前四个文件只读单个或多个设备，到设备池的
阻塞与非阻塞两种取状态方式，再到按键模式、别名、纯数据描述和异常解剖。每个示例只讲一个
主题，可以单独读懂；所有示例都接受 `--help`，都用 `argparse` 参数化，路径不写死。

示例是**真机示例**：库里没有 mock、回放或假后端。只有 `describe_device.py` 与
`errors.py` 完全不打开设备，其余示例在没有设备或没有读权限时打印中文原因后以退出码 0
结束，不会抛 traceback。

## 准备

- 运行平台为 Linux，设备节点是 `/dev/input/event*`。
- 当前用户要能读设备：把用户加入 `input` 组，或按 udev 规则授予读权限；安装与授权步骤
  见 `/guide/components/fly_stick/01-install`，排查步骤见
  `/guide/components/fly_stick/07-troubleshooting`。
- 设备描述文件在仓库的 `packages/fly_stick/devices/` 下；示例默认使用
  `devices/Thrustmaster/ta320.toml`，可用 `--profile` 换成别的文件。设备池按描述文件里的
  `device_name` 与真实设备名**精确相等**匹配，名字对不上时池是空的，只打印提示。

所有命令都在 `packages/fly_stick/` 目录下执行。

## 阅读顺序

| 顺序 | 文件 | 主题 | 对应文档 | 运行命令 | 无硬件时 |
| --- | --- | --- | --- | --- | --- |
| 1 | `single_device.py` | 最短路径：枚举设备、打开一台、循环读状态；说明 `get_state()` 只含本次事件 | `/guide/components/fly_stick/02-enumerate-devices` | `uv run python examples/single_device.py`（`--list` 只列设备） | 提示后退出 0 |
| 2 | `multi_device.py` | 一轮循环里同时读多台设备；`--name` 可重复，匹配不上的设备提示并跳过 | `/guide/components/fly_stick/02-enumerate-devices` | `uv run python examples/multi_device.py --name "设备名"` | 提示后退出 0 |
| 3 | `device_pool.py` | 设备池入门：`reset()` 后用阻塞的 `await pool.fetch()` 等状态变化 | `/guide/components/fly_stick/04-device-pool` | `uv run python examples/device_pool.py --profile devices/Thrustmaster/ta320.toml` | 提示后退出 0 |
| 4 | `device_pool_block.py` | 仿真循环里的非阻塞写法：每个控制周期用 `fetch_nowait()` 取当前状态 | `/guide/components/fly_stick/04-device-pool`、`/guide/components/fly_stick/06-model-integration` | `uv run python examples/device_pool_block.py --profile devices/Thrustmaster/ta320.toml` | 提示后退出 0 |
| 5 | `btn_mode.py` | `DeviceButtonMode.Hold` 与 `Trigger` 的差别：Trigger 每次读取后清零按键与帽 | `/guide/components/fly_stick/05-button-modes` | `uv run python examples/btn_mode.py --profile devices/Thrustmaster/ta320.toml` | 提示后退出 0 |
| 6 | `alias.py` | 描述文件里的 `alias` 与 `to_alias_dict()` / `get_alias_axes()` 等按别名取键；没有别名的 code 用 `str(code)` 作键 | `/guide/components/fly_stick/03-device-description`、`/guide/components/fly_stick/04-device-pool` | `uv run python examples/alias.py --profile devices/Thrustmaster/ta320.toml` | 打印别名表后退出 0 |
| 7 | `describe_device.py` | 纯数据：构造 `DeviceDescription` 与 `DeviceItem`、`build_state()` 零状态、`from_toml()` 的两类解析错误 | `/guide/components/fly_stick/03-device-description` | `uv run python examples/describe_device.py --profile devices/Thrustmaster/ta320.toml` | 完整跑完，退出 0 |
| 8 | `pool_lifecycle.py` | 设备池生命周期：构造时的设备匹配、`debounce_time` 与 `button_mode`、`reset()`、运行时切换模式、`stop()`；库没有 `close()`，`reset()` 不会重新枚举设备 | `/guide/components/fly_stick/04-device-pool` | `uv run python examples/pool_lifecycle.py --profile devices/Thrustmaster/ta320.toml` | 完整跑完，池为空，退出 0 |
| 9 | `errors.py` | 异常解剖：`FileNotFoundError`、`PermissionError`、`from_toml()` 的 `OSError`/`ValueError`、非法按键模式的 `ValueError`、未 `reset()` 时 `fetch_nowait()` 的 `RuntimeError` | `/guide/components/fly_stick/07-troubleshooting` | `uv run python examples/errors.py` | 完整跑完，退出 0 |

## 无硬件时能跑到什么程度

| 文件 | 说明 |
| --- | --- |
| `describe_device.py` | 全程不碰设备：构造对象、取零状态、用临时文件制造解析错误。任何环境都能完整跑完。 |
| `errors.py` | 全程不要求操纵杆：不存在的路径、权限位为 000 的临时文件、坏 TOML、非法模式、空设备池。以 root 运行时无读权限分支会落到 `OSError`（权限位被绕过），脚本同样按中文说明打印。 |
| `alias.py` | 先打印描述文件里的 code 与别名对照表，找不到匹配设备时在这里退出。 |
| `pool_lifecycle.py` | 设备匹配在构造时就完成，之后的 `reset()`、模式切换、`stop()`、停止后的读取行为都会照常演示。 |
| `btn_mode.py` | 没有匹配设备时在建立设备池之前退出；`--help` 不碰设备。 |
| `single_device.py`、`multi_device.py`、`device_pool.py`、`device_pool_block.py` | 没有设备时打印中文原因后退出 0；`--list` 可以只枚举设备名与路径。 |

## 约定

- 设备池的读取接口有两条路径：`await pool.fetch(...)` 会等待状态变化或超时，适合主循环；
  `pool.fetch_nowait()` 立即返回最近一次状态，但它要求设备池已经在运行，未 `reset()` 或
  已 `stop()` 时抛 `RuntimeError`。两者共用同一份输入寄存器，混用会互相吞掉变化。
- 设备池不再使用时调用 `await pool.stop()`；库没有 `close()`。`stop()` 之后再读取只会
  拿到陈旧快照，不会报错。
- 设备热插拔后要新建 `PyDevicePool`，`reset()` 不会重新枚举设备。
