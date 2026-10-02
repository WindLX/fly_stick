# 故障处理

本章按「现象 → 原因 → 处理」列出接入 `fly_stick` 时最常见的失败方式。定位时先看异常类型与日志文本，再对照对应小节。

## 导入 fly_stick 失败

**现象**：`import fly_stick` 抛 `ModuleNotFoundError`；在非 Linux 平台上导入 `fly_stick._core` 抛 `ImportError`。

**原因**：`fly_stick._core` 是 maturin 构建的原生扩展，只有先安装才存在；扩展本体用 `#[cfg(target_os = "linux")]` 限定在 `packages/fly_stick/src/lib.rs:7-9`，其它平台不会生成 `_core`。

**处理**：在 `packages/fly_stick` 下执行 `just setup` （`uv sync` 加 `maturin develop`）；在模型目录下执行 `just setup-stick` （`models/fr_gtm/justfile:23-26`），它会同时安装 `fly_stick` 与 `fly_ruler_proto_python`。确认公开面：

```bash
uv run python -c "import fly_stick; print(fly_stick.__all__)"
```

## 枚举不到设备

**现象**：`fetch_connected_joysticks()` 返回空列表；示例会打印中文原因并正常退出（`packages/fly_stick/examples/single_device.py` 的设备预检分支）；`await pool.reset()` 返回 `{}`。

**原因**：没有可读的 `/dev/input/event*` 节点，或者设备被其它进程独占。

**处理**：先确认内核能看到设备，再确认 Python 侧能看到：

```bash
ls -l /dev/input/event*
```

```python
from fly_stick import fetch_connected_joysticks

for info in fetch_connected_joysticks():
    print(info.path, info.name)
```

`JoystickInfo` 只有 `path` 与 `name` 两个字段，名称读不到时回退为 `"Unknown"` （`packages/fly_stick/src/utils.rs:10-15`、`:240-253`）。

## 权限不足

**现象**：`PyJoystick(path)` 抛 `OSError`；设备池模式下 stderr 出现 `Failed to create joystick for <设备名>: ...`。

**原因**：`/dev/input/event*` 通常是 `crw-rw---- root input`，当前用户不在 `input` 组时 `Device::open` 失败（`packages/fly_stick/src/inner/joystick.rs:47-84`）；`PyJoystick` 把这类 IO 错误抛给 Python（`packages/fly_stick/src/wrapper/joystick_wrapper.rs:12-16`），设备池则在监视任务里只记一条警告并跳过该设备（`packages/fly_stick/src/inner/device_pool.rs:421-427`）。

**处理**：把用户加入 `input` 组后重新登录，或为设备写 udev 规则放宽权限。改权限前先确认设备归属，避免影响其它输入设备。

## 设备名不匹配

**现象**：stderr 出现 `Device '<名字>' not found`，但没有异常；`reset()` 返回 `{}`，随后 `fetch_nowait()` 也返回 `{}`。

**原因**：设备池用 `info.name == desc.device_name` 精确相等匹配（`packages/fly_stick/src/inner/device_pool.rs:73`），名字里有空格、大小写差异或型号后缀都会匹配失败；失败只写警告日志并跳过该描述（`packages/fly_stick/src/inner/device_pool.rs:76-79`），不抛异常。多份描述指向同一设备名时，只有先命中的描述能拿到该设备（`packages/fly_stick/src/inner/device_pool.rs:82-85`）。

**处理**：用 `fetch_connected_joysticks()` 打印真实 `name`，把它逐字复制进 profile 的 `device_name`；再核对 `[[axes]]` / `[[buttons]]` 的 `code`。仓库自带 7 份描述，例如 `packages/fly_stick/devices/Thrustmaster/t16000m.toml` 的 `device_name` 是 `Thrustmaster T.16000M`。

## RuntimeError: Device monitoring is not running. Call reset() first.

**现象**：`pool.fetch_nowait()` 抛出该 `RuntimeError`。

**原因**：设备池尚未启动监控，或已经 `stop()`。`fetch_nowait()` 先检查 `running` 标志，为假就返回这句话（`packages/fly_stick/src/inner/device_pool.rs:161-164`），再由包装层转成 `RuntimeError` （`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:43-59`）。

**处理**：调用任何读取前先 `devices = await pool.reset()`；`stop()` 之后再读取必须先重新 `reset()`。注意 `reset()` 不会重新枚举设备（`packages/fly_stick/src/inner/device_pool.rs:134-143`），热插拔后新插入的设备不会被认到。

## RuntimeError: Fetch operation timed out

**现象**：`await pool.fetch(timeout_seconds=...)` 等待一段时间后抛 `RuntimeError: Fetch operation timed out`。

**原因**：`fetch()` 在超时时间内没有观察到寄存器变化（`packages/fly_stick/src/inner/device_pool.rs:250-253`）：可能是设备没有事件、描述里没有该 `code`，或者去抖把变化丢弃了。

**处理**：确认设备确实是这部分 `code` 的来源；调大 `timeout_seconds`，或改用 `fetch_nowait()` 由调用方控制节奏。注意 `fetch()` 只有超时这一种情况会抛错：监控未运行时它直接返回 `input_register` 的克隆而不是报错（`packages/fly_stick/src/inner/device_pool.rs:215-219`），所以「不报错但一直是 `{}`」通常意味着还没 `reset()`。

## Trigger 模式读不到持续按住

**现象**：按钮明明一直按着，读取结果里只有一次 `1`。

**原因**：`Trigger` 每次交付后调用 `reset_trigger_register()`，把所有按键与方向帽清零（`packages/fly_stick/src/inner/device_pool.rs:177-180`、`:292-302`）。

**处理**：需要持续状态就改用 `Hold`，或把 `pool.button_mode` 改回 `Hold` （`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:112-120`）。两种模式的行为差别见 [按钮模式](/guide/components/fly_stick/05-button-modes)。

## 两个读取接口混用时收不到变化

**现象**：轮询 `fetch_nowait()` 的代码能读到变化，但同一设备池上 `await pool.fetch()` 一直不返回；反过来 `fetch()` 收到一次后 `fetch_nowait()` 看不到新值。

**原因**：两个入口共享「最后交付状态」寄存器 `last_input_register`。`fetch_nowait()` 每次都无条件把它覆盖成当前状态（`packages/fly_stick/src/inner/device_pool.rs:171-174`），而 `fetch()` 靠 `input_register != last_input_register` 判断是否有新输入（`packages/fly_stick/src/inner/device_pool.rs:231-248`），被覆盖后就把变化当成已消费。

**处理**：一个设备池只用一种读取方式。模型示例统一用 `fetch_nowait()` （`models/fr_gtm/examples/fly_stick_gtm.py:499`、`models/fr_f16/examples/fly_stick_f16.py:407`）。

## 退出时如何收尾

**现象**：想找 `pool.close()` 却只有 `stop()`；担心后台任务残留。

**原因**：`PyDevicePool` 只暴露 `async stop()` （`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:85-92`），它内部停止监控并发出关闭信号（`packages/fly_stick/src/inner/device_pool.rs:376-387`）；设备池的 `Drop` 是空实现，不做清理（`packages/fly_stick/src/inner/device_pool.rs:529-537`）。

**处理**：在退出路径上显式 `await pool.stop()`：示例把它放在 `KeyboardInterrupt` 分支（`packages/fly_stick/examples/device_pool.py:177-183`）或 `finally` 块（`models/fr_gtm/examples/fly_stick_gtm.py:594-602`）里。`PyJoystick` 走同步接口 `get_state()`，没有独立的后台任务需要停止。
