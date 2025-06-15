use crate::utils::JoystickState;
use evdev::Device;
use std::collections::HashMap;
use std::path::Path;

/// A joystick interface that wraps an evdev device.
///
/// This struct provides a high-level abstraction over a joystick/gamepad device,
/// exposing axes, buttons, and hat switches. It maintains information about
/// the device capabilities and axis ranges.
///
/// # Fields
///
/// * `device` - The underlying evdev device handle
/// * `axes` - Vector of available analog axis codes (e.g., X, Y axes)
/// * `buttons` - Vector of available button/key codes
/// * `hats` - Vector of hat switch (D-pad) axis codes
/// * `axis_info` - Mapping of axis codes to their min/max value ranges
pub struct Joystick {
    device: Device,
    axes: Vec<evdev::AbsoluteAxisCode>,
    buttons: Vec<evdev::KeyCode>,
    hats: Vec<evdev::AbsoluteAxisCode>,
    axis_info: HashMap<evdev::AbsoluteAxisCode, (i32, i32)>,
}

impl Joystick {
    /// Creates a new Joystick instance by opening the specified device.
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
    /// Returns a new Joystick instance or an error if the device cannot be opened
    /// or configured.
    ///
    /// # Errors
    ///
    /// * `std::io::Error` - If the device cannot be opened or set to non-blocking mode
    pub fn new(device_path: &str) -> Result<Self, std::io::Error> {
        let device = Device::open(Path::new(device_path))?;

        // Set device to non-blocking mode
        device.set_nonblocking(true)?;

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

        Ok(Joystick {
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
    /// # Returns
    ///
    /// Returns a JoystickState containing:
    /// * axes: Maps axis codes to normalized float values [-1.0, 1.0]
    /// * buttons: Maps button codes to integer values (0 or 1)
    /// * hats: Maps hat codes to tuples of (x, y) integer values
    ///
    /// # Errors
    ///
    /// * `std::io::Error` - If there's an error reading from the device (other than WouldBlock)
    ///
    /// # Note
    ///
    /// This method uses non-blocking reads, so it will return immediately even if
    /// no events are available.
    pub fn get_state(&mut self) -> Result<JoystickState, std::io::Error> {
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
                                    buttons_data.insert(key_type.code(), 1);
                                } else {
                                    buttons_data.insert(key_type.code(), 0);
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
                                    let value = if value < 0 {
                                        -1
                                    } else if value > 0 {
                                        1
                                    } else {
                                        0
                                    };
                                    if axis == evdev::AbsoluteAxisCode::ABS_HAT0X {
                                        hats_data.insert(axis.0, value);
                                    } else if axis == evdev::AbsoluteAxisCode::ABS_HAT0Y {
                                        hats_data.insert(axis.0, value);
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
                return Err(e);
            }
        }

        Ok(JoystickState {
            axes: axes_data,
            buttons: buttons_data,
            hats: hats_data,
        })
    }
}
