# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`fly_stick` is a **Linux-only** Python extension built with Rust and PyO3. It reads game-controller input via the Linux `evdev` subsystem and exposes `PyJoystick`, `PyDevicePool`, and descriptor types to Python. The Rust crate is built as a `cdylib` and PyO3 is configured with `abi3-py39`, so a single manylinux wheel covers CPython 3.9+ on Linux x86_64.

## Build & development commands

All commands assume the working directory is the repository root (`toolkit/fly_stick/`).

Install Python dependencies:

```bash
uv sync
```

Build and install the extension into the active virtualenv for local development:

```bash
uv run maturin develop
```

Run Rust tests:

```bash
cargo test
```

Run Python tests:

```bash
uv run pytest
```

Build a release wheel:

```bash
uv run maturin build --release
```

Format and lint Rust:

```bash
cargo fmt
cargo clippy
```

Python linting is not currently configured. Add a ruff/mypy setup only if you introduce non-trivial Python logic beyond `src/fly_stick/__init__.py`.

## Running a single test

Rust single test:

```bash
cargo test <test_name>
```

Python single test:

```bash
uv run pytest tests/test_<name>.py -v
```

## Architecture

### Extension boundary

`src/lib.rs` defines the PyO3 `_core` extension module. It is gated with `#[cfg(target_os = "linux")]` because the only backend uses `evdev`. On non-Linux builds the module symbol is absent and the crate will not produce a usable Python extension.

### Rust layers

- `src/inner/` — core logic with no direct PyO3 dependency.
  - `description.rs` — `DeviceDescription` and `DeviceItem` parsed from TOML; defines expected axes/buttons/hats and builds default `JoystickState`.
  - `joystick.rs` — opens a single `/dev/input/event*` device via `evdev::Device`, normalizes ABS axis values, and reads events into `JoystickState`.
  - `device_pool.rs` — manages multiple logical devices, spawns async Tokio tasks per device to update a shared input register, supports `fetch()` (await change/timeout) and `fetch_nowait()`, plus debouncing and trigger/hold button modes.
- `src/utils.rs` — cross-cutting types exposed to Python: `JoystickInfo`, `JoystickState`, `DeviceButtonMode`, plus `fetch_connected_joysticks()` wrapping `evdev::enumerate()`.
- `src/wrapper/` — thin PyO3 wrappers around the inner types.
  - `joystick_wrapper.rs` — `PyJoystick`.
  - `device_pool_wrapper.rs` — `PyDevicePool`; its async methods are exposed as Rust `async fn` and can be awaited from Python asyncio.

### Python side

- `src/fly_stick/__init__.py` re-exports all public symbols from `fly_stick._core`.
- `src/fly_stick/_core.pyi` provides the type stubs.

### Concurrency model

`DevicePool` uses Tokio via `pyo3-async-runtimes`. Each monitored device gets a Tokio task that reads `evdev` events and updates a shared input register protected by `std::sync::Mutex`. `stop()` or `reset()` sends a shutdown signal through an `mpsc` channel to abort those tasks.

### Device descriptions

Devices are configured with TOML files under `devices/`. `DeviceDescription.from_toml(path)` is exposed to Python and expects the file format shown in `README.md`. Example files and button-mapping diagrams live in `examples/` and `figures/`.

### Platform constraints

- Only Linux is supported.
- Do not add Windows/macOS-specific API calls without also adding a corresponding platform backend; `evdev` itself is Linux-only.
- When modifying `Cargo.toml`, keep `evdev` under a Linux-only dependency section or gate usages with `#[cfg(target_os = "linux")]`.
