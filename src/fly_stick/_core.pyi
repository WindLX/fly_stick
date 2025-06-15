from typing import Optional

class JoystickState:
    """Complete joystick state containing axes, buttons, and hats"""

    axes: dict[int, float]
    buttons: dict[int, int]
    hats: dict[int, int]

    def __init__(self) -> None: ...
    def __eq__(self, value: object) -> bool: ...
    def to_dict(self) -> dict[str, dict[int, float | int]]: ...

class JoystickInfo:
    """Joystick information containing path and name"""

    path: str
    name: str

    def __init__(self, path: str, name: str) -> None: ...

def fetch_connected_joysticks() -> list[JoystickInfo]:
    """
    Fetch connected game controller devices
    This function retrieves a list of currently connected game controller devices.
    Each device is represented as a tuple containing the device path and device name.

    Returns:
        Device list, each element is a tuple of (device_path, device_name)
    """
    ...

class DeviceItem:
    """Device item with code and optional alias"""

    code: int
    alias: Optional[str]

    def __init__(self, code: int, alias: Optional[str] = None) -> None: ...

class DeviceDescription:
    """Device description containing metadata and input items.

    This class represents a complete description of a joystick/gamepad device,
    including its metadata (name, author, creation date, description) and
    all available input elements (axes, buttons, and hats/POV switches).

    Attributes:
        device_name (str): Name of the device
        author (Optional[str]): Author or creator of the device description
        created (Optional[str]): Creation date/timestamp of the description
        description (Optional[str]): Detailed description of the device
        axes (list[DeviceItem]): List of analog axes available on the device
        buttons (list[DeviceItem]): List of buttons available on the device
        hats (list[DeviceItem]): List of hat/POV switches available on the device

    Example:
        >>> device = DeviceDescription(
        ...     device_name="Xbox Controller",
        ...     author="Microsoft",
        ...     description="Standard Xbox gamepad",
        ...     axes=[...],
        ...     buttons=[...],
        ...     hats=[...]
        ... )
        >>> state = device.build_state()
    """

    """Device description containing metadata and input items"""

    device_name: str
    author: Optional[str]
    created: Optional[str]
    description: Optional[str]
    axes: list[DeviceItem]
    buttons: list[DeviceItem]
    hats: list[DeviceItem]

    def __init__(
        self,
        device_name: Optional[str] = None,
        author: Optional[str] = None,
        created: Optional[str] = None,
        description: Optional[str] = None,
        axes: Optional[list[DeviceItem]] = None,
        buttons: Optional[list[DeviceItem]] = None,
        hats: Optional[list[DeviceItem]] = None,
    ) -> None: ...
    @staticmethod
    def from_toml(toml_file: str) -> DeviceDescription:
        """Create DeviceDescription from TOML file"""
        ...

    def build_state(self) -> JoystickState:
        """Build state dictionary from device description"""
        ...

class PyJoystick:
    """Joystick class for managing a single joystick device.

    This class provides methods to initialize, read state, and manage a single joystick device.
    It handles the underlying device interactions and provides an easy-to-use interface for
    fetching joystick states.

    Args:
        device_path: Path to the joystick device file
        debounce_seconds: Time interval in seconds to debounce input events (default: 0.1)

    Methods:
        get_state(): Fetch current state of the joystick, including axes, buttons, and hats
        stop(): Stop the joystick and clean up resources

    Example:
        >>> joystick = PyJoystick('/dev/input/js0')
        >>> state = joystick.get_state()
        >>> print(state.axes, state.buttons, state.hats)
    """

    def __init__(self, device_path: str) -> None: ...
    def get_state(self) -> JoystickState: ...

class PyDevicePool:
    """
    Device pool for managing joystick states and device connections.

    PyDevicePool provides an asynchronous interface for managing multiple joystick devices,
    handling state fetching, and coordinating device interactions with built-in debouncing.

    Args:
        device_desc_files: List of file paths containing device descriptions/configurations
        debounce_seconds: Time interval in seconds to debounce input events (default: 0.1)

    Methods:
        reset(): Asynchronously reset all devices in the pool to their initial state
        fetch_nowait(): Non-blocking fetch of current joystick state, returns immediately
        fetch(timeout_seconds=None): Asynchronously fetch joystick state with optional timeout
        stop(): Gracefully stop the device pool and clean up resources

    Example:
        >>> pool = PyDevicePool(['config1.toml', 'config2.toml'], debounce_seconds=0.05)
        >>> await pool.reset()
        >>> state = await pool.fetch(timeout_seconds=1.0)
        >>> await pool.stop()

    Note:
        This class manages the lifecycle of joystick devices and should be properly
        stopped using the stop() method to ensure clean resource cleanup.
    """

    """Device pool for managing joystick states"""

    def __init__(
        self, device_desc_files: list[str], debounce_seconds: float = 0.1
    ) -> None: ...
    async def reset(self) -> None:
        """Reset all devices in the pool to their initial state.
        This method initializes all devices based on the provided device description files.
        It sets up the necessary event loops and prepares the devices for state fetching.
        This method should be called before any fetch operations to ensure devices are ready.
        Raises:
            RuntimeError: If the device pool is already running or has not been properly initialized.
        """
        ...

    def fetch_nowait(self) -> dict[str, JoystickState]:
        """Fetch current joystick state without blocking.
        This method retrieves the current state of all joysticks in the pool without waiting.
        It returns immediately with the latest state information.
        Raises:
            RuntimeError: If the device pool has not been initialized or is not running.
        Returns:
            dict[str, JoystickState]: A dictionary mapping joystick names to their current state.
        Note:
            This method is non-blocking and returns the most recent state available.
            It is useful for scenarios where you need to check joystick states without waiting.
        Example:
            >>> states = device_pool.fetch_nowait()
            >>> for name, state in states.items():
            ...     print(f"{name}: {state.axes}, {state.buttons}, {state.hats}")
        """
        ...

    async def fetch(
        self, timeout_seconds: Optional[float] = None
    ) -> dict[str, JoystickState]:
        """Fetch current joystick state with optional timeout.
        This method retrieves the current state of all joysticks in the pool, waiting for
        the specified timeout if provided. If no timeout is specified, it will wait indefinitely
        until the state is available.
        Raises:
            RuntimeError: If the device pool has not been initialized or is not running.
            TimeoutError: If the operation times out before fetching the state.

        Args:
            timeout_seconds (Optional[float], optional): Timeout in seconds for the fetch operation.
                If None, it will wait indefinitely. Defaults to None.

        Returns:
            dict[str, JoystickState]: A dictionary mapping joystick names to their current state.
        Note:
            This method is asynchronous and will block until the state is available or the timeout
            is reached. It is useful for scenarios where you need to wait for joystick states to be
            updated before proceeding.
        Example:
            >>> try:
            ...     states = await device_pool.fetch(timeout_seconds=2.0)
            ...     for name, state in states.items():
            ...         print(f"{name}: {state.axes}, {state.buttons}, {state.hats}")
        except TimeoutError:
            print("Fetching joystick state timed out. No state available.")
        Raises:
            RuntimeError: If the device pool has not been initialized or is not running.
            TimeoutError: If the operation times out before fetching the state.
        """

    async def stop(self) -> None:
        """Stop the device pool and clean up resources.
        This method gracefully stops the device pool, ensuring all resources are cleaned up
        and no further state fetching can occur. It should be called when the device pool is no
        longer needed to prevent resource leaks.
        Raises:
            RuntimeError: If the device pool is not running or has already been stopped.
        Note:
            Always call this method when done with the device pool to ensure proper cleanup.
        Example:
            >>> await device_pool.stop()
            >>> print("Device pool stopped successfully.")
        """
        ...
