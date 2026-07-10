use std::io;
use std::net::{IpAddr, SocketAddr};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use tokio::net::UdpSocket;
use tokio::sync::{watch, Notify};

pub const IQ24_SCALE: f32 = 16_777_216.0;
pub const LOGIC_PACKET_LEN: usize = 3;
pub const AIRCRAFT_PACKET_LEN: usize = 12;
pub const STATE_PACKET_LEN: usize = 48;

#[derive(Debug, Clone)]
pub struct ActiveSidestickConfigData {
    pub bind_host: String,
    pub teensy_host: String,
    pub command_port: u16,
    pub logic_port: u16,
    pub state_port: u16,
    pub stale_after: Duration,
}

impl Default for ActiveSidestickConfigData {
    fn default() -> Self {
        Self {
            bind_host: "0.0.0.0".to_string(),
            teensy_host: "30.30.30.6".to_string(),
            command_port: 5405,
            logic_port: 5406,
            state_port: 5407,
            stale_after: Duration::from_millis(100),
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct AxisTelemetryData {
    pub position_rad: f32,
    pub velocity_rad_s: f32,
    pub current_a: f32,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct StickTelemetryData {
    pub roll: AxisTelemetryData,
    pub pitch: AxisTelemetryData,
}

#[derive(Debug, Clone, Default)]
struct CachedState {
    stick_1: StickTelemetryData,
    stick_2: StickTelemetryData,
    ap_enabled: bool,
    active: bool,
    coupling_disconnected: bool,
    last_state_packet_at: Option<Instant>,
    has_state_packet: bool,
}

#[derive(Debug, Clone)]
pub struct ActiveSidestickStateData {
    pub stick_1: StickTelemetryData,
    pub stick_2: StickTelemetryData,
    pub ap_enabled: bool,
    pub active: bool,
    pub coupling_disconnected: bool,
    pub connected: bool,
    pub stale: bool,
}

pub struct ActiveSidestick {
    config: ActiveSidestickConfigData,
    cached: Arc<Mutex<CachedState>>,
    changed: Arc<Notify>,
    command_socket: Option<Arc<UdpSocket>>,
    shutdown: Option<watch::Sender<bool>>,
}

pub struct ActiveSidestickFetchContext {
    cached: Arc<Mutex<CachedState>>,
    changed: Arc<Notify>,
    stale_after: Duration,
}

impl ActiveSidestickFetchContext {
    pub async fn fetch(self, timeout: Option<Duration>) -> io::Result<ActiveSidestickStateData> {
        if self
            .cached
            .lock()
            .expect("Active sidestick state lock poisoned")
            .has_state_packet
        {
            return Ok(snapshot(&self.cached, self.stale_after));
        }

        let notified = self.changed.notified();
        match timeout {
            Some(timeout) => tokio::time::timeout(timeout, notified).await.map_err(|_| {
                io::Error::new(io::ErrorKind::TimedOut, "Active sidestick fetch timed out")
            })?,
            None => notified.await,
        }
        Ok(snapshot(&self.cached, self.stale_after))
    }
}

impl ActiveSidestick {
    pub fn new(config: ActiveSidestickConfigData) -> Self {
        Self {
            config,
            cached: Arc::new(Mutex::new(CachedState::default())),
            changed: Arc::new(Notify::new()),
            command_socket: None,
            shutdown: None,
        }
    }

    pub fn is_running(&self) -> bool {
        self.shutdown.is_some()
    }

    pub async fn start(&mut self) -> io::Result<()> {
        if self.is_running() {
            return Ok(());
        }

        let teensy_addr =
            resolve_target(&self.config.teensy_host, self.config.command_port).await?;
        let logic_socket =
            UdpSocket::bind(bind_addr(&self.config.bind_host, self.config.logic_port)).await?;
        let state_socket =
            UdpSocket::bind(bind_addr(&self.config.bind_host, self.config.state_port)).await?;
        let command_socket = Arc::new(UdpSocket::bind(bind_addr(&self.config.bind_host, 0)).await?);

        let (shutdown_tx, shutdown_rx) = watch::channel(false);
        spawn_logic_receiver(
            logic_socket,
            teensy_addr.ip(),
            self.config.command_port,
            Arc::clone(&self.cached),
            Arc::clone(&self.changed),
            shutdown_rx.clone(),
        );
        spawn_state_receiver(
            state_socket,
            teensy_addr.ip(),
            self.config.command_port,
            Arc::clone(&self.cached),
            Arc::clone(&self.changed),
            shutdown_rx,
        );

        self.command_socket = Some(command_socket);
        self.shutdown = Some(shutdown_tx);
        Ok(())
    }

    pub async fn stop(&mut self) {
        if let Some(shutdown) = self.shutdown.take() {
            let _ = shutdown.send(true);
        }
        self.command_socket = None;
    }

    pub async fn send_aircraft_state(
        &self,
        aoa_rad: f32,
        elevator_rad: f32,
        aileron_rad: f32,
    ) -> io::Result<()> {
        let socket = self.command_socket.as_ref().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::NotConnected,
                "Active sidestick is not started",
            )
        })?;
        let target = resolve_target(&self.config.teensy_host, self.config.command_port).await?;
        let packet = encode_aircraft_packet([aoa_rad, elevator_rad, aileron_rad])?;
        socket.send_to(&packet, target).await?;
        Ok(())
    }

    pub fn snapshot(&self) -> ActiveSidestickStateData {
        snapshot(&self.cached, self.config.stale_after)
    }

    pub fn fetch_context(&self) -> io::Result<ActiveSidestickFetchContext> {
        if !self.is_running() {
            return Err(io::Error::new(
                io::ErrorKind::NotConnected,
                "Active sidestick is not started. Call start() first.",
            ));
        }
        Ok(ActiveSidestickFetchContext {
            cached: Arc::clone(&self.cached),
            changed: Arc::clone(&self.changed),
            stale_after: self.config.stale_after,
        })
    }
}

fn bind_addr(host: &str, port: u16) -> String {
    format!("{host}:{port}")
}

async fn resolve_target(host: &str, port: u16) -> io::Result<SocketAddr> {
    let mut addresses = tokio::net::lookup_host(bind_addr(host, port)).await?;
    addresses.next().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::AddrNotAvailable,
            format!("No socket address found for {host}:{port}"),
        )
    })
}

fn accepts_sender(sender: SocketAddr, teensy_ip: IpAddr, command_port: u16) -> bool {
    sender.ip() == teensy_ip && sender.port() == command_port
}

fn spawn_logic_receiver(
    socket: UdpSocket,
    teensy_ip: IpAddr,
    command_port: u16,
    cached: Arc<Mutex<CachedState>>,
    changed: Arc<Notify>,
    mut shutdown: watch::Receiver<bool>,
) {
    tokio::spawn(async move {
        let mut buffer = [0_u8; LOGIC_PACKET_LEN];
        loop {
            tokio::select! {
                changed = shutdown.changed() => {
                    if changed.is_err() || *shutdown.borrow() {
                        break;
                    }
                }
                received = socket.recv_from(&mut buffer) => {
                    let Ok((len, sender)) = received else { break; };
                    if len != LOGIC_PACKET_LEN || !accepts_sender(sender, teensy_ip, command_port) {
                        continue;
                    }
                    let mut state = cached.lock().expect("Active sidestick state lock poisoned");
                    state.ap_enabled = buffer[0] != 0;
                    state.active = buffer[1] != 0;
                    state.coupling_disconnected = buffer[2] != 0;
                    drop(state);
                    changed.notify_waiters();
                }
            }
        }
    });
}

fn spawn_state_receiver(
    socket: UdpSocket,
    teensy_ip: IpAddr,
    command_port: u16,
    cached: Arc<Mutex<CachedState>>,
    changed: Arc<Notify>,
    mut shutdown: watch::Receiver<bool>,
) {
    tokio::spawn(async move {
        let mut buffer = [0_u8; STATE_PACKET_LEN];
        loop {
            tokio::select! {
                changed = shutdown.changed() => {
                    if changed.is_err() || *shutdown.borrow() {
                        break;
                    }
                }
                received = socket.recv_from(&mut buffer) => {
                    let Ok((len, sender)) = received else { break; };
                    if len != STATE_PACKET_LEN || !accepts_sender(sender, teensy_ip, command_port) {
                        continue;
                    }
                    let Ok((stick_1, stick_2)) = decode_state_packet(&buffer) else { continue; };
                    let mut state = cached.lock().expect("Active sidestick state lock poisoned");
                    state.stick_1 = stick_1;
                    state.stick_2 = stick_2;
                    state.last_state_packet_at = Some(Instant::now());
                    state.has_state_packet = true;
                    drop(state);
                    changed.notify_waiters();
                }
            }
        }
    });
}

fn snapshot(cached: &Arc<Mutex<CachedState>>, stale_after: Duration) -> ActiveSidestickStateData {
    let state = cached.lock().expect("Active sidestick state lock poisoned");
    let stale = state
        .last_state_packet_at
        .map(|received_at| received_at.elapsed() > stale_after)
        .unwrap_or(true);
    ActiveSidestickStateData {
        stick_1: state.stick_1.clone(),
        stick_2: state.stick_2.clone(),
        ap_enabled: state.ap_enabled,
        active: state.active,
        coupling_disconnected: state.coupling_disconnected,
        connected: state.has_state_packet && !stale,
        stale,
    }
}

pub fn encode_iq24(value: f32) -> io::Result<[u8; 4]> {
    if !value.is_finite() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "IQ24 value must be finite",
        ));
    }
    let scaled = value * IQ24_SCALE;
    if scaled < i32::MIN as f32 || scaled > i32::MAX as f32 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "IQ24 value is out of range",
        ));
    }
    Ok((scaled as i32).to_be_bytes())
}

pub fn decode_iq24(bytes: &[u8]) -> io::Result<f32> {
    let raw: [u8; 4] = bytes.try_into().map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "IQ24 field must contain exactly four bytes",
        )
    })?;
    Ok(i32::from_be_bytes(raw) as f32 / IQ24_SCALE)
}

pub fn encode_aircraft_packet(values: [f32; 3]) -> io::Result<[u8; AIRCRAFT_PACKET_LEN]> {
    let mut packet = [0_u8; AIRCRAFT_PACKET_LEN];
    for (index, value) in values.into_iter().enumerate() {
        packet[index * 4..(index + 1) * 4].copy_from_slice(&encode_iq24(value)?);
    }
    Ok(packet)
}

pub fn decode_state_packet(packet: &[u8]) -> io::Result<(StickTelemetryData, StickTelemetryData)> {
    if packet.len() != STATE_PACKET_LEN {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Active sidestick state packet must be 48 bytes",
        ));
    }
    let mut values = [0_f32; 12];
    for (index, field) in packet.chunks_exact(4).enumerate() {
        values[index] = decode_iq24(field)?;
    }
    Ok((
        StickTelemetryData {
            roll: AxisTelemetryData {
                position_rad: values[0],
                velocity_rad_s: values[1],
                current_a: values[2],
            },
            pitch: AxisTelemetryData {
                position_rad: values[3],
                velocity_rad_s: values[4],
                current_a: values[5],
            },
        },
        StickTelemetryData {
            roll: AxisTelemetryData {
                position_rad: values[6],
                velocity_rad_s: values[7],
                current_a: values[8],
            },
            pitch: AxisTelemetryData {
                position_rad: values[9],
                velocity_rad_s: values[10],
                current_a: values[11],
            },
        },
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn unused_port() -> u16 {
        std::net::UdpSocket::bind("127.0.0.1:0")
            .unwrap()
            .local_addr()
            .unwrap()
            .port()
    }

    #[test]
    fn iq24_uses_big_endian_signed_encoding() {
        assert_eq!(encode_iq24(0.5).unwrap(), [0x00, 0x80, 0x00, 0x00]);
        assert_eq!(encode_iq24(-0.5).unwrap(), [0xff, 0x80, 0x00, 0x00]);
        assert_eq!(decode_iq24(&[0xff, 0x80, 0x00, 0x00]).unwrap(), -0.5);
    }

    #[test]
    fn state_packet_maps_two_sticks_in_firmware_order() {
        let mut packet = [0_u8; STATE_PACKET_LEN];
        for index in 0..12 {
            packet[index * 4..(index + 1) * 4]
                .copy_from_slice(&encode_iq24(index as f32 + 0.25).unwrap());
        }
        let (stick_1, stick_2) = decode_state_packet(&packet).unwrap();
        assert_eq!(stick_1.roll.position_rad, 0.25);
        assert_eq!(stick_1.pitch.current_a, 5.25);
        assert_eq!(stick_2.roll.position_rad, 6.25);
        assert_eq!(stick_2.pitch.current_a, 11.25);
        assert!(decode_state_packet(&packet[..47]).is_err());
    }

    #[test]
    fn aircraft_packet_has_three_iq24_fields() {
        let packet = encode_aircraft_packet([0.5, -0.5, 1.0]).unwrap();
        assert_eq!(packet.len(), AIRCRAFT_PACKET_LEN);
        assert_eq!(&packet[..4], &[0x00, 0x80, 0x00, 0x00]);
        assert_eq!(&packet[4..8], &[0xff, 0x80, 0x00, 0x00]);
    }

    #[tokio::test]
    async fn accepts_valid_udp_telemetry_and_marks_stale_after_timeout() {
        let command_port = unused_port();
        let logic_port = unused_port();
        let state_port = unused_port();
        let config = ActiveSidestickConfigData {
            bind_host: "127.0.0.1".to_string(),
            teensy_host: "127.0.0.1".to_string(),
            command_port,
            logic_port,
            state_port,
            stale_after: Duration::from_millis(5),
        };
        let mut sidestick = ActiveSidestick::new(config);
        sidestick.start().await.unwrap();

        let sender = UdpSocket::bind(("127.0.0.1", command_port)).await.unwrap();
        sender
            .send_to(&[1, 1, 0], ("127.0.0.1", logic_port))
            .await
            .unwrap();
        let mut packet = [0_u8; STATE_PACKET_LEN];
        packet[..4].copy_from_slice(&encode_iq24(0.25).unwrap());
        sender
            .send_to(&packet, ("127.0.0.1", state_port))
            .await
            .unwrap();

        let received = sidestick
            .fetch_context()
            .unwrap()
            .fetch(Some(Duration::from_millis(100)))
            .await
            .unwrap();
        assert!(received.connected);
        assert!(!received.stale);
        assert!(received.ap_enabled);
        assert!(received.active);
        assert_eq!(received.stick_1.roll.position_rad, 0.25);

        tokio::time::sleep(Duration::from_millis(10)).await;
        assert!(sidestick.snapshot().stale);
        sidestick.stop().await;
    }

    #[tokio::test]
    async fn sends_aircraft_state_to_the_configured_teensy_port() {
        let command_port = unused_port();
        let logic_port = unused_port();
        let state_port = unused_port();
        let listener = UdpSocket::bind(("127.0.0.1", command_port)).await.unwrap();
        let config = ActiveSidestickConfigData {
            bind_host: "127.0.0.1".to_string(),
            teensy_host: "127.0.0.1".to_string(),
            command_port,
            logic_port,
            state_port,
            stale_after: Duration::from_millis(100),
        };
        let mut sidestick = ActiveSidestick::new(config);
        sidestick.start().await.unwrap();
        sidestick.send_aircraft_state(0.5, -0.5, 1.0).await.unwrap();

        let mut received = [0_u8; AIRCRAFT_PACKET_LEN];
        let (len, _) = listener.recv_from(&mut received).await.unwrap();
        assert_eq!(len, AIRCRAFT_PACKET_LEN);
        assert_eq!(received, encode_aircraft_packet([0.5, -0.5, 1.0]).unwrap());
        sidestick.stop().await;
    }

    #[tokio::test]
    async fn ignores_telemetry_from_an_unexpected_sender_port() {
        let command_port = unused_port();
        let logic_port = unused_port();
        let state_port = unused_port();
        let unexpected_port = unused_port();
        let config = ActiveSidestickConfigData {
            bind_host: "127.0.0.1".to_string(),
            teensy_host: "127.0.0.1".to_string(),
            command_port,
            logic_port,
            state_port,
            stale_after: Duration::from_millis(100),
        };
        let mut sidestick = ActiveSidestick::new(config);
        sidestick.start().await.unwrap();

        let sender = UdpSocket::bind(("127.0.0.1", unexpected_port))
            .await
            .unwrap();
        sender
            .send_to(&[0_u8; STATE_PACKET_LEN], ("127.0.0.1", state_port))
            .await
            .unwrap();
        tokio::time::sleep(Duration::from_millis(5)).await;

        let state = sidestick.snapshot();
        assert!(!state.connected);
        assert!(state.stale);
        sidestick.stop().await;
    }
}
