import asyncio

from rich.pretty import pprint

from fly_stick import DeviceDescription, PyDevicePool


async def main():
    """
    Demonstrate how to use the DevicePool class to effect multiple fly_stick devices.
    """
    # Create a device pool with a named device description map
    logical_name = "ta320"
    device_desc = DeviceDescription.from_toml("devices/Thrustmaster/ta320.toml")
    device_pool = PyDevicePool(
        device_descs={
            logical_name: device_desc,
        },
        debounce_seconds=0.1,
    )
    print(f"Using profile: {logical_name} ({device_desc.device_name})")

    # Start effecting devices
    await device_pool.reset()

    try:
        while True:
            # Fetch current input from all devices
            inputs = await device_pool.fetch()
            input_ = inputs.get(logical_name)
            if not input_:
                print(f"No inputs found for device profile: {logical_name}")
            else:
                pprint(input_.get_alias_axes(desc=device_desc))
            await asyncio.sleep(0.01)  # Adjust the sleep time as needed
    except KeyboardInterrupt:
        print("Stopping device effecting...")
        await device_pool.stop()


if __name__ == "__main__":
    asyncio.run(main())
