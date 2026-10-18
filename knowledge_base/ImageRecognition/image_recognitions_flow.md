### image_recognitions.py 流程说明

本文档概述 `app-prismax-rp-backend/app_prismax_tele_op_services/image_recognitions.py` 的核心能力、输入输出规范、主要函数流程与使用示例，便于测试与联调。


## 概述
- 目标：对托盘场景图像进行左右计数与状态对比分析。
- 能力：
  - 单张图片计数（左、右）
  - 成对图片对比（START/END），可推断左右数量变化与物体移动方向
  - 多帧投票融合（最多前 5 帧），提升稳健性
  - 结果一致性校验（总数守恒与左右差分校验）
- 模型：默认使用 `gpt-4o` 多模态（可配置）。


## 依赖与密钥管理
- 依赖 OpenAI Python SDK 与 GCP Secret Manager：
  - 从 GCP Secret Manager 读取 OpenAI API Key，优先级：
    - `GOOGLE_CLOUD_PROJECT` 或 `PROJECT_ID` 或 `GCP_PROJECT` 或默认 `'thepinai'`
    - Secret 名：环境变量 `OPENAI_API_KEY_SECRET_ID`（默认 `'OPENAI_API_KEY'`）
  - 客户端惰性初始化：首次调用时创建 `OpenAI(api_key=...)`


## 场景与提示词
- 根据 `robotId` 区分两类托盘场景：
  - `arm1`：左为矩形托盘，右为圆形托盘
  - `arm2`：左右均为黑色矩形托盘
- 提示词均强调：只返回严格 JSON：`{"left": <int>, "right": <int>}`，忽略机械臂、轨道、线缆、分隔/托盘本体、桌面等干扰元素。


## 输入输出规范
- 单张图片计数
  - 输入：`image_b64: str`（base64 或 data-url），`robotId: str`（`arm1`/`arm2`）
  - 输出：`{"left": int, "right": int}`
- 成对图片对比（逐视角独立分析）
  - 输入：
    ```json
    {
      "cam1": {"start": "<b64>", "end": "<b64>"},
      "cam2": {"start": "<b64>", "end": "<b64>"}
    }
    ```
  - 输出：
    ```json
    {
      "model": "gpt-4o",
      "views": {
        "cam1": {"start": {"left": 0, "right": 0}, "end": {"left": 0, "right": 0}},
        "cam2": {"start": {"left": 0, "right": 0}, "end": {"left": 0, "right": 0}}
      },
      "meta": {"ms": 1234}
    }
    ```
- 成对图片一次提示/含移动推断（pairwise）
  - 输出与上类似，但会在 `meta.moved` 中追加移动信息：
    ```json
    "meta": {
      "ms": 1234,
      "moved": {
        "cam1": {"l_to_r": 1, "r_to_l": 0},
        "cam2": {"l_to_r": 0, "r_to_l": 1}
      }
    }
    ```
- 多帧投票融合
  - 输入：每个视角的多帧 `start/end` 列表（最多取前 5 帧）：
    ```json
    {
      "cam1": {
        "start": ["<b64_1>", "<b64_2>", "..."],
        "end":   ["<b64_1>", "<b64_2>", "..."]
      }
    }
    ```
  - 输出：与 `views` 结构一致，`start/end` 的 `left/right` 取多数投票值。


## 主要函数

### analyze_single_image(image_b64, robotId, model_name="gpt-4o") -> Dict[str, int]
- 逻辑：
  1) 将 base64 转为 data-url 形式
  2) 构造 system+user 内容（基于 `PROMPT_LIST[robotId]` + 图片）
  3) 调用 Responses API；优先读取 `resp.output_text`
  4) 尝试 `json.loads` 解析；失败则用正则提取 `{...}` 兜底
  5) 将 `left/right` 转为 `int` 返回
- 返回：`{"left": int, "right": int}`（默认缺失或失败时各为 0）

### analyze_compare(views, robotId, model_name="gpt-4o") -> Dict[str, Any]
- 用“逐视角两次单张分析”的方式：对每个 `cam` 的 `start/end` 各调用一次 `analyze_single_image`。
- 汇总耗时并返回统一结构（见上）。

### analyze_compare_pairwise(views, robotId, model_name="gpt-4o") -> Dict[str, Any]
- 用一次多模态提示同时输入 START/END 两张图，请模型同时输出：
  ```json
  {"start":{"left":<int>,"right":<int>},"end":{"left":<int>,"right":<int>},"moved":{"l_to_r":<int>,"r_to_l":<int>}}
  ```
- 解析失败时回退为两次单张分析；返回的 `views` 与 `analyze_compare` 保持一致；移动信息放入 `meta.moved`。

### evaluate_compare_result(res) -> Tuple[bool, int]
- 一致性规则校验：
  - 每个视角 `total_start == total_end`（总数守恒）
  - 左右变化量互为相反数：`(end.left - start.left) == - (end.right - start.right)`
  - 返回 `(abnormal: bool, success_count: int)`；`success_count` 汇总有效移动量。

### single_frame_views_by_index(multi_views, idx) -> views
- 从多帧输入中抽取第 `idx` 帧组成 `views`（便于分帧分析）。

### build_voted_views_across_five(multi_views, robotId, result1=None, result2=None, model_name="gpt-4o")
- 融合前 5 帧：
  - 帧 1、2 可复用已计算结果 `result1/result2`，减少重复请求
  - 帧 3..5 会重新调用单张分析
  - 分别对 `start.left/right` 与 `end.left/right` 做“众数投票”得到最终计数


## 使用示例

### 1) 单张计数
```python
from app_prismax_tele_op_services.image_recognitions import analyze_single_image

res = analyze_single_image(image_b64="<base64>", robotId="arm2")
# -> {"left": 1, "right": 2}
```

### 2) 成对图片对比（逐视角）
```python
from app_prismax_tele_op_services.image_recognitions import analyze_compare

views = {
    "cam1": {"start": "<b64_s>", "end": "<b64_e>"},
    "cam2": {"start": "<b64_s2>", "end": "<b64_e2>"},
}
res = analyze_compare(views, robotId="arm2")
# -> {"model": "...", "views": {...}, "meta": {"ms": ...}}
```

### 3) 成对一次提示/含移动
```python
from app_prismax_tele_op_services.image_recognitions import analyze_compare_pairwise

views = {"cam1": {"start": "<b64_s>", "end": "<b64_e>"}}
res = analyze_compare_pairwise(views, robotId="arm2")
# res["views"]["cam1"] -> {"start": {...}, "end": {...}}
# res["meta"]["moved"]["cam1"] -> {"l_to_r": x, "r_to_l": y}
```

### 4) 多帧投票融合（最多 5 帧）
```python
from app_prismax_tele_op_services.image_recognitions import build_voted_views_across_five

multi_views = {
    "cam1": {
        "start": ["<b64_s1>", "<b64_s2>", "<b64_s3>"],
        "end":   ["<b64_e1>", "<b64_e2>", "<b64_e3>"],
    }
}
res = build_voted_views_across_five(multi_views, robotId="arm2")
# -> {"cam1": {"start": {"left": ...,"right": ...}, "end": {...}}}
```


## 注意事项与异常处理
- 所有 JSON 解析都带正则兜底；无法解析时默认 0 或回退到单张分析。
- 输出均强转为 `int`，避免类型不一致。
- 若 Secret 读取失败会打印日志并返回 `None`，请确保已在 GCP 中配置 OpenAI Key：
  - 项目 ID 通过环境变量提供（见前述优先级）
  - Secret 名通过 `OPENAI_API_KEY_SECRET_ID` 配置（默认 `OPENAI_API_KEY`）
- 默认模型为 `gpt-4o`，可通过参数 `model_name` 覆盖。


## 测试建议
- 准备典型场景集：空托盘、只左侧、只右侧、两侧均有、遮挡/反光、不同背景/光照。
- 对 pairwise 输出使用 `evaluate_compare_result` 做一致性判定；通过 `success_count` 评估移动推断质量。
- 对视频帧抽样 3~5 帧进行投票融合，验证稳健性提升。


## 图片获取来源（前端）
前端在 Tele-Op 控制模式下，通过 WebSocket 接收来自机器人服务器推送的 JPEG 帧数据（payload 为 base64），前端直接拼为 Data URL 显示。该 Data URL/base64 字符串可直接作为本文件识别接口 `views` 的 `start/end` 输入。

- 主相机帧接收并转为 `data:image/jpeg;base64,...`（`TeleOp.js`）

```652:658:app-prismax-rp/src/components/TeleOp/TeleOp.js
wsRef.current.onmessage = (event) => {
    try {
        const data = JSON.parse(event.data);

        if (data.type === 'video_frame') {
            setVideoSrc(`data:image/jpeg;base64,${data.data}`);
```

- 第二相机帧接收（`TeleOp.js`）

```695:701:app-prismax-rp/src/components/TeleOp/TeleOp.js
ws2Ref.current.onmessage = (event) => {
    try {
        const data = JSON.parse(event.data);

        if (data.type === 'video_frame') {
            setVideoSrc2(`data:image/jpeg;base64,${data.data}`);
```

- 前端展示直接使用 `<img src={...}>`，无需 `canvas.toDataURL`（`VideoFeed.js`）

```139:146:app-prismax-rp/src/components/TeleOp/VideoFeed.js
<img
    src={mainVideoSrc}
    alt="Live camera feed"
    className={styles.videoFeed}
    style={{width: '100%', height: '100%', objectFit: 'contain'}}
/>
```

- 本地开发模式下逻辑一致：从本地 WS 获取帧并拼接 Data URL（`TeleOpLocal.js`）

```315:321:app-prismax-rp/src/components/TeleOp/TeleOpLocal.js
if (data.type === 'video_frame') {
    setVideoSrc(`data:image/jpeg;base64,${data.data}`);
    frameCountRef.current++;
    const now = Date.now();
    const elapsed = now - lastFpsUpdateRef.current;
```

```355:357:app-prismax-rp/src/components/TeleOp/TeleOpLocal.js
if (data.type === 'video_frame') {
    setVideoSrc2(`data:image/jpeg;base64,${data.data}`);
}
```

- 衔接到识别接口
  - 若需要“取某一时刻的快照”用于识别，可直接取当前的 `videoSrc/videoSrc2` 字符串（或去掉 `data:image/jpeg;base64,` 前缀，仅保留 base64）作为 `views[cam].start/end` 传给后端 `/vision/dolls_compare`。
  - 当前实现未使用前端 `canvas.toDataURL` 进行截图，直接复用服务端推送的 JPEG base64 帧即可。


