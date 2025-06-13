# Example: Asynchronous Device Monitoring with fly_stick
# This example demonstrates how to asynchronously monitor multiple fly_stick devices
# found any input devices
# and print their state changes. It uses asyncio for non-blocking I/O operations.
# and handles device monitoring in a way that allows for graceful shutdown on user interruption.

import asyncio
import fly_stick


async def monitor_device(device_path: str, device_name: str) -> None:
    """
    Asynchronously monitor input from a single device.

    Args:
        device_path: Path to the device
        device_name: Human-readable name of the device

    Raises:
        IOError: If device cannot be accessed
        asyncio.CancelledError: If monitoring is cancelled
    """
    try:
        joystick = fly_stick.PyJoystick(device_path)
        print(f"Started monitoring {device_name}")

        while True:
            # Get device state
            axes, buttons, hats = joystick.get_state()

            # Only print status when there are changes
            if axes or buttons or hats:
                print(f"[{device_name}] axes: {axes}, buttons: {buttons}, hats: {hats}")

            # Use async sleep
            await asyncio.sleep(0.01)

    except IOError as e:
        print(f"Failed to monitor {device_name}: {e}")
    except asyncio.CancelledError:
        print(f"Stopped monitoring {device_name}")
        raise


async def main() -> None:
    """
    Demonstrate how to asynchronously monitor multiple fly_stick devices.

    This function enumerates all available input devices and creates monitoring
    tasks for each device. The monitoring continues until interrupted by Ctrl+C.
    """
    # Enumerate all available input devices
    devices = fly_stick.fetch_connected_devices()

    if not devices:
        print("No input devices found!")
        return

    print(f"Found {len(devices)} devices:")
    for device_path, device_name in devices:
        print(f"  {device_name} at {device_path}")

    # Create list of monitoring tasks
    tasks: list[asyncio.Task] = []
    for device_path, device_name in devices:
        task = asyncio.create_task(monitor_device(device_path, device_name))
        tasks.append(task)

    print(f"\nStarting monitoring {len(tasks)} devices (Press Ctrl+C to stop)...")

    try:
        # Wait for all tasks to complete (will run indefinitely)
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("\nStopping device monitoring...")
        # Cancel all tasks
        for task in tasks:
            task.cancel()
        # Wait for task cleanup to complete
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
