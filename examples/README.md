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
  `devices/Thrustmaster/ta320.toml`，可用 `--profile` 换成别的文件。设备池要求名称唯一匹配；
  同名设备有多个时，在描述中用 `device_path` 指定节点。匹配失败时 `reset()` 抛异常。

所有命令都在 `packages/fly_stick/` 目录下执行。

## 阅读顺序

| 顺序 | 文件 | 主题 | 对应文档 | 运行命令 | 无硬件时 |
| --- | --- | --- | --- | --- | --- |
| 1 | `single_device.py` | 最短路径：枚举设备、打开一台、循环读状态；说明 `get_state()` 只含本次事件 | `/guide/components/fly_stick/02-enumerate-devices` | `uv run python examples/single_device.py`（`--list` 只列设备） | 提示后退出 0 |
| 2 | `multi_device.py` | 一轮循环里同时读多台设备；`--name` 可重复，匹配不上的设备提示并跳过 | `/guide/components/fly_stick/02-enumerate-devices` | `uv run python examples/multi_device.py --name "设备名"` | 提示后退出 0 |
| 3 | `device_pool.py` | 设备池入门：`reset()` 后用阻塞的 `await pool.fetch()` 等状态变化 | `/guide/components/fly_stick/04-device-pool` | `uv run python examples/device_pool.py --profile devices/Thrustmaster/ta320.toml` | 提示后退出 0 |
| 4 | `device_pool_block.py` | 仿真循环里的非阻塞写法：每个控制周期用 `fetch_nowait()` 取当前状态 | `/guide/components/fly_stick/04-device-pool`、`/guide/components/fly_stick/06-model-integration` | `uv run python examples/device_pool_block.py --profile devices/Thrustmaster/ta320.toml` | 提示后退出 0 |
| 5 | `btn_mode.py` | `DeviceButtonMode.Hold` 与 `Trigger` 的差别：Trigger 为每个读取入口保留按下脉冲；帽状态持久 | `/guide/components/fly_stick/05-button-modes` | `uv run python examples/btn_mode.py --profile devices/Thrustmaster/ta320.toml` | 提示后退出 0 |
| 6 | `alias.py` | 描述文件里的 `alias` 与 `to_alias_dict()` / `get_alias_axes()` 等按别名取键；没有别名的 code 用 `str(code)` 作键 | `/guide/components/fly_stick/03-device-description`、`/guide/components/fly_stick/04-device-pool` | `uv run python examples/alias.py --profile devices/Thrustmaster/ta320.toml` | 打印别名表后退出 0 |
| 7 | `describe_device.py` | 纯数据：构造 `DeviceDescription` 与 `DeviceItem`、`build_state()` 零状态、`from_toml()` 的两类解析错误 | `/guide/components/fly_stick/03-device-description` | `uv run python examples/describe_device.py --profile devices/Thrustmaster/ta320.toml` | 完整跑完，退出 0 |
| 8 | `pool_lifecycle.py` | 设备池生命周期：`reset()` 重枚举并全量预打开、`debounce_time` 与 `button_mode`、运行时切换和 `stop()` | `/guide/components/fly_stick/04-device-pool` | `uv run python examples/pool_lifecycle.py --profile devices/Thrustmaster/ta320.toml` | 完整跑完，退出 0 |
| 9 | `errors.py` | 异常解剖：`FileNotFoundError`、`PermissionError`、`from_toml()` 的 `OSError`/`ValueError`、非法按键模式的 `ValueError`、未 `reset()` 时 `fetch_nowait()` 的 `RuntimeError` | `/guide/components/fly_stick/07-troubleshooting` | `uv run python examples/errors.py` | 完整跑完，退出 0 |

## 无硬件时能跑到什么程度

| 文件 | 说明 |
| --- | --- |
| `describe_device.py` | 全程不碰设备：构造对象、取零状态、用临时文件制造解析错误。任何环境都能完整跑完。 |
| `errors.py` | 全程不要求操纵杆：不存在的路径、权限位为 000 的临时文件、坏 TOML、非法模式、空设备池。以 root 运行时无读权限分支会落到 `OSError`（权限位被绕过），脚本同样按中文说明打印。 |
| `alias.py` | 先打印描述文件里的 code 与别名对照表，找不到匹配设备时在这里退出。 |
| `pool_lifecycle.py` | 有匹配设备时演示完整生命周期；无匹配设备时显示 `LookupError` 后退出。 |
| `btn_mode.py` | 没有匹配设备时在建立设备池之前退出；`--help` 不碰设备。 |
| `single_device.py`、`multi_device.py`、`device_pool.py`、`device_pool_block.py` | 没有设备时打印中文原因后退出 0；`--list` 可以只枚举设备名与路径。 |

## 约定

- `await pool.fetch(...)` 等待状态变化，超时抛 `TimeoutError`；`pool.fetch_nowait()` 立即
  返回最新完整快照。两者读取进度独立，可混用。一个池同一时间只允许一个 `fetch()` 等待。
- 设备池不再使用时调用 `await pool.stop()`；它等待监视任务退出并释放设备。停止后再读取抛
  `RuntimeError`。运行中设备故障会停止整个池并抛 `OSError`；修复后显式 `reset()` 恢复。
- 每次 `reset()` 都重新枚举；运行中不自动重连。
