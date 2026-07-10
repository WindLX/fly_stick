# fly_stick 工作指南

## 项目用途

`fly_stick` 是 Linux evdev 操纵杆输入库，Rust/PyO3 提供设备发现、异步读取和设备池，Python API 负责易用封装与 TOML 设备描述。它不支持非 Linux 输入后端。

## 工具链与验证

- 查看命令：`just --list`；安装与开发扩展：`just setup`。
- 格式化与检查：`just fmt`、`just check`。
- Rust/Python 测试：`just test-rust`、`just test-python`；完整：`just test`。
- 构建 wheel：`just build`；交付前：`just pre-commit`。

## 本项目约束

- evdev 访问和设备生命周期留在 Rust；Python 不轮询或复制底层事件状态机。
- PyO3 异步对象必须可显式 stop/close，任务退出不能泄漏 fd 或 Tokio task。
- TOML alias、axis/button/hat code 是用户配置兼容面，变化需解析与映射回归测试。
- 平台相关测试必须明确 Linux/设备权限前提；无硬件单测使用 mock/fake event。
- 修改 PyO3 公共 API 时同步 Python 导出、类型声明、examples 与 README。
- maturin 生成物和 vendored/锁定依赖不可手工改写。
- 编写 markdown 文档时，没有新段落时，不要因为行过宽而换行。
