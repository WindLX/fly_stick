use crate::utils::JoystickState;
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::fs;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[pyclass]
/// Represents a single device item with a unique code and optional alias.
///
/// This structure is used to identify and reference specific device components
/// or features within the system. Each device item has a mandatory numeric code
/// for identification and an optional human-readable alias for convenience.
///
/// # Fields
///
/// * `code` - A unique 16-bit identifier for the device item
/// * `alias` - An optional string alias that provides a more descriptive name
///
/// # Examples
///
/// ```rust
/// let device_item = DeviceItem {
///     code: 0x1001,
///     alias: Some("Temperature Sensor".to_string()),
/// };
/// ```
///
/// # Python Integration
///
/// This struct is exposed to Python through PyO3, allowing both fields to be
/// accessed as read-only properties from Python code.
pub struct DeviceItem {
    /// The code of the device item
    #[pyo3(get)]
    pub code: u16,
    /// An alias for the device item, used for easier reference
    #[pyo3(get)]
    pub alias: Option<String>,
}

#[pymethods]
/// Creates a new `DeviceItem` with the specified code and optional alias.
///
/// # Arguments
///
/// * `code` - A 16-bit unsigned integer representing the device code
/// * `alias` - An optional string alias for the device
///
/// # Returns
///
/// Returns a new instance of `DeviceItem` with the provided code and alias.
///
/// # Examples
///
/// ```
/// let device = DeviceItem::new(0x1234, Some("My Device".to_string()));
/// let device_no_alias = DeviceItem::new(0x5678, None);
/// ```
impl DeviceItem {
    #[new]
    fn new(code: u16, alias: Option<String>) -> Self {
        Self { code, alias }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[pyclass]
/// Represents a complete description of an input device configuration.
///
/// This struct contains metadata about the device as well as definitions for all
/// input elements (axes, buttons, and hats). It can be serialized/deserialized
/// and exposed to Python via PyO3.
///
/// # Fields
///
/// * `device_name` - The name of the device (defaults to a predefined value if not specified)
/// * `author` - Optional author information for the device configuration
/// * `created` - Optional creation date/time information
/// * `description` - Optional detailed description of the device
/// * `axes` - Vector of axis input definitions (defaults to empty if not specified)
/// * `buttons` - Vector of button input definitions (defaults to empty if not specified)
/// * `hats` - Vector of hat/D-pad input definitions (defaults to empty if not specified)
///
/// # Examples
///
/// ```rust
/// let device_desc = DeviceDescription {
///     device_name: "Custom Joystick".to_string(),
///     author: Some("John Doe".to_string()),
///     created: Some("2024-01-01".to_string()),
///     description: Some("A custom flight stick configuration".to_string()),
///     axes: vec![],
///     buttons: vec![],
///     hats: vec![],
/// };
/// ```
pub struct DeviceDescription {
    #[serde(default = "default_device_name")]
    #[pyo3(get)]
    pub device_name: String,
    #[pyo3(get)]
    pub author: Option<String>,
    #[pyo3(get)]
    pub created: Option<String>,
    #[pyo3(get)]
    pub description: Option<String>,
    #[serde(default)]
    #[pyo3(get)]
    pub axes: Vec<DeviceItem>,
    #[serde(default)]
    #[pyo3(get)]
    pub buttons: Vec<DeviceItem>,
    #[serde(default)]
    #[pyo3(get)]
    pub hats: Vec<DeviceItem>,
}

fn default_device_name() -> String {
    "Unknown Device".to_string()
}

#[pymethods]
/// Represents a device description containing metadata and input configuration.
///
/// This struct holds information about a device including its name, author, creation date,
/// description, and collections of input elements (axes, buttons, and hats). It provides
/// functionality to create instances from TOML configuration files and build initial
/// state representations for input handling.
///
/// # Fields
/// * `device_name` - The name of the device
/// * `author` - Optional author information
/// * `created` - Optional creation date/time
/// * `description` - Optional device description
/// * `axes` - Collection of axis input items
/// * `buttons` - Collection of button input items  
/// * `hats` - Collection of hat/directional pad input items
///
/// # Examples
/// ```rust
/// // Create from TOML file
/// let device = DeviceDescription::from_toml("config.toml")?;
///
/// // Build initial input state
/// let state = device.build_state();
/// ```
impl DeviceDescription {
    #[new]
    fn new(
        device_name: Option<String>,
        author: Option<String>,
        created: Option<String>,
        description: Option<String>,
        axes: Option<Vec<DeviceItem>>,
        buttons: Option<Vec<DeviceItem>>,
        hats: Option<Vec<DeviceItem>>,
    ) -> Self {
        Self {
            device_name: device_name.unwrap_or_else(default_device_name),
            author,
            created,
            description,
            axes: axes.unwrap_or_default(),
            buttons: buttons.unwrap_or_default(),
            hats: hats.unwrap_or_default(),
        }
    }

    /// Create a DeviceDescription instance from a TOML file.
    ///
    /// # Arguments
    /// * `toml_file` - Path to the TOML file containing device configuration
    ///
    /// # Returns
    /// DeviceDescription instance with axes, buttons, and hats populated
    #[staticmethod]
    pub fn from_toml(toml_file: &str) -> PyResult<Self> {
        let content = fs::read_to_string(toml_file)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(e.to_string()))?;
        let device: DeviceDescription = toml::from_str(&content)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        Ok(device)
    }

    /// Build a state dictionary from the device description.
    ///
    /// # Returns
    /// A HashMap with device state organized by type
    pub fn build_state(&self) -> JoystickState {
        let mut input_data = JoystickState::new();

        for axis in &self.axes {
            input_data.axes.insert(axis.code, 0.0);
        }

        for button in &self.buttons {
            input_data.buttons.insert(button.code, 0);
        }

        for hat in &self.hats {
            input_data.hats.insert(hat.code, 0);
        }

        input_data
    }
}

impl DeviceDescription {
    /// Create a DeviceDescription instance from a TOML file (Rust-only version).
    pub fn from_toml_rust(toml_file: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let content = fs::read_to_string(toml_file)?;
        let device: DeviceDescription = toml::from_str(&content)?;
        Ok(device)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_device_item_creation() {
        let item = DeviceItem::new(1, Some("test_alias".to_string()));
        assert_eq!(item.code, 1);
        assert_eq!(item.alias, Some("test_alias".to_string()));

        let item_no_alias = DeviceItem::new(2, None);
        assert_eq!(item_no_alias.code, 2);
        assert_eq!(item_no_alias.alias, None);
    }

    #[test]
    fn test_input_data_creation() {
        let input_data = JoystickState::new();
        assert!(input_data.axes.is_empty());
        assert!(input_data.buttons.is_empty());
        assert!(input_data.hats.is_empty());
    }

    #[test]
    fn test_device_description_creation() {
        let desc = DeviceDescription::new(
            Some("Test Device".to_string()),
            Some("Test Author".to_string()),
            Some("2023-01-01".to_string()),
            Some("Test Description".to_string()),
            Some(vec![DeviceItem::new(0, Some("X".to_string()))]),
            Some(vec![DeviceItem::new(1, Some("Button A".to_string()))]),
            Some(vec![DeviceItem::new(2, Some("Hat".to_string()))]),
        );

        assert_eq!(desc.device_name, "Test Device");
        assert_eq!(desc.author, Some("Test Author".to_string()));
        assert_eq!(desc.created, Some("2023-01-01".to_string()));
        assert_eq!(desc.description, Some("Test Description".to_string()));
        assert_eq!(desc.axes.len(), 1);
        assert_eq!(desc.buttons.len(), 1);
        assert_eq!(desc.hats.len(), 1);
    }

    #[test]
    fn test_device_description_defaults() {
        let desc = DeviceDescription::new(None, None, None, None, None, None, None);
        assert_eq!(desc.device_name, "Unknown Device");
        assert_eq!(desc.author, None);
        assert_eq!(desc.created, None);
        assert_eq!(desc.description, None);
        assert!(desc.axes.is_empty());
        assert!(desc.buttons.is_empty());
        assert!(desc.hats.is_empty());
    }

    #[test]
    fn test_build_state_empty() {
        let desc = DeviceDescription::new(None, None, None, None, None, None, None);
        let input_data = desc.build_state();
        assert!(input_data.axes.is_empty());
        assert!(input_data.buttons.is_empty());
        assert!(input_data.hats.is_empty());
    }

    #[test]
    fn test_build_state_with_items() {
        let desc = DeviceDescription::new(
            None,
            None,
            None,
            None,
            Some(vec![DeviceItem::new(0, None), DeviceItem::new(1, None)]),
            Some(vec![DeviceItem::new(2, None)]),
            Some(vec![DeviceItem::new(3, None)]),
        );

        let input_data = desc.build_state();

        assert_eq!(input_data.axes.len(), 2);
        assert_eq!(input_data.axes.get(&0), Some(&0.0));
        assert_eq!(input_data.axes.get(&1), Some(&0.0));

        assert_eq!(input_data.buttons.len(), 1);
        assert_eq!(input_data.buttons.get(&2), Some(&0));

        assert_eq!(input_data.hats.len(), 1);
        assert_eq!(input_data.hats.get(&3), Some(&0));
    }

    #[test]
    fn test_from_toml_rust_valid() {
        let toml_content = r#"
device_name = "Test Gamepad"
author = "Test Author"
created = "2023-01-01"
description = "A test gamepad"

[[axes]]
code = 0
alias = "X"

[[axes]]
code = 1
alias = "Y"

[[buttons]]
code = 304
alias = "A"

[[hats]]
code = 16
alias = "DPAD"
"#;

        let mut temp_file = NamedTempFile::new().unwrap();
        temp_file.write_all(toml_content.as_bytes()).unwrap();
        let path = temp_file.path().to_str().unwrap();

        let desc = DeviceDescription::from_toml_rust(path).unwrap();
        assert_eq!(desc.device_name, "Test Gamepad");
        assert_eq!(desc.author, Some("Test Author".to_string()));
        assert_eq!(desc.axes.len(), 2);
        assert_eq!(desc.buttons.len(), 1);
        assert_eq!(desc.hats.len(), 1);
        assert_eq!(desc.axes[0].code, 0);
        assert_eq!(desc.axes[0].alias, Some("X".to_string()));
    }

    #[test]
    fn test_from_toml_rust_minimal() {
        let toml_content = r#"
# Minimal TOML with defaults
"#;

        let mut temp_file = NamedTempFile::new().unwrap();
        temp_file.write_all(toml_content.as_bytes()).unwrap();
        let path = temp_file.path().to_str().unwrap();

        let desc = DeviceDescription::from_toml_rust(path).unwrap();
        assert_eq!(desc.device_name, "Unknown Device");
        assert_eq!(desc.author, None);
        assert!(desc.axes.is_empty());
        assert!(desc.buttons.is_empty());
        assert!(desc.hats.is_empty());
    }

    #[test]
    fn test_from_toml_rust_file_not_found() {
        let result = DeviceDescription::from_toml_rust("nonexistent_file.toml");
        assert!(result.is_err());
    }

    #[test]
    fn test_from_toml_rust_invalid_toml() {
        let invalid_toml = r#"
device_name = "Test
invalid toml content
"#;

        let mut temp_file = NamedTempFile::new().unwrap();
        temp_file.write_all(invalid_toml.as_bytes()).unwrap();
        let path = temp_file.path().to_str().unwrap();

        let result = DeviceDescription::from_toml_rust(path);
        assert!(result.is_err());
    }

    #[test]
    fn test_serde_serialization() {
        let desc = DeviceDescription::new(
            Some("Test Device".to_string()),
            Some("Author".to_string()),
            None,
            None,
            Some(vec![DeviceItem::new(0, Some("X".to_string()))]),
            None,
            None,
        );

        let serialized = toml::to_string(&desc).unwrap();
        let deserialized: DeviceDescription = toml::from_str(&serialized).unwrap();

        assert_eq!(desc.device_name, deserialized.device_name);
        assert_eq!(desc.author, deserialized.author);
        assert_eq!(desc.axes.len(), deserialized.axes.len());
        assert_eq!(desc.axes[0].code, deserialized.axes[0].code);
    }
}
