# fly_stick

Linux evdev 操纵杆输入库：Rust/PyO3 提供设备 API 与 TOML 设备描述解析，Python 只做导出与类型声明。

## 事实源与入口

- **约定**：命令以 `just --list` 为准；安装 `just setup`，格式 `just fmt`，检查 `just check`，测试 `just test`，交付 `just pre-commit`。单项入口是私有 recipe `just _test-rust` / `just _test-python`。
- **约定**：wheel 构建使用 `just build`；本项目仅支持 Linux 输入后端。
- **约定**：用户与开发者文档写在本目录 `docs/` 下，写作与转发约定见「文档」一节。
- `src/`、`src/fly_stick/` —— 设备访问、PyO3 接口与 Python 导出面
- `examples/` —— 由简到繁的实时手柄示例，阅读顺序见 `examples/README.md`
- `docs/` —— 用户手册（`docs/guide/`）与开发者手册（`docs/dev/`）

## 文档

- **约定**：正本在 `docs/guide/`、`docs/dev/`；根站 `docs/{guide,dev}/components/fly_stick/` 下的同名页面只是 `<!--@include-->` 壳页，改内容改本目录，新增章节时同时建壳页并在 `docs/.vitepress/config.mts` 登记侧边栏。
- **约定**：面向使用者写安装、使用范式、示例与排障，面向开发者写架构、公开接口、扩展点与验证；中文散文，段落单行不手工折行，跨页链接用站点绝对路径，行为结论带源码位置（`packages/fly_stick/src/...:行号`）。
- **禁止**：正文写文档站结构、维护流程、门禁命令或写作规则，也不写完成状态、进度与占位内容；本目录不重复门禁脚本（链接与正文检查由根站 `check_links.ts`、`check_prose.ts` 覆盖 `docs/`）。
- **约定**：接口参考页由生成器从 `src/fly_stick/_core.pyi` 的 docstring 生成，改存根后在主仓重生成（`cd docs && just api`）；存根行号会进入页面的「实现位置」锚点，增删行要一并重生成，`cd docs && just _drift` 用于发现忘记重生成。

## 本目录特有边界

- **必须**：evdev 访问与设备生命周期由 Rust 管理；Python 不轮询或复制底层事件状态机。
- **必须**：PyO3 异步对象可显式 `stop()`，任务退出不泄漏 fd 或 Tokio task；设备池没有 `close()`，`stop()` 是唯一停止入口。
- **必须**：TOML alias、axis/button/hat code 变化有解析与映射回归。
- **必须**：平台测试写明 Linux/设备权限前提；无硬件单测使用 mock/fake event。
- **必须**：PyO3 API 变化同步 Python 导出、类型声明 `_core.pyi`、`examples/`、`README.md`，并重跑主仓 `cd docs && just api`。
- **禁止**：手改 maturin 生成物或 vendored/锁定依赖。
- **禁止**：再引入实验性 UDP 主动侧杆协议（`ActiveSidestick` 系列已删除）。
