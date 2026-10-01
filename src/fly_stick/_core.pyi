"""fly_stick Rust 扩展（`fly_stick._core`）的公开类型声明。

本文件为 PyO3 导出的类与函数提供类型提示，供静态检查与 IDE 补全使用；
实际实现位于 Rust 侧 `src/` 下的绑定代码。
"""

class ActiveSidestickConfig:
    """主动侧杆的 UDP 通信与状态过期配置。

    描述 `ActiveSidestick` 与 Teensy 主动侧杆控制器通信时使用的本地绑定
    地址、目标主机、各通道端口以及遥测状态的有效期。

    Attributes:
        bind_host: 本地 UDP 绑定地址。
        teensy_host: Teensy 主动侧杆控制器的目标主机地址。
        command_port: 指令通道的 UDP 端口。
        logic_port: 逻辑通道的 UDP 端口。
        state_port: 状态遥测通道的 UDP 端口。
        stale_after_ms: 遥测过期阈值（毫秒）；超过该时长未收到状态包即视为
            过期。
    """

    bind_host: str
    teensy_host: str
    command_port: int
    logic_port: int
    state_port: int
    stale_after_ms: int

    def __init__(
        self,
        bind_host: str = "0.0.0.0",
        teensy_host: str = "30.30.30.6",
        command_port: int = 5405,
        logic_port: int = 5406,
        state_port: int = 5407,
        stale_after_ms: int = 100,
    ) -> None:
        """构造通信配置。

        Args:
            bind_host: 本地 UDP 绑定地址。
            teensy_host: Teensy 主动侧杆控制器的目标主机地址。
            command_port: 指令通道的 UDP 端口。
            logic_port: 逻辑通道的 UDP 端口。
            state_port: 状态遥测通道的 UDP 端口。
            stale_after_ms: 遥测过期阈值（毫秒），必须大于 0。

        Raises:
            ValueError: `stale_after_ms` 不大于 0 时抛出。
        """
        ...

class SidestickAxisTelemetry:
    """单根侧杆单个轴的力反馈遥测。

    Attributes:
        position_rad: 轴的角位置，单位弧度。
        velocity_rad_s: 轴的角速度，单位弧度每秒。
        current_a: 轴的电机电流，单位安培。
    """

    position_rad: float
    velocity_rad_s: float
    current_a: float

class SidestickStickTelemetry:
    """单根侧杆的俯仰与滚转遥测。

    Attributes:
        roll: 滚转轴遥测。
        pitch: 俯仰轴遥测。
    """

    roll: SidestickAxisTelemetry
    pitch: SidestickAxisTelemetry

class ActiveSidestickState:
    """一次主动侧杆状态快照。

    Attributes:
        stick_1: 一号杆的遥测。
        stick_2: 二号杆的遥测。
        ap_enabled: 自动驾驶是否启用。
        active: 主动侧杆是否处于激活状态。
        coupling_disconnected: 力耦合是否已断开。
        connected: 是否已收到状态包且未过期。
        stale: 是否超过 `stale_after_ms` 未收到状态包。
    """

    stick_1: SidestickStickTelemetry
    stick_2: SidestickStickTelemetry
    ap_enabled: bool
    active: bool
    coupling_disconnected: bool
    connected: bool
    stale: bool

class ActiveSidestick:
    """主动侧杆的异步客户端。

    通过 UDP 与 Teensy 主动侧杆控制器通信：拉取两根杆的力反馈遥测状态，
    并下发迎角与舵面偏度，用于力耦合与自动驾驶状态回显。

    Args:
        config: 通信配置；为 `None` 时使用各字段的默认值。

    Examples:
        ```python
        import asyncio

        from fly_stick import ActiveSidestick, ActiveSidestickConfig

        async def main() -> None:
            config = ActiveSidestickConfig(teensy_host="30.30.30.6")
            sidestick = ActiveSidestick(config)
            await sidestick.start()
            try:
                state = await sidestick.fetch(timeout_seconds=1.0)
                print(state.stick_1.roll.position_rad)
            finally:
                await sidestick.stop()

        asyncio.run(main())
        ```
    """

    def __init__(self, config: ActiveSidestickConfig | None = None) -> None:
        """记录配置，网络资源在 `start()` 中申请。

        Args:
            config: 通信配置；为 `None` 时使用各字段的默认值。
        """
        ...
    async def start(self) -> None:
        """启动 UDP 收发循环。

        绑定本地端口并开始接收遥测、发送指令；重复调用时直接返回。

        Raises:
            OSError: 套接字绑定或目标地址解析失败时抛出。
            ValueError: 配置参数或报文编码非法时抛出。
            RuntimeError: 连接不可用时抛出。
            TimeoutError: 底层 I/O 超时时抛出。
        """
        ...
    async def stop(self) -> None:
        """停止 UDP 收发循环并释放套接字。"""
        ...
    def fetch_nowait(self) -> ActiveSidestickState:
        """立即返回最近一次遥测快照，不等待新数据。

        Returns:
            ActiveSidestickState: 当前缓存的状态快照。

        Raises:
            RuntimeError: 尚未调用 `start()` 时抛出。
        """
        ...
    async def fetch(self, timeout_seconds: float | None = None) -> ActiveSidestickState:
        """等待并返回新的遥测状态。

        若已收到过状态包，则立即返回当前快照，否则等待新状态或超时。

        Args:
            timeout_seconds: 等待超时秒数；`None` 表示一直等待。

        Returns:
            ActiveSidestickState: 收到的状态快照。

        Raises:
            TimeoutError: 超过 `timeout_seconds` 仍未收到状态包时抛出。
            RuntimeError: 尚未调用 `start()` 或连接不可用时抛出。
            OSError: 其他底层 I/O 错误。
        """
        ...
    def send_aircraft_state(
        self, aoa_rad: float, elevator_rad: float, aileron_rad: float
    ) -> None:
        """向主动侧杆下发当前迎角与舵面偏度。

        Args:
            aoa_rad: 迎角，单位弧度。
            elevator_rad: 升降舵偏度，单位弧度。
            aileron_rad: 副翼偏度，单位弧度。

        Raises:
            RuntimeError: 尚未调用 `start()` 时抛出。
            OSError: 报文发送失败时抛出。
            ValueError: 报文编码失败时抛出。
        """
        ...
    @property
    def running(self) -> bool:
        """UDP 收发循环是否正在运行。"""
        ...

class JoystickInfo:
    """单个操纵杆设备的基本信息。

    Attributes:
        path: 设备节点路径，如 `/dev/input/event0`。
        name: 设备名称；读取失败时为 `"Unknown"`。
    """

    path: str
    name: str

    def __init__(self, path: str, name: str) -> None:
        """构造设备信息。

        Args:
            path: 设备节点路径。
            name: 设备名称。
        """
        ...

class JoystickState:
    """一次采样得到的完整操纵杆状态。

    包含按硬件 code 索引的轴、按键与帽开关（POV）数值。

    Attributes:
        axes: 轴 code 到归一化数值（约 -1.0 到 1.0）的映射。
        buttons: 按键 code 到按下状态（0 未按下，1 按下）的映射。
        hats: 帽开关 code 到方向值（-1、0 或 1）的映射。
    """

    axes: dict[int, float]
    buttons: dict[int, int]
    hats: dict[int, int]

    def __init__(self) -> None:
        """构造三个内部映射均为空的初始状态。"""
        ...
    def __eq__(self, value: object) -> bool:
        """比较轴、按键与帽开关是否逐一相等。"""
        ...
    def __repr__(self) -> str:
        """返回含轴、按键与帽开关的调试字符串。"""
        ...
    def to_dict(self) -> dict[str, dict[int, float | int]]:
        """转换为按硬件 code 索引的嵌套字典。

        Returns:
            dict[str, dict[int, float | int]]: 含 `"axes"`、`"buttons"` 与
            `"hats"` 三个键，其值为 code 到数值的字典。
        """
        ...

    def to_alias_dict(
        self, desc: DeviceDescription
    ) -> dict[str, dict[str, float | int]]:
        """转换为按别名索引的嵌套字典。

        Args:
            desc: 提供 code 到别名映射的设备描述。

        Returns:
            dict[str, dict[str, float | int]]: 含 `"axes"`、`"buttons"` 与
            `"hats"` 三个键，其值为别名到数值的字典；没有别名的输入项回退
            为 code 的字符串形式。
        """
        ...

    def get_alias_axes(self, desc: DeviceDescription) -> dict[str, float]:
        """按别名取出各轴数值。

        Args:
            desc: 提供轴 code 到别名映射的设备描述。

        Returns:
            dict[str, float]: 别名到轴数值的字典。
        """
        ...

    def get_alias_buttons(self, desc: DeviceDescription) -> dict[str, int]:
        """按别名取出各按键数值。

        Args:
            desc: 提供按键 code 到别名映射的设备描述。

        Returns:
            dict[str, int]: 别名到按键数值的字典。
        """
        ...

    def get_alias_hats(self, desc: DeviceDescription) -> dict[str, int]:
        """按别名取出各帽开关数值。

        Args:
            desc: 提供帽开关 code 到别名映射的设备描述。

        Returns:
            dict[str, int]: 别名到帽开关数值的字典。
        """
        ...

def fetch_connected_joysticks() -> list[JoystickInfo]:
    """枚举当前连接的输入设备。

    通过 evdev 枚举系统输入设备并保留设备路径与名称；名称读取失败时回退
    为 `"Unknown"`。

    Returns:
        list[JoystickInfo]: 已连接设备的信息列表。

    Examples:
        ```python
        from fly_stick import fetch_connected_joysticks

        for device in fetch_connected_joysticks():
            print(device.path, device.name)
        ```
    """
    ...

class DeviceButtonMode:
    """`PyDevicePool` 的按键触发模式。

    定义按键按下的两种登记方式：

    - `trigger`：仅在按下的瞬间登记一次，随后立即复位；适合开火、触发事件
      等每次按下只执行一次的动作。
    - `hold`：按住期间持续登记为按下；适合需要持续输入的交互。

    模式在创建 `PyDevicePool` 时指定，决定输入处理期间按键事件的语义。

    Examples:
        ```python
        from fly_stick import DeviceButtonMode

        mode = DeviceButtonMode.trigger()
        print(str(mode), mode == DeviceButtonMode.trigger())
        ```
    """

    def __init__(self, mode: str) -> None:
        """按字符串模式构造。

        Args:
            mode: 模式字符串，取值为 `"trigger"` 或 `"hold"`。

        Raises:
            ValueError: `mode` 不是 `"trigger"` 或 `"hold"` 时抛出。
        """
        ...

    @staticmethod
    def trigger() -> DeviceButtonMode:
        """返回 `trigger` 模式。

        Returns:
            DeviceButtonMode: `trigger` 模式常量。
        """
        ...
    @staticmethod
    def hold() -> DeviceButtonMode:
        """返回 `hold` 模式。

        Returns:
            DeviceButtonMode: `hold` 模式常量。
        """
        ...
    def __str__(self) -> str:
        """返回 `"Trigger"` 或 `"Hold"`。"""
        ...
    def __repr__(self) -> str:
        """返回 `DeviceButtonMode.Trigger` 形式的调试字符串。"""
        ...
    def __eq__(self, other: object) -> bool:
        """比较两个按键模式是否相同。"""
        ...

class DeviceItem:
    """设备输入项：硬件 code 与可选别名。

    Attributes:
        code: 硬件输入 code。
        alias: 便于阅读的别名；为 `None` 时仅以 code 标识。
    """

    code: int
    alias: str | None

    def __init__(self, code: int, alias: str | None = None) -> None:
        """按 code 与可选别名构造输入项。

        Args:
            code: 硬件输入 code。
            alias: 可选别名。
        """
        ...

class DeviceDescription:
    """完整描述一个操纵杆或手柄设备的输入布局。

    保存设备元数据（名称、作者、创建日期、说明）以及全部输入元素（轴、
    按键、帽开关）。既可从 TOML 文件加载，也可据此构造初始
    `JoystickState`。

    Attributes:
        device_name: 设备名称；未提供时默认为 `"Unknown Device"`。
        author: 设备描述的作者。
        created: 设备描述的创建日期或时间戳。
        description: 设备详细说明。
        axes: 轴输入项列表。
        buttons: 按键输入项列表。
        hats: 帽开关（POV）输入项列表。

    Examples:
        ```python
        from fly_stick import DeviceDescription

        device = DeviceDescription.from_toml("devices/Thrustmaster/ta320.toml")
        state = device.build_state()
        print(device.device_name, sorted(state.axes))
        ```
    """

    device_name: str
    author: str | None
    created: str | None
    description: str | None
    axes: list[DeviceItem]
    buttons: list[DeviceItem]
    hats: list[DeviceItem]

    def __init__(
        self,
        device_name: str | None = None,
        author: str | None = None,
        created: str | None = None,
        description: str | None = None,
        axes: list[DeviceItem] | None = None,
        buttons: list[DeviceItem] | None = None,
        hats: list[DeviceItem] | None = None,
    ) -> None:
        """构造设备描述。

        Args:
            device_name: 设备名称；为 `None` 时使用 `"Unknown Device"`。
            author: 作者。
            created: 创建日期或时间戳。
            description: 设备详细说明。
            axes: 轴输入项；为 `None` 时使用空列表。
            buttons: 按键输入项；为 `None` 时使用空列表。
            hats: 帽开关输入项；为 `None` 时使用空列表。
        """
        ...
    @staticmethod
    def from_toml(toml_file: str) -> DeviceDescription:
        """从 TOML 文件加载设备描述。

        Args:
            toml_file: TOML 配置文件路径。

        Returns:
            DeviceDescription: 解析得到的设备描述。

        Raises:
            OSError: 读取文件失败时抛出。
            ValueError: TOML 内容无法解析为设备描述时抛出。
        """
        ...

    def build_state(self) -> JoystickState:
        """按输入项构造初始状态。

        所有轴、按键与帽开关都置零，用于在收到真实输入前占位。

        Returns:
            JoystickState: 含全部已声明输入项且数值为零的状态。
        """
        ...

class PyJoystick:
    """单个操纵杆设备的高层封装。

    打开指定 evdev 设备并记录其轴、按键与帽开关能力，提供阻塞式状态读取；
    设备生命周期由该对象持有。

    Args:
        device_path: 设备节点路径，如 `/dev/input/event0`。

    Examples:
        ```python
        from fly_stick import PyJoystick

        joystick = PyJoystick("/dev/input/js0")
        state = joystick.get_state()
        print(state.axes, state.buttons, state.hats)
        ```
    """

    def __init__(self, device_path: str) -> None:
        """打开设备节点并缓存其轴、按键与帽开关能力。

        Args:
            device_path: 设备节点路径，如 `/dev/input/event0`。
        """
        ...
    def get_state(self) -> JoystickState:
        """读取一次当前状态。

        Returns:
            JoystickState: 本次采样的轴、按键与帽开关数值。

        Raises:
            OSError: 读取设备失败时抛出。
        """
        ...

class PyDevicePool:
    """多个操纵杆设备的异步状态池。

    按逻辑名称管理一组 `DeviceDescription`，异步初始化设备、合并各设备的
    输入状态并执行按键去抖；状态通过 `fetch` 系列方法获取。

    Args:
        device_descs: 逻辑设备名到设备描述的映射。
        debounce_seconds: 按键去抖间隔，单位秒；默认为 0.1。
        btn_mode: 按键触发模式，默认为 `hold`。

    Examples:
        ```python
        import asyncio

        from fly_stick import DeviceDescription, PyDevicePool

        async def main() -> None:
            pool = PyDevicePool(
                {
                    "ta320": DeviceDescription.from_toml(
                        "devices/Thrustmaster/ta320.toml"
                    ),
                }
            )
            await pool.reset()
            states = await pool.fetch(timeout_seconds=1.0)
            print(states["ta320"].axes)
            await pool.stop()

        asyncio.run(main())
        ```

    Note:
        设备池不再使用时应调用 `await pool.stop()`，以释放设备与后台任务。
    """

    def __init__(
        self,
        device_descs: dict[str, DeviceDescription],
        debounce_seconds: float = 0.1,
        btn_mode: DeviceButtonMode = ...,
    ) -> None:
        """记录设备描述、去抖时长与按键语义模式，设备在 `reset()` 中打开。

        Args:
            device_descs: 逻辑设备名到设备描述的映射。
            debounce_seconds: 按键与帽开关的去抖时长，单位秒。
            btn_mode: 按键语义模式，决定读取后是否清空按键与帽。
        """
        ...
    async def reset(self) -> dict[str, tuple[DeviceDescription, JoystickInfo]]:
        """按注册的设备描述初始化设备池并启动事件循环。

        必须在调用 `fetch` 系列方法之前等待本方法完成。

        Returns:
            dict[str, tuple[DeviceDescription, JoystickInfo]]: 逻辑设备名到
            `(设备描述, 设备信息)` 的映射。
        """
        ...

    def fetch_nowait(self) -> dict[str, JoystickState]:
        """非阻塞地返回各设备最近一次的状态。

        Returns:
            dict[str, JoystickState]: 逻辑设备名到当前状态的映射。

        Raises:
            RuntimeError: 设备池尚未初始化或已停止时抛出。

        Examples:
            ```python
            states = pool.fetch_nowait()
            for name, state in states.items():
                print(name, state.axes)
            ```
        """
        ...

    async def fetch(
        self, timeout_seconds: float | None = None
    ) -> dict[str, JoystickState]:
        """等待状态变化或超时，然后返回各设备状态。

        Args:
            timeout_seconds: 超时秒数；`None` 表示一直等待。

        Returns:
            dict[str, JoystickState]: 逻辑设备名到当前状态的映射。

        Raises:
            RuntimeError: 设备池未初始化、已停止或等待超时时抛出。
        """

    async def stop(self) -> None:
        """停止设备池并释放设备与后台任务。

        Note:
            设备池不再使用时务必调用本方法以完成清理。
        """
        ...

    @property
    def debounce_time(self) -> float:
        """当前按键去抖间隔，单位秒。"""
        ...
    @property
    def devices(self) -> dict[str, tuple[DeviceDescription, JoystickInfo]]:
        """已注册的逻辑设备名到 `(设备描述, 设备信息)` 的映射。"""
        ...
    @property
    def button_mode(self) -> DeviceButtonMode:
        """当前按键触发模式。"""
        ...
    @button_mode.setter
    def button_mode(self, mode: DeviceButtonMode) -> None:
        """设置按键触发模式。"""
        ...
