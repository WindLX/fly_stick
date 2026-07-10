pub mod active;
pub mod inner;
pub mod utils;
pub mod wrapper;

use pyo3::prelude::*;

#[cfg(target_os = "linux")]
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    pyo3_log::init();

    m.add_class::<wrapper::device_pool_wrapper::PyDevicePool>()?;
    m.add_class::<wrapper::joystick_wrapper::PyJoystick>()?;
    m.add_class::<wrapper::active_wrapper::ActiveSidestickConfig>()?;
    m.add_class::<wrapper::active_wrapper::ActiveSidestick>()?;
    m.add_class::<wrapper::active_wrapper::SidestickAxisTelemetry>()?;
    m.add_class::<wrapper::active_wrapper::SidestickStickTelemetry>()?;
    m.add_class::<wrapper::active_wrapper::ActiveSidestickState>()?;

    m.add_class::<utils::JoystickInfo>()?;
    m.add_class::<utils::JoystickState>()?;
    m.add_class::<utils::DeviceButtonMode>()?;
    m.add_function(wrap_pyfunction!(utils::fetch_connected_joysticks, m)?)?;

    m.add_class::<inner::description::DeviceItem>()?;
    m.add_class::<inner::description::DeviceDescription>()?;
    Ok(())
}
