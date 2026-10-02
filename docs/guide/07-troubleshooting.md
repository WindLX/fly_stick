# 排障

## `reset()` 抛 `LookupError`

描述没有匹配到当前连接设备。检查 `device_name` 与系统枚举名称是否完全一致；调用 `fetch_connected_joysticks()` 查看名称和路径。没有同名设备时连接设备或选择正确 profile。

## `reset()` 抛 `ValueError`

同名设备有多个但描述未设 `device_path`，或配置重复。为每份描述指定正确路径；检查同一池内是否有多个逻辑名指向同一路径，以及分类内的重复 code/alias key。

## `reset()` 抛 `OSError`

打开某个节点失败时，池不会部分启动；此前打开的设备会全部关闭。检查 `/dev/input/event*` 权限、设备是否仍连接和路径是否有效，修正后重新调用 `reset()`。

## `fetch()` 抛 `TimeoutError`

指定时间内没有新状态变化。确认描述包含正在操作的 code，并检查设备是否可读。需要定时采样当前快照时使用 `fetch_nowait()`；它不会消费 `fetch()` 的读取进度。

## 读取抛 `OSError`

设备运行中读取失败会停止整个池并释放所有句柄。设备修复或重新连接后，显式 `await pool.reset()`。库不自动重连。

## 读取抛 `RuntimeError`

读取前需要 `await pool.reset()`；`stop()` 后必须重新 `reset()`。如果错误说明另一个 `fetch()` 正在等待，检查是否有另一个协程仍在同一池上调用 `fetch()`，或取消该协程后再读。等待中的 `fetch()` 可取消；`stop()` 会唤醒它。

## Trigger 没有按住状态

`Trigger` 交付按下脉冲；它适合一次性动作。连续控制按住期间的输入用 `Hold`。方向帽和轴始终保留最新状态，不受按钮模式清零。

## 短按能否可靠触发

设备池保存快照版本和按下计数，因此同一批次内按下后立即释放仍能产生 Trigger 脉冲；每个读取入口会将多次未观察按下合并为一个。需要逐次处理快速连按时，快照接口无法表达事件队列语义，应使用专用逐事件消费设计。

## 始终使用 `finally` 停止

`await pool.stop()` 是唯一的生命周期停止入口。它等待监视任务退出并释放设备文件句柄：

```python
pool = PyDevicePool({"stick": description})
try:
    await pool.reset()
    while True:
        state = await pool.fetch()
finally:
    await pool.stop()
```
