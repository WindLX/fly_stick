# 扩展与维护

本章面向改动 `fly_stick` 本身的场景：改哪一层、用哪些命令验证、公开 API 变化时要同步哪些文件、没有硬件时怎么测，以及设备描述的增删流程。所有路径相对仓库根，同一文件重复引用只写文件名与行号。

## 改动落在哪一层

| 想改的东西 | 文件 |
| --- | --- |
| Python 可见的方法与属性、参数默认值、错误映射 | `packages/fly_stick/src/wrapper/*.rs` |
| 状态值对象、按键模式、别名映射 | `packages/fly_stick/src/utils.rs` |
| 设备匹配、监控任务、去抖 | `packages/fly_stick/src/inner/device_pool.rs` |
| 单设备打开与事件解析、轴归一化 | `packages/fly_stick/src/inner/joystick.rs` |
| TOML 字段与默认值 | `packages/fly_stick/src/inner/description.rs` |
| 模块导出清单 | `packages/fly_stick/src/lib.rs:12-21` |

分层关系与依赖方向见 [架构总览](/dev/components/fly_stick/01-architecture)。

## 开发与验证命令

包内命令以 `packages/fly_stick/justfile` 为准：

| 命令 | 内容 | 位置 |
| --- | --- | --- |
| `just setup` | `uv sync --group dev` + `maturin develop` | 同文件 `:13-15` |
| `just fmt` | `cargo fmt --all` + `ruff format` | 同文件 `:22-24` |
| `just check` | 格式、clippy（`-D warnings`）、ruff、mypy | 同文件 `:32-37` |
| `just test` | 依次跑下面的两个单项入口 | 同文件 `:44` |
| `just _test-rust` | `cargo test --all-features` | 同文件 `:67-68` |
| `just _test-python` | `maturin develop` + `pytest tests` | 同文件 `:74-76` |
| `just build` | `maturin build --release` | 同文件 `:51-52` |
| `just pre-commit` | `check test build` | 同文件 `:59` |

`_test-rust` 与 `_test-python` 是私有单项入口，不出现在 `just --list` 里（`packages/fly_stick/justfile:61`）。`mypy` 以严格模式检查 `src/fly_stick` 与 `tests` （`packages/fly_stick/pyproject.toml:44-47`），`ruff` 行宽 88、目标 Python 3.12（同文件 `:37-42`）。仓库根还提供聚合入口：`just check-packages`、`just test-packages` 会带上 `check-stick` 与 `test-stick` （`justfile:27,29`），后两者转到包目录执行上面的 `just check`、`just test` （`justfile:81-85`）。

改完 Rust 代码后必须重新 `maturin develop` 才能让 Python 看到新符号；`just _test-python` 与 `just setup` 都已经包含这一步。

## 公开 API 变化时的同步清单

新增或改动一个 Python 可见的对象，需要同时处理五处：

1. Rust 侧的 `#[pymethods]` （例如 `packages/fly_stick/src/utils.rs:272`）。
2. 手写存根 `packages/fly_stick/src/fly_stick/_core.pyi`：类、方法签名与 Google 风格的 docstring（`Args`/`Returns`/`Raises` 三段）。
3. `packages/fly_stick/src/fly_stick/__init__.py:7-16` 的导入与 `:18-27` 的 `__all__`。
4. `packages/fly_stick/tests/test_import.py:5-14` 的 `EXPECTED_PUBLIC_NAMES`，否则 `test_public_package_imports` （同文件 `:17-22`）会失败。
5. 重新生成接口参考，让声明与发布出去的页面保持一致。

存根同时是接口参考页的来源，增删成员后要重新生成；重生成命令与漂移检查见 `AGENTS.md`，公开对象的说明见 [接口参考](/dev/components/fly_stick/api)。

## 没有硬件时的验证

- Rust 单元测试：现有 11 个 `#[test]` 全部集中在 `packages/fly_stick/src/inner/description.rs:219-409`，覆盖默认值、`build_state()`、TOML 正常/缺字段/文件不存在/非法内容与 serde 往返。它们用 `from_toml_rust` （同文件 `:212-216`）与 `tempfile` （`packages/fly_stick/Cargo.toml:39-40`）写临时文件，不需要设备。
- Python 侧：`packages/fly_stick/tests/` 下只有 `test_import.py`，它只断言包名与 8 个导出名（`:17-22`），同样不需要设备。`fly_stick` 的导入本身会触发 `pyo3_log::init()` （`packages/fly_stick/src/lib.rs:10`），不接触 evdev。
- 设备相关的两个模块 `inner/device_pool.rs` 与 `inner/joystick.rs` 目前没有单元测试，它们的逻辑依赖真实的 `Device` 与 tokio 运行时。想在没有硬件时覆盖这类逻辑，需要在测试里自建假的设备来源或事件序列。
- 示例脚本需要真实设备与设备节点读权限。因为脚本用相对路径读 `devices/...`，运行目录必须是包目录：`cd packages/fly_stick` 后执行 `uv run python examples/device_pool.py`。枚举结果为空时 `examples/single_device.py:86-88` 打印一行提示并正常返回。

## 新增一份设备描述

1. 先在真机上读内核上报的名字：

   ```bash
   uv run python -c "import fly_stick; \
   print([(d.name, d.path) for d in fly_stick.fetch_connected_joysticks()])"
   ```

   名字来自 evdev，读取失败时是 `"Unknown"` （`packages/fly_stick/src/utils.rs:240-253`）。

2. 在 `packages/fly_stick/devices/<厂商>/<型号>.toml` 建文件，`device_name` 与上一步的输出逐字节一致——池用的是 `info.name == desc.device_name` 精确比较（`packages/fly_stick/src/inner/device_pool.rs:73`）。
3. 逐个填入 `[[axes]]`、`[[buttons]]`、`[[hats]]`，`code` 取 evdev 编号，`alias` 按需给。字段规则与现有 7 份描述的清单见 [设备描述契约](/dev/components/fly_stick/03-device-description-contract)。
4. 解析自检：

   ```bash
   uv run python -c "from fly_stick import DeviceDescription as D; \
   d = D.from_toml('devices/Thrustmaster/ta320.toml'); \
   print(d.device_name, len(d.axes), len(d.buttons), len(d.hats))"
   ```

   换成新文件的路径即可。`tests/` 与 Rust 测试都不会扫描 `devices/` 目录，这一步是唯一的自动校验入口。

5. 若该设备要与已有描述同时注册，先确认没有第二个文件写了同样的 `device_name`；同名时只会有一个被绑定。

删除一份描述前，先确认没有引用：示例脚本与模型示例都用显式路径引用 `devices/` 下的文件。删除后对应的输入项会从该设备的 `build_state()` 里消失（`packages/fly_stick/src/inner/description.rs:191-207`），不影响其他描述。

## 依赖与构建的注意点

新增 crate 依赖写进 `packages/fly_stick/Cargo.toml:17-37`，测试专用依赖写进 `:39-40`。`pyo3` 同时启用了 `extension-module` 与 `abi3-py39` （同文件 `:20-26`），后者把编译 ABI 下限压到 CPython 3.9，与 `requires-python = ">=3.12"` （`packages/fly_stick/pyproject.toml:9`）是两件事，改其中一个不必改另一个。平台门控只覆盖 `#[pymodule]` 入口（`packages/fly_stick/src/lib.rs:7-8`），新增依赖仍会在非 Linux 上参与编译。maturin 的生成物与锁定依赖不做手工修改。
