use crate::inner::description::DeviceDescription;
use crate::inner::device_pool::DevicePool;
use crate::utils::{DeviceButtonMode, JoystickInfo};

use std::collections::HashMap;
use std::sync::Arc;
use std::sync::Mutex;
use std::time::Duration;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;
use pyo3_async_runtimes::tokio::future_into_py;

#[pyclass]
pub struct PyDevicePool {
    inner: Arc<DevicePool>,
    pending_fetch: Mutex<Option<(u64, Py<PyAny>)>>,
}

#[pymethods]
impl PyDevicePool {
    #[new]
    #[pyo3(signature = (device_descs = HashMap::new(), debounce_seconds = 0.1, button_mode = DeviceButtonMode::Hold))]
    pub fn new(
        device_descs: HashMap<String, DeviceDescription>,
        debounce_seconds: f64,
        button_mode: DeviceButtonMode,
    ) -> PyResult<Self> {
        let pool = DevicePool::new(device_descs, debounce_seconds, button_mode)
            .map_err(|error| error.to_pyerr())?;
        Ok(Self {
            inner: Arc::new(pool),
            pending_fetch: Mutex::new(None),
        })
    }

    pub fn reset<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            inner.reset().await.map_err(|error| error.to_pyerr())
        })
    }

    pub fn fetch_nowait<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let states = self
            .inner
            .fetch_nowait()
            .map_err(|error| error.to_pyerr())?;
        let dict = PyDict::new(py);
        for (device_name, state) in states {
            dict.set_item(device_name, state)?;
        }
        Ok(dict)
    }

    #[pyo3(signature = (timeout_seconds = None))]
    pub fn fetch<'py>(
        &self,
        py: Python<'py>,
        timeout_seconds: Option<f64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let timeout_duration = match timeout_seconds {
            Some(seconds) if !seconds.is_finite() || seconds < 0.0 => {
                return Err(PyValueError::new_err(
                    "timeout_seconds must be a finite non-negative number",
                ));
            }
            Some(seconds) => Some(Duration::from_secs_f64(seconds)),
            None => None,
        };
        let inner = Arc::clone(&self.inner);
        let mut pending = self.pending_fetch.lock().unwrap();
        if let Some((token, future)) = pending.as_ref() {
            if !future.bind(py).call_method0("done")?.extract::<bool>()? {
                return Err(PyRuntimeError::new_err(
                    "another fetch() call is already waiting on this device pool",
                ));
            }
            inner.release_fetch(*token);
            *pending = None;
        }
        let guard = inner.reserve_fetch().map_err(|error| error.to_pyerr())?;
        let token = guard.token();
        let future = future_into_py(py, async move {
            let states = inner
                .fetch_reserved(timeout_duration, guard)
                .await
                .map_err(|error| error.to_pyerr())?;
            Python::attach(|py| {
                let dict = PyDict::new(py);
                for (device_name, state) in states {
                    dict.set_item(device_name, state)?;
                }
                Ok(dict.unbind())
            })
        })?;
        *pending = Some((token, future.clone().unbind()));
        Ok(future)
    }

    pub fn stop<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            inner.stop().await.map_err(|error| error.to_pyerr())
        })
    }

    #[getter]
    pub fn debounce_time(&self) -> f64 {
        self.inner.get_debounce_time().as_secs_f64()
    }

    #[getter]
    pub fn button_mode(&self) -> DeviceButtonMode {
        self.inner.get_button_mode()
    }

    #[setter]
    pub fn set_button_mode(&self, mode: DeviceButtonMode) {
        self.inner.set_button_mode(mode);
    }

    #[getter]
    pub fn devices(&self) -> HashMap<String, (DeviceDescription, JoystickInfo)> {
        self.inner.get_devices()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::utils::DeviceButtonMode;
    use pyo3::types::PyAnyMethods;

    #[test]
    fn pending_python_future_blocks_fetch_after_rust_slot_was_released() {
        Python::initialize();
        Python::attach(|py| {
            let pool = PyDevicePool::new(HashMap::new(), 0.0, DeviceButtonMode::Hold).unwrap();
            let guard = pool.inner.reserve_fetch().unwrap();
            let token = guard.token();
            drop(guard);

            let asyncio = py.import("asyncio").unwrap();
            let event_loop = asyncio.call_method0("new_event_loop").unwrap();
            let python_future = event_loop.call_method0("create_future").unwrap();
            *pool.pending_fetch.lock().unwrap() = Some((token, python_future.unbind()));

            let error = pool.fetch(py, None).unwrap_err();
            assert!(error.is_instance_of::<PyRuntimeError>(py));
            assert!(error.to_string().contains("another fetch() call"));
            assert!(pool.pending_fetch.lock().unwrap().is_some());
            event_loop.call_method0("close").unwrap();
        });
    }
}
