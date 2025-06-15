from typing import Optional
import asyncio

import fly_stick


async def monitor_device(
    device_path: str, device_name: str, channel: Optional[asyncio.Queue] = None
) -> None:
    """
    Asynchronously monitor input from a single device.

    Args:
        device_path: Path to the device
        device_name: Name of the device
        channel: Optional queue for sending axis data
    """
    try:
        joystick = fly_stick.PyJoystick(device_path)
        print(f"Started monitoring {device_name}")

        while True:
            # Get device state
            state = joystick.get_state()
            axes, buttons, hats = state.axes, state.buttons, state.hats

            # If this is the target device and has channel, send specific axis data
            if device_name == "Thrustmaster T.A320 Copilot" and channel and axes:
                # Extract axis 0,1,5 data
                axis_data: dict[str, float] = {}
                if 0 in axes:
                    axis_data["aileron"] = axes[0]
                if 1 in axes:
                    axis_data["elevator"] = axes[1]

                if axis_data:
                    await channel.put(axis_data)

            if device_name == "Thrustmaster TWCS Throttle" and channel and axes:
                # Extract axis 2 data
                axis_data: dict[str, float] = {}
                if 2 in axes:
                    axis_data["throttle"] = axes[2]
                if 5 in axes:
                    axis_data["rudder"] = axes[5]

                if axis_data:
                    await channel.put(axis_data)

            # Use async sleep
            await asyncio.sleep(0.01)

    except IOError as e:
        print(f"Failed to monitor {device_name}: {e}")
    except asyncio.CancelledError:
        print(f"Stopped monitoring {device_name}")
        raise


async def data_consumer(channel: asyncio.Queue) -> None:
    """
    Consume data from channel and send via TCP.

    Args:
        channel: Queue containing axis data
    """
    # Save complete data from previous moment
    last_data: dict[str, float] = {
        "aileron": 0.0,
        "elevator": 0.0,
        "rudder": 0.0,
        "throttle": 0.0,
    }

    while True:
        try:
            # Non-blocking get new data
            try:
                new_data: dict[str, float] = channel.get_nowait()
                # Update corresponding axis data
                last_data.update(new_data)

            except asyncio.QueueEmpty:
                # Continue using previous data when no new data available
                pass

            # Output complete 4-axis data
            print(f"Complete axis data: {last_data}")

            # Fixed 0.01s polling frequency
            await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            break


async def main() -> None:
    """
    Demonstrate how to asynchronously monitor multiple fly_stick devices and send TCP data.
    """

    # Create channel for data transmission
    channel: asyncio.Queue = asyncio.Queue()

    # Enumerate all available input devices
    devices = fly_stick.fetch_connected_joysticks()

    if not devices:
        print("No input devices found!")
        return

    print(f"Found {len(devices)} devices:")
    for device in devices:
        device_path, device_name = device.path, device.name
        print(f"  {device_name} at {device_path}")

    # Create monitoring task list
    tasks: list[asyncio.Task] = []
    for device in devices:
        device_path, device_name = device.path, device.name
        if device_name == "Thrustmaster T.A320 Copilot":
            task = asyncio.create_task(
                monitor_device(device_path, device_name, channel)
            )
        elif device_name == "Thrustmaster TWCS Throttle":
            task = asyncio.create_task(
                monitor_device(device_path, device_name, channel)
            )
        else:
            raise ValueError(f"Unsupported device: {device_name}")
        tasks.append(task)

    # Add data consumer task
    consumer_task = asyncio.create_task(data_consumer(channel))
    tasks.append(consumer_task)

    print(f"\nStarting monitoring {len(tasks)-1} devices (Press Ctrl+C to stop)...")

    try:
        # Wait for all tasks to complete (will actually run indefinitely)
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
