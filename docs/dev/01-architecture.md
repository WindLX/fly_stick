# fly_stick 架构

`fly_stick` 是 Linux evdev 操纵杆（joystick，游戏杆/飞行摇杆）的输入库：Rust 侧通过 PyO3 暴露设备 API，Python 侧只把扩展模块里的名字再导出一遍。包内没有 Python 业务逻辑，设备访问、状态寄存器与后台任务的生命周期全部由 Rust 管理。文中路径相对仓库根，同一文件重复引用时只写文件名与行号。

## 分层的四个部分

分层是单向的：值类型层被实现层复用，实现层被边界层复用，注册层只做挂载。

| 层 | 文件 | 职责 |
| --- | --- | --- |
| 注册层 | `packages/fly_stick/src/lib.rs` | `#[pymodule]` 入口，登记类与函数 |
| 边界层 | `packages/fly_stick/src/wrapper/*.rs` | PyO3 类、参数默认值、错误映射 |
| 实现层 | `packages/fly_stick/src/inner/*.rs` | 设备枚举、监控任务、TOML 描述 |
| 值类型层 | `packages/fly_stick/src/utils.rs` | 状态值对象、按键模式、别名映射 |

`packages/fly_stick/src/lib.rs` 把 `PyDevicePool`、`PyJoystick`、`JoystickInfo`、`JoystickState`、`DeviceButtonMode`、`DeviceItem`、`DeviceDescription` 七个类与`fetch_connected_joysticks` 一个函数挂到模块上。

模块声明本身不受平台门控，`packages/fly_stick/src/lib.rs` 无条件声明 `inner`、`utils`、`wrapper` 三个模块；只有 `#[pymodule]` 入口被 `#[cfg(target_os = "linux")]`覆盖（`packages/fly_stick/src/lib.rs`）。因此非 Linux 上依赖照样参与编译，缺的只是`PyInit__core` 这个模块初始化符号。

依赖方向有一处例外值得注意：值类型层的 `packages/fly_stick/src/utils.rs` 反过来 `use`了实现层的 `DeviceDescription` 与 `DeviceItem`，因为别名映射需要读取描述项。所以`utils.rs` 与 `inner/description.rs` 是双向可见的一组类型，改动描述字段时两者要一起看。

## Python 包面

`packages/fly_stick/src/fly_stick/__init__.py:7-16` 逐个裸名导入扩展符号，`:18-27` 的`__all__` 恰好列出八个名字。这个集合由 `packages/fly_stick/tests/test_import.py:5-14` 的`EXPECTED_PUBLIC_NAMES` 锁定，公开面变化会直接让该测试失败。

构建配置里发行名与导入名不同：`name = "fly-stick"` 是 pip 安装名，`module-name = "fly_stick._core"` 是扩展模块名（`packages/fly_stick/pyproject.toml:2,17`）。Rust 库名 `_core`（`packages/fly_stick/Cargo.toml:10-11`）与包的 `python-source = "src"`（`packages/fly_stick/pyproject.toml:21`）共同决定了最终的 `fly_stick._core`。

## 异步模型

异步运行时是 Tokio，由 `pyo3-async-runtimes` 的 `tokio-runtime` 特性引入。`reset()`、`fetch()`、`stop()` 通过 `future_into_py` 返回可等待对象；`fetch_nowait()` 与属性读取同步取共享状态，不调用 `block_on`。边界实现见 `packages/fly_stick/src/wrapper/device_pool_wrapper.rs`。

`PyDevicePool` 用 `Arc<DevicePool>` 共享内部对象；`fetch()` 等待时不持有生命周期锁。原子占用标志拒绝第二个并行 `fetch()`；`fetch_nowait()` 使用独立读取游标，可与等待中的 `fetch()` 并行。边界实现见 `packages/fly_stick/src/wrapper/device_pool_wrapper.rs`。

池为所有设备创建一个监视任务，由该任务独占全部 evdev 句柄。`stop()` 发信号并等待监视任务退出，因此返回时 fd 已释放。运行错误先清理所有设备，再通知读取者；下一次读取抛 `OSError`，显式 `reset()` 才能恢复。生命周期实现见 `packages/fly_stick/src/inner/device_pool.rs`。

## 数据流

```text
evdev 枚举                     src/utils.rs
   │
   ▼
reset()：重枚举、匹配并全量预打开   src/inner/device_pool.rs
   │  input_register = 各描述的零状态
   ▼
单监视任务轮询全部设备           src/inner/device_pool.rs
   │  每 10 ms 读取事件差分
   ▼
完整快照 + 按钮边沿计数         src/inner/device_pool.rs
   │
   ▼
fetch() / fetch_nowait()        src/inner/device_pool.rs, 208-258
   │
   ▼
Python dict                     src/wrapper/device_pool_wrapper.rs
```

## 轮询而不是事件驱动

Rust 侧没有把 evdev 的读端挂到 epoll 或回调上，而是把设备设为非阻塞（`packages/fly_stick/src/inner/joystick.rs`），由监控循环每 10 ms 调一次`fetch_events()` （`packages/fly_stick/src/inner/joystick.rs`，循环节拍在`packages/fly_stick/src/inner/device_pool.rs`）。这意味着空转时每个设备每秒约产生一百次读取系统调用，新事件被发现前可能等待一个轮询周期。

## 状态归属

设备状态分为差分和快照：`PyJoystick.get_state()` 返回当前读取批次的事件差分；池把它累积为完整设备快照。按下事件另计数，因此同批按下与释放仍可产生 Trigger 脉冲；轴、按键和帽的最终物理值仍由快照表示。返回 Python 的对象是副本；别名方法只映射字典键，不修改原始状态。实现在 `packages/fly_stick/src/inner/joystick.rs`、`packages/fly_stick/src/inner/device_pool.rs` 与 `packages/fly_stick/src/utils.rs`。

evdev 只在两处被直接使用：单设备读写的 `inner/joystick.rs` 与枚举设备的`utils.rs:240-253`；池通过 `Joystick` 间接使用设备，不自己碰 evdev。

## 与仓库其它部分的接口

设备描述 TOML 存放在 `packages/fly_stick/devices/`，示例脚本在 `packages/fly_stick/examples/`，对外接口见 [接口参考](/dev/components/fly_stick/api)。把本包接进飞行器模型的完整用法见 [模型接入](/guide/components/fly_stick/06-model-integration)。

## 继续阅读

- 设备监控循环、去抖与错误映射：[实现细节](/dev/components/fly_stick/02-implementation)
- TOML 到 `DeviceDescription` 的契约：[设备描述契约](/dev/components/fly_stick/03-device-description-contract)
- 修改实现与同步存根：[扩展与维护](/dev/components/fly_stick/04-extending)
- 公开对象与使用边界：[接口参考](/dev/components/fly_stick/api)
