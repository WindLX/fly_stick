from typing import TypedDict, NamedTuple

class HatPosition(NamedTuple):
    """Hat switch position with x and y coordinates"""

    x: int
    y: int

class JoystickState(NamedTuple):
    """Complete joystick state containing axes, buttons, and hats"""

    axes: dict[int, float]
    buttons: dict[int, int]
    hats: dict[int, HatPosition]

class DeviceInfo(NamedTuple):
    """Device information containing path and name"""

    device_path: str
    device_name: str

class PyJoystick:
    """Game controller/joystick device class"""

    def __init__(self, device_path: str) -> None:
        """
        Initialize game controller device

        Args:
            device_path: Device path, e.g. "/dev/input/event0"

        Raises:
            IOError: Raised when device cannot be opened
        """
        ...

    def get_state(
        self,
    ) -> JoystickState:
        """
        Get current device state

        Returns:
            Tuple containing three dictionaries:
            - axes_dict: Axis state dictionary {axis_id: normalized_value(-1.0 to 1.0)}
            - buttons_dict: Button state dictionary {button_id: state(0 or 1)}
            - hats_dict: Hat state dictionary {hat_id: (x_value, y_value)}
        """
        ...

def fetch_connected_devices() -> list[DeviceInfo]:
    """
    Fetch connected game controller devices
    This function retrieves a list of currently connected game controller devices.
    Each device is represented as a tuple containing the device path and device name.

    Returns:
        Device list, each element is a tuple of (device_path, device_name)
    """
    ...
