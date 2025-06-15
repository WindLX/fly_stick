import asyncio

from rich.pretty import pprint
from fly_stick import PyDevicePool


async def main():
    """
    Demonstrate how to use the DevicePool class to monitor multiple fly_stick devices.
    """
    # Create a device pool with default settings
    device_pool = PyDevicePool(
        [
            "devices/thrustmaster/ta320.toml",
        ],
        debounce_seconds=0.1,
    )

    # Start monitoring devices
    await device_pool.reset()

    try:
        while True:
            # Fetch current input from all devices
            inputs = device_pool.fetch_nowait()
            pprint(inputs)
            await asyncio.sleep(0.01)  # Adjust the sleep time as needed
    except KeyboardInterrupt:
        print("Stopping device monitoring...")
        await device_pool.stop()


if __name__ == "__main__":
    asyncio.run(main())
