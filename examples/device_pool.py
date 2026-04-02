import asyncio

from rich.pretty import pprint
from fly_stick import PyDevicePool, DeviceDescription


async def main():
    """
    Demonstrate how to use the DevicePool class to monitor multiple fly_stick devices.
    """
    # Create a device pool with default settings
    descs = {
        "ta320": DeviceDescription.from_toml("devices/Thrustmaster/ta320.toml"),
        "twcs": DeviceDescription.from_toml("devices/Thrustmaster/twcs.toml"),
    }

    device_pool = PyDevicePool(
        device_descs=descs,
        debounce_seconds=0.1,
    )

    # Start monitoring devices
    await device_pool.reset()

    try:
        while True:
            # Fetch current input from all devices
            inputs = device_pool.fetch_nowait()
            for device_name, state in inputs.items():
                print(f"Device: {device_name}")
                pprint(state.to_dict())
            await asyncio.sleep(0.01)  # Adjust the sleep time as needed
    except KeyboardInterrupt:
        print("Stopping device monitoring...")
        await device_pool.stop()


if __name__ == "__main__":
    asyncio.run(main())
