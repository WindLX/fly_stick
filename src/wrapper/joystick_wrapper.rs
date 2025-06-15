use crate::{inner::joystick::Joystick, utils::JoystickState};
use pyo3::prelude::*;

#[pyclass]
pub struct PyJoystick {
    joystick: Joystick,
}

#[pymethods]
impl PyJoystick {
    #[new]
    pub fn new(device_path: &str) -> PyResult<Self> {
        let joystick = Joystick::new(device_path)?;
        Ok(PyJoystick { joystick })
    }

    pub fn get_state(&mut self) -> PyResult<JoystickState> {
        match self.joystick.get_state() {
            Ok(state) => Ok(state),
            Err(e) => Err(PyErr::new::<pyo3::exceptions::PyIOError, _>(format!(
                "Failed to get joystick state: {}",
                e
            ))),
        }
    }
}
