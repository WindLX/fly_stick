use crate::inner::device_pool::DevicePool;
use crate::utils::JoystickState;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use pyo3_async_runtimes::tokio::future_into_py;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::Mutex;

#[pyclass]
pub struct PyDevicePool {
    inner: Arc<Mutex<DevicePool>>,
}

#[pymethods]
impl PyDevicePool {
    #[new]
    #[pyo3(signature = (device_desc_files = Vec::new(), debounce_seconds = 0.1))]
    fn new(device_desc_files: Vec<String>, debounce_seconds: f64) -> Self {
        let pool = DevicePool::new(device_desc_files, debounce_seconds);
        Self {
            inner: Arc::new(Mutex::new(pool)),
        }
    }

    fn reset<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let mut pool = inner.lock().await;
            let connected_devices = pool.reset().await;
            Ok(connected_devices)
        })
    }

    fn fetch_nowait(&self, py: Python) -> PyResult<PyObject> {
        let inner = Arc::clone(&self.inner);

        pyo3_async_runtimes::tokio::get_runtime().block_on(async {
            let pool = inner.lock().await;
            match pool.fetch_nowait() {
                Ok(state_map) => {
                    let dict = PyDict::new(py);
                    for (device_name, state) in state_map {
                        let py_state = joystick_state_to_py(py, &state)?;
                        dict.set_item(device_name, py_state)?;
                    }
                    Ok(dict.into())
                }
                Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e)),
            }
        })
    }

    #[pyo3(signature = (timeout_seconds = None))]
    fn fetch<'py>(
        &self,
        py: Python<'py>,
        timeout_seconds: Option<f64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py::<_, PyObject>(py, async move {
            let pool = inner.lock().await;
            let timeout_duration = timeout_seconds.map(Duration::from_secs_f64);

            match pool.fetch(timeout_duration).await {
                Ok(state_map) => Python::with_gil(|py| {
                    let dict = PyDict::new(py);
                    for (device_name, state) in state_map {
                        let py_state = joystick_state_to_py(py, &state)?;
                        dict.set_item(device_name, py_state)?;
                    }
                    Ok(dict.into())
                }),
                Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e)),
            }
        })
    }

    fn stop<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let mut pool = inner.lock().await;
            pool.stop().await;
            Ok(())
        })
    }
}

fn joystick_state_to_py(py: Python, state: &JoystickState) -> PyResult<PyObject> {
    let dict = PyDict::new(py);

    // Convert axes
    let axes_dict = PyDict::new(py);
    for (code, value) in &state.axes {
        axes_dict.set_item(*code, *value)?;
    }
    dict.set_item("axes", axes_dict)?;

    // Convert buttons
    let buttons_dict = PyDict::new(py);
    for (code, value) in &state.buttons {
        buttons_dict.set_item(*code, *value)?;
    }
    dict.set_item("buttons", buttons_dict)?;

    // Convert hats
    let hats_dict = PyDict::new(py);
    for (code, value) in &state.hats {
        hats_dict.set_item(*code, *value)?;
    }
    dict.set_item("hats", hats_dict)?;

    Ok(dict.into())
}
