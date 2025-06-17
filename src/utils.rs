use crate::inner::description::{DeviceDescription, DeviceItem};

use std::collections::HashMap;

use pyo3::{prelude::*, types::PyDict};

/// Joystick information containing path and name
#[derive(Debug, Clone)]
#[pyclass]
pub struct JoystickInfo {
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
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
/// * `hats` - A mapping of hat identifiers to their directional state (-1, 0, or 1)
///
/// # Python Integration
///
/// This struct is exposed to Python through PyO3, allowing direct access to all fields
/// for reading and writing input state data.
pub struct JoystickState {
    #[pyo3(get)]
    pub axes: HashMap<u16, f32>,
    #[pyo3(get)]
    pub buttons: HashMap<u16, u8>,
    #[pyo3(get)]
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

    pub fn __repr__(&self) -> String {
        format!(
            "JoystickState {{ axes: {:?}, buttons: {:?}, hats: {:?} }}",
            self.axes, self.buttons, self.hats
        )
    }

    /// Converts the JoystickState to a Python dictionary.
    /// This method creates a PyDict containing
    /// three keys: "axes", "buttons", and "hats".
    /// Each key maps to a dictionary of the respective input data.
    ///
    /// # Returns
    /// A PyObject representing the dictionary containing axes, buttons, and hats.
    /// # Errors
    /// Returns a PyErr if there is an error during dictionary creation.
    /// # Example
    /// ```python
    /// joystick_state = JoystickState()
    /// joystick_state.axes = {0: 1.0, 1: -1.0}
    /// joystick_state.buttons = {0: 1, 1: 0}
    /// joystick_state.hats = {0: 1}
    /// joystick_dict = joystick_state.to_dict()
    /// print(joystick_dict)  # {'axes': {0: 1.0, 1: -1.0}, 'buttons': {0: 1, 1: 0}, 'hats': {0: 1}}
    /// ```
    pub fn to_dict(&self, py: Python) -> PyResult<PyObject> {
        let dict = PyDict::new(py);

        // Convert axes
        let axes_dict = PyDict::new(py);
        for (code, value) in &self.axes {
            axes_dict.set_item(*code, *value)?;
        }
        dict.set_item("axes", axes_dict)?;

        // Convert buttons
        let buttons_dict = PyDict::new(py);
        for (code, value) in &self.buttons {
            buttons_dict.set_item(*code, *value)?;
        }
        dict.set_item("buttons", buttons_dict)?;

        // Convert hats
        let hats_dict = PyDict::new(py);
        for (code, value) in &self.hats {
            hats_dict.set_item(*code, *value)?;
        }
        dict.set_item("hats", hats_dict)?;

        Ok(dict.into())
    }

    /// Converts the JoystickState to a dictionary with aliases based on the provided DeviceDescription.
    /// This method creates a PyDict containing
    /// three keys: "axes", "buttons", and "hats".
    /// Each key maps to a dictionary where the keys are aliases from the DeviceDescription
    /// and the values are the corresponding input data from the JoystickState.
    /// If there is no alias for a given input, the code is used as the key.
    /// # Arguments
    /// * `py` - The Python interpreter instance.
    /// * `desc` - A reference to a DeviceDescription containing the aliases for axes,
    ///   buttons, and hats.
    ///
    /// # Returns
    /// A PyObject representing the dictionary containing axes, buttons, and hats with aliases.
    ///
    /// # Errors
    /// Returns a PyErr if there is an error during dictionary creation.
    ///
    /// # Example
    /// ```python
    /// joystick_state = JoystickState()
    /// joystick_state.axes = {0: 1.0, 1: -1.0}
    /// joystick_state.buttons = {0: 1, 1: 0}
    /// joystick_state.hats = {0: 1}
    /// desc = DeviceDescription(...)  # Assume this is defined with appropriate aliases
    /// joystick_alias_dict = joystick_state.to_alias_dict(py, desc)
    /// print(joystick_alias_dict)  # {'axes': {'alias1': 1.0, 'alias2': -1.0}, 'buttons': {'alias1': 1, 'alias2': 0}, 'hats': {'alias1': 1}}
    /// ```
    pub fn to_alias_dict(&self, py: Python, desc: &DeviceDescription) -> PyResult<PyObject> {
        let result_dict = PyDict::new(py);

        // Process axes
        let axes_dict = self.get_alias_axes(py, desc)?;
        result_dict.set_item("axes", axes_dict)?;

        // Process buttons
        let buttons_dict = self.get_alias_buttons(py, desc)?;
        result_dict.set_item("buttons", buttons_dict)?;

        // Process hats
        let hats_dict = self.get_alias_hats(py, desc)?;
        result_dict.set_item("hats", hats_dict)?;

        Ok(result_dict.into())
    }

    /// Returns a reference to the axes HashMap keyed by aliases.
    pub fn get_alias_axes(&self, py: Python, desc: &DeviceDescription) -> PyResult<PyObject> {
        let axes_alias_map = Self::find_by_alias(&desc.axes, &self.axes);
        let axes_dict = PyDict::new(py);
        for (alias, value) in axes_alias_map {
            axes_dict.set_item(alias, value)?;
        }
        Ok(axes_dict.into())
    }

    /// Returns a reference to the buttons HashMap keyed by aliases.
    pub fn get_alias_buttons(&self, py: Python, desc: &DeviceDescription) -> PyResult<PyObject> {
        let buttons_alias_map = Self::find_by_alias(&desc.buttons, &self.buttons);
        let buttons_dict = PyDict::new(py);
        for (alias, value) in buttons_alias_map {
            buttons_dict.set_item(alias, value)?;
        }
        Ok(buttons_dict.into())
    }

    /// Returns a reference to the hats HashMap keyed by aliases.
    pub fn get_alias_hats(&self, py: Python, desc: &DeviceDescription) -> PyResult<PyObject> {
        let hats_alias_map = Self::find_by_alias(&desc.hats, &self.hats);
        let hats_dict = PyDict::new(py);
        for (alias, value) in hats_alias_map {
            hats_dict.set_item(alias, value)?;
        }
        Ok(hats_dict.into())
    }
}

impl JoystickState {
    // Helper function to find value by alias
    fn find_by_alias<T: Clone>(items: &[DeviceItem], data: &HashMap<u16, T>) -> HashMap<String, T> {
        let mut alias_map = HashMap::new();
        for item in items {
            if let Some(alias) = &item.alias {
                if let Some(value) = data.get(&item.code) {
                    alias_map.insert(alias.clone(), value.clone());
                }
            } else {
                // If no alias is provided, use the code as the key
                if let Some(value) = data.get(&item.code) {
                    alias_map.insert(item.code.to_string(), value.clone());
                }
            }
        }
        alias_map
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
/// Returns a vector of JoystickInfo structs containing the device path and name.
/// Joystick names default to "Unknown" if they cannot be retrieved.
///
/// # Returns
/// A `Vec<JoystickInfo>` containing information about all connected devices.
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

/// Represents the mode of operation for device buttons in the DevicePool.
/// This enum defines how button presses are handled:
/// - `Trigger`: The button press is registered only when the button is pressed down, then the state will be reset immediately after.
///   This mode is suitable for actions that should only occur once per press, such as firing a shot or triggering an event.
///   The button state will not remain active after the initial press.
/// - `Hold`: The button press is registered continuously while the button is held down.
////// This enum is used to configure the behavior of buttons in the DevicePool,
/// allowing for different interaction styles depending on the application requirements.
/// The mode can be set when creating a DevicePool instance,
/// and it affects how button events are processed during input handling.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[pyclass]
pub enum DeviceButtonMode {
    Trigger,
    Hold,
}

#[pymethods]
impl DeviceButtonMode {
    #[new]
    pub fn new(mode: &str) -> PyResult<Self> {
        match mode {
            "trigger" => Ok(DeviceButtonMode::Trigger),
            "hold" => Ok(DeviceButtonMode::Hold),
            _ => Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                "Invalid button mode. Use 'trigger' or 'hold'.",
            )),
        }
    }

    #[staticmethod]
    pub fn trigger() -> Self {
        DeviceButtonMode::Trigger
    }

    #[staticmethod]
    pub fn hold() -> Self {
        DeviceButtonMode::Hold
    }

    pub fn __repr__(&self) -> String {
        match self {
            DeviceButtonMode::Trigger => "DeviceButtonMode.Trigger".to_string(),
            DeviceButtonMode::Hold => "DeviceButtonMode.Hold".to_string(),
        }
    }

    pub fn __str__(&self) -> String {
        match self {
            DeviceButtonMode::Trigger => "Trigger".to_string(),
            DeviceButtonMode::Hold => "Hold".to_string(),
        }
    }

    pub fn __eq__(&self, other: &Self) -> bool {
        self == other
    }
}
