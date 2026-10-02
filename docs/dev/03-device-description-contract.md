# 设备描述契约

`DeviceDescription` 是逻辑输入布局和物理设备匹配规则的唯一配置对象。TOML 与 Python 构造器得到同一字段结构；设备池在每次 `reset()` 时验证并应用它。

## 字段与默认值

`device_name` 默认 `"Unknown Device"`；可选 `device_path` 精确指定 `/dev/input/event*` 节点；`author`、`created`、`description` 默认 `None`；`axes`、`buttons`、`hats` 默认空列表。`DeviceItem(code, alias=None)` 中 code 在各自分类内唯一；有效 alias key 是 alias 或 `str(code)`，也必须在该分类内唯一。空名称、空路径、空白 alias、重复 code 与重复有效 key 都是 `ValueError`。

三类 code 分别校验，所以相同数字可同时作为轴 code 和按键 code。alias 命名空间也按类别分开。

## 物理设备匹配

`reset()` 重新枚举 Linux 输入节点。描述不带 `device_path` 时，必须只有一台 `device_name` 完全相同的设备；零台抛 `LookupError`，多台抛 `ValueError`。带路径时，名称和路径必须同时匹配，否则抛 `LookupError`。多个逻辑设备匹配到同一路径或重复声明路径时抛 `ValueError`。

全部描述匹配完成后，池依次打开所有设备，全部成功才启动监视。中途打开失败会丢弃先前打开的句柄、清空活动设备表并抛 `OSError`。运行期间不自动重连；再次 `reset()` 会重新枚举、匹配和打开。

## 状态投影

`build_state()` 按描述建立完整的零值快照。底层 `PyJoystick.get_state()` 返回事件差分；池用差分更新快照。别名转换只包含状态中定义的 code，code 无 alias 时以十进制字符串为键。

## 来源

实现位于 `packages/fly_stick/src/inner/description.rs` 与 `packages/fly_stick/src/inner/device_pool.rs`；Python 签名见 `packages/fly_stick/src/fly_stick/_core.pyi`。现有 profile 清单与设备名示例见 `packages/fly_stick/devices/`。
