import asyncio

from rich.pretty import pprint
from fly_stick import PyDevicePool, DeviceButtonMode


async def main():
    """
    Demonstrate how to use the DevicePool class to monitor multiple fly_stick devices.
    """
    # Create a device pool with default settings
    device_pool = PyDevicePool(
        [
            "devices/Thrustmaster/ta320.toml",
        ],
        debounce_seconds=0.1,
        btn_mode=DeviceButtonMode.trigger(),
    )
    device_desc = device_pool.device_descriptions[0]
    device_name = device_desc.device_name
    print(f"Using device: {device_name}")

    # Start monitoring devices
    await device_pool.reset()

    try:
        while True:
            # Fetch current input from all devices
            inputs = await device_pool.fetch()
            input_ = inputs.get(device_name)
            if not input_:
                print(f"No inputs found for device: {device_name}")
            else:
                pprint(input_.get_alias_buttons(desc=device_desc))
            await asyncio.sleep(0.01)  # Adjust the sleep time as needed
    except KeyboardInterrupt:
        print("Stopping device monitoring...")
        await device_pool.stop()


if __name__ == "__main__":
    asyncio.run(main())
