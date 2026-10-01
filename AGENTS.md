# fly_stick

Linux evdev 操纵杆输入库，Rust/PyO3 提供设备 API，Python 提供封装和 TOML 描述。

## 事实源与入口

- **约定**：命令以 `just --list` 为准；安装 `just setup`，格式/检查 `just fmt` / `just check`，测试 `just test-rust` / `just test-python` / `just test`，交付 `just pre-commit`。
- **约定**：wheel 构建使用 `just build`；本项目仅支持 Linux 输入后端。
- `src/`、`src/fly_stick/` —— 设备访问、PyO3 接口与用户封装

## 本目录特有边界

- **必须**：evdev 访问与设备生命周期由 Rust 管理；Python 不轮询或复制底层事件状态机。
- **必须**：PyO3 异步对象可显式 stop/close，任务退出不泄漏 fd 或 Tokio task。
- **必须**：TOML alias、axis/button/hat code 变化有解析与映射回归。
- **必须**：平台测试写明 Linux/设备权限前提；无硬件单测使用 mock/fake event。
- **必须**：PyO3 API 变化同步 Python 导出、类型声明、examples 和 README。
- **禁止**：手改 maturin 生成物或 vendored/锁定依赖。
