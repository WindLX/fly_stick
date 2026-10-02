# 更新记录

## 0.1.2

- 修复设备池异步读取的竞态：前一次 `fetch()` 对应的 Python Future 尚未结束时，新的 `fetch()` 继续被拒绝，避免 Rust 等待槽释放后两个未完成请求互相覆盖。`fetch_nowait()` 仍使用独立读取进度。
- 设备池的 `fetch()` 与 `fetch_nowait()` 返回各逻辑设备的完整状态快照；`PyJoystick.get_state()` 仍返回单次读取的事件差分。`Hold` 保持按钮物理状态，`Trigger` 为每个读取入口单独交付按下脉冲。
- 设备池构造参数名统一为 `button_mode`，可读写属性也为 `button_mode`。将 `PyDevicePool(..., btn_mode=...)` 改为 `PyDevicePool(..., button_mode=...)`；旧关键字不再接受。默认模式仍为 `DeviceButtonMode.hold()`。
