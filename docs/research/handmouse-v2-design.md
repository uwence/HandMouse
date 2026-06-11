# HandMouse v2 设计文档
版本: v0.1
状态: 可直接交给 backend-eng 实现
范围: 单手 webcam 指针控制 + 手势快捷动作 + 显式激活态 + 60fps MVO
---
## 读者说明
- 这份文档把 T2 / T3 / T4 三份研究报告合并为一个可实现方案。； - 所有硬数字都标注了来源，优先引用阶段研究、现有代码、以及可验证公开文档。
- 这不是“继续研究”的文档，而是“拆任务开工”的文档。； - 如果实现过程中发现与本文冲突，优先以公开 API 行为和真实 benchmark 为准。
---
## A. Executive Summary
1. v2 默认走“相对指针 + 自适应 gain + 双阈值 pinch + 显式激活态”，不是绝对映射。[src: T4 §1, §2, §3, §4]； 2. 主链路必须从 `IMAGE + detect()` 改成 `VIDEO + detect_for_video(ms)`，并保留 `LIVE_STREAM + detect_async()` 作为可选异步路径。[src: T3 §1, MediaPipe docs]
3. 60fps 的关键不是先做量化，而是先把“旧帧积压”去掉，确保 latest-frame semantics。[src: T3 §3]； 4. 指针控制要引入 `pointer_engine.py`，把手部归一化、速度分段增益、深度补偿和 dead zone 收拢到一个独立层。[src: T4 §2, §5, §6]
5. `GestureDetector` 需要从 press-to-click 改成 release-to-commit，这样 pinch 才不会在 hold 时立即点击。[src: T4 §3]； 6. `GrabScrollDetector` 需要从“抓住即滚动”升级成“保持 + 移动 = scroll，释放 = stop”的状态机。[src: T4 §4]
7. 现有 `shortcut_detector.py` 可以保留，但它应被放在显式激活态之后，而不是和鼠标主路径耦合。[src: current code]； 8. 当前代码里 `HandTracker` 仍是 `running_mode=IMAGE` 且调用 `detect()`，这是 v2 首要技术债。[src: current code, T3 §1]
9. 当前代码里默认摄像头分辨率是 1280x720，v2 主路径应先降到 640x480，再视实测决定是否回升。[src: T3 §2, current code]； 10. Debug overlay 要显示激活态、pinch 距离、速度、加速度、输出 delta、fps、帧龄和摄像头 backend。[src: T3 §4, current code]
---
## B. 目标与非目标
### B.1 目标
- 相对指针控制。； - 自适应加速曲线。
- 双阈值 pinch。； - 显式激活态。
- 异步 MediaPipe VIDEO 流。； - 60fps MVO。
- 低延迟、低积压、可调试、可回退。
### B.2 非目标
- 双手交互。； - 自训练模型。
- GUI / Tray 常驻产品化。； - 平台移植到 macOS / Linux / Android。
- 把整个系统改成绝对定位。
### B.3 产品边界
- 单手足够完成指针、滚动、快捷动作。[src: T2 §2.3]； - 主路径必须能在普通 Windows 笔记本上工作。
- 只有在 v2 稳定后，才讨论更激进的 ROI 裁剪、GPU 后端或自训模型。
### B.4 与现有实现的关系
- v1 现有结构已经有 `camera.py`、`hand_tracker.py`、`pointer_mapper.py`、`gesture_detector.py`、`grab_scroll_detector.py`、`shortcut_detector.py`、`shortcut_controller.py`、`mouse_controller.py`、`debug_view.py`、`config.py`。[src: current code]； - v2 不是推倒重来，而是把这些模块重新分层。
- 最核心的新增文件是 `pointer_engine.py`。； - 最核心的新增概念是 `engagement.py`。
---
## C. 架构图
```mermaid
graph TD
    A[CameraCaptureThread] --> B[FrameBuffer(latest, size=1)]
    B --> C[HandLandmarkerWorker]
    C -->|VIDEO: detect_for_video(ms)| D[HandTrackingResult]
    C -->|optional LIVE_STREAM: detect_async| D
    D --> E[PointerEngine]
    D --> F[GestureFSM]
    D --> G[GrabScrollFSM]
    D --> H[ShortcutDetector]
    E --> I[MouseController]
    F --> I
    G --> J[ScrollController]
    H --> K[ShortcutController]
    D --> L[DebugOverlay]
    E --> L
    F --> L
    G --> L
    H --> L
    M[Hotkey/State Overlay] --> N[EngagementFSM]
    N --> E
    N --> F
    N --> G
    N --> K
    N --> L
```
### 架构说明
- Camera 线程只负责拿最新帧，不负责业务逻辑。[src: T3 §3]； - HandLandmarkerWorker 只负责推理，不负责鼠标注入。
- PointerEngine 只负责从手部结果产生 `ScreenDelta`。； - GestureFSM 只负责 pinch / activation 事件。
- GrabScrollFSM 只负责抓取滚动。； - ShortcutDetector 只负责 swipe 类快捷动作。
- DebugOverlay 只显示状态，不做决策。； - Hotkey / State Overlay 是统一的激活门控入口。
---
## D. 模块设计
### D.1 `camera.py`
#### 文件职责
- 打开摄像头。； - 指定分辨率。
- 指定 backend。； - 保证只保留最新帧。
- 负责摄像头释放。
#### 现状
- 当前 `CameraConfig` 只有 `width`、`height`、`index`。[src: current code]； - 当前默认值是 1280x720, index=0。[src: config.py]
- 当前 `Camera.read()` 有重试逻辑，说明读帧不稳是已知问题。[src: current code]
#### v2 设计
- 增加 `backend_preference`。； - 增加 `buffer_size=1`。
- 默认主路径使用 `640x480`。； - fallback 允许 `960x540` 或 `1280x720`。
- 读帧语义必须是 latest-frame，而不是 FIFO 队列。
#### 公共 API
- `Camera.open()`； - `Camera.read() -> (ok, frame)`
- `Camera.release()`； - `Camera.frame_age_ms()`
- `Camera.backend_name`
#### 关键参数
- `width`: 640 / 960 / 1280； - `height`: 480 / 540 / 720
- `index`: 0 为默认摄像头； - `backend_preference`: `CAP_DSHOW` 优先，`CAP_MSMF` 次之，`CAP_ANY` 兜底。[src: T3 §4]
- `buffer_size`: 1
#### 内部状态机
- `CLOSED`； - `OPENING`
- `OPEN`； - `DEGRADED`
- `FAILED`
#### 设计理由
- OpenCV 允许显式指定 backend，Windows 上不该交给默认猜测。[src: T3 §4, OpenCV docs]； - 缓冲压到 1 的目的是丢旧帧，不是追求高吞吐。
- 对交互系统，旧帧比丢帧更糟。[src: T3 §3]
---
### D.2 `hand_tracker.py`
#### 文件职责
- 管理 MediaPipe Hand Landmarker。； - 将 BGR frame 转成 MediaPipe image。
- 产出单手追踪结果。； - 管理模型下载与本地缓存。
#### 现状
- 当前构造器用 `running_mode=IMAGE`。[src: current code]； - 当前调用的是 `detect(image)`。[src: current code]
- 当前默认 `max_num_hands=2`。[src: current code]； - 当前默认模型下载到 `~/.handmouse/models/hand_landmarker.task`。[src: current code]
#### v2 设计
- 默认切到 `running_mode=VIDEO`。； - 主路径使用 `detect_for_video(mp_image, frame_timestamp_ms)`。
- 可选路径保留 `running_mode=LIVE_STREAM` + `detect_async()`。； - 默认 `max_num_hands=1`。
- 结果对象要携带 handedness、confidence、landmarks、thumb_tip、index_tip。
#### 公共 API
- `HandTracker.process(frame_bgr, frame_timestamp_ms) -> HandTrackingResult`； - `HandTracker.process_async(frame_bgr, frame_timestamp_ms, callback)`
- `HandTracker.close()`
#### 关键参数
- `running_mode`: `VIDEO` 默认，`LIVE_STREAM` 可选。[src: T3 §1, MediaPipe docs]； - `frame_timestamp_ms`: `int(time.perf_counter() * 1000)`。[src: task body]
- `min_hand_detection_confidence`: 0.5 起步，误检多时上调到 0.6~0.7。[src: T2 §2.2]； - `min_hand_presence_confidence`: 0.5 起步。[src: T2 §2.2]
- `min_tracking_confidence`: 0.5 起步。[src: T2 §2.2]； - `num_hands`: 1。[src: T2 §2.2]
#### 内部状态机
- `UNINITIALIZED`； - `READY`
- `TRACKING`； - `MISSING`
- `RECOVERING`； - `CLOSED`
#### 设计理由
- MediaPipe 官方明确说明，video / live stream 模式会利用 tracking 来避免每帧都触发 palm detection，从而降低 latency。[src: MediaPipe docs]； - 官方 Python guide 明确暴露 `detect`、`detect_for_video`、`detect_async` 三种调用方式。[src: MediaPipe docs]
- v2 的关键不是“有没有模型”，而是“有没有吃到 tracking 复用”。[src: T3 §1]
#### 返回结构
- `landmarks: list[FramePoint]`； - `thumb_tip: FramePoint | None`
- `index_tip: FramePoint | None`； - `raw_landmarks: Any | None`
- `handedness_label: str | None`； - `handedness_confidence: float | None`
---
### D.3 `pointer_engine.py`
#### 文件职责
- 消费 index tip、palm width、hand center、上一帧状态。； - 输出 `ScreenDelta`。
- 管理速度、加速度、深度补偿、dead zone 和滤波。
#### 为什么要新建
- 现在的 `pointer_mapper.py` 是线性 gain + smoothing，功能太窄。[src: current code]； - v2 的指针层需要显式建模速度和手部尺度，而不是只看一个点位移。
- 这层一旦和 gesture FSM 绑死，后面很难单独调参。
#### 公共 API
- `PointerEngine.update(hand_result, now_ms) -> ScreenDelta | None`； - `PointerEngine.reset()`
- `PointerEngine.last_frame_point`； - `PointerEngine.last_velocity`
- `PointerEngine.last_gain`； - `PointerEngine.last_depth_factor`
#### 输入
- index tip 的 FramePoint。； - palm width 或 hand scale。
- hand center。； - 上一帧控制点。
- 当前时间戳。
#### 输出
- `dx: int`； - `dy: int`
- 仅输出整数像素位移。
#### 核心公式
- 输入归一化到 control region。[src: T4 §2, current code]； - 速度定义：`v = Δnorm / Δt`，单位是 palm-width/s。[src: T4 §2]
- 增益函数：`g(v)` 分段平滑。[src: T4 §2]； - 深度补偿：`A_z = clamp((s_ref / s_t)^gamma, z_min, z_max)`。[src: T4 §5]
- 最终位移：`Δcursor = K * g(v) * A_active * A_z * u_t`。[src: T4 §2, §5]
#### 建议默认值
- `v_jitter = 0.20 palm-width/s`。[src: T4 §8]； - `v_mid = 1.0 palm-width/s`。[src: T4 §8]
- `v_fast = 3.0 palm-width/s`。[src: T4 §8]； - `g_lo = 0.85`。[src: T4 §8]
- `g_hi = 3.0`。[src: T4 §8]； - `gamma = 0.7 ~ 1.2`，默认 0.9。[src: T4 §5]
- `z_min = 0.70`。[src: T4 §5]； - `z_max = 1.25`。[src: T4 §5]
- `dead_zone_radius = 0.15 ~ 0.30 palm-width/s`。[src: T4 §6]
#### 内部状态机
- `IDLE`； - `ARMED`
- `ACTIVE`； - `COOLDOWN`
#### 设计理由
- 自由空间输入更像 mouse-like relative control，而不是 touchpad absolute mapping。[src: T4 §1, §7]； - 纯线性 gain 对低速精度和高速跨屏都不好。[src: T4 §2]
- dead zone 应该放在输入空间，不应把屏幕中心做成死区。[src: T4 §6]； - 深度补偿应该是修正项，不是主控制量。[src: T4 §5]
---
### D.4 `engagement.py`
#### 文件职责
- 统一管理“有没有进入控制模式”。； - 将手在镜头前和真正允许输出指针这两个概念分离。
- 连接 hotkey 和姿势激活。
#### 为什么要新建
- 现有代码没有“激活态”概念。[src: current code]； - 现在 debug / control 只是按键切换，不足以表达真正的控制门控。
- v2 必须有 `idle -> armed -> active -> cooldown` 这种明确状态。
#### 公共 API
- `EngagementFSM.update(hotkey_state, pose_state, now_ms) -> EngagementResult`； - `EngagementFSM.arm()`
- `EngagementFSM.disarm()`； - `EngagementFSM.toggle_active()`
- `EngagementFSM.reset()`
#### 建议输入
- `hotkey_m_pressed: bool`； - `palm_visible: bool`
- `palm_hold_ms: int`； - `hand_lost: bool`
- `escape_requested: bool`
#### 建议输出
- `is_active: bool`； - `state: EngagementState`
- `reason: str`
#### 建议默认值
- `activation_hotkey = m`； - `palm_hold_ms = 200`
- `cooldown_ms = 50 ~ 150`； - `auto_idle_after_missing_frames = 3 ~ 5`
#### 内部状态机
- `IDLE`； - `ARMED`
- `ACTIVE`； - `COOLDOWN`
#### 设计理由
- 激活态是自由空间输入的基本安全门。[src: T4 §4]； - 显式开关是最稳的主入口；姿势激活是无键盘备选。[src: T4 §4]
- ROI / z-band 适合做安全门禁，不适合做主逻辑。[src: T4 §4]
---
### D.5 `gesture_detector.py`
#### 文件职责
- 从 thumb tip 与 index tip 计算 pinch 状态。； - 产出 click / hold / release 事件。
- 管理 pinch 的 hysteresis。
#### 现状
- 当前状态机是 `NO_HAND -> MOVING -> PINCH_CANDIDATE -> CLICK -> COOLDOWN`。[src: current code]； - 当前逻辑是 hold 到 `hold_ms` 就立即 click。[src: current code]
- 当前 config 是单阈值 `pinch_threshold` + `release_threshold`。[src: config.py]
#### v2 设计
- 改成 release-to-commit。； - 状态机应是 `PINCH_OPEN -> PINCH_PRESSED -> PINCH_HOLD -> EMIT_CLICK`。
- click 只在“松开”时发出，而不是在 hold 达标时立刻发出。； - pinch 距离必须双阈值。
#### 公共 API
- `GestureDetector.update(thumb, index, now_ms) -> GestureResult`； - `GestureDetector.reset()`
#### 建议参数
- `pinch_close = 0.05`。[src: T4 §8, T2 §3.1]； - `pinch_open = 0.075`。[src: T4 §8, T2 §3.1]
- `pinch_confirm_frames = 2 ~ 3`。[src: T4 §3, §8]； - `cooldown_ms = 120 ~ 250`
- `release_confirm_frames = 2 ~ 3`
#### 内部状态机
- `PINCH_OPEN`； - `PINCH_PRESSED`
- `PINCH_HOLD`； - `EMIT_CLICK`
- `COOLDOWN`
#### 设计理由
- 单阈值容易在临界点抖动。[src: T4 §3]； - release-to-commit 更适合“按下-保持-松开”的 mouse click 语义。
- 这个改动会把误触显著压下去。
---
### D.6 `grab_scroll_detector.py`
#### 文件职责
- 识别抓握姿势。； - 在抓握姿势下把位移转换成 scroll delta。
- 松开后停止滚动。
#### 现状
- 当前状态机是 `NO_HAND -> CANDIDATE -> GRABBING -> DRAGGING -> RELEASED`。[src: current code]； - 当前实现已经包含 `hold_ms`、`release_grace_ms`、`dead_zone`、`scroll_sensitivity`、`max_scroll_per_frame`。[src: config.py, current code]
- 当前判断抓握用到了 thumb/index 距离、curl 比例和最少弯曲手指数。[src: current code]
#### v2 设计
- 保留现有几何判断。； - 更强调“保持 + 移动 = scroll，释放 = stop”。
- 允许在抓握中先经过短暂 hold，再进入滚动输出。； - 保留 release grace，防止瞬间掉检测就退出。
#### 公共 API
- `GrabScrollDetector.update(landmarks, now_ms) -> GrabScrollResult`； - `GrabScrollDetector.reset()`
#### 建议参数
- `hold_ms = 120`。[src: current config]； - `release_grace_ms = 120`。[src: current config]
- `dead_zone = 0.015`。[src: current config]； - `scroll_sensitivity = 180.0`。[src: current config]
- `max_scroll_per_frame = 18`。[src: current config]； - `thumb_index_max_distance = 1.8`。[src: current config]
- `curled_finger_ratio = 1.65`。[src: current config]； - `min_curled_fingers = 2`。[src: current config]
#### 内部状态机
- `NO_HAND`； - `CANDIDATE`
- `GRABBING`； - `DRAGGING`
- `RELEASED`
#### 设计理由
- 这个模块可以复用现有几何，不必为 v2 重写。[src: T4 §4, current code]； - 关键是把它从主鼠标路径里解耦出来，避免滚动和指针抢节奏。
---
### D.7 `shortcut_detector.py`
#### 文件职责
- 识别 swipe 类快捷动作。； - 提供 left / right / up / down 四类动作。
- 作为可选快捷通道。
#### 现状
- 当前状态机是 `NO_HAND -> TRACKING -> DETECTED -> COOLDOWN`。[src: current code]； - 当前分类依据是 `min_distance` 与 `axis_ratio`。[src: current code]
- 当前动作会交给 `shortcut_controller.py` 触发键盘或滚轮操作。[src: current code]
#### v2 设计
- 保留该模块，但它必须在 `EngagementFSM` 激活后才可触发。； - 在 debug overlay 中显示快捷动作状态。
- 让它继续服务“辅助动作”，不要侵入主指针闭环。
#### 公共 API
- `ShortcutDetector.update(point, now_ms) -> ShortcutResult`； - `ShortcutDetector.reset()`
#### 建议参数
- 维持当前默认值，等 v2 进入实机后再调。[src: config.py]； - `min_distance = 0.18`
- `max_duration_ms = 900`； - `cooldown_ms = 700`
- `axis_ratio = 1.4`
---
### D.8 `mouse_controller.py` / `shortcut_controller.py`
#### 文件职责
- 把 `ScreenDelta` 或绝对坐标变成系统输入。； - 执行 click / scroll / keyboard shortcuts。
#### 现状
- `shortcut_controller.py` 仍依赖 PyAutoGUI，`moveTo` 默认是瞬移而不是平滑移动。[src: current code, PyAutoGUI docs]； - `ShortcutController.execute()` 目前支持 arrow / scroll 触发。[src: current code]
#### v2 设计
- `mouse_controller.py` 先保留 PyAutoGUI 验证链路。； - 如果后续对抖动或延迟仍不满意，再替换成 `SendInput`。
- 不要把注入层和识别层耦合。
#### 公共 API
- `MouseController.move(dx, dy)`； - `MouseController.click()`
- `MouseController.scroll(amount)`； - `MouseController.set_position(x, y)`
#### 设计理由
- PyAutoGUI 的 `duration=0` 已经是最短路径，不是当前首要瓶颈。[src: T3 §4, PyAutoGUI docs]； - `SendInput` 适合作为更直接、更底层的最终注入层。[src: T3 §4, Microsoft docs]
---
### D.9 `debug_view.py`
#### 文件职责
- 画 hand landmarks。； - 画 control region。
- 画 raw index tip。； - 画 pointer target。
- 画状态面板。
#### 现状
- 当前 overlay 已经显示 Mode、Gesture、Action、Active、Scroll、FPS、Pinch、Hand。[src: current code]； - 当前有 control region 和 raw index 的可视化。[src: current code]
#### v2 设计
- 增加 `EngagementState`。； - 增加 pinch close / open 双阈值线。
- 增加 velocity、acceleration、depth factor、output delta。； - 增加 frame age 和 backend 名称。
- 在控制模式和 debug 模式之间明确区分。
#### 额外显示项
- `handedness_label`； - `handedness_confidence`
- `frame_timestamp_ms`； - `frame_age_ms`
- `capture_backend`； - `inference_mode`
- `latest_frame_seq`
---
## E. 配置设计
### E.1 现有 dataclass 盘点
#### `CameraConfig`
- `width: int`； - `height: int`
- `index: int`； - 默认值: `1280 x 720 x 0`。[src: config.py]
#### `ControlRegion`
- `left: float`； - `top: float`
- `right: float`； - `bottom: float`
- 归一化到摄像头画面。[src: config.py]
#### `PointerConfig`
- `smoothing: float`； - `dead_zone_px: float`
- `control_region: ControlRegion`； - `relative_sensitivity: float = 1.4`。[src: config.py]
- 默认值: `0.35 / 4.0 / 0.12, 0.10, 0.88, 0.90 / 1.4`。[src: config.py]
#### `GestureConfig`
- `pinch_threshold: float`； - `hold_ms: int`
- `cooldown_ms: int`； - `release_threshold: float`
- 默认值: `0.05 / 120 / 350 / 0.08`。[src: config.py]
#### `ShortcutConfig`
- `min_distance: float`； - `max_duration_ms: int`
- `cooldown_ms: int`； - `axis_ratio: float`
- 默认值: `0.18 / 900 / 700 / 1.4`。[src: config.py]
#### `GrabScrollConfig`
- `hold_ms: int`； - `release_grace_ms: int`
- `dead_zone: float`； - `scroll_sensitivity: float`
- `max_scroll_per_frame: int`； - `thumb_index_max_distance: float`
- `curled_finger_ratio: float`； - `min_curled_fingers: int`
- 默认值: `120 / 120 / 0.015 / 180.0 / 18 / 1.8 / 1.65 / 2`。[src: config.py]
#### `AppConfig`
- `camera: CameraConfig`； - `pointer: PointerConfig`
- `gesture: GestureConfig`； - `shortcut: ShortcutConfig`
- `grab_scroll: GrabScrollConfig`。[src: config.py]
### E.2 v2 建议新增字段
#### `CameraConfig` 新增
- `backend_preference: tuple[str, ...]`； - `buffer_size: int = 1`
- `prefer_latest_frame: bool = True`； - `default_resolution_profile: str = "mvo_640x480"`
#### `HandTrackerConfig` 新增
- `running_mode: Literal["VIDEO", "LIVE_STREAM"] = "VIDEO"`； - `num_hands: int = 1`
- `min_hand_detection_confidence: float = 0.5`； - `min_hand_presence_confidence: float = 0.5`
- `min_tracking_confidence: float = 0.5`； - `model_path: str | None`
#### `PointerConfig` 新增
- `mode: Literal["relative", "absolute"] = "relative"`； - `v_jitter: float = 0.20`
- `v_mid: float = 1.0`； - `v_fast: float = 3.0`
- `g_lo: float = 0.85`； - `g_hi: float = 3.0`
- `depth_gamma: float = 0.9`； - `z_min: float = 0.70`
- `z_max: float = 1.25`； - `z_scale_reference: float`
- `dead_zone_radius: float = 0.20`
#### `EngagementConfig` 新增
- `activation_hotkey: str = "m"`； - `palm_hold_ms: int = 200`
- `cooldown_ms: int = 100`； - `missing_frames_to_idle: int = 4`
- `escape_hotkey: str = "q"`
#### `GestureConfig` v2 修改
- `pinch_close: float = 0.05`； - `pinch_open: float = 0.075`
- `confirm_frames: int = 2`； - `release_confirm_frames: int = 2`
- `cooldown_ms: int = 150`； - `emit_on_release: bool = True`
#### `GrabScrollConfig` v2 补充
- `hold_then_move_enabled: bool = True`； - `release_stop_enabled: bool = True`
- `post_release_grace_ms: int = 120`
### E.3 配置依赖关系
- `PointerConfig.control_region` 依赖摄像头分辨率，但值本身是归一化坐标。； - `depth_gamma` 依赖 `palm_width` 或类似手尺度 proxy。
- `pinch_threshold` 依赖归一化距离，不依赖像素。； - `dead_zone_px` 是像素空间抑噪；`dead_zone_radius` 是归一化输入空间抑噪，两者不要混用。
- `running_mode=VIDEO` 时，`frame_timestamp_ms` 必须存在。； - `LIVE_STREAM` 时，`result_callback` 必须可用。[src: MediaPipe docs]
---
## F. 状态机
### F.1 Engagement 状态机
```text
[IDLE]
  | hotkey m / palm hold 200ms
  v
[ARMED]
  | landmarks stable + no cooldown
  v
[ACTIVE]
  | hand lost / q / explicit disarm
  v
[COOLDOWN]
  | 50~150ms
  v
[IDLE] or [ARMED]
```
#### 说明
- `IDLE` 不输出指针。； - `ARMED` 允许识别，但不一定输出。
- `ACTIVE` 允许 pointer / gesture / scroll / shortcut 全部工作。； - `COOLDOWN` 防止刚释放就立刻误触。
---
### F.2 Pinch 状态机（release-to-commit）
```text
             distance < close for N frames
[PINCH_OPEN] ------------------------------> [PINCH_PRESSED]
      ^                                           |
      |                                           | distance stays < open
      |                                           v
      |                                      [PINCH_HOLD]
      |                                           |
      |           release: distance > open for M frames
      +-------------------------------------------+
                          emit click on release
```
#### 说明
- `close` 负责进入按下。； - `open` 负责退出按下。
- 中间区间保持状态。； - click 在 release 时发出。
---
### F.3 Grab Scroll 状态机
```text
[NO_HAND]
   |
   | hand appears
   v
[CANDIDATE] -- hold_ms elapsed --> [GRABBING] -- move --> [DRAGGING]
     |                                  |                    |
     | no grab pose                     | release grace      | release
     v                                  v                    v
 [RELEASED] <------------------------ [RELEASED] <--------- [RELEASED]
```
#### 说明
- 先确认抓握，再输出滚动。； - 松手后有 grace period。
- 只有移动超出 dead zone 才输出 scroll delta。
---
## G. 性能预算
### G.1 目标
- 端到端 16ms / frame。； - 目标帧率 60fps。
- 目标是“稳态可持续”，不是单帧跑得快。[src: task body]
### G.2 建议预算
- capture < 1ms； - RGB / resize < 1ms
- inference < 12ms (640x480, VIDEO mode)； - pointer < 1ms
- FSM < 1ms； - injection < 1ms
- overlay < 1ms； - 余量给 sleep-balance / OS 调度
### G.3 分段计时指标
- mean； - p50
- p95； - max
- dropped frames； - latest frame age
### G.4 关键判断
- `VIDEO/LIVE_STREAM` 比 `IMAGE/detect()` 更重要。[src: T3 §1]； - 640x480 比 1280x720 更重要。[src: T3 §2]
- latest-frame 比排队更重要。[src: T3 §3]； - backend 显式化比默认值更重要。[src: T3 §4]
### G.5 参考事实
- MediaPipe 官方 Hand Landmarker benchmark：Pixel 6 CPU 17.12ms / GPU 12.27ms。[src: T2 §1]； - 这不是 Windows 笔记本 benchmark，只能当方向参考。[src: T2 §3.2]
- 官方公开任务资产当前可验证的是 float16。[src: T2 §1, T3 §1]
---
## H. 安全规则
- 启动默认进入 DEBUG 模式，不直接进入 CONTROL 模式。； - `m` 切 ACTIVE。
- `q` 退出。； - PyAutoGUI 保持 FAILSAFE。
- 手丢失时自动回 IDLE。； - 连续检测失败时自动回 IDLE。
- 紧急停止：5 指张开并保持 1s -> IDLE。； - 如果摄像头读帧失败，立即停止主循环，不要盲重试到失控。
- 如果推理线程延迟飙升，优先降分辨率，而不是继续堆复杂逻辑。
### 安全优先级
1. 显式退出。； 2. 手势回 IDLE。
3. 连续失效回 IDLE。； 4. 任何未知状态都不能默认输出鼠标事件。
---
## I. 风险与未决项
### I.1 摄像头 backside 兼容
- 某些摄像头背光 / 逆光会导致 landmarks 波动。； - 建议先记录 backend 与设备型号，再调参。
- 不要把“模型不行”与“摄像头不行”混为一谈。
### I.2 暗光环境
- 低照度会显著拉低检测稳定性。； - 设计上必须允许自动回退到 IDLE。
- overlay 要显示 `hand missing` 原因。
### I.3 双屏 DPI 不一致
- 如果后续改成跨屏，指针映射必须读真实屏幕几何。； - 当前 v2 先假设单屏或统一 DPI。
- 多屏是后续扩展，不是本次范围。
### I.4 不同手型与不同用户
- 不同手大尺寸差异会影响 palm width 归一化。； - 需要保留 per-user calibration 接口。
- 但 v2 不要求自训练模型。
### I.5 MediaPipe 模型可得性
- 当前官方公开可验证的是 float16 资产。[src: T2 §1]； - 不能把未公开的 int8/lite 变体当作稳定承诺。
- 如果后续官方资产发生变化，需要重新确认。
### I.6 压测与稳定性
- 旧帧积压比单帧慢更危险。； - 任何新模块只要引入队列，默认大小都应从 1 开始。
- 如果必须排队，必须定义丢弃策略。
### I.7 误触风险
- pinch 的 close/open 必须双阈值。； - 激活态必须显式存在。
- scroll 与 click 的状态机必须隔离。
### I.8 Debug / Control 混淆
- DEBUG 模式不能真的发系统输入。； - CONTROL 模式才允许注入。
- overlay 要清晰标注当前模式。
---
## J. 实施拆分
> 下面这些卡片可以直接 dispatch 给 backend-eng。
### J.1 任务 1：切换 HandTracker 到 VIDEO / detect_for_video
- 涉及文件：`src/handmouse/hand_tracker.py`、`src/handmouse/app.py`、`tests/test_hand_tracker.py`。； - 公共 API：`HandTracker.process(frame_bgr, frame_timestamp_ms)`。
- 测试要求：VIDEO 模式下能处理 timestamp；无手、单手、异常 frame 都要覆盖。； - 依赖：MediaPipe Python guide 行为确认。[src: MediaPipe docs]
- 完成标准：主循环不再调用 `detect()`。
### J.2 任务 2：新增 PointerEngine 自适应 gain / 深度补偿
- 涉及文件：`src/handmouse/pointer_engine.py`、`src/handmouse/config.py`、`tests/test_pointer_engine.py`。； - 公共 API：`PointerEngine.update()`。
- 测试要求：jitter 区输出 0；mid 区近似 1:1；fast 区增益提升；depth factor 在上下界内夹紧。； - 依赖：任务 1 输出的 hand landmarks。
- 完成标准：pointer mapping 不再只靠线性 smoothing。
### J.3 任务 3：新增 EngagementFSM 与 hotkey / pose 激活
- 涉及文件：`src/handmouse/engagement.py`、`src/handmouse/app.py`、`src/handmouse/debug_view.py`、`tests/test_engagement.py`。； - 公共 API：`EngagementFSM.update()`。
- 测试要求：hotkey 激活、姿势激活、自动回 IDLE、冷却逻辑。； - 依赖：无。
- 完成标准：系统有明确激活态，不再“人在镜头前就算控制中”。
### J.4 任务 4：把 GestureDetector 改成 release-to-commit pinch
- 涉及文件：`src/handmouse/gesture_detector.py`、`tests/test_gesture_detector.py`。； - 公共 API：`GestureDetector.update()` 保持不变，但状态机重写。
- 测试要求：close/open 双阈值、hold 不立即 click、release 才 click、抖动不会重复点击。； - 依赖：任务 3 的 active 门控。
- 完成标准：pinch 语义从 press-to-click 改成 release-to-commit。
### J.5 任务 5：改造 GrabScrollDetector 为保持 + 移动 = scroll
- 涉及文件：`src/handmouse/grab_scroll_detector.py`、`tests/test_grab_scroll_detector.py`。； - 公共 API：`GrabScrollDetector.update()` 保持不变，但状态机细化。
- 测试要求：hold 后开始滚动、release stop、dead zone 生效、max_scroll_per_frame 生效。； - 依赖：任务 3 的 active 门控。
- 完成标准：scroll 行为稳定，不抢占 pinch / pointer 节奏。
### J.6 任务 6：拆分 capture / inference / control 并强化 overlay
- 涉及文件：`src/handmouse/app.py`、`src/handmouse/camera.py`、`src/handmouse/debug_view.py`。； - 公共 API：主循环内部使用 latest-frame 语义。
- 测试要求：帧龄、fps、backend 名称、控制模式都能显示。； - 依赖：任务 1、2、3、4、5。
- 完成标准：debug overlay 能直接看出系统当前是快、慢、还是卡在旧帧。
### J.7 任务 7：补齐回归测试矩阵
- 涉及文件：`tests/test_app.py`、`tests/test_pointer_mapper.py`、`tests/test_shortcut_detector.py`、新增测试文件。； - 测试要求：覆盖 active / idle / cooldown / no-hand / low-light / missing frame。
- 依赖：前述实现任务。； - 完成标准：关键状态机都可回归。
---
## K. 引用与来源
### K.1 阶段研究文档
- `D:/Data/ProjectAgent/HandMouse/docs/research/phase2-library-evaluation.md`； - `D:/Data/ProjectAgent/HandMouse/docs/research/phase3-performance-optimization.md`
- `D:/Data/ProjectAgent/HandMouse/docs/research/phase4-pointer-control-paradigms.md`
### K.2 当前代码
- `D:/Data/ProjectAgent/HandMouse/src/handmouse/config.py`； - `D:/Data/ProjectAgent/HandMouse/src/handmouse/hand_tracker.py`
- `D:/Data/ProjectAgent/HandMouse/src/handmouse/pointer_mapper.py`； - `D:/Data/ProjectAgent/HandMouse/src/handmouse/gesture_detector.py`
- `D:/Data/ProjectAgent/HandMouse/src/handmouse/grab_scroll_detector.py`； - `D:/Data/ProjectAgent/HandMouse/src/handmouse/shortcut_detector.py`
- `D:/Data/ProjectAgent/HandMouse/src/handmouse/shortcut_controller.py`； - `D:/Data/ProjectAgent/HandMouse/src/handmouse/debug_view.py`
- `D:/Data/ProjectAgent/HandMouse/src/handmouse/app.py`
### K.3 官方公开文档 URL
- MediaPipe Hand Landmarker Python guide；   - https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python
- MediaPipe Hand Landmarker page；   - https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker
- libinput pointer acceleration；   - https://wayland.freedesktop.org/libinput/doc/latest/pointer-acceleration.html
- libinput absolute axes；   - https://wayland.freedesktop.org/libinput/doc/latest/absolute-axes.html
- PyAutoGUI mouse docs；   - https://pyautogui.readthedocs.io/en/latest/mouse.html
- Microsoft SendInput docs；   - https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
- OpenCV VideoCapture docs；   - https://docs.opencv.org/4.13.0/d8/dfe/classcv_1_1VideoCapture.html
  - https://docs.opencv.org/4.13.0/d4/d15/group__videoio__flags__base.html
### K.4 研究结论对应关系
- `IMAGE -> VIDEO/LIVE_STREAM` 来自 T3 + MediaPipe docs。[src: T3 §1, MediaPipe docs]； - `640x480` 主路径来自 T3 工程建议。[src: T3 §2]
- `latest-frame semantics` 来自 T3。[src: T3 §3]； - `CAP_DSHOW / CAP_MSMF / buffer=1` 来自 T3。[src: T3 §4]
- `relative + adaptive gain + hysteresis + active state` 来自 T4。[src: T4 §1, §2, §3, §4]； - `pinch close/open = 0.05 / 0.075` 来自 T4 默认参数表。[src: T4 §8]
- `z 只做补偿` 来自 T4 深度补偿章节。[src: T4 §5]； - `dead zone 在输入空间` 来自 T4 dead zone 章节。[src: T4 §6]
- `Press-to-click -> release-to-commit` 是本次综合决策。[src: T4 §3, task body]
---
## L. 交付检查清单
- [ ] 文档自包含。； - [ ] 结构满足 A-K。
- [ ] 包含 mermaid 图。； - [ ] 包含三个 ASCII 状态机。
- [ ] 包含完整 config 设计。； - [ ] 包含至少 6 个可 dispatch 的实现任务。
- [ ] 所有关键数字都有来源标注。； - [ ] 文件路径正确。
- [ ] 术语与现有代码一致。
---
## M. 备注
- 这份文档的优先目标是“能开工”，不是“字面最短”。； - 选择相对指针和显式激活态，是为了先把误触和复杂度压住。
- 选择 VIDEO / detect_for_video，是为了先把 MediaPipe tracking 的价值吃到。； - 之后如果实测需要，再讨论 ROI 裁剪、GPU、SendInput、或更激进的量化。
