# 安装 fly_stick

`fly_stick` 是 Linux evdev 操纵杆输入的 Rust/PyO3 扩展：打开设备、维护事件状态机都在 Rust 侧，包内没有 Python 业务逻辑，`src/fly_stick/__init__.py` 只把扩展模块 `fly_stick._core` 的公开名字再导出（`packages/fly_stick/src/fly_stick/__init__.py:7-27`）。发行名是 `fly-stick`，导入名是 `fly_stick`，两者不同，安装和 `import` 时不要混用。

## 环境前提

- 操作系统为 Linux。扩展模块本身带平台门槛：`_core` 的定义外层是 `#[cfg(target_os = "linux")]` （`packages/fly_stick/src/lib.rs`）。
- Python 3.12 及以上（`packages/fly_stick/pyproject.toml:9`）。
- 从源码安装需要 Rust 工具链与 `uv`：`just setup` 的两条命令分别依赖它们（`packages/fly_stick/justfile:6-8`）。
- 当前用户对目标设备节点有读权限。设备在 `Device::open` 处打开（`packages/fly_stick/src/inner/joystick.rs`），该调用返回的 `std::io::Error` 由 PyO3 按 `ErrorKind` 映射，权限不足对应 `PermissionError` （PyO3 0.28.2 的 `src/err/impls.rs`，由 `packages/fly_stick/Cargo.toml:23-26` 引入）。
- 只有 Linux 才值得装：其他平台上 `_core` 不会被编译出来。

## 发行名与导入名

| 名字 | 值 | 依据 |
| --- | --- | --- |
| 发行名 | `fly-stick` | `packages/fly_stick/pyproject.toml:2` |
| 导入名 | `fly_stick` | `packages/fly_stick/src/fly_stick/__init__.py:7` |
| 扩展模块 | `fly_stick._core` | `packages/fly_stick/pyproject.toml:17` |
| wheel 来源目录 | `src` + 包 `fly_stick` | `packages/fly_stick/pyproject.toml:18-21` |

wheel 的 ABI 标签是 `abi3`，下限定在 CPython 3.9（`packages/fly_stick/Cargo.toml:20-26` 的 `abi3-py39` 特性）；它与安装约束 `requires-python >=3.12` 相互独立，低 ABI 下限只影响 wheel 的兼容面。

## 从 PyPI 安装

```bash
pip install fly-stick
```

发布流程只构建 Linux wheel：工作流在 `ubuntu-latest` 上跑 `x86_64` 与 `aarch64` 两个目标，并启用 `manylinux: auto` （`packages/fly_stick/.github/workflows/release.yml:12-17`、`:31-37`）；打 `v*.*.*` 标签后把 wheel 与 sdist 传到 PyPI 的 `fly-stick` 项目（`packages/fly_stick/.github/workflows/release.yml:3-6`、`:73-93`）。

安装后立即验证导出面：

```bash
python -c "import fly_stick; print(fly_stick.__all__)"
```

`__all__` 一共 8 个名字（`packages/fly_stick/src/fly_stick/__init__.py:18-27`），仓库里的 Python 测试断言它与模块实际导出一致（`packages/fly_stick/tests/test_import.py:5-22`）。

在非 Linux 上，`import fly_stick` 会失败在 `from fly_stick._core import ...` 这一行（`packages/fly_stick/src/fly_stick/__init__.py:7`），报 `ModuleNotFoundError: No module named 'fly_stick._core'`，因为该扩展只在 Linux 目标下定义（`packages/fly_stick/src/lib.rs`）。这是缺模块的导入错误，不是构建警告。

## 从源码安装

```bash
cd packages/fly_stick
just setup
```

`just setup` 依次执行 `uv sync --group dev` 与 `uv run maturin develop` （`packages/fly_stick/justfile:6-8`）：前者同步依赖并建立虚拟环境，后者把扩展编译进该环境。开发依赖组包含 `mypy>=2.0.0`、`pytest>=9.0.2`、`rich>=14.0.0`、`ruff>=0.11.0` （`packages/fly_stick/pyproject.toml:29-35`）；运行时依赖声明为 `rich>=15.0.0` 与 `toml>=0.10.2` （`packages/fly_stick/pyproject.toml:10-13`），构建后端是 `maturin>=1.0,<2.0` （`packages/fly_stick/pyproject.toml:23-27`）。wheel 用 `just build` 产出，即 `uv run maturin build --release` （`packages/fly_stick/justfile:30-31`）。

在源码树里核实：

```bash
uv run python -c "import fly_stick; print(fly_stick.__all__)"
uv run python -c "from fly_stick import fetch_connected_joysticks; \
print(len(fetch_connected_joysticks()))"
```

### 没有硬件时能验证到什么

- `just test-rust` 跑 `cargo test --all-features` （`packages/fly_stick/justfile:21-22`）。Rust 测试不碰设备：例如用 `DeviceDescription::from_toml_rust` 配合临时文件解析TOML（`packages/fly_stick/src/inner/description.rs`、`:219-224`）。
- `just test-python` 先 `uv run maturin develop` 再 `uv run pytest tests` （`packages/fly_stick/justfile:24-26`）；当前 Python 测试只检查导入与导出面（`packages/fly_stick/tests/test_import.py:17-22`）。
- 直接调用 `fetch_connected_joysticks()` 也安全：没有可读设备时它返回空列表，不抛异常（`packages/fly_stick/src/utils.rs`）。

## 在模型示例里安装

fr_gtm、fr_f16 与 fr_evtol 三个模型仓各自提供 `setup-stick`，以 fr_gtm 为例（`models/fr_gtm/justfile:23-26`）：

```bash
cd models/fr_gtm
just setup-stick
```

该 recipe 执行：

```bash
uv run --with-editable ../../packages/fly_stick \
  --with-editable ../../packages/fly_ruler_proto/bindings/python \
  python -c "import fly_stick, fly_ruler_proto_python"
```

也就是把这两个包以 editable 方式临时加入一次 `uv run` 的环境，并当场用导入语句确认可用；它不会把 `fly-stick` 写进模型仓的持久依赖。装好后按模型仓的示例入口运行，用法见[模型集成](/guide/components/fly_stick/06-model-integration)。

## 相关页面

- [枚举设备](/guide/components/fly_stick/02-enumerate-devices)
- [设备描述](/guide/components/fly_stick/03-device-description)
- [排障](/guide/components/fly_stick/07-troubleshooting)
- [API 参考](/api/fly_stick/)
