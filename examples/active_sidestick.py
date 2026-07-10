"""Read SidestickTeensy Active telemetry and send aircraft control-surface state."""

from __future__ import annotations

import asyncio

from fly_stick import ActiveSidestick, ActiveSidestickConfig


async def main() -> None:
    sidestick = ActiveSidestick(
        ActiveSidestickConfig(
            bind_host="0.0.0.0",
            teensy_host="30.30.30.6",
        )
    )
    await sidestick.start()
    try:
        while True:
            state = await sidestick.fetch(timeout_seconds=1.0)
            if state.stale:
                print("Active telemetry timed out")
                continue

            print(
                f"stick_1 roll={state.stick_1.roll.position_rad:.3f} rad, "
                f"pitch={state.stick_1.pitch.position_rad:.3f} rad"
            )
            # [AOA, elevator deflection, aileron deflection], all in radians.
            sidestick.send_aircraft_state(0.0, 0.0, 0.0)
    finally:
        await sidestick.stop()


if __name__ == "__main__":
    asyncio.run(main())
