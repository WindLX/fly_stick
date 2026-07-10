class ActiveSidestickConfig:
    bind_host: str
    teensy_host: str
    command_port: int
    logic_port: int
    state_port: int
    stale_after_ms: int

    def __init__(
        self,
        bind_host: str = "0.0.0.0",
        teensy_host: str = "30.30.30.6",
        command_port: int = 5405,
        logic_port: int = 5406,
        state_port: int = 5407,
        stale_after_ms: int = 100,
    ) -> None: ...

class SidestickAxisTelemetry:
    position_rad: float
    velocity_rad_s: float
    current_a: float

class SidestickStickTelemetry:
    roll: SidestickAxisTelemetry
    pitch: SidestickAxisTelemetry

class ActiveSidestickState:
    stick_1: SidestickStickTelemetry
    stick_2: SidestickStickTelemetry
    ap_enabled: bool
    active: bool
    coupling_disconnected: bool
    connected: bool
    stale: bool

class ActiveSidestick:
    def __init__(self, config: ActiveSidestickConfig | None = None) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def fetch_nowait(self) -> ActiveSidestickState: ...
    async def fetch(
        self, timeout_seconds: float | None = None
    ) -> ActiveSidestickState: ...
    def send_aircraft_state(
        self, aoa_rad: float, elevator_rad: float, aileron_rad: float
    ) -> None: ...
    @property
    def running(self) -> bool: ...

class JoystickInfo:
    """Joystick information containing path and name"""

    path: str
    name: str

    def __init__(self, path: str, name: str) -> None: ...

class JoystickState:
    """Complete joystick state containing axes, buttons, and hats"""

    axes: dict[int, float]
    buttons: dict[int, int]
    hats: dict[int, int]

    def __init__(self) -> None: ...
    def __eq__(self, value: object) -> bool: ...
    def __repr__(self) -> str: ...
    def to_dict(self) -> dict[str, dict[int, float | int]]:
        """Convert joystick state to a dictionary representation keyed by code"""
        ...

    def to_alias_dict(
        self, desc: DeviceDescription
    ) -> dict[str, dict[str, float | int]]:
        """Convert joystick state to a dictionary representation keyed by alias"""
        ...

    def get_alias_axes(self, desc: DeviceDescription) -> dict[str, float]:
        """Get axes values keyed by alias"""
        ...

    def get_alias_buttons(self, desc: DeviceDescription) -> dict[str, int]:
        """Get buttons values keyed by alias"""
        ...

    def get_alias_hats(self, desc: DeviceDescription) -> dict[str, int]:
        """Get hats values keyed by alias"""
        ...

def fetch_connected_joysticks() -> list[JoystickInfo]:
    """
    Fetch connected game controller devices
    This function retrieves a list of currently connected game controller devices.
    Each device is represented as a tuple containing the device path and device name.

    Returns:
        Device list, each element is a tuple of (device_path, device_name)
    """
    ...

class DeviceButtonMode:
    """Represents the mode of operation for device buttons in the DevicePool.
    This enum defines how button presses are handled:
    - `Trigger`: The button press is registered only when the button is pressed down,
      then the state will be reset immediately after.
      This mode is suitable for actions that should only occur once per press, such as
      firing a shot or triggering an event.
      The button state will not remain active after the initial press.
    - `Hold`: The button press is registered continuously while the button is held down.
    ///This enum is used to configure the behavior of buttons in the DevicePool,
    allowing for different interaction styles depending on the application requirements.
    The mode can be set when creating a DevicePool instance,
    and it affects how button events are processed during input handling."""

    def __init__(self, mode: str) -> None:
        """Initialize DeviceButtonMode with a string mode, string must be one of:
        - "trigger"
        - "hold"
        """
        ...

    @staticmethod
    def trigger() -> DeviceButtonMode: ...
    @staticmethod
    def hold() -> DeviceButtonMode: ...
    def __str__(self) -> str: ...
    def __repr__(self) -> str: ...
    def __eq__(self, other: object) -> bool: ...

class DeviceItem:
    """Device item with code and optional alias"""

    code: int
    alias: str | None

    def __init__(self, code: int, alias: str | None = None) -> None: ...

class DeviceDescription:
    """Device description containing metadata and input items.

    This class represents a complete description of a joystick/gamepad device,
    including its metadata (name, author, creation date, description) and
    all available input elements (axes, buttons, and hats/POV switches).

    Attributes:
        device_name (str): Name of the device
        author (str | None): Author or creator of the device description
        created (str | None): Creation date/timestamp of the description
        description (str | None): Detailed description of the device
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
    author: str | None
    created: str | None
    description: str | None
    axes: list[DeviceItem]
    buttons: list[DeviceItem]
    hats: list[DeviceItem]

    def __init__(
        self,
        device_name: str | None = None,
        author: str | None = None,
        created: str | None = None,
        description: str | None = None,
        axes: list[DeviceItem] | None = None,
        buttons: list[DeviceItem] | None = None,
        hats: list[DeviceItem] | None = None,
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

    This class provides methods to initialize, read state,
      and manage a single joystick device.
    It handles the underlying device interactions and provides an easy-to-use interface
      for fetching joystick states.

    Args:
        device_path: Path to the joystick device file
        debounce_seconds: Time interval in seconds to debounce input events
            (default: 0.1)

    Methods:
        get_state(): Fetch current state of the joystick, including axes, buttons,
          and hats
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

    PyDevicePool asynchronously manages joystick devices, state, and debouncing.

    Args:
        device_descs: Dict of device descriptions keyed by device name.
            Each description should be an instance of DeviceDescription.
        debounce_seconds: Button debounce interval in seconds (default: 0.1).

    Methods:
        reset(): Reset all devices to their initial state.
        fetch_nowait(): Return the current joystick state without blocking.
        fetch(timeout_seconds=None): Fetch joystick state with an optional timeout.
        stop(): Gracefully stop the device pool and clean up resources

    Example:
        >>> pool = PyDevicePool({
        ...     "ta320": DeviceDescription.from_toml("devices/Thrustmaster/ta320.toml"),
        ...     "twcs": DeviceDescription.from_toml("devices/Thrustmaster/twcs.toml"),
        ... })
        >>> await pool.reset()
        >>> state = await pool.fetch(timeout_seconds=1.0)
        >>> await pool.stop()

    Note:
        This class manages the lifecycle of joystick devices and should be properly
        stopped using the stop() method to ensure clean resource cleanup.
    """

    """Device pool for managing joystick states"""

    def __init__(
        self,
        device_descs: dict[str, DeviceDescription],
        debounce_seconds: float = 0.1,
        btn_mode: DeviceButtonMode = ...,
    ) -> None: ...
    async def reset(self) -> dict[str, tuple[DeviceDescription, JoystickInfo]]:
        """Reset all devices in the pool to their initial state.
        Initializes devices from their descriptions and starts their event loops.
        Call this before fetching device state.
        Returns:
            A mapping from device names to descriptions and joystick information.
        Note:
            Await this method until all devices are initialized.
        Raises:
            RuntimeError: If the device pool cannot be initialized.
        """
        ...

    def fetch_nowait(self) -> dict[str, JoystickState]:
        """Fetch current joystick state without blocking.
        Retrieves the latest state of every joystick without waiting.
        It returns immediately with the latest state information.
        Raises:
            RuntimeError: If the device pool has not been initialized or is not running.
        Returns:
            A mapping from joystick names to their current state.
        Note:
            This method is non-blocking and returns the most recent state available.
            Useful when polling joystick states without waiting.
        Example:
            >>> states = device_pool.fetch_nowait()
            >>> for name, state in states.items():
            ...     print(f"{name}: {state.axes}, {state.buttons}, {state.hats}")
        """
        ...

    async def fetch(
        self, timeout_seconds: float | None = None
    ) -> dict[str, JoystickState]:
        """Fetch current joystick state with optional timeout.
        Waits for the current joystick state until the optional timeout expires.
        Raises:
            RuntimeError: If the device pool has not been initialized or is not running.
            TimeoutError: If the operation times out before fetching the state.

        Args:
            timeout_seconds: Timeout in seconds; `None` waits indefinitely.

        Returns:
            A mapping from joystick names to their current state.
        Note:
            Waits until state changes are available or the timeout is reached.
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
        Gracefully stops the device pool and releases its resources.
        Raises:
            RuntimeError: If the device pool is not running or has already been stopped.
        Note:
            Always call this method when the device pool is no longer needed.
        Example:
            >>> await device_pool.stop()
            >>> print("Device pool stopped successfully.")
        """
        ...

    @property
    def debounce_time(self) -> float: ...
    @property
    def devices(self) -> dict[str, tuple[DeviceDescription, JoystickInfo]]: ...
    @property
    def btn_mode(self) -> DeviceButtonMode: ...
    @btn_mode.setter
    def btn_mode(self, mode: DeviceButtonMode) -> None: ...
