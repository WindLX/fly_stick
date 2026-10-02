from __future__ import annotations

import fly_stick

EXPECTED_PUBLIC_NAMES = {
    "DeviceButtonMode",
    "DeviceDescription",
    "DeviceItem",
    "JoystickInfo",
    "JoystickState",
    "PyDevicePool",
    "PyJoystick",
    "fetch_connected_joysticks",
}


def test_public_package_imports() -> None:
    """包可导入，且导出面与 `__all__` 完全一致。"""
    assert fly_stick.__name__ == "fly_stick"
    assert set(fly_stick.__all__) == EXPECTED_PUBLIC_NAMES
    for name in sorted(EXPECTED_PUBLIC_NAMES):
        assert getattr(fly_stick, name) is not None
