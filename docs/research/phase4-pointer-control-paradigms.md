# Phase 4：指针控制范式研究

## 结论先行
建议默认采用：**相对指针 + 自适应加速曲线 + 双阈值 pinch + 显式激活态**。

原因很直接：
- Webcam 手势是**自由空间输入**，不是稳定 2D 物理面，绝对映射会被视角、手抖、遮挡、距离变化放大。
- 相对映射可以把“手怎么动”转成“指针怎么走”，再用加速曲线把“慢速精确”和“快速跨屏”同时保住。
- pinch 用双阈值比单阈值稳得多，能显著减少抖动触发。
- 激活态必须显式存在，否则系统会把“人在镜头前”误判成“人在控制”。

如果你只想要一句话：**webcam hand control 更像 mouse-like relative control，不像 touchpad absolute mapping。**

---

## 1) 绝对 vs 相对：业界怎么理解

### 结论
- **绝对**：输入坐标直接映射到目标坐标。适合“输入面”和“目标面”一一对应的场景，比如触摸屏、数位板、直接书写、校准良好的单一平面。
- **相对**：输入的是位移/速度，不是绝对位置。适合鼠标、自由空间手势、VR/AR 中的射线选择、以及任何没有稳定物理平面的输入。

### 为什么 Quest / VR 手势通常不用绝对
- 3D 手在空间里没有一个天然稳定的“屏幕平面”。
- 用户姿态、相机位置、头部移动都会让绝对投影漂移。
- VR/AR 里更常见的是 **ray / reticle / relative displacement**，而不是“把手指坐标直接贴到屏幕像素上”。

### 为什么 Mac 触控板是“相对感”而不是 webcam 绝对映射
- 触控板是一个固定、近身、可触摸的物理面，用户能持续接触并通过手指位移驱动指针。
- macOS 公开的是 tracking speed / gesture 体验，而不是“把手指坐标绝对贴到屏幕”这种语义。
- 它本质上更接近“带手势的相对控制面”，而不是 webcam 手势那种无接触自由空间控制。

### 为什么 Wacom 数位板更适合绝对
- 数位板是一个稳定 2D 平面，笔尖位置和绘图坐标天然同构。
- 绝对映射对“画线、定位、笔迹”非常自然。
- 这类输入的优势是“点哪到哪”，不是“拖多久到哪”。

### 什么时候绝对更舒服
- 直接书写 / 绘画 / 标注
- 需要严格一一对应的位置输入
- 输入表面和目标平面有明确几何关系
- 用户愿意接受校准、并且手部轨迹稳定

### 什么时候相对更舒服
- 自由空间输入
- 没有稳定物理表面
- 需要跨大范围移动
- 输入噪声大、视角变化大、容易遮挡
- 需要兼顾疲劳和精度

### 工程判断
对 HandMouse 这种 webcam 手势控制，默认应选 **相对**。
绝对只适合特定模式：例如“笔迹/白板式”场景，或者你明确做了一个虚拟平面并接受校准成本。

---

## 2) 加速曲线：不要做成线性

### 行业共识
鼠标/指针控制的主流思路不是纯线性，而是：
- **慢速时给精度**
- **中速时尽量接近 1:1**
- **高速时放大位移，便于跨屏**

libinput 的公开实现很典型：
- 默认是 **adaptive** profile
- 慢速会有 **deceleration**
- 常规速度接近 **1:1**
- 高速时线性提升到更高增益
- 公开文档里，最大减速大约到 **0.3x**，最大加速大约到 **3.5x**

对于 webcam 手势，我建议比鼠标更保守一点：
- 低速区不要太“飘”
- 高速区不要太猛
- 曲线要平滑，别用硬折线

### 推荐实现：分段平滑增益
定义：
- `p_t = (x_t, y_t)`：当前手部控制点
- `s_hand`：手尺度，建议用 palm width 归一化
- `u_t = (p_t - p_{t-1}) / s_hand`
- `v_t = ||u_t|| / Δt`：归一化速度

然后：

```text
if v_t < v_jitter:
    g(v_t) = 0
elif v_t < v_mid:
    g(v_t) = g_lo + (1 - g_lo) * (v_t - v_jitter) / (v_mid - v_jitter)
else:
    g(v_t) = 1 + (g_hi - 1) * smoothstep(v_mid, v_fast, v_t)
```

其中：
- `g_lo = 0.85 ~ 1.00`
- `g_hi = 2.5 ~ 3.5`
- `v_jitter = 0.15 ~ 0.30 palm-width/s`
- `v_mid = 0.8 ~ 1.2 palm-width/s`
- `v_fast = 2.5 ~ 4.0 palm-width/s`
- `smoothstep(a,b,x) = t^2(3-2t), t = clamp((x-a)/(b-a), 0, 1)`

最终位移：

```text
Δcursor_t = K * g(v_t) * A_active * A_z * u_t
```

- `K`：像素缩放常数
- `A_active`：激活态门控，active=1，idle=0
- `A_z`：深度补偿项

### 为什么不是纯线性
纯线性对 webcam 手势很差，原因有三个：
1. 生理手抖和视觉抖动会直接映射到指针抖动。
2. 远距离跨屏会变得太累。
3. 不同用户的手速跨度太大，线性很难同时兼顾新手和熟练用户。

---

## 3) Hysteresis：pinch 必须双阈值

### 结论
pinch 不能只用一个阈值。要用 **close / open 双阈值**。

### 推荐定义
用 thumb tip 和 index tip 的距离做 pinch：

```text
d_pin = ||thumb_tip - index_tip|| / s_hand
```

其中 `s_hand` 建议用 palm width 归一化，比如：

```text
s_hand = ||index_mcp - pinky_mcp||
```

推荐阈值：
- `close_threshold = 0.045 ~ 0.060`
- `open_threshold  = 0.065 ~ 0.090`

建议默认值：
- `close = 0.05`
- `open  = 0.075`

### 解释
- `d_pin < close_threshold`：进入 pinch pressed
- `d_pin > open_threshold`：退出 pinch pressed
- 中间区间保持当前状态

### 为什么要 hysteresis
- 单阈值会在临界点来回抖
- 手势识别本身就有噪声
- pinch 这个动作天然有“压下去”和“松开去”两个稳定态

### 推荐状态机
```text
open -> pressed  : d_pin < close_threshold for N frames
pressed -> open  : d_pin > open_threshold for M frames
```

建议：
- `N = 2 ~ 3`
- `M = 2 ~ 4`
- 加 30~60 ms 的短时间确认，别做单帧触发

---

## 4) 激活态：至少 3 个候选方案

### 方案 A：显式开关（推荐默认）
例子：键盘热键、脚踏开关、语音“开始控制”、UI 按钮。

优点：
- 最稳
- 误触最低
- 方便调试和回退

缺点：
- 有额外操作成本
- 不够“无缝”

适用：
- 生产环境
- 对误触敏感
- 需要强可控性

---

### 方案 B：姿势激活
例子：open palm、index point up、某个固定手势。

优点：
- 全手势化
- 不依赖额外硬件
- 体验连续

缺点：
- 误识别率高于显式开关
- 不同用户姿势差异大
- 光照、遮挡、镜头角度会影响

适用：
- 演示
- 轻量交互
- 用户愿意接受少量误触

---

### 方案 C：空间/距离激活
例子：手必须进入某个 ROI，或者 z 必须落在某个带宽内。

优点：
- 适合摄像头输入
- 可作为安全门槛
- 能减少远距离背景误触

缺点：
- 强依赖镜头摆位
- 用户需要记住“在什么位置才能触发”

适用：
- 桌面固定摄像头
- 手势控制只覆盖局部区域

---

### 推荐：混合式
我建议：
1. **显式开关作为主入口**
2. **姿势激活作为无键盘备选**
3. **ROI / z-band 只做安全门禁，不做主逻辑**

也就是说：
- `idle`：系统不接收控制
- `armed`：系统允许识别，但还不发指针
- `active`：开始输出指针
- `cooldown`：释放后短暂防抖

推荐状态：
```text
idle -> armed -> active -> cooldown -> armed/idle
```

---

## 5) Z 深度补偿

### MediaPipe 的数据假设
根据 MediaPipe Hands / Hand Landmarker：
- `x, y` 是图像归一化坐标，范围大致 `[0,1]`
- `z` 是**相对深度**，以 wrist 为原点
- **z 越小，越靠近摄像头**
- `z` 的量级大致和 `x` 相近，但不是物理毫米
- `world landmarks` 提供的是米制 3D 坐标，origin 在手的近似几何中心

### 结论
`z` 不应该直接当成绝对距离用。最稳的做法是：
- `z` 做**修正项**
- 2D 手尺度变化做**主 proxy**
- 如果能拿到 world landmarks，优先用 world 3D 做校准，再回退到 image z

### 推荐算法 1：基于手尺度的补偿
手靠近镜头时，2D 投影会变大；因此应降低 cursor gain。

```text
s_t = median(
    ||index_mcp - pinky_mcp||,
    ||wrist - middle_mcp||,
    ||wrist - index_mcp||
)
A_z = clamp((s_ref / s_t)^γ, z_min, z_max)
```

推荐参数：
- `γ = 0.7 ~ 1.2`
- `z_min = 0.7`
- `z_max = 1.3`

含义：
- 手变大（更靠近） -> `s_t` 变大 -> `A_z` 变小 -> 指针更稳
- 手变小（更远） -> `A_z` 变大一点 -> 不会太“钝”

### 推荐算法 2：z + 尺度混合
```text
z_raw = median(z_fingertips) - z_wrist
z_proxy = λ * z_raw + (1 - λ) * log(s_ref / s_t)
A_z = clamp(1 + k_z * z_proxy, z_min, z_max)
```

推荐参数：
- `λ = 0.3 ~ 0.5`
- `k_z = 0.15 ~ 0.30`
- `z_min = 0.7`
- `z_max = 1.25`

### 工程建议
- **先做尺度补偿，再叠 z 修正**
- z 不要单独决定控制强度
- z 更适合做“深度抑制 / 深度补偿 / 近手降增益”

---

## 6) Dead zone：不要做成“屏幕中心死区”

### 我的判断
对 webcam 手势，dead zone 最好定义在**输入空间**，不是屏幕空间。

### 推荐几何
- **运动 dead zone**：圆形或椭圆形
- **激活 ROI**：矩形或圆角矩形

### 为什么圆形更好
- 运动噪声大致是各向同性的
- 圆形更符合“半径”直觉
- 方形会在角落产生不连续边界

### 推荐值
如果输入已经做了 palm width 归一化：
- motion dead zone：`0.15 ~ 0.30 palm-width/s`
- 额外静止抖动抑制：`2 ~ 4 px` 等价量级（取决于分辨率和滤波）

### 不建议的做法
- 把“屏幕中心一块区域”做成 motion dead zone
- 把边缘做成特殊 dead zone

原因：
- 会伤害边缘 target acquisition
- 会让用户感觉“到边上突然不灵了”
- 这更像 UI 限制，不像输入抑噪

### 如果一定要中心 ROI
那是激活门禁，不是 dead zone：
- ROI 用于“是否允许控制”
- dead zone 用于“允许控制后，微小抖动是否忽略”

---

## 7) Touchpad-like vs Mouse-like

### 结论
对 webcam 手势，**Mouse-like** 更合适，**Touchpad-like** 只能作为特定模式。

### Mouse-like 的优点
- 对自由空间输入更自然
- 需要的手部动作更少
- 配合加速曲线能跨大范围移动
- 更适合长时间使用

### Touchpad-like 的问题
- 它假设有一个稳定、可触摸的表面
- 会把“接触/滑动”的肌肉记忆强行搬到空中
- webcam 场景里手会飘、会抖、会失焦，体验通常不稳

### 什么时候可以做成 touchpad-like
- 你明确要做“虚拟触控板”模式
- 用户愿意把某个平面当作操作面
- 你有很好的校准、clutch、重置机制

否则，默认还是 mouse-like。

---

## 8) 推荐默认参数（首轮可落地）

### 模式
- `relative`：是
- `acceleration`：是
- `hysteresis`：是
- `explicit active state`：是
- `absolute mapping`：否，除非进入特殊“书写/白板”模式

### 初始参数
```text
pinch_close_threshold = 0.05
pinch_open_threshold  = 0.075
pinch_confirm_frames  = 2~3

v_jitter = 0.20 palm-width/s
v_mid    = 1.0 palm-width/s
v_fast   = 3.0 palm-width/s

g_lo = 0.85

g_hi = 3.0
gamma = 1.4

z_min = 0.70
z_max = 1.25
k_z   = 0.20
lambda_z = 0.4

roi = center 60~80% width, 60~75% height
cooldown = 150~300 ms
```

### 滤波
- 位置：1-pole EMA，`α = 0.2 ~ 0.35`
- z：比 xy 稍重一点，`α_z = 0.15 ~ 0.25`
- 若检测波动大，再加一个中值滤波窗口 `3~5 frames`

---

## 9) 最终建议
如果你要我拍板：

1. **默认走相对模式**
2. **曲线用自适应 gain，不要纯线性**
3. **pinch 用双阈值 hysteresis**
4. **必须有显式激活态**
5. **z 只做补偿，不做主控制量**
6. **dead zone 放在输入空间，圆形/椭圆形优先**
7. **绝对模式只留给特殊的“虚拟平面/书写”模式**

---

## 参考来源
- libinput Pointer acceleration: https://wayland.freedesktop.org/libinput/doc/latest/pointer-acceleration.html
- libinput Absolute axes: https://wayland.freedesktop.org/libinput/doc/latest/absolute-axes.html
- Apple Mac mouse / trackpad tracking speed: https://support.apple.com/guide/mac-help/change-mouse-settings-on-mac-mchlp1138/mac
- Apple trackpad settings: https://support.apple.com/guide/mac-help/change-trackpad-settings-mchl7fce08f0/mac
- Google AI Edge / MediaPipe Hand landmarker: https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker
- MediaPipe Hands docs with z / world landmarks semantics: https://chuoling.github.io/mediapipe/solutions/hands.html
- Microsoft Raw Input docs: https://learn.microsoft.com/en-us/windows/win32/inputdev/raw-input
