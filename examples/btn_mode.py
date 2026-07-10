import asyncio

from rich.pretty import pprint

from fly_stick import DeviceButtonMode, DeviceDescription, PyDevicePool


async def main():
    """
    Demonstrate how to use the DevicePool class to monitor multiple fly_stick devices.
    """
    # Create a device pool with trigger button mode enabled
    logical_name = "ta320"
    device_desc = DeviceDescription.from_toml("devices/Thrustmaster/ta320.toml")
    device_pool = PyDevicePool(
        device_descs={
            logical_name: device_desc,
        },
        debounce_seconds=0.1,
        btn_mode=DeviceButtonMode.trigger(),
    )
    print(f"Using profile: {logical_name} ({device_desc.device_name})")

    # Start monitoring devices
    await device_pool.reset()

    try:
        while True:
            # Fetch current input from all devices
            inputs = await device_pool.fetch()
            input_ = inputs.get(logical_name)
            if not input_:
                print(f"No inputs found for device profile: {logical_name}")
            else:
                pprint(input_.get_alias_buttons(desc=device_desc))
            await asyncio.sleep(0.01)  # Adjust the sleep time as needed
    except KeyboardInterrupt:
        print("Stopping device monitoring...")
        await device_pool.stop()


if __name__ == "__main__":
    asyncio.run(main())
