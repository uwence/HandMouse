# Phase 3 - 性能优化路径（HandMouse）

## 结论先说
当前最值钱的优化，不是先碰量化或 GPU，而是把“全帧 + 每帧同步 `detect()` + `IMAGE` 模式”改成“低分辨率 + `VIDEO/LIVE_STREAM` + 跟踪复用 + 最新帧语义”。

我看了当前代码和官方文档后，判断真实瓶颈大概率在这条链路上：

`1280x720 摄像头抓帧 -> BGR/RGB 转换 -> MediaPipe HandLandmarker 每帧同步推理 -> 画 overlay -> PyAutoGUI 注入`

其中最关键的问题是：当前代码在 `src/handmouse/hand_tracker.py:53-79` 硬编码 `running_mode=IMAGE`，但主循环在 `src/handmouse/app.py:58-87` 是连续视频流；这意味着你没有吃到 MediaPipe 在 `VIDEO/LIVE_STREAM` 模式下的 tracking 复用收益。官方文档明确写了：在 video/live stream 模式里，Hand Landmarker 会用 tracking 避免每帧都触发 palm detection，从而降低延迟。

## 已验证事实
1. MediaPipe Hand Landmarker 官方页面给出的 task benchmark：Pixel 6 上 `HandLandmarker (full)` 的平均延迟是 CPU 17.12ms、GPU 12.27ms。
2. 官方页面显示该 task 的公开模型包是 `float16`，我实测其 canonical 任务文件 `hand_landmarker.task` 的 `Content-Length` 是 7,819,105 bytes；同一路径的 `int8` / `float32` 404，不是公开发布资产。
3. OpenCV 文档明确支持显式指定 camera backend：`CAP_DSHOW`、`CAP_MSMF`、`CAP_ANY`；`CAP_PROP_BUFFERSIZE` 也是可设属性。
4. PyAutoGUI 文档说明 `moveTo()` 默认是瞬移；只有当 `duration >= MINIMUM_DURATION`（默认 0.1s）时才会变慢。你现在用 `duration=0`，已经是 PyAutoGUI 的最短路径。
5. Microsoft `SendInput` 文档说明它把输入事件按序注入系统输入流，不会被其他 `mouse_event` / `keybd_event` 插队，适合做更直接的鼠标注入层。

## 当前瓶颈分析（按链路）
### 1) 摄像头输入
- 现在默认 1280x720，且 `Camera.open()` 只设了宽高，没有指定 backend，也没有显式缓冲策略。
- `Camera.read()` 里有重试循环，说明你已经在兜底“读帧不稳”。
- 这段的风险不是纯耗时，而是“抓到的帧不一定是最新帧”。

### 2) 视觉推理
- 当前是 `detect()` 每帧同步推理，且 `IMAGE` 模式会把每帧都当单图处理。
- 这会让 tracking 机制失效或大幅弱化，等于把 MediaPipe 最有价值的省时机制浪费掉。
- 这通常比单纯换 PyAutoGUI 更重要。

### 3) 后处理与注入
- 手势判定、overlay、按键/滚动注入都在同一条主循环里。
- 这意味着任何一步慢，都会直接拖慢整个 FPS。
- 但这里通常不是最大头，最大头还是推理本身。

## 优化清单（按收益排序）

### A. 必做：把 `IMAGE + detect()` 改成 `VIDEO` 或 `LIVE_STREAM`
预估收益：非常高

实施成本：中等

风险：低

为什么：
- 官方文档明确说明，video/live stream 模式会利用 tracking，减少 palm detection 触发次数，直接降低延迟。
- 你现在代码里 `min_hand_presence_confidence` / `min_tracking_confidence` 这两个参数，只有在 video/live stream 模式下才真正有意义。

建议实现方式：
- 如果你想保留单线程逻辑，先改 `detect_for_video(mp_image, frame_timestamp_ms)`。
- 如果你想做真正的异步重叠，改 `LIVE_STREAM + detect_async()`，把结果放回 callback，再用最新结果驱动控制层。

### B. 必做：把分辨率先降到 640x480 做主路径
预估收益：高

实施成本：低

风险：中等（主要是手部太小会掉精度）

理由：
- 官方没有给出 hand_landmarker 的分辨率 vs latency 表，所以不存在“官方甜点位”可直接照抄。
- 但从计算路径看，输入像素数下降，预处理和推理压力都会下降。
- 对实时鼠标/滚动控制，通常先求稳定到 60fps，再根据实际丢精度情况往上加分辨率。

建议起步：
- 主控制路径：`640x480`
- 如果手部太小或抖动明显，再试 `960x540`
- 只有在 640x480 精度明显不够时，才回退到 1280x720

### C. 必做：改成“最新帧语义”，不要积压旧帧
预估收益：高

实施成本：中等

风险：低

建议：
- capture 线程只保留最新一帧，队列大小固定为 1。
- 推理线程拿到的是“此刻最新帧”，不是排队 200ms 前的旧帧。
- 对手势控制这类交互，旧帧比丢帧更糟。

一句话原则：
- 宁可跳帧，不要排队。

### D. 必做：OpenCV backend 显式化 + 缓冲压到 1
预估收益：中高

实施成本：低

风险：低

建议顺序：
1. 先试 `CAP_DSHOW`
2. 再试 `CAP_MSMF`
3. 保留 `CAP_ANY` 作为兜底，但不要让它成为默认
4. 设 `CAP_PROP_BUFFERSIZE = 1`（如果 backend 接受）

说明：
- OpenCV 官方只保证你可以指定 backend；并没有给你“Windows 上谁一定更快”的绝对结论。
- 所以这里的正确做法不是听传闻，而是对你的摄像头实测。

### E. 建议：保持 float16，不要把 int8 当成眼前捷径
预估收益：不确定；对当前项目短期收益很可能不如前面几项

实施成本：高

风险：中高

事实：
- 当前公开发布的 Hand Landmarker 资产是 `float16`。
- 我检查了 canonical 路径，`int8` 资产没有公开发布。
- LiteRT / TFLite 的通用文档确实说：
  - float16 通常可让模型更小，GPU 也更友好；
  - full integer quantization 通常更小、更快，但要看算子和硬件支持。

结论：
- 对当前 HandMouse，不建议把“做一个 int8 自定义模型”放进 MVO。
- 这条更像独立研究分支，不是最先该做的优化。

### F. 可做：把 PyAutoGUI 换成 `SendInput` / ctypes
预估收益：中等

实施成本：中等

风险：中

判断：
- 你现在 `duration=0`，已经绕开了 PyAutoGUI 自身最明显的慢路径。
- 所以这里不是当前最大瓶颈。
- 但如果你要做更稳定、更直接的输入注入，`SendInput` 是更合理的底层接口。

建议策略：
- 先保留 PyAutoGUI 做验证。
- 真正冲 60fps 之后，再把注入层单独替换成 `SendInput`。

### G. 进阶：外部 ROI 裁剪，而不是先上复杂硬件加速
预估收益：高

实施成本：中高

风险：中

MediaPipe 的 task API 本身没有给你一个“直接让用户指定 ROI 再跑内部 landmark”的简单按钮。更现实的做法是：
- 用上一帧的手部位置裁剪出 ROI
- 只把 ROI 送进 landmarker
- 再把局部坐标映射回全局坐标

这条路的收益确实可能很大，但实现复杂度也明显上升。

### H. 最后再看：GPU / DirectML / OpenVINO / TensorRT / XPU
预估收益：中到高，但取决于迁移成本

实施成本：高

风险：高

当前判断：
- 我没有找到 MediaPipe HandLandmarker 在 Windows Python 里对这些后端的“官方一键支持”证据。
- 这意味着它们更像迁移工程，而不是当前版本的最小可行优化。
- 如果你先把前面 A/B/C/D 做完，很多时候 CPU 方案已经够用，没必要一开始就上重型后端。

## 推荐的最小可行优化（MVO）配置
如果目标是尽快把系统拉近 60fps，我建议先定这个配置：

- 分辨率：`640x480`
- MediaPipe 模式：`VIDEO` 优先；如果要重构成异步，再上 `LIVE_STREAM`
- 推理接口：`detect_for_video()` 或 `detect_async()`，不要继续 `detect()`
- 线程模型：capture / inference / control 分离，队列只保留最新帧
- OpenCV backend：`CAP_DSHOW` 与 `CAP_MSMF` 逐个实测，默认显式指定一个
- 缓冲：`CAP_PROP_BUFFERSIZE=1`（若支持）
- 模型：继续用官方 `float16` 资产
- 注入：先保留 PyAutoGUI 验证，后面再评估 `SendInput`

## 60fps 目标下的“必须做”和“可做”
### 必须做
- 改 `IMAGE -> VIDEO/LIVE_STREAM`
- 改 `detect() -> detect_for_video()/detect_async()`
- 把输入降到 640x480 起步
- 最新帧语义，禁止积压
- 显式 backend + 缓冲控制
- 控制路径尽量轻量，控制模式下少画 overlay

### 可做
- 外部 ROI 裁剪
- `SendInput` 注入
- 更激进的模型/量化实验
- GPU / OpenVINO / TensorRT / XPU 迁移

## Benchmark / profile 方法
### 1. 先做分段计时，不要只看总 FPS
建议拆成这几段：
- camera read
- BGR -> RGB
- MediaPipe inference
- gesture / pointer mapping
- input injection
- overlay render

记录每段：
- 平均值
- p50
- p95
- 最大值
- 丢帧数

### 2. Python 侧工具怎么选
- `cProfile`：看 Python 函数调用栈，适合定位手势/控制层里的纯 Python 热点
- `py-spy --native`：适合看整个进程，包括 native 扩展、OpenCV、MediaPipe 周边耗时
- `line_profiler`：只给纯 Python 热点做细粒度分析，不要拿它去硬看 C++ 扩展

### 3. 实测方式
- 连续跑至少 300~1000 帧
- 统计稳态，不要拿启动前几十帧当结论
- 异步模式下要记住“帧年龄”，不要只看 callback 数量
- 先测空载摄像头，再测带 overlay，再测带注入，逐层加上去

## 公开来源
1. MediaPipe Hand Landmarker 官方页面
   - 模式、tracking 说明、task benchmark（Pixel 6 CPU/GPU）
   - https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker
2. MediaPipe Hand Landmarker Python guide
   - `detect` / `detect_for_video` / `detect_async`
   - tracking 在 video/live stream 下减少 latency 的说明
   - https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python
3. LiteRT / TFLite post-training quantization
   - float16 / int8 / full integer quantization 的通用收益说明
   - https://ai.google.dev/edge/litert/models/post_training_quantization
   - https://www.tensorflow.org/lite/performance/model_optimization
4. OpenCV VideoCapture docs
   - backend preference, `CAP_DSHOW`, `CAP_MSMF`, `CAP_ANY`
   - `CAP_PROP_BUFFERSIZE`, `CAP_PROP_FPS`
   - https://docs.opencv.org/4.13.0/d8/dfe/classcv_1_1VideoCapture.html
   - https://docs.opencv.org/4.13.0/d4/d15/group__videoio__flags__base.html
5. PyAutoGUI mouse docs
   - `moveTo()` 默认 instant，`MINIMUM_DURATION=0.1`
   - https://pyautogui.readthedocs.io/en/latest/mouse.html
6. Microsoft SendInput docs
   - 输入事件序列注入说明
   - https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput

## 备注
- 这份结论里，只有官方 benchmark、模型资产大小、OpenCV/PyAutoGUI/SendInput 行为是直接验证过的。
- “640x480 / 960x540 的甜点位”、“backend 谁更快”、“ROI 裁剪是否值得”这些是工程建议，不是官方 benchmark；需要你们在真实机器上做 A/B 测试确认。
