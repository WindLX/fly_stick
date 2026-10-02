# fly_stick 实现细节

本章说明池的监控循环、去抖、别名映射、寄存器共享、`reset()` 与 `stop()` 的实际行为，以及失败路径。路径相对仓库根，同一文件重复引用只写文件名与行号。

## 构造与设备匹配

`PyDevicePool(...)` 直接构造 Rust 结构，本身不返回错误（`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:23-32`）。`DevicePool::new` 构造时即枚举设备（`packages/fly_stick/src/inner/device_pool.rs:65`），按 `info.name == desc.device_name` 精确比较（`:73`），每个逻辑名取第一个命中的物理设备并从候选列表移除（`:82-85`），同一物理设备因此不会被两个逻辑名重复绑定；没有命中时只写日志并跳过（`:76-79`），该逻辑名不进入 `devices`。初始寄存器取自 `desc.build_state()` （`:88-91`），`running` 初值 `false` （`:104`）。

## 监控循环

`reset()` 最终调用 `start_monitoring()` （同文件 `:315-364`）：置 `running = true` （`:321`），建容量为 1 的关停通道（`:323`），为 `devices` 每个条目派生一个任务（`:341-353`），把设备路径、共享寄存器与去抖时长复制进去；supervisor 只等关停信号，收到后 `abort` 全部设备任务（`:355-363`）。

`monitor_device` （`:413-474`）每轮五步：`Joystick::new(device_path)` 打开设备，失败就 `warn!` 后返回（`:421-427`）；`while *running` （`:431`）；调 `get_state()` 且只处理 `Ok` （`:432`）；把命中的轴、按钮、帽写进 `input_register` 的对应逻辑名（`:442-467`）；`sleep(10ms)` （`:470`）。写入侧只覆盖设备声明过的 code（`:445` 轴、`:453` 按钮、`:462` 帽）；轴更新不看去抖（`:444-448`），按钮与帽要过那道门（`:451-466`）。

一帧事件怎么变成数值由 `get_state()` （`packages/fly_stick/src/inner/joystick.rs:108-161`）决定：

- 轴归一化 `(value - min) / (max - min) * 2.0 - 1.0` （`:128-129`），min/max 由构造时的 `get_absinfo()` 记下（`:58-69`）。
- 帽开关取原始 value 的符号，得到 -1、0 或 1（`:133-139`）。
- 按键 `value == 1` 记 1，其他值记 0（`:119-123`）；evdev 自动重复（value 为 2）也记 0。
- 只记录声明过的 code（按键 `:118`，轴与帽 `:130,132`），返回的 map 只含本次读取涉及的 code（`:109-111,156-160`）。

## 去抖

`should_update_input` （`packages/fly_stick/src/inner/device_pool.rs:490-505`）以设备名与 code 为键记下上次更新时刻：距上次不足 `debounce_time` 就返回 false（`:497-501`），否则刷新时间戳并返回 true（`:503`）。按钮与帽共用同一张 `HashMap<u16, Instant>` （`:439-440,451-466`），不做命名空间区分；首次出现的 code 没有历史时间戳，直接放行（`:497`）。去抖时长在派生任务时被复制（`:329`），且只有 getter 没有 setter （`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:94-101`），运行中无法修改。按键模式相反：有 setter（同文件 `:112-120`），每次 fetch 时读字段（`device_pool.rs:177,237`），运行中改模式立即生效。

## 别名映射

`get_alias_axes`、`get_alias_buttons`、`get_alias_hats` 与 `to_alias_dict()` （`packages/fly_stick/src/utils.rs:140-202`）都走 `find_by_alias` （`:207-222`）：只有 `data.get(&item.code)` 命中才产出条目（`:211,216`），所以结果只含本次读取涉及的键；`alias` 为 `Some` 时用别名字符串做键（`:210-213`），为 `None` 时用 `item.code.to_string()` （`:214-218`）；同一列表内别名重复时后插入的覆盖先插入的（`:212`）。`to_dict()` （`:86-111`）不做别名替换，键始终是整数 code。

## 两个 fetch API 与 `last_input_register`

池里有 `input_register` （监控任务写的当前值）与 `last_input_register` （上次交给调用方的值）两份寄存器（`device_pool.rs:32-33`）。

`fetch_nowait()` （`:160-187`）：`running == false` 时返回错误字符串 `"Device monitoring is not running. Call reset() first."` （`:162-164`）；克隆当前寄存器（`:166-169`）；无条件把 last 覆盖成当前值（`:172-174`）；Trigger 模式再清空按键与帽（`:176-180`，实现见 `:292-302`）；返回克隆。

`fetch()` （`:208-258`）：`running == false` 时返回 `Ok(input_register.clone())` （`:215-219`），不报错；比较当前与上次（`:231`），不等就更新 last（`:233-235`）、Trigger 清按键帽（`:237-245`）后返回；超时返回 `"Fetch operation timed out"` （`:250-253`）；都不满足就 `sleep(10ms)` 继续循环（`:256`）。

共享同一份 last 的后果：`fetch_nowait()` 每次都把 last 推到最新，紧随其后的 `await fetch()` 必须等到下一次变化才会返回；`fetch()` 刚消费掉的变化也不会在 `fetch_nowait()` 里重复出现。两者交替使用时，变化会被先到的调用吃掉。Trigger 的清零发生在返回值构造之前（`:176-180,237-245`），语义是读到按下的同一帧就复位按键与帽；Hold 不做处理（`:182-184,242-244`），寄存器保留按下值直到设备送来释放事件。

## `reset()` 与 `stop()` 的实际行为

`reset()` （`device_pool.rs:134-143`）依次做：`stop_monitoring()` （`:376-387`）置 `running = false` 并触发 `shutdown_tx`，supervisor `abort` 设备任务；`reset_input_register()` （`:271-280`）按 `build_state()` 逐个逻辑名覆盖写入寄存器（不先清空），随后把 last 设成同一份；清空 `last_button_time` （`:137-140`）；`start_monitoring()` 重新派生任务，任务里才重新 `Joystick::new`。`devices` 自构造后不再更新（`:100` 后无写入点），`reset()` 只重新打开原路径，热插拔新设备与未匹配的逻辑名都不会补上。

`stop()` （`:524-526`）只调 `stop_monitoring()`，不清寄存器、不改 `devices`，池也没有 `close()` （`packages/fly_stick/src/wrapper/device_pool_wrapper.rs` 全文 130 行无该定义）。析构同样不清理：`Drop for DevicePool` （`:529-537`）只派生一个空 async 块，注释说明此时已无法调用 `self.stop()`；真正让任务停下的是 `shutdown_tx` 随结构体一起被丢弃，使 `shutdown_rx.recv()` 返回 `None`，supervisor 于是 `abort` 全部任务（`:355-363`）。这条路径不经过 `stop_monitoring()`，`running` 不会被置回 `false`。

## 错误到 Python 异常的映射

| 触发条件 | Rust 位置（前缀 `packages/fly_stick/`） | 异常 |
| --- | --- | --- |
| TOML 文件读不到 | `src/inner/description.rs:180-181` | `OSError` |
| TOML 语法或类型错误 | `src/inner/description.rs:182-183` | `ValueError` |
| 按键模式字符串非法 | `src/utils.rs:275-283` | `ValueError` |
| 打开或读取设备失败 | `src/wrapper/joystick_wrapper.rs:13-16,18-26` | `OSError` |
| 未运行就 `fetch_nowait()` | `src/wrapper/device_pool_wrapper.rs:56` | `RuntimeError` |
| `fetch()` 超时 | `src/wrapper/device_pool_wrapper.rs:80` | `RuntimeError` |

`PyIOError` 是 Python 3 里 `OSError` 的别名，所以表里两处 I/O 失败都落到 `OSError`；字符串型错误由边界层包成 `PyRuntimeError` （`device_pool_wrapper.rs:56,80`）。`fetch()` 在池停止时不抛异常（`device_pool.rs:215-219`），只有 `fetch_nowait()` 抛；这一点与存根的措辞不同，见 [接口参考](/dev/components/fly_stick/api)。

## 只写日志的失败路径

三条失败链只产生 Rust 日志，不产生 Python 异常：

1. 构造时设备名匹配不上：`warn!("Device '{}' not found", ...)` 后跳过（`packages/fly_stick/src/inner/device_pool.rs:76-79`）。该逻辑名不在 `devices` 里，`fetch()` 返回的 dict 也就没有这个键。
2. 监控任务打开设备失败：`warn!("Failed to create joystick for ...")` 后任务返回（`:421-427`）。逻辑名仍在 `devices` 与寄存器中，值停在 `build_state()` 的零状态；寄存器永不变化，`fetch_nowait()` 一直返回零值，带超时的 `fetch()` 每次等到超时，不设超时的 `fetch()` 不会返回。
3. 运行中读设备失败：`get_state()` 的 `Err` 被 `if let Ok(...)` 丢弃（`:432`），循环按 10 ms 重试；设备被拔掉后池不会报错。

`pyo3_log::init()` 在模块初始化时安装转发器（`packages/fly_stick/src/lib.rs:10`，依赖见 `packages/fly_stick/Cargo.toml:30`），Rust 的 `log` 记录进入 Python 的 `logging`。要区分 "设备没有输入"与"设备根本没打开"，调用方需自行检查 `pool.devices` 的键集合（`packages/fly_stick/src/wrapper/device_pool_wrapper.rs:122-129`）。
