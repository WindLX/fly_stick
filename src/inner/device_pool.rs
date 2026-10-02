use crate::inner::description::DeviceDescription;
use crate::inner::joystick::{Joystick, JoystickEvents};
use crate::utils::{fetch_connected_joysticks, DeviceButtonMode, JoystickInfo, JoystickState};

use std::collections::{HashMap, HashSet};
use std::io;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, RwLock};
use std::time::{Duration, Instant};

use tokio::sync::{oneshot, Mutex as AsyncMutex, Notify};
use tokio::task::JoinHandle;
use tokio::time::{sleep, timeout};

#[derive(Debug)]
pub enum PoolError {
    Lookup(String),
    Configuration(String),
    Io(IoFailure),
    Runtime(String),
    Timeout,
}

#[derive(Clone, Debug)]
pub struct IoFailure {
    errno: Option<i32>,
    message: String,
    context: Option<String>,
    path: Option<String>,
}

impl IoFailure {
    fn new(error: io::Error, context: Option<String>, path: Option<String>) -> Self {
        Self {
            errno: error.raw_os_error(),
            message: error.to_string(),
            context,
            path,
        }
    }

    fn display_message(&self) -> String {
        match &self.context {
            Some(context) => format!("{context}: {}", self.message),
            None => self.message.clone(),
        }
    }
}

impl PoolError {
    pub fn to_pyerr(&self) -> pyo3::PyErr {
        use pyo3::exceptions::{
            PyIOError, PyLookupError, PyRuntimeError, PyTimeoutError, PyValueError,
        };
        match self {
            Self::Lookup(message) => PyLookupError::new_err(message.clone()),
            Self::Configuration(message) => PyValueError::new_err(message.clone()),
            Self::Io(error) => {
                PyIOError::new_err((error.errno, error.display_message(), error.path.clone()))
            }
            Self::Runtime(message) => PyRuntimeError::new_err(message.clone()),
            Self::Timeout => PyTimeoutError::new_err("Fetch operation timed out"),
        }
    }
}

impl From<io::Error> for PoolError {
    fn from(error: io::Error) -> Self {
        Self::Io(IoFailure::new(error, None, None))
    }
}

#[derive(Default)]
struct SharedState {
    running: bool,
    failure: Option<IoFailure>,
    version: u64,
    states: HashMap<String, JoystickState>,
    press_counts: HashMap<(String, u16), u64>,
}

#[derive(Default)]
struct ReaderProgress {
    version: u64,
    presses: HashMap<(String, u16), u64>,
}

struct MonitorTask {
    stop: Option<oneshot::Sender<()>>,
    task: JoinHandle<()>,
}

pub struct DevicePool {
    descriptions: HashMap<String, DeviceDescription>,
    devices: RwLock<HashMap<String, (DeviceDescription, JoystickInfo)>>,
    shared: Arc<Mutex<SharedState>>,
    mode: RwLock<DeviceButtonMode>,
    debounce_time: Duration,
    lifecycle: AsyncMutex<Option<MonitorTask>>,
    changed: Arc<Notify>,
    fetch_active: Arc<AtomicU64>,
    fetch_sequence: AtomicU64,
    fetch_gate: Arc<Mutex<()>>,
    fetch_progress: Mutex<ReaderProgress>,
    nowait_progress: Mutex<ReaderProgress>,
}

type DeviceMap = HashMap<String, (DeviceDescription, JoystickInfo)>;
type EventSources = Vec<(String, String, Box<dyn EventSource>)>;
type OpenedDevices = (DeviceMap, EventSources);

impl DevicePool {
    pub fn new(
        descriptions: HashMap<String, DeviceDescription>,
        debounce_seconds: f64,
        mode: DeviceButtonMode,
    ) -> Result<Self, PoolError> {
        if !debounce_seconds.is_finite() || debounce_seconds < 0.0 {
            return Err(PoolError::Configuration(
                "debounce_seconds must be a finite non-negative number".to_string(),
            ));
        }
        validate_descriptions(&descriptions)?;
        Ok(Self {
            descriptions,
            devices: RwLock::new(HashMap::new()),
            shared: Arc::new(Mutex::new(SharedState::default())),
            mode: RwLock::new(mode),
            debounce_time: Duration::from_secs_f64(debounce_seconds),
            lifecycle: AsyncMutex::new(None),
            changed: Arc::new(Notify::new()),
            fetch_active: Arc::new(AtomicU64::new(0)),
            fetch_sequence: AtomicU64::new(0),
            fetch_gate: Arc::new(Mutex::new(())),
            fetch_progress: Mutex::new(ReaderProgress::default()),
            nowait_progress: Mutex::new(ReaderProgress::default()),
        })
    }

    pub fn get_debounce_time(&self) -> Duration {
        self.debounce_time
    }

    pub fn get_button_mode(&self) -> DeviceButtonMode {
        *self.mode.read().unwrap()
    }

    pub fn set_button_mode(&self, mode: DeviceButtonMode) {
        let mut shared = self.shared.lock().unwrap();
        let mut current_mode = self.mode.write().unwrap();
        if *current_mode == mode {
            return;
        }
        *current_mode = mode;
        sync_progress(&shared, &mut self.fetch_progress.lock().unwrap());
        sync_progress(&shared, &mut self.nowait_progress.lock().unwrap());
        shared.version += 1;
        drop(current_mode);
        drop(shared);
        self.changed.notify_one();
    }

    pub fn get_devices(&self) -> HashMap<String, (DeviceDescription, JoystickInfo)> {
        self.devices.read().unwrap().clone()
    }

    pub async fn reset(
        &self,
    ) -> Result<HashMap<String, (DeviceDescription, JoystickInfo)>, PoolError> {
        let mut monitor = self.lifecycle.lock().await;
        self.stop_monitor_locked(&mut monitor).await?;
        self.clear_after_reset();

        let connected = fetch_connected_joysticks();
        let selected = match select_devices(&self.descriptions, &connected) {
            Ok(selected) => selected,
            Err(error) => return Err(error),
        };

        let (devices, sources) = match open_selected_devices(selected, Joystick::new) {
            Ok(opened) => opened,
            Err(error) => {
                self.clear_after_reset();
                return Err(error);
            }
        };

        *self.devices.write().unwrap() = devices.clone();
        {
            let mut shared = self.shared.lock().unwrap();
            shared.states = self
                .descriptions
                .iter()
                .filter(|(logical_name, _)| devices.contains_key(*logical_name))
                .map(|(logical_name, description)| {
                    (logical_name.clone(), description.build_state())
                })
                .collect();
            shared.press_counts.clear();
            shared.failure = None;
            shared.version += 1;
            sync_progress(&shared, &mut self.fetch_progress.lock().unwrap());
            sync_progress(&shared, &mut self.nowait_progress.lock().unwrap());
            shared.running = true;
        }

        let shared = Arc::clone(&self.shared);
        let changed = Arc::clone(&self.changed);
        let debounce_time = self.debounce_time;
        let (stop_tx, stop_rx) = oneshot::channel();
        let task = tokio::spawn(async move {
            monitor_devices(sources, shared, changed, debounce_time, stop_rx).await;
        });
        *monitor = Some(MonitorTask {
            stop: Some(stop_tx),
            task,
        });
        self.changed.notify_one();
        Ok(devices)
    }

    pub fn fetch_nowait(&self) -> Result<HashMap<String, JoystickState>, PoolError> {
        let shared = self.shared.lock().unwrap();
        ensure_running(&shared)?;
        let mode = *self.mode.read().unwrap();
        let mut progress = self.nowait_progress.lock().unwrap();
        let states = snapshot_for_reader(&shared, &mut progress, mode);
        Ok(states)
    }

    pub async fn fetch(
        &self,
        timeout_duration: Option<Duration>,
    ) -> Result<HashMap<String, JoystickState>, PoolError> {
        let guard = self.reserve_fetch()?;
        self.fetch_reserved(timeout_duration, guard).await
    }

    pub fn reserve_fetch(&self) -> Result<FetchGuard, PoolError> {
        let _gate = self.fetch_gate.lock().unwrap();
        let token = loop {
            let token = self.fetch_sequence.fetch_add(1, Ordering::Relaxed) + 1;
            if token != 0 {
                break token;
            }
        };
        if self
            .fetch_active
            .compare_exchange(0, token, Ordering::AcqRel, Ordering::Acquire)
            .is_err()
        {
            return Err(PoolError::Runtime(
                "another fetch() call is already waiting on this device pool".to_string(),
            ));
        }
        Ok(FetchGuard(
            Arc::clone(&self.fetch_active),
            Arc::clone(&self.fetch_gate),
            token,
        ))
    }

    pub fn release_fetch(&self, token: u64) {
        let _gate = self.fetch_gate.lock().unwrap();
        let _ = self
            .fetch_active
            .compare_exchange(token, 0, Ordering::AcqRel, Ordering::Acquire);
    }

    pub async fn fetch_reserved(
        &self,
        timeout_duration: Option<Duration>,
        fetch_guard: FetchGuard,
    ) -> Result<HashMap<String, JoystickState>, PoolError> {
        let token = fetch_guard.token();
        let wait_for_change = async {
            loop {
                let notified = self.changed.notified();
                {
                    let _gate = self.fetch_gate.lock().unwrap();
                    if self.fetch_active.load(Ordering::Acquire) != token {
                        return Err(PoolError::Runtime(
                            "fetch() request was cancelled or superseded".to_string(),
                        ));
                    }
                    let shared = self.shared.lock().unwrap();
                    ensure_running(&shared)?;
                    let mode = *self.mode.read().unwrap();
                    let mut progress = self.fetch_progress.lock().unwrap();
                    if shared.version != progress.version {
                        let states = snapshot_for_reader(&shared, &mut progress, mode);
                        return Ok(states);
                    }
                }
                notified.await;
            }
        };
        match timeout_duration {
            Some(duration) => timeout(duration, wait_for_change)
                .await
                .map_err(|_| PoolError::Timeout)?,
            None => wait_for_change.await,
        }
    }

    pub async fn stop(&self) -> Result<(), PoolError> {
        let mut monitor = self.lifecycle.lock().await;
        self.stop_monitor_locked(&mut monitor).await
    }

    async fn stop_monitor_locked(
        &self,
        monitor: &mut Option<MonitorTask>,
    ) -> Result<(), PoolError> {
        {
            let mut shared = self.shared.lock().unwrap();
            shared.running = false;
        }
        self.changed.notify_one();
        let result = if let Some(active) = monitor.as_mut() {
            if let Some(stop) = active.stop.take() {
                let _ = stop.send(());
            }
            Some((&mut active.task).await)
        } else {
            None
        };
        if let Some(result) = result {
            *monitor = None;
            result.map_err(|error| {
                PoolError::Io(IoFailure::new(
                    io::Error::other(format!("monitor task failed: {error}")),
                    None,
                    None,
                ))
            })?;
        }
        Ok(())
    }

    fn clear_after_reset(&self) {
        *self.devices.write().unwrap() = HashMap::new();
        let mut shared = self.shared.lock().unwrap();
        shared.running = false;
        shared.failure = None;
        shared.states.clear();
        shared.press_counts.clear();
        shared.version += 1;
        sync_progress(&shared, &mut self.fetch_progress.lock().unwrap());
        sync_progress(&shared, &mut self.nowait_progress.lock().unwrap());
        drop(shared);
        self.changed.notify_waiters();
    }
}

pub struct FetchGuard(Arc<AtomicU64>, Arc<Mutex<()>>, u64);

impl FetchGuard {
    pub fn token(&self) -> u64 {
        self.2
    }
}

impl Drop for FetchGuard {
    fn drop(&mut self) {
        let _gate = self.1.lock().unwrap();
        let _ = self
            .0
            .compare_exchange(self.2, 0, Ordering::AcqRel, Ordering::Acquire);
    }
}

fn ensure_running(shared: &SharedState) -> Result<(), PoolError> {
    if let Some(error) = &shared.failure {
        return Err(PoolError::Io(error.clone()));
    }
    if !shared.running {
        return Err(PoolError::Runtime(
            "device pool is not running; call reset() first".to_string(),
        ));
    }
    Ok(())
}

fn sync_progress(shared: &SharedState, progress: &mut ReaderProgress) {
    progress.version = shared.version;
    progress.presses.clone_from(&shared.press_counts);
}

fn snapshot_for_reader(
    shared: &SharedState,
    progress: &mut ReaderProgress,
    mode: DeviceButtonMode,
) -> HashMap<String, JoystickState> {
    let mut snapshot = shared.states.clone();
    match mode {
        DeviceButtonMode::Hold => {}
        DeviceButtonMode::Trigger => {
            for (logical_name, state) in &mut snapshot {
                for (code, value) in &mut state.buttons {
                    let key = (logical_name.clone(), *code);
                    let count = shared.press_counts.get(&key).copied().unwrap_or_default();
                    let seen = progress.presses.get(&key).copied().unwrap_or_default();
                    *value = u8::from(count > seen);
                    progress.presses.insert(key, count);
                }
            }
        }
    }
    progress.version = shared.version;
    snapshot
}

fn validate_descriptions(
    descriptions: &HashMap<String, DeviceDescription>,
) -> Result<(), PoolError> {
    let mut explicit_paths = HashSet::new();
    for (logical_name, description) in descriptions {
        if logical_name.trim().is_empty() {
            return Err(PoolError::Configuration(
                "logical device names must not be empty".to_string(),
            ));
        }
        description.validate().map_err(PoolError::Configuration)?;
        if let Some(path) = &description.device_path {
            if !explicit_paths.insert(path) {
                return Err(PoolError::Configuration(format!(
                    "device_path {path:?} is configured more than once"
                )));
            }
        }
    }
    Ok(())
}

fn select_devices(
    descriptions: &HashMap<String, DeviceDescription>,
    connected: &[JoystickInfo],
) -> Result<HashMap<String, (DeviceDescription, JoystickInfo)>, PoolError> {
    let mut selected = HashMap::with_capacity(descriptions.len());
    let mut selected_paths = HashSet::new();
    for (logical_name, description) in descriptions {
        let matches: Vec<_> = connected
            .iter()
            .filter(|info| {
                info.name == description.device_name
                    && description
                        .device_path
                        .as_ref()
                        .is_none_or(|path| path == &info.path)
            })
            .collect();
        match matches.as_slice() {
            [] => {
                return Err(PoolError::Lookup(format!(
                    "no connected device matches logical device {logical_name:?} ({:?}, path {:?})",
                    description.device_name, description.device_path
                )))
            }
            [info] => {
                if !selected_paths.insert(info.path.as_str()) {
                    return Err(PoolError::Configuration(format!(
                        "multiple logical devices resolve to device path {:?}",
                        info.path
                    )));
                }
                selected.insert(logical_name.clone(), (description.clone(), (*info).clone()));
            }
            _ => {
                let paths = matches
                    .iter()
                    .map(|info| info.path.as_str())
                    .collect::<Vec<_>>();
                return Err(PoolError::Configuration(format!(
                    "logical device {logical_name:?} matches multiple nodes for name {:?}: {paths:?}; set device_path",
                    description.device_name,
                )));
            }
        }
    }
    Ok(selected)
}

fn open_selected_devices<S, F>(selected: DeviceMap, mut open: F) -> Result<OpenedDevices, PoolError>
where
    S: EventSource + 'static,
    F: FnMut(&str) -> io::Result<S>,
{
    let mut sources: EventSources = Vec::with_capacity(selected.len());
    let mut devices = DeviceMap::with_capacity(selected.len());
    for (logical_name, (description, info)) in selected {
        let source = open(&info.path).map_err(|error| {
            PoolError::Io(IoFailure::new(
                error,
                Some(format!("failed to open logical device {logical_name:?}")),
                Some(info.path.clone()),
            ))
        })?;
        let device_path = info.path.clone();
        devices.insert(logical_name.clone(), (description, info));
        sources.push((logical_name, device_path, Box::new(source)));
    }
    Ok((devices, sources))
}

trait EventSource: Send {
    fn read_events(&mut self) -> io::Result<JoystickEvents>;
}

impl EventSource for Joystick {
    fn read_events(&mut self) -> io::Result<JoystickEvents> {
        self.get_events()
    }
}

async fn monitor_devices(
    mut sources: EventSources,
    shared: Arc<Mutex<SharedState>>,
    changed: Arc<Notify>,
    debounce_time: Duration,
    mut stop: oneshot::Receiver<()>,
) {
    let mut last_button_press: HashMap<(String, u16), Instant> = HashMap::new();
    loop {
        tokio::select! {
            _ = &mut stop => break,
            _ = sleep(Duration::from_millis(10)) => {
                let mut failure = None;
                let mut changed_state = false;
                {
                    let mut shared = shared.lock().unwrap();
                    for (logical_name, device_path, source) in &mut sources {
                        match source.read_events() {
                            Ok(events) => {
                                changed_state |= apply_events(
                                    &mut shared,
                                    logical_name,
                                    events,
                                    debounce_time,
                                    &mut last_button_press,
                                );
                            }
                            Err(error) => {
                                failure = Some(IoFailure::new(
                                    error,
                                    Some(format!("failed to read logical device {logical_name:?}")),
                                    Some(device_path.clone()),
                                ));
                                break;
                            }
                        }
                    }
                    if let Some(message) = &failure {
                        shared.running = false;
                        shared.failure = Some(message.clone());
                        shared.version += 1;
                    } else if changed_state {
                        shared.version += 1;
                    }
                }
                if failure.is_some() {
                    drop(sources);
                    changed.notify_one();
                    return;
                }
                if changed_state {
                    changed.notify_one();
                }
            }
        }
    }
    drop(sources);
}

fn apply_events(
    shared: &mut SharedState,
    logical_name: &str,
    events: JoystickEvents,
    debounce_time: Duration,
    last_button_press: &mut HashMap<(String, u16), Instant>,
) -> bool {
    let Some(state) = shared.states.get_mut(logical_name) else {
        return false;
    };
    let mut changed = false;
    for (code, value) in events.delta.axes {
        if let Some(current) = state.axes.get_mut(&code) {
            if *current != value {
                *current = value;
                changed = true;
            }
        }
    }
    for (code, value) in events.delta.hats {
        if let Some(current) = state.hats.get_mut(&code) {
            if *current != value {
                *current = value;
                changed = true;
            }
        }
    }
    for (code, pressed) in events.button_events {
        let Some(current) = state.buttons.get_mut(&code) else {
            continue;
        };
        if pressed {
            if *current != 0 {
                continue;
            }
            let key = (logical_name.to_string(), code);
            let now = Instant::now();
            if last_button_press
                .get(&key)
                .is_some_and(|previous| now.duration_since(*previous) < debounce_time)
            {
                continue;
            }
            last_button_press.insert(key.clone(), now);
            *current = 1;
            *shared.press_counts.entry(key).or_default() += 1;
            changed = true;
        } else if *current != 0 {
            *current = 0;
            changed = true;
        }
    }
    changed
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::inner::description::DeviceItem;
    use pyo3::types::PyAnyMethods;
    use std::sync::atomic::{AtomicBool, AtomicUsize};

    fn description(name: &str, path: Option<&str>) -> DeviceDescription {
        DeviceDescription {
            device_name: name.to_string(),
            device_path: path.map(str::to_string),
            author: None,
            created: None,
            description: None,
            axes: vec![DeviceItem::new(0, Some("roll".to_string()))],
            buttons: vec![DeviceItem::new(1, Some("fire".to_string()))],
            hats: vec![DeviceItem::new(16, Some("pov_x".to_string()))],
        }
    }

    fn info(path: &str, name: &str) -> JoystickInfo {
        JoystickInfo::new(path.to_string(), name.to_string())
    }

    #[test]
    fn io_errors_keep_errno_context_and_filename_in_python() {
        let error = PoolError::Io(IoFailure::new(
            io::Error::from_raw_os_error(13),
            Some("failed to open logical device \"stick\"".to_string()),
            Some("/dev/input/event7".to_string()),
        ))
        .to_pyerr();
        pyo3::Python::initialize();
        pyo3::Python::attach(|py| {
            let value = error.value(py);
            assert_eq!(
                value.getattr("errno").unwrap().extract::<i32>().unwrap(),
                13
            );
            assert_eq!(
                value
                    .getattr("filename")
                    .unwrap()
                    .extract::<String>()
                    .unwrap(),
                "/dev/input/event7"
            );
            assert!(value
                .getattr("strerror")
                .unwrap()
                .extract::<String>()
                .unwrap()
                .contains("logical device \"stick\""));
        });
    }

    #[test]
    fn stale_fetch_guard_cannot_release_a_newer_reservation() {
        let pool = DevicePool::new(HashMap::new(), 0.0, DeviceButtonMode::Hold).unwrap();
        let first = pool.reserve_fetch().unwrap();
        let first_token = first.token();
        pool.release_fetch(first_token);
        let second = pool.reserve_fetch().unwrap();
        assert_ne!(first_token, second.token());

        drop(first);
        assert_eq!(pool.fetch_active.load(Ordering::Acquire), second.token());
        drop(second);
        assert_eq!(pool.fetch_active.load(Ordering::Acquire), 0);
    }

    #[tokio::test]
    async fn superseded_fetch_cannot_consume_a_new_triggers_progress() {
        let pool = DevicePool::new(HashMap::new(), 0.0, DeviceButtonMode::Trigger).unwrap();
        let mut state = description("Controller", None).build_state();
        state.buttons.insert(1, 1);
        {
            let mut shared = pool.shared.lock().unwrap();
            shared.running = true;
            shared.version = 1;
            shared.states.insert("stick".to_string(), state);
            shared.press_counts.insert(("stick".to_string(), 1), 1);
        }

        let old_guard = pool.reserve_fetch().unwrap();
        let old_token = old_guard.token();
        let stale_wait = pool.fetch_reserved(None, old_guard);
        pool.release_fetch(old_token);
        let new_guard = pool.reserve_fetch().unwrap();

        assert!(matches!(
            stale_wait.await,
            Err(PoolError::Runtime(message)) if message.contains("superseded")
        ));
        assert_eq!(pool.fetch_progress.lock().unwrap().version, 0);

        let snapshot = pool
            .fetch_reserved(Some(Duration::ZERO), new_guard)
            .await
            .unwrap();
        assert_eq!(snapshot["stick"].buttons[&1], 1);
    }

    fn events(
        buttons: &[(u16, bool)],
        axis: Option<(u16, f32)>,
        hat: Option<(u16, i8)>,
    ) -> JoystickEvents {
        let mut delta = JoystickState::new();
        if let Some((code, value)) = axis {
            delta.axes.insert(code, value);
        }
        if let Some((code, value)) = hat {
            delta.hats.insert(code, value);
        }
        for (code, pressed) in buttons {
            delta.buttons.insert(*code, u8::from(*pressed));
        }
        JoystickEvents {
            delta,
            button_events: buttons.to_vec(),
        }
    }

    struct FakeSource {
        fail: bool,
        dropped: Arc<AtomicBool>,
    }

    impl EventSource for FakeSource {
        fn read_events(&mut self) -> io::Result<JoystickEvents> {
            if self.fail {
                Err(io::Error::from_raw_os_error(5))
            } else {
                Ok(JoystickEvents::default())
            }
        }
    }

    impl Drop for FakeSource {
        fn drop(&mut self) {
            self.dropped.store(true, Ordering::Release);
        }
    }

    #[test]
    fn matching_requires_unique_name_or_exact_configured_path() {
        let descriptions = HashMap::from([("stick".to_string(), description("Controller", None))]);
        let connected = [
            info("/dev/input/event1", "Controller"),
            info("/dev/input/event2", "Controller"),
        ];
        assert!(matches!(
            select_devices(&descriptions, &connected),
            Err(PoolError::Configuration(_))
        ));

        let descriptions = HashMap::from([(
            "stick".to_string(),
            description("Controller", Some("/dev/input/event2")),
        )]);
        let selected = select_devices(&descriptions, &connected).unwrap();
        assert_eq!(selected["stick"].1.path, "/dev/input/event2");
    }

    #[test]
    fn missing_match_and_duplicate_paths_have_distinct_errors() {
        let descriptions = HashMap::from([("stick".to_string(), description("Missing", None))]);
        assert!(matches!(
            select_devices(&descriptions, &[]),
            Err(PoolError::Lookup(_))
        ));

        let descriptions = HashMap::from([
            ("one".to_string(), description("Controller", None)),
            (
                "two".to_string(),
                description("Controller", Some("/dev/input/event1")),
            ),
        ]);
        let connected = [
            info("/dev/input/event1", "Controller"),
            info("/dev/input/event2", "Controller"),
        ];
        assert!(matches!(
            select_devices(&descriptions, &connected),
            Err(PoolError::Configuration(_))
        ));

        let descriptions = HashMap::from([
            (
                "one".to_string(),
                description("One", Some("/dev/input/event1")),
            ),
            (
                "two".to_string(),
                description("Two", Some("/dev/input/event1")),
            ),
        ]);
        assert!(matches!(
            validate_descriptions(&descriptions),
            Err(PoolError::Configuration(_))
        ));
    }

    #[test]
    fn trigger_reads_have_independent_progress_and_hold_is_a_snapshot() {
        let mut shared = SharedState {
            running: true,
            states: HashMap::from([(
                "stick".to_string(),
                description("Controller", None).build_state(),
            )]),
            ..SharedState::default()
        };
        let mut last_press = HashMap::new();
        apply_events(
            &mut shared,
            "stick",
            events(&[(1, true)], None, Some((16, 1))),
            Duration::ZERO,
            &mut last_press,
        );

        let mut fetch = ReaderProgress::default();
        let mut nowait = ReaderProgress::default();
        let first = snapshot_for_reader(&shared, &mut fetch, DeviceButtonMode::Trigger);
        assert_eq!(first["stick"].buttons[&1], 1);
        assert_eq!(first["stick"].hats[&16], 1);
        let second = snapshot_for_reader(&shared, &mut fetch, DeviceButtonMode::Trigger);
        assert_eq!(second["stick"].buttons[&1], 0);
        assert_eq!(second["stick"].hats[&16], 1);
        let independent = snapshot_for_reader(&shared, &mut nowait, DeviceButtonMode::Trigger);
        assert_eq!(independent["stick"].buttons[&1], 1);

        let held = snapshot_for_reader(
            &shared,
            &mut ReaderProgress::default(),
            DeviceButtonMode::Hold,
        );
        assert_eq!(held["stick"].buttons[&1], 1);
    }

    #[test]
    fn trigger_preserves_short_presses_and_merges_unobserved_repeats() {
        let mut shared = SharedState {
            running: true,
            states: HashMap::from([(
                "stick".to_string(),
                description("Controller", None).build_state(),
            )]),
            ..SharedState::default()
        };
        let mut last_press = HashMap::new();
        apply_events(
            &mut shared,
            "stick",
            events(&[(1, true), (1, false), (1, true), (1, false)], None, None),
            Duration::ZERO,
            &mut last_press,
        );
        assert_eq!(shared.states["stick"].buttons[&1], 0);
        assert_eq!(shared.press_counts[&("stick".to_string(), 1)], 2);

        let mut progress = ReaderProgress::default();
        let first = snapshot_for_reader(&shared, &mut progress, DeviceButtonMode::Trigger);
        assert_eq!(first["stick"].buttons[&1], 1);
        let second = snapshot_for_reader(&shared, &mut progress, DeviceButtonMode::Trigger);
        assert_eq!(second["stick"].buttons[&1], 0);
    }

    #[test]
    fn presses_debounce_but_release_and_hat_center_are_immediate() {
        let mut shared = SharedState {
            running: true,
            states: HashMap::from([(
                "stick".to_string(),
                description("Controller", None).build_state(),
            )]),
            ..SharedState::default()
        };
        let mut last_press = HashMap::new();
        let interval = Duration::from_secs(10);
        apply_events(
            &mut shared,
            "stick",
            events(&[(1, true)], None, Some((16, 1))),
            interval,
            &mut last_press,
        );
        apply_events(
            &mut shared,
            "stick",
            events(&[(1, false)], None, Some((16, 0))),
            interval,
            &mut last_press,
        );
        assert_eq!(shared.states["stick"].buttons[&1], 0);
        assert_eq!(shared.states["stick"].hats[&16], 0);
        assert_eq!(shared.press_counts[&("stick".to_string(), 1)], 1);

        apply_events(
            &mut shared,
            "stick",
            events(&[(1, true)], None, None),
            interval,
            &mut last_press,
        );
        assert_eq!(shared.states["stick"].buttons[&1], 0);
        assert_eq!(shared.press_counts[&("stick".to_string(), 1)], 1);
    }

    #[test]
    fn mode_switch_syncs_old_pulses_without_changing_physical_button_state() {
        let mut shared = SharedState {
            running: true,
            states: HashMap::from([(
                "stick".to_string(),
                description("Controller", None).build_state(),
            )]),
            ..SharedState::default()
        };
        let mut last_press = HashMap::new();
        apply_events(
            &mut shared,
            "stick",
            events(&[(1, true)], None, None),
            Duration::ZERO,
            &mut last_press,
        );
        let mut progress = ReaderProgress::default();
        sync_progress(&shared, &mut progress);
        assert_eq!(
            snapshot_for_reader(&shared, &mut progress, DeviceButtonMode::Trigger)["stick"].buttons
                [&1],
            0
        );
        assert_eq!(
            snapshot_for_reader(&shared, &mut progress, DeviceButtonMode::Hold)["stick"].buttons
                [&1],
            1
        );
    }

    #[test]
    fn failed_preopen_drops_already_opened_sources_before_returning() {
        let selected = HashMap::from([
            (
                "one".to_string(),
                (description("One", None), info("/dev/one", "One")),
            ),
            (
                "two".to_string(),
                (description("Two", None), info("/dev/two", "Two")),
            ),
        ]);
        let dropped = Arc::new(AtomicBool::new(false));
        let calls = AtomicUsize::new(0);
        let result = open_selected_devices(selected, |_| {
            if calls.fetch_add(1, Ordering::Relaxed) == 0 {
                Ok(FakeSource {
                    fail: false,
                    dropped: Arc::clone(&dropped),
                })
            } else {
                Err(io::Error::from_raw_os_error(13))
            }
        });
        match result {
            Err(PoolError::Io(error)) => {
                assert!(error.context.as_deref().unwrap().contains("logical device"));
                assert!(error.path.as_deref().unwrap().starts_with("/dev/"));
                assert_eq!(error.errno, Some(13));
            }
            _ => panic!("expected an I/O error"),
        }
        assert!(dropped.load(Ordering::Acquire));
    }

    #[tokio::test]
    async fn stopping_waits_until_sources_are_dropped() {
        let dropped = Arc::new(AtomicBool::new(false));
        let shared = Arc::new(Mutex::new(SharedState {
            running: true,
            ..SharedState::default()
        }));
        let changed = Arc::new(Notify::new());
        let (stop_tx, stop_rx) = oneshot::channel();
        let task = tokio::spawn(monitor_devices(
            vec![(
                "stick".to_string(),
                "/dev/input/event1".to_string(),
                Box::new(FakeSource {
                    fail: false,
                    dropped: Arc::clone(&dropped),
                }),
            )],
            shared,
            changed,
            Duration::ZERO,
            stop_rx,
        ));
        stop_tx.send(()).unwrap();
        task.await.unwrap();
        assert!(dropped.load(Ordering::Acquire));
    }

    #[tokio::test]
    async fn cancelled_stop_keeps_task_handle_until_a_later_stop_joins_it() {
        let pool = Arc::new(DevicePool::new(HashMap::new(), 0.0, DeviceButtonMode::Hold).unwrap());
        let (stop_tx, stop_rx) = oneshot::channel();
        let (stopped_tx, stopped_rx) = oneshot::channel();
        let (release_tx, release_rx) = oneshot::channel();
        let task = tokio::spawn(async move {
            let _ = stop_rx.await;
            let _ = stopped_tx.send(());
            let _ = release_rx.await;
        });
        *pool.lifecycle.lock().await = Some(MonitorTask {
            stop: Some(stop_tx),
            task,
        });

        let stopping_pool = Arc::clone(&pool);
        let stopping = tokio::spawn(async move { stopping_pool.stop().await });
        stopped_rx.await.unwrap();
        stopping.abort();
        let _ = stopping.await;
        assert!(pool.lifecycle.lock().await.is_some());

        release_tx.send(()).unwrap();
        pool.stop().await.unwrap();
        assert!(pool.lifecycle.lock().await.is_none());
    }

    #[tokio::test]
    async fn read_failure_stops_pool_and_releases_every_source() {
        let dropped = Arc::new(AtomicBool::new(false));
        let shared = Arc::new(Mutex::new(SharedState {
            running: true,
            ..SharedState::default()
        }));
        let changed = Arc::new(Notify::new());
        let (_stop_tx, stop_rx) = oneshot::channel();
        let task = tokio::spawn(monitor_devices(
            vec![(
                "stick".to_string(),
                "/dev/input/event1".to_string(),
                Box::new(FakeSource {
                    fail: true,
                    dropped: Arc::clone(&dropped),
                }),
            )],
            Arc::clone(&shared),
            changed,
            Duration::ZERO,
            stop_rx,
        ));
        task.await.unwrap();
        let state = shared.lock().unwrap();
        assert!(!state.running);
        let failure = state.failure.as_ref().unwrap();
        assert_eq!(failure.errno, Some(5));
        assert_eq!(failure.path.as_deref(), Some("/dev/input/event1"));
        assert!(failure
            .context
            .as_deref()
            .unwrap()
            .contains("logical device \"stick\""));
        assert!(dropped.load(Ordering::Acquire));
    }

    #[tokio::test]
    async fn fetch_can_be_cancelled_stop_wakes_waiter_and_second_fetch_is_rejected() {
        let pool = Arc::new(DevicePool::new(HashMap::new(), 0.0, DeviceButtonMode::Hold).unwrap());
        pool.shared.lock().unwrap().running = true;
        let first_pool = Arc::clone(&pool);
        let first = tokio::spawn(async move { first_pool.fetch(None).await });
        while pool.fetch_active.load(Ordering::Acquire) == 0 {
            tokio::task::yield_now().await;
        }
        assert!(matches!(
            pool.fetch(Some(Duration::ZERO)).await,
            Err(PoolError::Runtime(_))
        ));
        first.abort();
        let _ = first.await;
        assert_eq!(pool.fetch_active.load(Ordering::Acquire), 0);

        pool.shared.lock().unwrap().running = true;
        let second_pool = Arc::clone(&pool);
        let waiting = tokio::spawn(async move { second_pool.fetch(None).await });
        while pool.fetch_active.load(Ordering::Acquire) == 0 {
            tokio::task::yield_now().await;
        }
        pool.stop().await.unwrap();
        assert!(matches!(waiting.await.unwrap(), Err(PoolError::Runtime(_))));
    }

    #[tokio::test]
    async fn empty_pool_reset_and_stop_complete_without_hardware() {
        let pool = DevicePool::new(HashMap::new(), 0.0, DeviceButtonMode::Hold).unwrap();
        let devices = tokio::time::timeout(Duration::from_secs(1), pool.reset())
            .await
            .unwrap()
            .unwrap();
        assert!(devices.is_empty());
        tokio::time::timeout(Duration::from_secs(1), pool.stop())
            .await
            .unwrap()
            .unwrap();
    }
}
