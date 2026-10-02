use crate::utils::JoystickState;

use std::collections::HashMap;
use std::path::Path;

use evdev::Device;

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

#[derive(Debug, Default)]
pub struct JoystickEvents {
    pub delta: JoystickState,
    pub button_events: Vec<(u16, bool)>,
}

impl JoystickEvents {
    fn record_button(&mut self, code: u16, value: i32) {
        match value {
            1 => {
                self.delta.buttons.insert(code, 1);
                self.button_events.push((code, true));
            }
            0 => {
                self.delta.buttons.insert(code, 0);
                self.button_events.push((code, false));
            }
            _ => {}
        }
    }
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

    /// Reads the event delta from the joystick device.
    ///
    /// Fetches pending events from the device. The returned maps contain only codes
    /// changed in this read; use `DevicePool` when a persistent full snapshot is needed.
    /// Axis values are normalized to [-1.0, 1.0]. Button values are 0 or 1, with
    /// evdev repeat events ignored. Hat axes return -1, 0, or 1.
    ///
    /// # Returns
    ///
    /// Returns an event-delta JoystickState containing:
    /// * axes: Maps axis codes to normalized float values [-1.0, 1.0]
    /// * buttons: Maps button codes to integer values (0 or 1)
    /// * hats: Maps hat codes to integer values (-1, 0, or 1)
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
        self.get_events().map(|events| events.delta)
    }

    pub fn get_events(&mut self) -> Result<JoystickEvents, std::io::Error> {
        let mut events = JoystickEvents::default();

        match self.device.fetch_events() {
            Ok(fetch_events) => {
                for event in fetch_events {
                    match event.destructure() {
                        evdev::EventSummary::Key(_, key_type, value) => {
                            if self.buttons.contains(&key_type) {
                                events.record_button(key_type.code(), value);
                            }
                        }
                        evdev::EventSummary::AbsoluteAxis(_, axis, value) => {
                            if let Some((min, max)) = self.axis_info.get(&axis) {
                                let normalized =
                                    (value - min) as f32 / (max - min) as f32 * 2.0 - 1.0;
                                if self.axes.contains(&axis) {
                                    events.delta.axes.insert(axis.0, normalized);
                                } else if self.hats.contains(&axis) {
                                    let value = if value < 0 {
                                        -1
                                    } else if value > 0 {
                                        1
                                    } else {
                                        0
                                    };
                                    events.delta.hats.insert(axis.0, value);
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

        Ok(events)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn button_repeat_is_not_a_release_and_delta_keeps_last_edge() {
        let mut events = JoystickEvents::default();
        events.record_button(288, 1);
        events.record_button(288, 2);
        assert_eq!(events.delta.buttons.get(&288), Some(&1));
        assert_eq!(events.button_events, vec![(288, true)]);

        events.record_button(288, 0);
        assert_eq!(events.delta.buttons.get(&288), Some(&0));
        assert_eq!(events.button_events, vec![(288, true), (288, false)]);
    }
}
