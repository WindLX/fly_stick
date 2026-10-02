set shell := ["bash", "-lc"]

# 列出全部命令。

default:
    @just --list

# 同步 dev 依赖组，再用 maturin develop 把扩展模块装进当前虚拟环境。
# 首次克隆仓库、或 Rust 侧改动之后执行一次即可。
#
# 同步依赖并安装扩展模块

setup:
    uv sync --group dev
    uv run --no-sync maturin develop

# 就地格式化 Rust 与 Python 源码：cargo fmt 与 ruff format。
# 处理 src/fly_stick、tests、examples 与 scripts。
#
# 就地格式化 Rust 与 Python 源码

fmt:
    cargo fmt --all
    uv run --no-sync ruff format src/fly_stick tests examples scripts

# 列出四个版本源的当前值并标记不匹配项，同时列出 CI 里固定的工具版本。
# 只读，不修改任何文件。
#
# 查看各版本源与工具版本

version:
    uv run --no-sync python scripts/version.py show

# 统一更新 Cargo.toml、pyproject.toml 与两个锁文件里的版本号。
# 额外参数透传给脚本，例如 --dry-run 预演、--no-locks 跳过锁文件。
#
# 设置统一的版本号

set-version VERSION *ARGS:
    uv run --no-sync python scripts/version.py set {{VERSION}} {{ARGS}}

# 静态检查：版本一致性、cargo fmt --check、cargo clippy（警告即错误）、
# ruff check、ruff format --check 与 mypy。
# 不构建扩展模块，也不需要真实设备。
#
# 跑全部静态检查

check: _check-version
    cargo fmt --all -- --check
    cargo clippy --all-targets --all-features -- -D warnings
    uv run --no-sync ruff check src/fly_stick tests examples scripts
    uv run --no-sync ruff format src/fly_stick tests examples scripts --check
    uv run --no-sync mypy src/fly_stick tests scripts

# 完整测试：先跑 Rust 单测，再重建扩展模块跑 Python 测试。
# 测试不依赖真实硬件。
#
# 跑 Rust 与 Python 测试

test: _test-rust _test-python

# 构建 release wheel，产物在 target/wheels 下。
# 发布流程也走这条命令，可用它核对很多 linux 平台标签与 abi3 产物。
#
# 构建 release wheel

build:
    uv run --no-sync maturin build --release

# 提交前把静态检查、测试与构建依次跑一遍。
# 与根仓库的 just check-stick / just test-stick 覆盖范围一致。
#
# 提交前跑检查、测试与构建

pre-commit: check test build

# ───────── 单项入口（私有，不在 just --list 里）─────────

# 校验 Cargo.toml、Cargo.lock、pyproject.toml 与 uv.lock 的版本是否一致。
# 四个版本源必须各恰好一条本地包记录，全部相同才算通过。
#
# 校验四处版本一致

_check-version:
    uv run --no-sync python scripts/version.py check

# 只跑 Rust 单测：TOML 解析、别名映射与设备描述默认值。
# pyo3 会把 libpython 链进测试可执行文件，而 uv 管理的 CPython 既不在系统库搜索路径里、
# 也需要 PYTHONHOME 才能让内嵌解释器找到标准库，所以这里把解释器与两处路径都固定下来。
#
# 只跑 Rust 单测

_test-rust:
    PYO3_PYTHON="$PWD/.venv/bin/python" \
        PYTHONHOME="$(uv run --no-sync python -c 'import sys; print(sys.base_prefix)')" \
        LD_LIBRARY_PATH="$(uv run --no-sync python -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        cargo test --no-default-features

# 重建扩展模块后只跑 Python 测试，主要是导出面冒烟。
#
# 重建扩展后只跑 Python 测试

_test-python:
    uv run --no-sync maturin develop
    uv run --no-sync pytest tests
