use pyo3::prelude::*;
use std::collections::HashMap;

/// Joystick information containing path and name
#[derive(Debug, Clone)]
#[pyclass]
pub struct JoystickInfo {
    #[pyo3(get, set)]
    pub path: String,
    #[pyo3(get, set)]
    pub name: String,
}

#[derive(Debug, Clone)]
#[pyclass]
/// Represents input data from a joystick or game controller device.
///
/// This structure contains the current state of all input elements including
/// analog axes, buttons, and directional hats. Each input type is stored in
/// a HashMap where the key represents the hardware identifier and the value
/// represents the current state.
///
/// # Fields
///
/// * `axes` - A mapping of axis identifiers to their normalized values (-1.0 to 1.0)
/// * `buttons` - A mapping of button identifiers to their press state (0 = released, 1 = pressed)
/// * `hats` - A mapping of hat identifiers to their directional state (bitmask representing direction)
///
/// # Python Integration
///
/// This struct is exposed to Python through PyO3, allowing direct access to all fields
/// for reading and writing input state data.
pub struct JoystickState {
    #[pyo3(get, set)]
    pub axes: HashMap<u16, f32>,
    #[pyo3(get, set)]
    pub buttons: HashMap<u16, u8>,
    #[pyo3(get, set)]
    pub hats: HashMap<u16, i8>,
}

#[pymethods]
impl JoystickState {
    /// Creates a new JoystickState instance with empty input data.
    #[new]
    pub fn new() -> Self {
        JoystickState {
            axes: HashMap::new(),
            buttons: HashMap::new(),
            hats: HashMap::new(),
        }
    }

    pub fn __eq__(&self, other: &Self) -> bool {
        self == other
    }
}

// Implement PartialEq for JoystickState to enable comparison
impl PartialEq for JoystickState {
    fn eq(&self, other: &Self) -> bool {
        self.axes == other.axes && self.buttons == other.buttons && self.hats == other.hats
    }
}

/// Fetches information about connected input devices.
///
/// Returns a vector of DeviceInfo structs containing the device path and name.
/// Joystick names default to "Unknown" if they cannot be retrieved.
///
/// # Returns
/// A `Vec<DeviceInfo>` containing information about all connected devices.
#[pyfunction]
pub fn fetch_connected_joysticks() -> Vec<JoystickInfo> {
    let devices = evdev::enumerate().collect::<Vec<_>>();
    let mut device_list = Vec::new();

    for (path, device) in devices {
        let device_info = JoystickInfo {
            path: path.to_string_lossy().to_string(),
            name: device.name().unwrap_or("Unknown").to_string(),
        };
        device_list.push(device_info);
    }

    device_list
}
