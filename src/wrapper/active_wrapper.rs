use std::io;
use std::sync::Arc;
use std::time::Duration;

use pyo3::prelude::*;
use pyo3_async_runtimes::tokio::future_into_py;
use tokio::sync::Mutex;

use crate::active::{
    ActiveSidestick as CoreActiveSidestick, ActiveSidestickConfigData, ActiveSidestickStateData,
    AxisTelemetryData, StickTelemetryData,
};

#[pyclass(from_py_object)]
#[derive(Clone)]
pub struct ActiveSidestickConfig {
    #[pyo3(get, set)]
    pub bind_host: String,
    #[pyo3(get, set)]
    pub teensy_host: String,
    #[pyo3(get, set)]
    pub command_port: u16,
    #[pyo3(get, set)]
    pub logic_port: u16,
    #[pyo3(get, set)]
    pub state_port: u16,
    #[pyo3(get, set)]
    pub stale_after_ms: u64,
}

#[pymethods]
impl ActiveSidestickConfig {
    #[new]
    #[pyo3(signature = (bind_host = "0.0.0.0".to_string(), teensy_host = "30.30.30.6".to_string(), command_port = 5405, logic_port = 5406, state_port = 5407, stale_after_ms = 100))]
    fn new(
        bind_host: String,
        teensy_host: String,
        command_port: u16,
        logic_port: u16,
        state_port: u16,
        stale_after_ms: u64,
    ) -> PyResult<Self> {
        if stale_after_ms == 0 {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                "stale_after_ms must be greater than zero",
            ));
        }
        Ok(Self {
            bind_host,
            teensy_host,
            command_port,
            logic_port,
            state_port,
            stale_after_ms,
        })
    }

    fn __repr__(&self) -> String {
        format!(
            "ActiveSidestickConfig(bind_host={:?}, teensy_host={:?}, command_port={}, logic_port={}, state_port={}, stale_after_ms={})",
            self.bind_host,
            self.teensy_host,
            self.command_port,
            self.logic_port,
            self.state_port,
            self.stale_after_ms,
        )
    }
}

impl From<&ActiveSidestickConfig> for ActiveSidestickConfigData {
    fn from(value: &ActiveSidestickConfig) -> Self {
        Self {
            bind_host: value.bind_host.clone(),
            teensy_host: value.teensy_host.clone(),
            command_port: value.command_port,
            logic_port: value.logic_port,
            state_port: value.state_port,
            stale_after: Duration::from_millis(value.stale_after_ms),
        }
    }
}

#[pyclass(from_py_object)]
#[derive(Clone)]
pub struct SidestickAxisTelemetry {
    #[pyo3(get)]
    pub position_rad: f32,
    #[pyo3(get)]
    pub velocity_rad_s: f32,
    #[pyo3(get)]
    pub current_a: f32,
}

impl From<AxisTelemetryData> for SidestickAxisTelemetry {
    fn from(value: AxisTelemetryData) -> Self {
        Self {
            position_rad: value.position_rad,
            velocity_rad_s: value.velocity_rad_s,
            current_a: value.current_a,
        }
    }
}

#[pymethods]
impl SidestickAxisTelemetry {
    fn __repr__(&self) -> String {
        format!(
            "SidestickAxisTelemetry(position_rad={}, velocity_rad_s={}, current_a={})",
            self.position_rad, self.velocity_rad_s, self.current_a
        )
    }
}

#[pyclass(from_py_object)]
#[derive(Clone)]
pub struct SidestickStickTelemetry {
    #[pyo3(get)]
    pub roll: SidestickAxisTelemetry,
    #[pyo3(get)]
    pub pitch: SidestickAxisTelemetry,
}

impl From<StickTelemetryData> for SidestickStickTelemetry {
    fn from(value: StickTelemetryData) -> Self {
        Self {
            roll: value.roll.into(),
            pitch: value.pitch.into(),
        }
    }
}

#[pymethods]
impl SidestickStickTelemetry {
    fn __repr__(&self) -> String {
        format!(
            "SidestickStickTelemetry(roll={:?}, pitch={:?})",
            self.roll.__repr__(),
            self.pitch.__repr__()
        )
    }
}

#[pyclass(from_py_object)]
#[derive(Clone)]
pub struct ActiveSidestickState {
    #[pyo3(get)]
    pub stick_1: SidestickStickTelemetry,
    #[pyo3(get)]
    pub stick_2: SidestickStickTelemetry,
    #[pyo3(get)]
    pub ap_enabled: bool,
    #[pyo3(get)]
    pub active: bool,
    #[pyo3(get)]
    pub coupling_disconnected: bool,
    #[pyo3(get)]
    pub connected: bool,
    #[pyo3(get)]
    pub stale: bool,
}

impl From<ActiveSidestickStateData> for ActiveSidestickState {
    fn from(value: ActiveSidestickStateData) -> Self {
        Self {
            stick_1: value.stick_1.into(),
            stick_2: value.stick_2.into(),
            ap_enabled: value.ap_enabled,
            active: value.active,
            coupling_disconnected: value.coupling_disconnected,
            connected: value.connected,
            stale: value.stale,
        }
    }
}

#[pymethods]
impl ActiveSidestickState {
    fn __repr__(&self) -> String {
        format!(
            "ActiveSidestickState(connected={}, stale={}, ap_enabled={}, active={}, coupling_disconnected={})",
            self.connected, self.stale, self.ap_enabled, self.active, self.coupling_disconnected
        )
    }
}

#[pyclass]
pub struct ActiveSidestick {
    inner: Arc<Mutex<CoreActiveSidestick>>,
}

#[pymethods]
impl ActiveSidestick {
    #[new]
    #[pyo3(signature = (config = None))]
    fn new(config: Option<ActiveSidestickConfig>) -> Self {
        let config = config.unwrap_or_else(|| {
            ActiveSidestickConfig::new(
                "0.0.0.0".to_string(),
                "30.30.30.6".to_string(),
                5405,
                5406,
                5407,
                100,
            )
            .expect("default active sidestick config must be valid")
        });
        Self {
            inner: Arc::new(Mutex::new(CoreActiveSidestick::new((&config).into()))),
        }
    }

    fn start<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let mut sidestick = inner.lock().await;
            sidestick.start().await.map_err(io_to_pyerr)?;
            Ok(())
        })
    }

    fn stop<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let mut sidestick = inner.lock().await;
            sidestick.stop().await;
            Ok(())
        })
    }

    fn fetch_nowait(&self) -> PyResult<ActiveSidestickState> {
        let inner = Arc::clone(&self.inner);
        pyo3_async_runtimes::tokio::get_runtime().block_on(async move {
            let sidestick = inner.lock().await;
            if !sidestick.is_running() {
                return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                    "Active sidestick is not started. Call await start() first.",
                ));
            }
            Ok(sidestick.snapshot().into())
        })
    }

    #[pyo3(signature = (timeout_seconds = None))]
    fn fetch<'py>(
        &self,
        py: Python<'py>,
        timeout_seconds: Option<f64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let fetch_context = {
                let sidestick = inner.lock().await;
                sidestick.fetch_context().map_err(io_to_pyerr)?
            };
            let timeout = timeout_seconds.map(Duration::from_secs_f64);
            fetch_context
                .fetch(timeout)
                .await
                .map(ActiveSidestickState::from)
                .map_err(io_to_pyerr)
        })
    }

    fn send_aircraft_state(
        &self,
        aoa_rad: f32,
        elevator_rad: f32,
        aileron_rad: f32,
    ) -> PyResult<()> {
        let inner = Arc::clone(&self.inner);
        pyo3_async_runtimes::tokio::get_runtime().block_on(async move {
            let sidestick = inner.lock().await;
            sidestick
                .send_aircraft_state(aoa_rad, elevator_rad, aileron_rad)
                .await
                .map_err(io_to_pyerr)
        })
    }

    #[getter]
    fn running(&self) -> bool {
        let inner = Arc::clone(&self.inner);
        pyo3_async_runtimes::tokio::get_runtime()
            .block_on(async move { inner.lock().await.is_running() })
    }
}

fn io_to_pyerr(error: io::Error) -> PyErr {
    match error.kind() {
        io::ErrorKind::TimedOut => {
            PyErr::new::<pyo3::exceptions::PyTimeoutError, _>(error.to_string())
        }
        io::ErrorKind::InvalidInput | io::ErrorKind::InvalidData => {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(error.to_string())
        }
        io::ErrorKind::NotConnected => {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(error.to_string())
        }
        _ => PyErr::new::<pyo3::exceptions::PyOSError, _>(error.to_string()),
    }
}
