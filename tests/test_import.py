from __future__ import annotations

import fly_stick


def test_public_package_imports() -> None:
    assert fly_stick.__name__ == "fly_stick"


def test_active_sidestick_public_types_are_constructible() -> None:
    config = fly_stick.ActiveSidestickConfig(
        bind_host="127.0.0.1",
        teensy_host="127.0.0.1",
        stale_after_ms=100,
    )
    sidestick = fly_stick.ActiveSidestick(config)

    assert config.logic_port == 5406
    assert config.state_port == 5407
    assert sidestick.running is False
