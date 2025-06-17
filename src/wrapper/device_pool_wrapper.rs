use crate::inner::description::DeviceDescription;
use crate::inner::device_pool::DevicePool;
use crate::utils::{DeviceButtonMode, JoystickInfo};

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use pyo3::prelude::*;
use pyo3::types::PyDict;
use pyo3_async_runtimes::tokio::future_into_py;
use tokio::sync::Mutex;

#[pyclass]
pub struct PyDevicePool {
    inner: Arc<Mutex<DevicePool>>,
}

#[pymethods]
impl PyDevicePool {
    #[new]
    #[pyo3(signature = (device_descs = HashMap::new(), debounce_seconds = 0.1, btn_mode = DeviceButtonMode::Hold))]
    pub fn new(
        device_descs: HashMap<String, DeviceDescription>,
        debounce_seconds: f64,
        btn_mode: DeviceButtonMode,
    ) -> Self {
        let pool = DevicePool::new(device_descs, debounce_seconds, btn_mode);
        Self {
            inner: Arc::new(Mutex::new(pool)),
        }
    }

    pub fn reset<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let mut pool = inner.lock().await;
            let connected_devices = pool.reset().await;
            Ok(connected_devices)
        })
    }

    pub fn fetch_nowait(&self, py: Python) -> PyResult<PyObject> {
        let inner = Arc::clone(&self.inner);

        pyo3_async_runtimes::tokio::get_runtime().block_on(async {
            let pool = inner.lock().await;
            match pool.fetch_nowait() {
                Ok(state_map) => {
                    let dict = PyDict::new(py);
                    for (device_name, state) in state_map {
                        dict.set_item(device_name, state)?;
                    }
                    Ok(dict.into())
                }
                Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e)),
            }
        })
    }

    #[pyo3(signature = (timeout_seconds = None))]
    pub fn fetch<'py>(
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
                        dict.set_item(device_name, state)?;
                    }
                    Ok(dict.into())
                }),
                Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e)),
            }
        })
    }

    pub fn stop<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let mut pool = inner.lock().await;
            pool.stop().await;
            Ok(())
        })
    }

    #[getter]
    pub fn debounce_time(&self) -> f64 {
        let inner = Arc::clone(&self.inner);
        pyo3_async_runtimes::tokio::get_runtime().block_on(async {
            let pool = inner.lock().await;
            pool.get_debounce_time().as_secs_f64()
        })
    }

    #[getter]
    pub fn button_mode(&self) -> DeviceButtonMode {
        let inner = Arc::clone(&self.inner);
        pyo3_async_runtimes::tokio::get_runtime().block_on(async {
            let pool = inner.lock().await;
            pool.get_btn_mode()
        })
    }

    #[setter]
    pub fn set_button_mode(&self, mode: DeviceButtonMode) -> PyResult<()> {
        let inner = Arc::clone(&self.inner);
        pyo3_async_runtimes::tokio::get_runtime().block_on(async {
            let mut pool = inner.lock().await;
            pool.set_btn_mode(mode);
            Ok(())
        })
    }

    #[getter]
    pub fn devices(&self) -> PyResult<HashMap<String, (DeviceDescription, JoystickInfo)>> {
        let inner = Arc::clone(&self.inner);
        pyo3_async_runtimes::tokio::get_runtime().block_on(async {
            let pool = inner.lock().await;
            Ok(pool.get_devices().to_owned())
        })
    }
}
