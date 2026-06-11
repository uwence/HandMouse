# HandMouse v2 — Review Handoff

> 入口文档。Reviewer 先读这份，然后按"建议 review 顺序"看代码。

**仓库**: `D:/Data/ProjectAgent/HandMouse`
**分支**: `feature/gesture-shortcuts`
**Python**: 3.11+（用户实测环境 3.14，但项目声明 3.11+）
**Last commit**: `1f1a616 docs: rewrite README for v2` (HEAD)
**Tests**: 76 passed (pytest)
**状态**: v2 实现完毕，5 个 v2 模块 + 集成 commit 全在分支上。README 同步到 v2 行为。已知一处 v1 vs v2 命名遗留（见 §6）。

---

## 1. 一句话项目

Windows 单手 webcam 手势控制鼠标：相对指针 + release-to-commit pinch + 抓握滚动 + swipe 快捷 + 显式激活态（EngagementFSM 门控）。MVO 目标 60fps / 16ms 端到端，CPU-only 中端笔记本。

---

## 2. v2 vs v1（关键变化）

| 维度 | v1 | v2 |
|---|---|---|
| 默认指针模式 | 绝对映射（`PointerMapper`）或仅 grab-scroll | **相对**（`PointerEngine`）自适应 gain + 深度补偿 + 输入空间 dead zone |
| Pinch 语义 | 按下 hold 120ms 即 click | **松开才 click**（release-to-commit，双阈值 0.05/0.075） |
| 激活态 | "人在镜头前=在控制" | **显式 FSM**: IDLE/ARMED/ACTIVE/COOLDOWN（`m` 键或 palm-hold 200ms 触发） |
| MediaPipe | IMAGE + `detect()` | **VIDEO + `detect_for_video(ms)`**（吃 tracking 复用，最大单点性能改进） |
| 摄像头 | 1280×720 默认 | **640×480**, DSHOW→MSMF→ANY, `CAP_PROP_BUFFERSIZE=1`（latest-frame 语义） |
| Hand pose 误识别 | 全靠"在画面里" | palm-open required for engagement（≥3 指伸展） |
| 调试 overlay | 8 行状态 | 9 行 + 底部 pinch threshold bar（绿/蓝双阈值线） |

---

## 3. 仓库结构

```
HandMouse/
├── README.md                                 v2 完整操作说明 + 调参 + 验收 checklist
├── pyproject.toml                            setuptools, requires-python>=3.11
├── requirements.txt                          opencv-python / mediapipe / pyautogui / pytest
├── docs/
│   ├── HANDOFF-V2.md                         ← 你正在读
│   ├── superpowers/{specs,plans}/            v1 阶段的设计和实施计划（保留作历史）
│   └── research/
│       ├── phase2-library-evaluation.md      11.9K 库选型研究
│       ├── phase3-performance-optimization.md 10.4K 性能研究（关键：VIDEO 模式必换）
│       ├── phase4-pointer-control-paradigms.md 12.1K 指针范式研究
│       └── handmouse-v2-design.md            30.9K 综合设计文档（v2 spec）
├── src/handmouse/                            10 个模块，共 ~1990 行
│   ├── config.py                             110 行  DEFAULT_CONFIG dataclass
│   ├── camera.py                             113 行  DSHOW→MSMF→ANY fallback, buffer=1
│   ├── hand_tracker.py                       220 行  MediaPipe HandLandmarker VIDEO 模式
│   ├── pointer_engine.py                     259 行  ★ 新：相对指针 + 自适应 gain
│   ├── engagement.py                         114 行  ★ 新：IDLE/ARMED/ACTIVE/COOLDOWN FSM
│   ├── gesture_detector.py                   105 行  ★ 改：release-to-commit pinch
│   ├── grab_scroll_detector.py               307 行  抓握+移动=scroll（refine: active 仅 DRAGGING 时 True）
│   ├── shortcut_detector.py                   93 行  单指大幅移动 → 方向键/scroll
│   ├── mouse_controller.py                    89 行  PyAutoGUI 包装（FAILSAFE=True）
│   ├── shortcut_controller.py                 58 行  shortcut action → pyautogui
│   ├── debug_view.py                         431 行  ★ 重写：9 行 panel + pinch bar
│   └── app.py                                271 行  ★ 重写主循环
└── tests/                                    7 个测试文件，~1230 行
    ├── test_engagement.py                    ★ 326 行 / 11 用例
    ├── test_gesture_detector.py              ★ 164 行（重写以匹配 release-to-commit）
    ├── test_pointer_engine.py                ★ 173 行 / 9 用例
    ├── test_hand_tracker.py                  ★ 189 行 / 3 用例（mock mediapipe）
    ├── test_grab_scroll_detector.py          158 行
    ├── test_shortcut_detector.py              97 行
    ├── test_shortcut_controller.py            72 行
    ├── test_pointer_mapper.py                186 行（v1 旧 RelativePointerMapper 仍保留）
    ├── test_mouse_controller.py               59 行
    └── test_app.py                            20 行（仅 `_mirror_frame`，app 主循环未覆盖）
```

★ = v2 新增或重写。

---

## 4. 各模块职责 + 关键设计决策

### 4.1 `config.py` — DEFAULT_CONFIG

| 字段 | 默认值 | 备注 |
|---|---|---|
| `camera.width/height/index` | 640/480/0 | v2 从 1280×720 降 |
| `camera.backend_preference` | `(CAP_DSHOW, CAP_MSMF, CAP_ANY)` | tuple，camera 依次尝试 |
| `camera.buffer_size` | 1 | latest-frame 语义 |
| `camera.fps_target` | 60 | 软目标，camera 是否接受看后端 |
| `pointer.control_region` | (0.12, 0.10, 0.88, 0.90) | 归一化，orange 框 |
| `pointer.smoothing/dead_zone_px/relative_sensitivity` | 0.35/4.0/1.4 | v1 旧字段，**当前 v2 主路径不读**——v2 用 `PointerEngineConfig`，见 §4.3 |
| `gesture.*` (pinch_threshold/hold_ms/...) | v1 旧字段，**v2 不读**——v2 用 `GestureConfig` 见 §4.4 |
| `shortcut.*` | v1 字段，仍被 ShortcutDetector 使用（v2 沿用） |
| `grab_scroll.*` | v1 字段，**v2 不读**——v2 用模块内 `GrabScrollConfig`（per J5） |

**已知遗留**：`config.py` 里的 `gesture` / `grab_scroll` / `pointer.smoothing` 等字段是 v1 时代占位。v2 模块用各自的 local config，app.py 不读这些字段。**Reviewer 重点看**：是否值得清理掉 v1 字段以减少认知负担。

### 4.2 `camera.py` — DSHOW→MSMF→ANY fallback

- 构造时 `BACKEND_CONSTANTS` 字典映射字符串到 cv2 常量
- `open()` 按 `config.backend_preference` 顺序逐个 `cv2.VideoCapture(index, CAP_*)`，第一个 `isOpened()` 的胜出
- 设置 `CAP_PROP_FRAME_WIDTH/HEIGHT/FPS/BUFFERSIZE`
- 所有 cv2 调用都 try/except（OpenCV 4.13 API 在某些属性上 TypeError）
- 暴露 `backend_name: str`（成功 fallback 后的 backend 名）
- 失败时抛 `RuntimeError`，包含 3 个 hint（权限/其他 app 占用/索引错）

**Reviewer 重点看**：`open()` 里 fallback 链的边界条件（cv2 backend 常量在不同 OpenCV 版本可能变），以及 `buffer_size=1` 在所有 backend 上是否真的被尊重。

### 4.3 `pointer_engine.py` — 相对指针核心

**核心公式**（实现细节在 `_gain_for_velocity` / `_depth_factor` / `_handle_missing_hand`）：
1. 输入：index tip + 21 landmarks + 上一帧控制点 + 时间戳
2. 估计 `s_t = median(||index_mcp - pinky_mcp||, ||wrist - middle_mcp||, ||wrist - index_mcp||)`（palm-width 归一化）
3. `s_ref`：首帧 `s_t`，或用户传入 `z_scale_reference`
4. **深度补偿** `A_z = clamp((s_ref / s_t)^gamma, z_min, z_max)`，默认 `gamma=0.9, z_min=0.70, z_max=1.25`
5. 归一化位移 `u_t = (p_t - p_{t-1})`（p 已 in control region）
6. 速度 `v = ||u_t|| / dt_seconds`
7. **分段 gain**：
   - `v < v_jitter (0.20)`: `g = 0`（dead zone）
   - `v_jitter ≤ v < v_mid (1.0)`: `g = g_lo + (1 - g_lo) * (v - v_jitter) / (v_mid - v_jitter)`，默认 `g_lo=0.85`
   - `v ≥ v_mid`: `g = 1 + (g_hi - 1) * smoothstep(v_mid, v_fast, v)`，默认 `g_hi=3.0, v_fast=3.0`
8. 输出 `delta = round(pixel_per_palm_width * g * A_z * u_t)`
9. 状态机 IDLE/ACTIVE/COOLDOWN（`missing_frames_to_idle=4` 帧无手 → COOLDOWN）

**关键属性**（debug overlay 读）：`last_velocity / last_gain / last_depth_factor / last_hand_scale / state`。
**没有** `last_frame_point`（这是 design 阶段我以为有，写了 `debug_view._draw_pointer_target` 用它，结果运行期 AttributeError，已删，commit `e7c9e7f`）。所以画图只能用 raw index tip 那个青色圆圈。

**Reviewer 重点看**：
- gain 曲线在 0.20 / 1.0 / 3.0 三个分段点的连续性（一阶导是否连续，否则光标会有速度跳变）
- 深度补偿 `(s_ref / s_t)^gamma` 在 `s_t` 极小（手非常远）或极大（手非常近）时的稳定性——clamp 兜了底，但 gamma=0.9 在 s_t = 2×s_ref 时 A_z = 0.535 是否合理
- `_handle_missing_hand` 在 `missing_frames_to_idle=1` 时的 race（被 unit test 覆盖）
- `update()` 第一帧直接 anchor 不输出——设计选择，没有"延迟一帧"问题
- `pixel_per_palm_width=None` → 默认 `screen_height`，对横屏 vs 竖屏/不同 DPI 体验差别

### 4.4 `gesture_detector.py` — Release-to-commit pinch

**状态机**：
```
PINCH_OPEN --(d < close for confirm_frames)--> PINCH_PRESSED
PINCH_PRESSED --(d <= open)--> PINCH_HOLD
PINCH_HOLD --(d > open for release_confirm_frames)--> COOLDOWN + emit click
COOLDOWN --(cooldown_ms elapsed)--> PINCH_OPEN
```

**关键参数**：默认 `pinch_close=0.05, pinch_open=0.075, confirm_frames=2, release_confirm_frames=2, cooldown_ms=150`。注意：hand 丢失时 `update(None, None)` → reset 到 PINCH_OPEN。

**Reviewer 重点看**：
- 双阈值是否真的提供 hysteresis（close=0.05, open=0.075 留 0.025 滞回，够用）
- 抖动（jitter in distance）能否被 confirm_frames 过滤——`test_hysteresis_short_distance_jitter_does_not_flip_state` 覆盖
- `emit_on_release=True` 写死（设计 v2 强制语义），但 flag 留着便于将来切换

### 4.5 `engagement.py` — 激活态 FSM

**状态机**：
```
IDLE
  | hotkey m 边沿          → ARMED
  | palm_visible 且 palm_hold_ms >= 200  → ARMED
ARMED
  | 手 landmarks 存在（next frame）      → ACTIVE
ACTIVE
  | 连续 missing_frames_to_idle 帧无手  → COOLDOWN
  | escape_requested (q)                → IDLE 立即
  | hotkey m 边沿                       → IDLE 立即（toggle）
COOLDOWN
  | cooldown_ms (100) 过后              → IDLE
```

**关键 API**：
```python
result: EngagementResult = engagement.update(
    hotkey_pressed: bool,        # 边沿触发 (rising edge)
    palm_visible: bool,
    palm_hold_ms: int,
    hand_missing: bool,
    escape_requested: bool,
    now_ms: int,
)
result.is_active: bool          # True 仅在 ACTIVE
result.state: EngagementState   # IDLE/ARMED/ACTIVE/COOLDOWN
result.reason: str              # 调试用: "hotkey" / "palm_hold" / "missing" / "escape" / "cooldown" / "idle" / "armed" / "active"
```

**Reviewer 重点看**：
- 状态机有 11 个测试覆盖（hotkey 边沿、palm hold 持续、escape、force_idle、cooldown timing）
- `hotkey_pressed` 边沿语义：app.py 里调用方负责边沿检测（OpenCV `waitKey` 不给 key-up）——app.py 用了 `last_m_state` / `last_q_state` 记录但实际是 redundant（见 §6 TODO）
- palm 可见判断在 app.py 里做（_is_palm_open 启发式），FSM 只消费 palm_hold_ms

### 4.6 `grab_scroll_detector.py` — 抓握滚动

**状态机**（v2 J5 refine）：
```
NO_HAND
  | 出现 grab pose
CANDIDATE --(hold_ms=120)--> GRABBING
GRABBING --(手中心 y 位移 > 0.015)--> DRAGGING
DRAGGING/GRABBING --(no grab pose + release_grace_ms=120 超时)--> RELEASED
RELEASED --(post_release_grace_ms=120 后)--> NO_HAND
```

**关键 v2 改动**（`active` 字段）：**`active=True` 仅在 DRAGGING 且 scroll_delta != 0 时**。即纯 hold 不算 active（避免误报"在滚"）。

**Reviewer 重点看**：
- grab pose 几何判断：thumb-index 距离 + 5 指中至少 2 个 curl ratio < 1.65。ratio 阈值在 unit test 覆盖
- release_grace + post_release_grace 双重保护：前者让短暂 hand-lost 不退出，后者让 re-grab 平滑
- scroll_sensitivity=180, max_scroll_per_frame=18 是经验值，需要真机调

### 4.7 `app.py` — 主循环

单线程 MVO 路径。流程：
```
loop:
  frame = camera.read()
  frame = cv2.flip(frame, 1)                 # mirror for intuitive control
  now_ms = int(perf_counter * 1000)
  hand_result = tracker.process(frame, frame_timestamp_ms=now_ms)
  hand_missing = not hand_result.landmarks
  palm_visible = _is_palm_open(hand_result.landmarks)   # 启发式，3+ 指伸展
  key = cv2.waitKey(1)
  engagement_result = engagement.update(
    hotkey_pressed=m_edge, palm_visible, palm_hold_ms,
    hand_missing, escape_requested=q_edge, now_ms,
  )
  if q_edge: break
  is_active = engagement_result.is_active
  mouse.set_control_enabled(is_active)
  shortcut.set_enabled(is_active)
  if is_active:
    delta = pointer.update(hand_result, now_ms)
    if delta: mouse.move_relative(delta)
    g = gesture.update(thumb_tip, index_tip, now_ms)
    if g.should_click: mouse.left_click()
  else:
    gesture.update(None, None, now_ms)         # 重置 gesture
    pointer.reset()
  grab_result = grab_scroll.update(landmarks, now_ms)
  if is_active and grab_result.scroll_delta:
    shortcut.scroll(grab_result.scroll_delta)
  if is_active and index_tip and not grab_result.is_grab_pose:
    sc = shortcut_detector.update(index_tip, now_ms)
    if sc.action: shortcut.execute(sc.action)
  telemetry = DebugTelemetry(fps, frame_age, backend, pointer, engagement_result, grab_result)
  cv2.imshow(WINDOW_NAME, debug_view.draw(frame, hand_result, g, is_active, telemetry))
```

**Reviewer 重点看**：
- `_is_palm_open` 的几何（3/4 指 tip/palm > 1.1 × mcp/palm）—— 启发式，未 unit test 覆盖（依赖 landmarks，不是纯函数）。MVO 简化
- 线程模型：**单线程**。T3 研究的 MVO 路径可以靠 VIDEO 模式 + buffer=1 在中端 CPU 跑 60fps。如果实测不够，需要切到 capture thread + inference thread
- `palm_visible_start_ms` 用闭包变量维护——简单，但 `_run_loop` 整体不好单元测试

### 4.8 `debug_view.py` — overlay

- 9 行状态 panel：Mode / Engagement / Pointer / Pinch / Grab / FPS / Frame age / Backend / Hand
- 底部 280px pinch bar，绿线=close(0.05)，蓝线=open(0.075)，填充色按当前 distance
- 21 landmark 骨架 + raw index tip 圆圈 + control region 框

**Reviewer 重点看**：
- panel 字号/边距/颜色常量（细）—— 跟实际效果 vs README 描述一致性
- pinch bar 在低分辨率/高 DPI 缩放下的位置（`bar_y = max(60, height - 40)` 简单粗暴）

---

## 5. 配置文件 + 调参点

| 改什么 | 在哪 |
|---|---|
| 摄像头分辨率/索引/backend | `config.py` `CameraConfig` |
| 控制区大小 | `config.py` `PointerConfig.control_region` |
| 相对指针 v_jitter/v_mid/v_fast/g_lo/g_hi/depth_gamma/z_min/z_max | `app.py` `PointerEngineConfig(...)` |
| Pinch close/open 阈值 | `app.py` `GestureConfig(...)` |
| 抓握阈值/sensitivity | `app.py` `GrabScrollConfig(...)` |
| 激活态参数 | `app.py` `EngagementConfig(...)` |

完整对照表见 README §Tuning。

---

## 6. 已知问题 / TODO / 风险

### 6.1 设计/实现遗留

1. **`config.py` 里有 v1 旧字段**没清理：
   - `PointerConfig.smoothing / dead_zone_px / relative_sensitivity` — v2 用 `PointerEngineConfig` 不读
   - `GestureConfig.pinch_threshold / hold_ms / cooldown_ms / release_threshold` — v2 用模块内 `GestureConfig` 不读
   - `GrabScrollConfig.*` 同上

   **建议**：要么把旧字段从 dataclass 删掉（breaking change 但 v2 还没发布），要么保留并加 comment 说明 deprecated。

2. **`pointer_mapper.py` 旧 v1 mapper 还在**（`PointerMapper` + `RelativePointerMapper`），被 `test_pointer_mapper.py` 覆盖但**没被 app.py 使用**。考虑是否删除（连带 test）。

3. **`shortcut_controller.py` 还在用 `pyautogui.press("left")` 4 次**——这有点 naive，应该用 keyboard combo (e.g. Win+Left 切桌面) 或只是单次 press。

4. **`hand_tracker.py` 的 `process_async()` 没实现**（注释说 LIVE_STREAM 需要它），目前 v2 只用 VIDEO 模式不需要。

5. **app.py 里的 `last_m_state` / `last_q_state` 边沿检测**其实不需要——OpenCV `waitKey` 返回 0 表示无按键，>0 表示按了，所以**任何非零 key 都是按了**。当前代码复杂化了（注释里也承认是 "press edge approximation"）。

### 6.2 测试覆盖

- 5 个新模块 100% 单元测试覆盖（engagement 11, gesture 9, pointer_engine 9, hand_tracker 3, grab_scroll 8）
- `app.py` 主循环**没**单元测试（依赖 OpenCV/摄像头/全栈）
- `debug_view.py` overlay 渲染**没**测试
- `_is_palm_open` 启发式**没**测试

### 6.3 性能 / 兼容性风险

- **MediaPipe Tasks Python wheel 只支持 3.9/3.10/3.11/3.12**，3.13+ 没明确覆盖。3.14 跑得了但不保证
- **MVO 60fps 是估算**（Pixel 6 17ms CPU，Win 笔记本估计 10-20ms），**没在真机跑过 benchmark**
- **单线程架构**：如果 MediaPipe inference >16ms（弱 CPU），主循环会掉帧，debug overlay 里的 FPS 会变低
- **多显示器 DPI 不一致**：`PointerEngineConfig.pixel_per_palm_width` 只用 `screen_height`，跨屏不准确（v2 设计明确说单屏）
- **PyAutoGUI 注入延迟**：当前 0ms `moveTo`，T3 研究说 `SendInput` 更快但 v2 没切

### 6.4 调试 / 可观测性

- 启动时一行 `INFO: Created TensorFlow Lite XNNPACK delegate for CPU` 是 MediaPipe 的，**不是错误**
- 偶尔的 `Network error: 500 for url: https://play.googleapis.com/log` 是 MediaPipe 试图上报 analytics，**可忽略**（用环境变量 `GLOG_logtostderr=0` 或断网可消除）
- debug overlay 是唯一的运行时可观测性——没有日志文件、没有 metrics

### 6.5 设计 spec 与实现的偏差

设计文档 (`docs/research/handmouse-v2-design.md`) 写的东西 vs 实际代码：

- §D.5 说 `GestureState` 应该有 `EMIT_CLICK`，实际代码用 `COOLDOWN` 替代（`should_click=True` 在 cooldown 进入瞬间 emit）—— J4 worker 选择简化
- §D.3 描述 `PointerEngine` 有 `last_frame_point`，**实际没实现**（debug_view 设计时被骗，commit `e7c9e7f` 删除引用）
- §C 架构图里有 `LIVE_STREAM` async path，**实际没实现**——v2 只走 VIDEO 同步

---

## 7. 怎么跑 / 怎么验

```bash
cd D:/Data/ProjectAgent/HandMouse
python -m handmouse.app   # 启动 OpenCV 窗口
```

第一次跑会下载 MediaPipe hand_landmarker.task 到 `%USERPROFILE%/.handmouse/models/`（约 7.5 MB，已下载见 `C:\Users\uwenc\.handmouse\models\hand_landmarker.task`）。

测试：
```bash
python -m pytest -v   # 76 passed
```

完整 14 步验收 checklist 见 README 末尾。

---

## 8. 建议 review 顺序

按"高层到细节"：

1. **本文档**（10 分钟）— 理解项目状态
2. **`docs/research/handmouse-v2-design.md`** §A-F（30 分钟）— 理解设计意图
3. **`src/handmouse/pointer_engine.py`**（30 分钟）— 核心算法，最容易有 edge case bug
4. **`src/handmouse/engagement.py`** + **`src/handmouse/gesture_detector.py`**（各 15 分钟）— 两个 state machine，对照 unit test
5. **`src/handmouse/hand_tracker.py`**（15 分钟）— VIDEO 模式 + detect_for_video，确认 timestamp 语义
6. **`src/handmouse/app.py`**（20 分钟）— 主循环 wiring
7. **`src/handmouse/camera.py`** + **`src/handmouse/debug_view.py`**（各 10 分钟）— 辅助
8. **`config.py`** 清理 v1 字段 — 见 §6.1
9. **真机跑一次** — README 14 步 checklist，把不达标的步骤 + 控制台输出贴给后续 reviewer

## 9. Reviewer 应该问的问题

针对每个模块，按下面三个维度问：

| 维度 | 问题 |
|---|---|
| 正确性 | 状态机有没有未覆盖的 transition？分段函数在边界是否连续？公式实现是否跟公式符号一致？ |
| 健壮性 | 异常输入（空 list、None、极大/极小值）有没有保护？frame 丢失时状态是否被错误 reset？ |
| 可维护性 | config 字段默认值是否在 docstring/comment 标注？测试是否覆盖了 happy path + edge？命名是否一致？ |

特别建议深挖：
- `pointer_engine.py` 的 `_gain_for_velocity` 和 `_depth_factor` 公式实现 vs 设计文档 §D.3
- `app.py` 单线程架构是否能 hold 住 MVO 60fps
- `_is_palm_open` 是否合理，以及 3/4 阈值与 grab_scroll 的 `min_curled_fingers=2` 是否会冲突
- `engagement.update` 的 `hotkey_pressed` 边沿语义，调用方（app.py）的边沿检测是否真的正确
