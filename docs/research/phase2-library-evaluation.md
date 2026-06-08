# HandMouse 阶段 2：手势库选型与替代方案

## 结论先行

1. **主选：MediaPipe Hand Landmarker（Tasks，当前只需按官方页面可见的 full / float16 版本）**
   - 这是现在最稳的生产选项：Windows 可用、Python 可用、开箱即用、维护仍活跃。
   - 官方当前公开页只列出 **HandLandmarker (full)**，输入 `192x192 / 224x224`，量化为 **float16**，没有在当前页上看到 lite / int8 的官方条目。
   - 适合 HandMouse 这种“先把 21 个手部关键点稳定拿到，再做自己的交互逻辑”的场景。

2. **备选：MMPose（优先 RTMPose 的 hand 2D keypoint 路线）**
   - 如果你要摆脱 MediaPipe 的端到端模型和 task 格式锁定，MMPose 是更好的开源退路。
   - 代价是：你要自己补齐手检测、裁剪、跟踪、坐标稳定、手势逻辑，工程量明显比 MediaPipe 大。

3. **Fallback：纯几何手势识别（肤色 / 轮廓 / 凸包 / 凹陷）**
   - 只适合“低成本、低精度、受控环境”的兜底。
   - 适合做最后一层保险，不适合当主路径。

4. **不建议把 MediaPipe Gesture Recognizer 当主库**
   - 官方当前可见的 canned gestures 只有：`None / Closed_Fist / Open_Palm / Pointing_Up / Thumb_Down / Thumb_Up / Victory / ILoveYou`。
   - 这对 UI 快捷动作够用，但对 HandMouse 这类交互，通常不够。
   - 它更像“粗手势分类器”，不是“完整交互手势引擎”。

---

## 1) 评估矩阵

| 方案 | 延迟 | 精度/功能 | 易用性 | 许可/锁定 | 活跃度 | 结论 |
|---|---:|---|---|---|---|---|
| **MediaPipe Hand Landmarker (Tasks)** | 官方 Pixel 6 CPU **17.12 ms** / GPU **12.27 ms**（全流水线） | 21 关键点 + handedness + 跟踪，够做鼠标/手势底座 | **最高** | `.task` 格式 + Google 生态，有一定锁定 | **高**：官方页最新更新时间 **2026-05-28** | **主选** |
| **MediaPipe Gesture Recognizer** | 官方 Pixel 6 CPU **16.76 ms** / GPU **20.87 ms**（全流水线） | 只有 8 个 canned gestures，适合粗分类 | 高 | 同上 | 高：官方页最新更新时间 **2026-05-28** | 作为“辅助层”可以，不建议做主路径 |
| **MMPose / RTMPose hand** | 没有官方同口径手势流水线 benchmark | 关键点路线更开放，适合自定义训练 | 中等 | 开源，但你要自己搭检测/跟踪/后处理 | **中高**：repo `pushed_at=2025-08-04`，最新 release `v1.3.2`（2024-07-12） | **备选** |
| **Ultraleap Gemini** | 设备级方案，理论上可快，但依赖硬件 | 体验可好，但强绑定硬件/SDK | 中等偏低 | **硬件 + SDK 锁定**，公开价格没法直接核实 | 产品线在，但公开开发文档本环境无法直接访问 | 只在你愿意上硬件时考虑 |
| **OpenCV DNN + 自训 ONNX** | 取决于你自己的模型 | 全靠你自己训练和调参 | **最低** | 最自由，但也是最费工 | 取决于你自己 | 只在你要完全自控时用 |
| **纯几何 fallback** | 很低 | 功能最弱，环境敏感 | 中等 | 无锁定 | 取决于实现 | **兜底** |

---

## 2) MediaPipe 当前最优实践

### 2.1 模型版本怎么选

当前官方可见页面里，Hand Landmarker 和 Gesture Recognizer 都只公开了 **full / float16** 这个条目：

- Hand Landmarker：`HandLandmarker (full)`, `192 x 192, 224 x 224`, `float 16`
- Gesture Recognizer：`HandGestureClassifier`, `192 x 192, 224 x 224`, `float 16`

所以这次选型不要押宝所谓“lite / int8 / 其他隐藏变体”的传闻；**按官方当前页面，能确认的就是 full / float16**。

### 2.2 参数建议

建议默认值：

- `running_mode = LIVE_STREAM`（做鼠标/实时交互时）
- `num_hands = 1`
- `min_hand_detection_confidence = 0.5`
- `min_hand_presence_confidence = 0.5`
- `min_tracking_confidence = 0.5`

如果误检多：

- 先把 `min_hand_detection_confidence` 提到 `0.6 ~ 0.7`
- 不要一上来把 `num_hands` 调成 2

如果漏检多：

- 先把 detection 阈值稍微降一点
- 保持 tracking 开着，让系统尽量少触发 palm detector

### 2.3 为啥先坚持 1 手

- 当前项目背景已经说明 **1 手够用**。
- `num_hands=2` 会增加跟踪和身份关联复杂度，也会把一些单手手势的稳定性打折。
- 除非产品明确需要双手交互，否则先别上 2 手。

### 2.4 Python 版本兼容性

当前 PyPI 上 `mediapipe 0.10.35` 的 classifiers 只列了：

- Python 3.9
- Python 3.10
- Python 3.11
- Python 3.12

也就是说：**Python 3.13 目前没有被官方 wheel 明确覆盖**。你现在如果要稳，**3.11 / 3.12 更合适**。

### 2.5 本地模型大小

当前本机模型文件：

- `~/.handmouse/models/hand_landmarker.task`
- 大小：**7,819,105 bytes**（约 **7.45 MiB**）

这个量级对 CPU-only 笔记本来说是合理的，不算重。

---

## 3) 你要的几个硬问题，直接回答

### 3.1 Hand Landmarker 现在到底支不支持 lite / full / int8 / float16？

**按当前可验证的官方页面：只确认到 full / float16。**

我没有在 2026-05-28 的官方页面上看到 lite / int8 的公开表项，所以这次评估不把它们当成“可依赖的官方承诺”。

### 3.2 有没有官方 benchmark？

有，而且是任务级 benchmark，不是你自己的机器上的 benchmark：

- Hand Landmarker：**17.12 ms CPU / 12.27 ms GPU**（Pixel 6）
- Gesture Recognizer：**16.76 ms CPU / 20.87 ms GPU**（Pixel 6）

注意：这是 **Pixel 6**，不是你的 Windows 笔记本。

### 3.3 CPU-only 笔记本上 640x480 / 30fps 怎么估？

这是估算，不是官方数值。

基于官方 Pixel 6 CPU benchmark 和当前模型大小，我会这样预估：

- **单帧 inference（稳态跟踪帧）**：大约 **10–20 ms**
- **端到端（采集 + resize + 推理 + 后处理）**：大约 **15–35 ms/frame**
- **重触发 palm detection 的帧**：可能到 **25–45 ms**

结论：

- **30fps 可行，但前提是 1 手 + LIVE_STREAM + tracking 正常工作。**
- 如果你把双手、复杂阈值、额外分类器全加上去，30fps 会开始吃紧。

### 3.4 Tasks vs Solutions（旧 API）差多少？

**没有找到官方同口径公开 benchmark。**

但从当前事实看：

- 官方可见页面和最新 PyPI 都在推 **Tasks**
- 旧 `solutions` 更像兼容层，不是性能卖点
- 如果是新项目，**别为旧 API 付技术债**

### 3.5 Gesture Recognizer 的 canned gestures 够不够？

**够做粗动作，不够做完整交互。**

它只有：

- `None`
- `Closed_Fist`
- `Open_Palm`
- `Pointing_Up`
- `Thumb_Down`
- `Thumb_Up`
- `Victory`
- `ILoveYou`

所以：

- 如果你的需求只是“几个 UI 快捷动作”，它够用
- 如果你要的是 pinch / drag / hold / hover / fine-grained 连续状态，它不够
- 对 HandMouse，建议把它当辅助，不当主引擎

---

## 4) 替代库怎么判断

### 4.1 Ultraleap Gemini

判断：**可以看，但不建议当前优先切。**

原因：

- 它是**硬件+SDK**路线，不是纯软件库路线
- 公开价格我没法从当前可访问的官方页面核实出来
- 本环境下 Ultraleap 的开发文档页面返回 AccessDenied，说明公开资料可读性一般
- 一旦你接受硬件依赖，迁移成本不止是代码，还是采购、部署、驱动、供应链

适合：

- 你明确要买硬件并接受厂商闭环
- 你追求的是“现成手势体验”，不是“最小依赖”

不适合：

- 你希望软件栈尽量轻
- 你想把未来维护风险压到最低

### 4.2 MMPose / RTMPose

判断：**这是最像“开放型备选”的方案。**

优点：

- 开源、生态成熟
- `mmpose 1.3.2` 已发布，repo 仍在更新
- 手部 2D keypoint 方向有 `rtmpose` 配置

缺点：

- 它不是 MediaPipe 那种“手一伸就给你整套 tracking + landmarks + handedness”的体验
- 你要自己补：hand detector、crop、tracking、平滑、gesture logic
- 真正把体验做齐，工程量会明显更高

适合：

- 你要长期规避单一厂商锁定
- 你愿意花工程时间换可控性

### 4.3 OpenPose

判断：**不建议新项目优先选。**

事实：

- 最新 release 是 **v1.7.0（2020-11-17）**
- repo 近年仍有 push，但 release 级更新非常慢

问题：

- 这是明显的 legacy 路线
- 在 Windows + Python 场景里，维护成本通常比 MMPose 更高
- 你最后多半还是得自己收尾一堆兼容问题

### 4.4 OpenCV DNN + 自训 ONNX

判断：**只适合你想完全自控时用。**

优点：

- 你完全掌握模型和推理链路
- 没有 MediaPipe / MMPose 的框架绑定

缺点：

- 你得自己做数据、训练、导出、推理、后处理、跟踪、稳定性
- 对 HandMouse 这种“实时交互”项目，初期投入很大

结论：

- 这是“终局掌控方案”，不是“当前最省事方案”

---

## 5) 迁移成本估算

### 5.1 MediaPipe -> MMPose

如果你现在已经围绕 MediaPipe 写了交互逻辑：

- **原型迁移**：1–3 个工作日
- **达到接近当前体验**：1–2 周
- **恢复稳定生产质量**：通常还要再多一点调参时间

主要成本在：

- 检测器 / 裁剪 / 跟踪逻辑重写
- landmarks 坐标系与后处理重做
- 你自己的手势状态机要重新验证

### 5.2 MediaPipe -> OpenCV DNN + ONNX

- **如果已有训练数据**：2–5 个工作日可做出能跑的原型
- **如果没有训练数据**：时间不确定，通常会明显拉长

### 5.3 MediaPipe -> Ultraleap

- 代码集成本身不一定很慢
- 真正的大头是：**硬件、驱动、采购、部署、运维**
- 这不是纯软件迁移，是方案迁移

---

## 6) 最终建议

### 推荐组合

- **主选**：**MediaPipe Hand Landmarker (Tasks, full / float16)**
- **备选**：**MMPose / RTMPose hand keypoint**
- **Fallback**：**纯几何手势识别**

### 为什么不是别的

- **不是 Gesture Recognizer 当主库**：类目太少，够粗不够细
- **不是 OpenPose**：太旧，维护性不划算
- **不是 Ultraleap**：硬件锁定太强，公开价格和文档可得性都不够友好
- **不是 OpenCV DNN 自训 ONNX**：过度自控，当前阶段成本太高

### 一句话结论

如果 HandMouse 现在要落地，我会继续用 **MediaPipe Hand Landmarker**，把手势语义写在你自己的状态机里；把 **MMPose** 当未来退路，把 **纯几何** 当最后保险。

---

## 7) 来源

1. MediaPipe Hand Landmarker 官方页（最后更新：2026-05-28）
   - https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker
   - 关键事实：`HandLandmarker (full)`，`192 x 192, 224 x 224`，`float 16`，CPU `17.12 ms`，GPU `12.27 ms`

2. MediaPipe Gesture Recognizer 官方页（最后更新：2026-05-28）
   - https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer
   - 关键事实：`HandGestureClassifier`，`float 16`，CPU `16.76 ms`，GPU `20.87 ms`，canned gestures 列表如上

3. MediaPipe Hand Landmarker Python 页（最后更新：2026-05-28）
   - https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python
   - 关键事实：Python 安装与创建 task 的官方入口

4. PyPI: mediapipe
   - https://pypi.org/project/mediapipe/
   - 版本：`0.10.35`
   - 上传时间：`2026-04-27T17:45:36.193474Z`
   - Python classifiers：`3.9 / 3.10 / 3.11 / 3.12`

5. PyPI: mmpose
   - https://pypi.org/project/mmpose/
   - 版本：`1.3.2`
   - 上传时间：`2024-07-12T12:18:25.794445Z`
   - `requires_python >=3.7`

6. GitHub: open-mmlab/mmpose
   - `pushed_at=2025-08-04T07:30:50Z`
   - `latest release = v1.3.2 (2024-07-12T12:18:03Z)`

7. GitHub: CMU-Perceptual-Computing-Lab/openpose
   - `pushed_at=2024-08-03T01:59:11Z`
   - `latest release = v1.7.0 (2020-11-17T05:48:13Z)`

8. Ultraleap 官方产品页
   - https://www.ultraleap.com/hand-tracking/
   - 可验证到：官网在卖 SDK / hardware / downloads / support；本环境无法直接读到其 docs 子站，公开价格未核实

9. 本机模型文件
   - `~/.handmouse/models/hand_landmarker.task`
   - size: `7,819,105 bytes`
