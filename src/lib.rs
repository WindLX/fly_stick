pub mod inner;
pub mod utils;
pub mod wrapper;

use pyo3::prelude::*;

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<wrapper::device_pool_wrapper::PyDevicePool>()?;
    m.add_class::<wrapper::joystick_wrapper::PyJoystick>()?;

    m.add_class::<utils::JoystickInfo>()?;
    m.add_class::<utils::JoystickState>()?;
    m.add_function(wrap_pyfunction!(utils::fetch_connected_joysticks, m)?)?;

    m.add_class::<inner::description::DeviceItem>()?;
    m.add_class::<inner::description::DeviceDescription>()?;
    Ok(())
}
