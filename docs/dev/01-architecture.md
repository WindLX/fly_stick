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

`packages/fly_stick/src/lib.rs:12-21` 把 `PyDevicePool`、`PyJoystick`、`JoystickInfo`、`JoystickState`、`DeviceButtonMode`、`DeviceItem`、`DeviceDescription` 七个类与`fetch_connected_joysticks` 一个函数挂到模块上。

模块声明本身不受平台门控，`packages/fly_stick/src/lib.rs:1-3` 无条件声明 `inner`、`utils`、`wrapper` 三个模块；只有 `#[pymodule]` 入口被 `#[cfg(target_os = "linux")]`覆盖（`packages/fly_stick/src/lib.rs:7-8`）。因此非 Linux 上依赖照样参与编译，缺的只是`PyInit__core` 这个模块初始化符号。

依赖方向有一处例外值得注意：值类型层的 `packages/fly_stick/src/utils.rs:1` 反过来 `use`了实现层的 `DeviceDescription` 与 `DeviceItem`，因为别名映射需要读取描述项。所以`utils.rs` 与 `inner/description.rs` 是双向可见的一组类型，改动描述字段时两者要一起看。

## Python 包面

`packages/fly_stick/src/fly_stick/__init__.py:7-16` 逐个裸名导入扩展符号，`:18-27` 的`__all__` 恰好列出八个名字。这个集合由 `packages/fly_stick/tests/test_import.py:5-14` 的`EXPECTED_PUBLIC_NAMES` 锁定，公开面变化会直接让该测试失败。

构建配置里发行名与导入名不同：`name = "fly-stick"` 是 pip 安装名，`module-name = "fly_stick._core"` 是扩展模块名（`packages/fly_stick/pyproject.toml:2,17`）。Rust 库名 `_core`（`packages/fly_stick/Cargo.toml:10-11`）与包的 `python-source = "src"`（`packages/fly_stick/pyproject.toml:21`）共同决定了最终的 `fly_stick._core`。

## 异步模型

异步运行时是 tokio，由 `pyo3-async-runtimes` 的 `tokio-runtime` 特性引入（`packages/fly_stick/Cargo.toml:27-29,34-36`）。边界层有两种入口形式：

- 让 Python `await` 的方法用 `future_into_py` 返回 awaitable：`reset()`（`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:34-41`）、`fetch()` （同文件`:61-83`）、`stop()` （同文件 `:85-92`）。
- 同步方法与属性用 `get_runtime().block_on(...)` 就地阻塞调用线程：`fetch_nowait()`（同文件 `:43-59`）以及四个 getter/setter（同文件 `:94-129`）。

整个池被一把异步互斥锁包住：`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:14-17` 里 `PyDevicePool`只持有一个 `Arc<tokio::sync::Mutex<DevicePool>>`。`fetch()` 在锁内部等待状态变化（同文件`:69-72` 到 `pool.fetch(...)`），所以在一次挂起的 `fetch()` 期间，其他`fetch_nowait()`、属性读取与 `reset()` 都会排队。同步 getter 走`block_on`，排队时阻塞的是调用它的 Python 线程。

池内部为每个已匹配设备派生一个 tokio 任务，另有一个 supervisor 任务等待关停信号后`abort` 全部设备任务（`packages/fly_stick/src/inner/device_pool.rs:341-353` 与`:355-363`）。

## 数据流

```text
evdev 枚举                     src/utils.rs:240-253
   │
   ▼
构造池：按设备名精确匹配        src/inner/device_pool.rs:65-86
   │  input_register = 各描述的零状态
   ▼
reset()：每设备一个 tokio 任务  src/inner/device_pool.rs:134-143, 341-353
   │  每 10 ms 轮询 get_state()
   ▼
input_register 增量合并         src/inner/device_pool.rs:437-467
   │
   ▼
fetch() / fetch_nowait()        src/inner/device_pool.rs:160-187, 208-258
   │
   ▼
Python dict                     src/wrapper/device_pool_wrapper.rs:43-83
```

## 轮询而不是事件驱动

Rust 侧没有把 evdev 的读端挂到 epoll 或回调上，而是把设备设为非阻塞（`packages/fly_stick/src/inner/joystick.rs:51`），由监控循环每 10 ms 调一次`fetch_events()` （`packages/fly_stick/src/inner/joystick.rs:113`，循环节拍在`packages/fly_stick/src/inner/device_pool.rs:470`）。这意味着空转时每个设备每秒约产生一百次读取系统调用，输入延迟的下限也是这个轮询周期。

## 状态归属

设备状态有两层：`get_state()` 返回的只是本次读取涉及的 code （`packages/fly_stick/src/inner/joystick.rs:108-161`）；池里的 `input_register`是跨轮次保留的持久快照，收到事件时只覆盖命中的键（`packages/fly_stick/src/inner/device_pool.rs:442-467`）。交给 Python 的`JoystickState` 是 Rust 侧 clone 出来的副本（`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:51-53,74-78`），Python 修改它不会回写寄存器。别名读取只是在投影时换键（`packages/fly_stick/src/utils.rs:207-222`），不改变寄存器内容。

evdev 只在两处被直接使用：单设备读写的 `inner/joystick.rs` 与枚举设备的`utils.rs:240-253`；池通过 `Joystick` 间接使用设备，不自己碰 evdev。

## 与仓库其它部分的接口

设备描述 TOML 存放在 `packages/fly_stick/devices/`，示例脚本在 `packages/fly_stick/examples/`，对外接口见 [接口参考](/dev/components/fly_stick/api)。把本包接进飞行器模型的完整用法见 [模型接入](/guide/components/fly_stick/06-model-integration)。

## 继续阅读

- 设备监控循环、去抖与错误映射：[实现细节](/dev/components/fly_stick/02-implementation)
- TOML 到 `DeviceDescription` 的契约：[设备描述契约](/dev/components/fly_stick/03-device-description-contract)
- 修改实现与同步存根：[扩展与维护](/dev/components/fly_stick/04-extending)
- 公开对象与使用边界：[接口参考](/dev/components/fly_stick/api)
