"""fly_stick Rust 扩展（`fly_stick._core`）的公开类型声明。

本文件为 PyO3 导出的类与函数提供类型提示，供静态检查与 IDE 补全使用；
实际实现位于 Rust 侧 `src/` 下的绑定代码。
"""

from asyncio import Future

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
    """轴、按键与方向帽状态；完整快照或本轮事件差分由读取方法决定。

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

    保存设备元数据（名称、可选设备路径、作者、创建日期、说明）以及全部输入元素（轴、
    按键、帽开关）。既可从 TOML 文件加载，也可据此构造初始
    `JoystickState`。

    Attributes:
        device_name: 设备名称；未提供时默认为 `"Unknown Device"`。
        device_path: 可选的 evdev 设备路径；同名设备不唯一时用它消歧。
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
    device_path: str | None
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
        device_path: str | None = None,
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
            device_path: 设备节点路径；为 `None` 时按唯一名称匹配。
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

    打开指定 evdev 设备并记录其轴、按键与帽开关能力，提供非阻塞的事件差分读取；
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
        """非阻塞地读取本批事件差分。

        Returns:
            JoystickState: 本次采样的轴、按键与帽开关数值。

        Raises:
            OSError: 读取设备失败时抛出。
        """
        ...

class PyDevicePool:
    """多个操纵杆设备的异步状态池。

    按逻辑名称管理一组 `DeviceDescription`，异步初始化设备、合并各设备的
    输入事件为完整快照并执行按键按下去抖；状态通过 `fetch` 系列方法获取。

    Args:
        device_descs: 逻辑设备名到设备描述的映射。
        debounce_seconds: 按键去抖间隔，单位秒；默认为 0.1。
        button_mode: 按键触发模式，默认为 `Hold`。

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
        button_mode: DeviceButtonMode = ...,
    ) -> None:
        """记录设备描述、去抖时长与按键语义模式，设备在 `reset()` 中打开。

        Args:
            device_descs: 逻辑设备名到设备描述的映射。
            debounce_seconds: 按钮按下边沿的去抖时长，单位秒；释放、轴与方向帽
                不受去抖影响。
            button_mode: 按键语义模式。
        """
        ...
    def reset(self) -> Future[dict[str, tuple[DeviceDescription, JoystickInfo]]]:
        """重新枚举、匹配并预打开全部设备，成功后启动监控。

        必须在调用 `fetch` 系列方法之前等待本方法完成。

        Returns:
            可等待的 Future；完成结果为逻辑设备名到 `(设备描述, 设备信息)` 的映射。

        Raises:
            LookupError: 某个描述没有匹配设备。
            ValueError: 名称匹配不唯一或配置重复。
            OSError: 任一设备打开失败；此时整个池保持停止。
        """
        ...

    def fetch_nowait(self) -> dict[str, JoystickState]:
        """非阻塞地返回各设备当前完整快照。

        本方法有独立读取进度；调用它不会消费 `fetch()` 等待的变化。

        Returns:
            可等待的 Future；完成结果为逻辑设备名到当前完整快照的映射。

        Raises:
            RuntimeError: 设备池尚未初始化或已停止时抛出。
            OSError: 监视设备发生读取故障时抛出，故障会停止整个池。

        Examples:
            ```python
            states = pool.fetch_nowait()
            for name, state in states.items():
                print(name, state.axes)
            ```
        """
        ...

    def fetch(
        self, timeout_seconds: float | None = None
    ) -> Future[dict[str, JoystickState]]:
        """等待状态变化或超时，然后返回各设备当前完整快照。

        同一设备池同时只允许一个 `fetch()` 等待；取消等待会释放该限制。
        `Trigger` 模式下每次按下会对每种读取入口锁存为一次脉冲；多次按下在
        两次观察之间合并为一个脉冲。`fetch()` 与 `fetch_nowait()` 的进度独立。

        Args:
            timeout_seconds: 超时秒数；`None` 表示一直等待。

        Returns:
            可等待的 Future；完成结果为逻辑设备名到当前完整快照的映射。

        Raises:
            RuntimeError: 设备池未运行，或已有另一 `fetch()` 等待。
            TimeoutError: 超时。
            OSError: 监控时设备读失败；整个池停止，需显式调用 `reset()` 恢复。
        """

    def stop(self) -> Future[None]:
        """停止设备池并释放设备与后台任务。

        Returns:
            可等待的 Future；全部监控任务退出并释放设备后以 `None` 完成。

        Note:
            设备池不再使用时务必等待本方法完成清理。
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
