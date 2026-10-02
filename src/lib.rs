// pyo3 的 `#[pyclass(from_py_object)]` 会为 `Copy` 类型生成一次 `Clone::clone`。这个 impl 是
// 宏展开出的兄弟项，写在枚举上的 `#[allow]` 覆盖不到，因此只能在 crate 级放宽这一条 lint。
#![allow(clippy::clone_on_copy)]

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

    m.add_class::<utils::JoystickInfo>()?;
    m.add_class::<utils::JoystickState>()?;
    m.add_class::<utils::DeviceButtonMode>()?;
    m.add_function(wrap_pyfunction!(utils::fetch_connected_joysticks, m)?)?;

    m.add_class::<inner::description::DeviceItem>()?;
    m.add_class::<inner::description::DeviceDescription>()?;
    Ok(())
}
