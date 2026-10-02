"""Public constructor and lifecycle contract tests without joystick hardware."""

from __future__ import annotations

import asyncio

import pytest

from fly_stick import (
    DeviceButtonMode,
    DeviceDescription,
    DeviceItem,
    JoystickInfo,
    PyDevicePool,
)


def test_public_constructors_and_description_defaults() -> None:
    assert DeviceItem(4).alias is None
    description = DeviceDescription()
    assert description.device_name == "Unknown Device"
    assert description.device_path is None
    assert description.axes == []
    assert DeviceDescription(device_path="/dev/input/event4").device_path == (
        "/dev/input/event4"
    )
    assert JoystickInfo("/dev/input/event4", "Controller").name == "Controller"


def test_description_rejects_duplicate_codes_and_effective_aliases() -> None:
    with pytest.raises(ValueError, match="duplicate axes code"):
        DeviceDescription(axes=[DeviceItem(1), DeviceItem(1, "roll")])
    with pytest.raises(ValueError, match="duplicate axes alias key"):
        DeviceDescription(axes=[DeviceItem(1), DeviceItem(2, "1")])
    with pytest.raises(ValueError, match="alias must not be empty"):
        DeviceDescription(buttons=[DeviceItem(1, " ")])


def test_pool_uses_button_mode_name_without_old_alias() -> None:
    pool = PyDevicePool({}, button_mode=DeviceButtonMode.trigger())
    assert pool.button_mode == DeviceButtonMode.trigger()
    with pytest.raises(TypeError):
        PyDevicePool({}, btn_mode=DeviceButtonMode.hold())  # type: ignore[call-arg]


def test_pool_read_errors_and_timeout_types() -> None:
    pool = PyDevicePool({})

    async def run() -> None:
        with pytest.raises(RuntimeError):
            pool.fetch_nowait()
        with pytest.raises(RuntimeError):
            await pool.fetch(timeout_seconds=0.0)
        with pytest.raises(ValueError):
            await pool.fetch(timeout_seconds=-1.0)
        with pytest.raises(LookupError):
            await PyDevicePool(
                {"missing": DeviceDescription(device_name="No such controller")}
            ).reset()

    asyncio.run(run())


def test_fetch_can_be_cancelled_and_stop_wakes_it() -> None:
    pool = PyDevicePool({})

    async def run() -> None:
        assert await pool.reset() == {}
        waiting = asyncio.ensure_future(pool.fetch())
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting

        with pytest.raises(TimeoutError):
            await pool.fetch(timeout_seconds=0.0)

        waiting = asyncio.ensure_future(pool.fetch())
        await pool.stop()
        with pytest.raises(RuntimeError):
            await waiting

    asyncio.run(run())


def test_second_parallel_fetch_is_rejected_and_nowait_is_independent() -> None:
    pool = PyDevicePool({})

    async def run() -> None:
        assert await pool.reset() == {}
        waiting = asyncio.ensure_future(pool.fetch())
        with pytest.raises(RuntimeError, match="another fetch"):
            pool.fetch(timeout_seconds=0.0)
        assert pool.fetch_nowait() == {}
        await pool.stop()
        with pytest.raises(RuntimeError):
            await waiting

    asyncio.run(run())
