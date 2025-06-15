use crate::inner::description::DeviceDescription;
use crate::inner::joystick::Joystick;
use crate::utils::{fetch_connected_joysticks, JoystickState};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tokio::sync::mpsc;
use tokio::time::sleep;

/// A pool for managing multiple input devices (joysticks/gamepads) with debouncing capabilities.
///
/// The `DevicePool` manages a collection of input devices and provides centralized handling
/// of their input states. It includes debouncing functionality to prevent rapid button
/// press registrations and maintains both current and previous input states for comparison.
///
/// # Features
/// - Device enumeration and management
/// - Input state tracking with current and previous state comparison
/// - Button debouncing to prevent accidental multiple triggers
/// - Thread-safe operation with Arc<Mutex<>> for concurrent access
/// - Graceful shutdown mechanism via message passing
///
/// # Thread Safety
/// All shared state is protected by Arc<Mutex<>> to ensure safe concurrent access
/// across multiple threads.
pub struct DevicePool {
    debounce_time: Duration,
    devices: Vec<DeviceDescription>,
    input_register: Arc<Mutex<HashMap<String, JoystickState>>>,
    last_input_register: Arc<Mutex<HashMap<String, JoystickState>>>,
    last_button_time: Arc<Mutex<HashMap<u16, Instant>>>,
    running: Arc<Mutex<bool>>,
    shutdown_tx: Option<mpsc::Sender<()>>,
}

/// Implementation of the DevicePool with methods for managing devices and input states.
impl DevicePool {
    /// Creates a new device pool instance with the specified debounce timing.
    ///
    /// Initializes all internal collections and synchronization primitives:
    /// - Sets up debounce timing from the provided seconds value
    /// - Creates empty device vector for managing connected devices
    /// - Initializes thread-safe input state tracking with Arc<Mutex<HashMap>>
    /// - Sets up button timing state for debounce logic
    /// - Configures running state and shutdown channel as None (not started)
    ///
    /// # Arguments
    /// * `debounce_seconds` - The debounce time in seconds as a floating-point value
    ///
    /// # Returns
    /// A new `DevicePool` instance ready for device management and input processing
    pub fn new(device_desc_files: Vec<String>, debounce_seconds: f64) -> Self {
        let mut pool = Self {
            debounce_time: Duration::from_secs_f64(debounce_seconds),
            devices: Vec::new(),
            input_register: Arc::new(Mutex::new(HashMap::new())),
            last_input_register: Arc::new(Mutex::new(HashMap::new())),
            last_button_time: Arc::new(Mutex::new(HashMap::new())),
            running: Arc::new(Mutex::new(false)),
            shutdown_tx: None,
        };
        pool.build_state(device_desc_files);
        pool
    }

    /// Resets the device pool by stopping any ongoing monitoring,
    /// clearing the input register, and restarting monitoring.
    ///
    /// This method is useful for reinitializing the device pool
    /// after changes to connected devices or input states.
    ///
    /// # Returns
    /// A vector of device names that are currently connected and monitored.
    pub async fn reset(&mut self) -> Vec<String> {
        self.stop_monitoring().await;
        self.reset_input_register();
        {
            let mut last_button_time = self.last_button_time.lock().unwrap();
            last_button_time.clear();
        }
        self.start_monitoring().await;
        self.check_devices()
    }

    /// Fetches the current input state without waiting for changes.
    ///
    /// This method retrieves the current input state from the input register
    /// and updates the last input register to reflect the current state.
    ///
    /// # Returns
    /// A `HashMap` containing the current input states for all devices.
    /// # Errors
    /// Returns an error if the device monitoring is not running.
    /// This can happen if `reset()` has not been called to start monitoring.
    /// # Example
    /// ```rust
    /// let pool = DevicePool::new(vec!["device1.toml".to_string()], 0.1);
    /// let current_state = pool.fetch_nowait()?;
    /// ```
    pub fn fetch_nowait(&self) -> Result<HashMap<String, JoystickState>, String> {
        let running = *self.running.lock().unwrap();
        if !running {
            return Err("Device monitoring is not running. Call reset() first.".to_string());
        }

        let current_input = {
            let input_register = self.input_register.lock().unwrap();
            input_register.clone()
        };

        {
            let mut last_input_register = self.last_input_register.lock().unwrap();
            *last_input_register = current_input.clone();
        }

        self.reset_trigger_register();
        Ok(current_input)
    }

    /// Fetches the current input state, waiting for changes or a timeout.
    ///
    /// This method continuously checks the input state until a change is detected
    /// or the specified timeout duration is reached.
    /// If a change is detected, it updates the last input register and resets the trigger register.
    ///
    /// # Arguments
    /// * `timeout_duration` - An optional duration to wait for changes before timing out.
    ///
    /// # Returns
    /// A `Result` containing a `HashMap` of the current input states if successful,
    /// or an error message if the operation times out or fails.
    /// # Errors
    /// Returns an error if the device monitoring is not running or if the operation times out.
    /// # Example
    /// ```rust
    /// let pool = DevicePool::new(vec!["device1.toml".to_string()], 0.1);
    /// let current_state = pool.fetch(Some(Duration::from_secs(5))).await?;
    /// ```
    pub async fn fetch(
        &self,
        timeout_duration: Option<Duration>,
    ) -> Result<HashMap<String, JoystickState>, String> {
        let start_time = Instant::now();

        loop {
            let running = *self.running.lock().unwrap();
            if !running {
                let input_register = self.input_register.lock().unwrap();
                return Ok(input_register.clone());
            }

            let current_input = {
                let input_register = self.input_register.lock().unwrap();
                input_register.clone()
            };

            let last_input = {
                let last_input_register = self.last_input_register.lock().unwrap();
                last_input_register.clone()
            };

            if current_input != last_input {
                {
                    let mut last_input_register = self.last_input_register.lock().unwrap();
                    *last_input_register = current_input.clone();
                }
                self.reset_trigger_register();
                return Ok(current_input);
            }

            if let Some(timeout_dur) = timeout_duration {
                if start_time.elapsed() > timeout_dur {
                    return Err("Fetch operation timed out".to_string());
                }
            }

            sleep(Duration::from_millis(10)).await;
        }
    }

    /// Builds the device pool state from the provided device description files.
    ///
    /// This method reads the device descriptions from the specified files,
    /// initializes the input register with the device states, and populates
    /// the devices vector with the parsed device descriptions.
    ///
    /// # Arguments
    /// * `device_desc_files` - A vector of strings representing the paths to the device description files.
    ///
    /// # Example
    /// ```rust
    /// let device_desc_files = vec!["device1.toml".to_string(), "device2.toml".to_string()];
    /// let mut pool = DevicePool::new(device_desc_files, 0.1);
    /// pool.build_state(device_desc_files);
    /// ```
    fn build_state(&mut self, device_desc_files: Vec<String>) {
        self.devices.clear();
        let mut input_register = self.input_register.lock().unwrap();
        input_register.clear();

        for desc_file in device_desc_files {
            if let Ok(desc) = DeviceDescription::from_toml(&desc_file) {
                let device_name = desc.device_name.clone();
                let state = desc.build_state();
                input_register.insert(device_name, state);
                self.devices.push(desc);
            }
        }
    }

    /// Resets the input register to the initial state based on the device descriptions.
    ///
    /// This method initializes the input register with the default states of all devices
    /// defined in the device descriptions. It also updates the last input register
    /// to match the current input register state.
    ///
    /// # Example
    /// ```rust
    /// let mut pool = DevicePool::new(vec!["device1.toml".to_string()], 0.1);
    /// pool.reset_input_register();
    /// ```
    fn reset_input_register(&self) {
        let mut input_register = self.input_register.lock().unwrap();
        let mut last_input_register = self.last_input_register.lock().unwrap();

        for desc in &self.devices {
            let state = desc.build_state();
            input_register.insert(desc.device_name.clone(), state.clone());
        }
        *last_input_register = input_register.clone();
    }

    /// Resets the trigger register by clearing all button and hat states.
    ///
    /// This method iterates through the input register and sets all button and hat values to zero,
    /// effectively resetting the trigger states for all devices.
    ///
    /// # Example
    /// ```rust
    /// let pool = DevicePool::new(vec!["device1.toml".to_string()], 0.1);
    /// pool.reset_trigger_register();
    /// ```
    fn reset_trigger_register(&self) {
        let mut input_register = self.input_register.lock().unwrap();
        for (_device_name, input_data) in input_register.iter_mut() {
            for (_button_key, button_value) in input_data.buttons.iter_mut() {
                *button_value = 0;
            }
            for (_hat_key, hat_value) in input_data.hats.iter_mut() {
                *hat_value = 0;
            }
        }
    }

    /// Checks the currently connected devices against the input register.
    ///
    /// This method fetches the list of connected joysticks and compares them
    /// with the input register. It returns a vector of device names that are
    /// currently registered in the input register.
    ///
    /// # Returns
    /// A vector of strings containing the names of devices that are currently connected
    /// and registered in the input register.
    /// # Example
    /// ```rust
    /// let pool = DevicePool::new(vec!["device1.toml".to_string()], 0.1);
    /// let connected_devices = pool.check_devices();
    /// ```
    fn check_devices(&self) -> Vec<String> {
        let devices = fetch_connected_joysticks();
        let input_register = self.input_register.lock().unwrap();

        devices
            .into_iter()
            .filter_map(|device_info| {
                if input_register.contains_key(&device_info.name) {
                    Some(device_info.name)
                } else {
                    None
                }
            })
            .collect()
    }

    /// Starts monitoring the connected devices for input changes.
    ///
    /// This method initializes the monitoring tasks for each connected joystick,
    /// allowing them to report input states asynchronously. It sets up a shutdown channel
    /// to gracefully stop monitoring when needed.
    ///
    /// # Example
    /// ```rust
    /// let mut pool = DevicePool::new(vec!["device1.toml".to_string()], 0.1);
    /// pool.start_monitoring().await;
    /// ```
    async fn start_monitoring(&mut self) {
        let running = *self.running.lock().unwrap();
        if running {
            return;
        }

        *self.running.lock().unwrap() = true;

        let (shutdown_tx, mut shutdown_rx) = mpsc::channel(1);
        self.shutdown_tx = Some(shutdown_tx);

        let input_register = Arc::clone(&self.input_register);
        let last_button_time = Arc::clone(&self.last_button_time);
        let running = Arc::clone(&self.running);
        let debounce_time = self.debounce_time;

        tokio::spawn(async move {
            let devices = fetch_connected_joysticks();
            let mut tasks = Vec::new();

            for device_info in devices {
                let input_register_clone = Arc::clone(&input_register);
                let last_button_time_clone = Arc::clone(&last_button_time);
                let running_clone = Arc::clone(&running);

                let task = tokio::spawn(async move {
                    Self::monitor_device(
                        device_info.path,
                        device_info.name,
                        input_register_clone,
                        last_button_time_clone,
                        running_clone,
                        debounce_time,
                    )
                    .await;
                });
                tasks.push(task);
            }

            tokio::select! {
                _ = shutdown_rx.recv() => {
                    for task in tasks {
                        task.abort();
                    }
                }
            }
        });
    }

    /// Stops monitoring the devices and cleans up resources.
    ///
    /// This method sets the running state to false, signaling all monitoring tasks to stop.
    /// It also sends a shutdown signal through the channel if it exists.
    ///
    /// # Example
    /// ```rust
    /// let mut pool = DevicePool::new(vec!["device1.toml".to_string()], 0.1);
    /// pool.stop_monitoring().await;
    /// ```
    async fn stop_monitoring(&mut self) {
        let running = *self.running.lock().unwrap();
        if !running {
            return;
        }

        *self.running.lock().unwrap() = false;

        if let Some(shutdown_tx) = self.shutdown_tx.take() {
            let _ = shutdown_tx.send(()).await;
        }
    }

    /// Monitors a single joystick device for input changes.
    ///
    /// This method continuously reads the state of the joystick and updates the input register
    /// with the current axes, buttons, and hats. It implements debouncing logic to prevent
    /// rapid button press registrations.
    ///
    /// # Arguments
    /// * `device_path` - The file path of the joystick device to monitor.
    /// * `device_name` - The name of the joystick device.
    /// * `input_register` - A shared reference to the input register where the state will be stored.
    /// * `last_button_time` - A shared reference to track the last time each button was pressed.
    /// * `running` - A shared reference indicating whether the monitoring is active.
    /// * `debounce_time` - The duration to wait before allowing another button press registration.
    ///
    /// # Example
    /// ```rust
    /// let device_path = "/dev/input/js0".to_string();
    /// let device_name = "Joystick 1".to_string();
    /// let input_register = Arc::new(Mutex::new(HashMap::new()));
    /// let last_button_time = Arc::new(Mutex::new(HashMap::new()));
    /// let running = Arc::new(Mutex::new(true));
    /// let debounce_time = Duration::from_millis(100);
    /// DevicePool::monitor_device(device_path, device_name, input_register, last_button_time, running, debounce_time).await;
    /// ```
    async fn monitor_device(
        device_path: String,
        device_name: String,
        input_register: Arc<Mutex<HashMap<String, JoystickState>>>,
        last_button_time: Arc<Mutex<HashMap<u16, Instant>>>,
        running: Arc<Mutex<bool>>,
        debounce_time: Duration,
    ) {
        let mut joystick = match Joystick::new(&device_path) {
            Ok(js) => js,
            Err(e) => {
                eprintln!("Failed to create joystick for {}: {}", device_name, e);
                return;
            }
        };

        println!("Started monitoring {}", device_name);

        while *running.lock().unwrap() {
            if let Ok(state) = joystick.get_state() {
                let axes = state.axes;
                let buttons = state.buttons;
                let hats = state.hats;

                let mut input_register = input_register.lock().unwrap();

                if let Some(input_data) = input_register.get_mut(&device_name) {
                    // Update axes
                    for (code, value) in axes {
                        input_data.axes.insert(code, value);
                    }

                    // Update buttons with debouncing
                    // Update buttons with debouncing
                    for (code, value) in buttons {
                        if Self::should_update_input(code, &last_button_time, debounce_time) {
                            input_data.buttons.insert(code, value);
                        }
                    }

                    // Update hats with debouncing
                    for (code, value) in hats {
                        if Self::should_update_input(code, &last_button_time, debounce_time) {
                            input_data.hats.insert(code, value);
                        }
                    }
                }
            }

            sleep(Duration::from_millis(10)).await;
        }

        println!("Stopped monitoring {}", device_name);
    }

    /// Determines if an input should be updated based on the debounce time.
    ///
    /// This method checks the last time a button was pressed and compares it
    /// with the current time. If the time since the last press is less than the
    /// debounce time, it returns false, indicating that the input should not be updated.
    /// Otherwise, it updates the last pressed time and returns true.
    ///
    /// # Arguments
    /// * `code` - The code of the button or hat being checked.
    /// * `last_button_time` - A shared reference to the last button press times.
    /// * `debounce_time` - The duration to wait before allowing another button press registration.
    ///
    /// # Returns
    /// A boolean indicating whether the input should be updated (true) or ignored (false).
    fn should_update_input(
        code: u16,
        last_button_time: &Arc<Mutex<HashMap<u16, Instant>>>,
        debounce_time: Duration,
    ) -> bool {
        let mut last_times = last_button_time.lock().unwrap();
        let now = Instant::now();

        if let Some(&last_time) = last_times.get(&code) {
            if now.duration_since(last_time) < debounce_time {
                return false;
            }
        }

        last_times.insert(code, now);
        true
    }

    /// Starts monitoring the devices for input changes.
    ///
    /// This method checks if the device pool is already running. If not, it starts monitoring
    /// the devices by calling `start_monitoring()`. It returns a vector of device names that are
    /// currently connected and registered in the input register.
    ///
    /// # Returns
    /// A vector of strings containing the names of devices that are currently connected
    /// and registered in the input register.
    /// # Example
    /// ```rust
    /// let mut pool = DevicePool::new(vec!["device1.toml".to_string()], 0.1);
    /// let connected_devices = pool.start().await;
    /// ```
    pub async fn stop(&mut self) {
        self.stop_monitoring().await;
    }
}

impl Drop for DevicePool {
    fn drop(&mut self) {
        let rt = tokio::runtime::Handle::try_current();
        if let Ok(handle) = rt {
            handle.spawn(async move {
                // Cannot call self.stop() here as we've moved self
            });
        }
    }
}
