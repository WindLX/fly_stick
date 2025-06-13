use std::collections::HashMap;
use std::path::Path;

use evdev::Device;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

#[pyclass]
/// A Python-exposed joystick interface that wraps an evdev device.
///
/// This struct provides a high-level abstraction over a joystick/gamepad device,
/// exposing axes, buttons, and hat switches for use in Python applications.
/// It maintains information about the device capabilities and axis ranges.
///
/// # Fields
///
/// * `device` - The underlying evdev device handle
/// * `axes` - Vector of available analog axis codes (e.g., X, Y axes)
/// * `buttons` - Vector of available button/key codes
/// * `hats` - Vector of hat switch (D-pad) axis codes
/// * `axis_info` - Mapping of axis codes to their min/max value ranges
struct PyJoystick {
    device: Device,
    axes: Vec<evdev::AbsoluteAxisCode>,
    buttons: Vec<evdev::KeyCode>,
    hats: Vec<evdev::AbsoluteAxisCode>,
    axis_info: HashMap<evdev::AbsoluteAxisCode, (i32, i32)>,
}

#[pymethods]
/// Python wrapper for joystick/gamepad device using evdev.
///
/// This struct provides a Python interface to access joystick devices on Linux systems
/// through the evdev library. It supports reading axes, buttons, and hat switches.
///
/// # Examples
///
/// ```python
/// joystick = PyJoystick("/dev/input/event0")
/// axes, buttons, hats = joystick.get_state()
/// ```
impl PyJoystick {
    /// Creates a new PyJoystick instance by opening the specified device.
    ///
    /// Opens the device at the given path and configures it for non-blocking reads.
    /// Automatically detects and categorizes available axes, buttons, and hat switches.
    ///
    /// # Arguments
    ///
    /// * `device_path` - Path to the input device (e.g., "/dev/input/event0")
    ///
    /// # Returns
    ///
    /// Returns a new PyJoystick instance or a PyIOError if the device cannot be opened
    /// or configured.
    ///
    /// # Errors
    ///
    /// * `PyIOError` - If the device cannot be opened or set to non-blocking mode
    #[new]
    fn new(device_path: &str) -> PyResult<Self> {
        let device = Device::open(Path::new(device_path)).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Failed to open device: {}", e))
        })?;

        // Set device to non-blocking mode
        device.set_nonblocking(true).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyIOError, _>(format!(
                "Failed to set non-blocking: {}",
                e
            ))
        })?;

        let mut axes = Vec::new();
        let mut buttons = Vec::new();
        let mut hats = Vec::new();
        let mut axis_info = HashMap::new();

        if let Ok(abs_info) = device.get_absinfo() {
            for (axis, info) in abs_info {
                axis_info.insert(axis, (info.minimum(), info.maximum()));
                if axis == evdev::AbsoluteAxisCode::ABS_HAT0X
                    || axis == evdev::AbsoluteAxisCode::ABS_HAT0Y
                {
                    hats.push(axis);
                } else {
                    axes.push(axis);
                }
            }
        }

        if let Some(key_info) = device.supported_keys() {
            for key in key_info {
                buttons.push(key);
            }
        }

        Ok(PyJoystick {
            device,
            axes,
            buttons,
            hats,
            axis_info,
        })
    }

    /// Reads the current state of the joystick device.
    ///
    /// Fetches all pending events from the device and processes them to determine
    /// the current state of axes, buttons, and hat switches. Axes values are normalized
    /// to the range [-1.0, 1.0]. Button values are 0 (released) or 1 (pressed).
    /// Hat switches return tuples of (x, y) values.
    ///
    /// # Arguments
    ///
    /// * `py` - Python interpreter reference for creating Python objects
    ///
    /// # Returns
    ///
    /// Returns a tuple containing three dictionaries:
    /// * axes_dict: Maps axis codes to normalized float values [-1.0, 1.0]
    /// * buttons_dict: Maps button codes to integer values (0 or 1)
    /// * hats_dict: Maps hat codes to tuples of (x, y) integer values
    ///
    /// # Errors
    ///
    /// * `PyIOError` - If there's an error reading from the device (other than WouldBlock)
    ///
    /// # Note
    ///
    /// This method uses non-blocking reads, so it will return immediately even if
    /// no events are available.
    fn get_state(&mut self, py: Python) -> PyResult<PyObject> {
        let mut axes_data = HashMap::new();
        let mut buttons_data = HashMap::new();
        let mut hats_data = HashMap::new();

        match self.device.fetch_events() {
            Ok(events) => {
                for event in events {
                    match event.destructure() {
                        evdev::EventSummary::Key(_, key_type, value) => {
                            if self.buttons.contains(&key_type) {
                                if value == 1 {
                                    buttons_data.insert(key_type, 1);
                                } else {
                                    buttons_data.insert(key_type, 0);
                                }
                            }
                        }
                        evdev::EventSummary::AbsoluteAxis(_, axis, value) => {
                            if let Some((min, max)) = self.axis_info.get(&axis) {
                                let normalized =
                                    (value - min) as f32 / (max - min) as f32 * 2.0 - 1.0;
                                if self.axes.contains(&axis) {
                                    axes_data.insert(axis.0, normalized);
                                } else if self.hats.contains(&axis) {
                                    if axis == evdev::AbsoluteAxisCode::ABS_HAT0X {
                                        hats_data.insert(axis, (value, 0));
                                    } else if axis == evdev::AbsoluteAxisCode::ABS_HAT0Y {
                                        if let Some(last) =
                                            hats_data.get_mut(&evdev::AbsoluteAxisCode::ABS_HAT0X)
                                        {
                                            last.1 = value;
                                        } else {
                                            hats_data.insert(axis, (0, value));
                                        }
                                    }
                                }
                            }
                        }
                        _ => (),
                    }
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                // No events available, return empty state
            }
            Err(e) => {
                return Err(PyErr::new::<pyo3::exceptions::PyIOError, _>(format!(
                    "Error fetching events: {}",
                    e
                )));
            }
        }

        let axes_dict = PyDict::new(py);
        for (k, v) in axes_data {
            axes_dict.set_item(k, v)?;
        }

        let buttons_dict = PyDict::new(py);
        for (k, v) in buttons_data {
            buttons_dict.set_item(k.code(), v)?;
        }

        let hats_dict = PyDict::new(py);
        for (k, v) in hats_data {
            hats_dict.set_item(k.0, PyTuple::new(py, &[v.0, v.1])?)?;
        }

        let result = PyTuple::new(
            py,
            &[
                axes_dict.as_any(),
                buttons_dict.as_any(),
                hats_dict.as_any(),
            ],
        )?;
        Ok(result.into())
    }
}

#[pyfunction]
/// Creates a Python tuple containing device information with the device path and name.
///
/// The tuple contains:
/// - Device path as a string (converted from PathBuf via lossy conversion)
/// - Device name as a string, defaulting to "Unknown" if the name cannot be retrieved
///
/// # Returns
/// A `PyResult<&PyTuple>` containing the device information tuple that can be passed to Python.
fn fetch_connected_devices(py: Python) -> PyResult<PyObject> {
    let devices = evdev::enumerate().collect::<Vec<_>>();
    let py_list = PyList::empty(py);

    for (path, device) in devices {
        let device_info = PyTuple::new(
            py,
            &[
                path.to_string_lossy().to_string(),
                device.name().unwrap_or("Unknown").to_string(),
            ],
        )?;
        py_list.append(device_info)?;
    }

    Ok(py_list.into())
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fetch_connected_devices, m)?)?;
    m.add_class::<PyJoystick>()?;
    Ok(())
}
