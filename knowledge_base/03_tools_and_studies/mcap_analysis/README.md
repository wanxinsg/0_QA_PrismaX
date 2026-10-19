# MCAP 数据解析工具

## 📁 目录结构

```
McapData/                           # 当前目录（运行脚本的目录）
├── parse_mcap.py                   # 完整的 MCAP 解析工具
├── quick_view.py                   # 快速查看工具
├── requirements.txt                # Python 依赖
└── README.md                       # 本文档

Feature_CaseDesign/4_Mcap Data/
└── output-20260129/                # 数据目录
    ├── 0/
    │   ├── robot.env_camera.color.image_raw.mp4
    │   ├── robot.left_camera.color.image_raw.mp4
    │   └── robot.right_camera.color.image_raw.mp4
    ├── 0.mcap
    ├── 50/
    │   └── (三个视频文件)
    ├── 50.mcap
    ├── 100/
    │   └── (三个视频文件)
    └── 100.mcap
```

## 🚀 快速开始

### 1. 安装依赖

```bash
cd /Users/wanxin/PycharmProjects/WORK/Prismax/0_QA_PrismaX/knowledge_base/03_tools_and_studies/mcap_analysis
pip install -r requirements.txt
```

### 2. 快速查看单个文件

```bash
# 查看 0.mcap 文件信息
python quick_view.py ../QA_Feature_CaseDesign/4_Mcap\ Data/output-20260129/0.mcap

# 或者如果没有参数，会自动查找并分析第一个找到的 MCAP 文件
python quick_view.py
```

### 3. 运行完整分析

```bash
# 分析所有 MCAP 文件并进行比较
python parse_mcap.py
```

这将：
- ✅ 分析 MCAP 文件结构
- ✅ 列出所有通道（topics）和消息类型
- ✅ 统计消息数量、时长、帧率等信息
- ✅ 比较三个数据集（0.mcap, 50.mcap, 100.mcap）的差异

## 📊 功能说明

### quick_view.py - 快速查看工具

快速查看单个 MCAP 文件的基本信息：

```bash
python quick_view.py <mcap文件路径>
```

输出内容：
- 📊 文件大小
- 📈 消息总数、通道数量
- ⏱️ 记录时长、开始/结束时间
- 📡 每个通道的详细信息（消息数、帧率、数据大小）

### parse_mcap.py - 完整解析工具

提供以下功能：

#### 1. 分析 MCAP 结构

```python
from parse_mcap import analyze_mcap_structure

analyze_mcap_structure("路径/到/文件.mcap")
```

#### 2. 提取消息统计

```python
from parse_mcap import extract_messages_by_topic

messages = extract_messages_by_topic(
    "路径/到/文件.mcap",
    topic_filter=["/robot/left_camera/color/image_raw"],  # 可选，过滤特定topic
    max_messages=1000  # 可选，限制消息数量
)
```

#### 3. 提取摄像头帧

```python
from parse_mcap import extract_camera_frames

extract_camera_frames(
    "路径/到/文件.mcap",
    output_dir="输出目录",
    topic_filter=None,  # 自动检测所有摄像头topic
    frame_interval=30   # 每30帧保存一次
)
```

#### 4. 比较多个文件

```python
from parse_mcap import compare_mcap_files

compare_mcap_files([
    "0.mcap",
    "50.mcap", 
    "100.mcap"
])
```

## 🔧 使用 mcap-cli 命令行工具

### 安装

```bash
pip install mcap-cli
```

### 常用命令

```bash
# 查看文件信息
mcap info ../QA_Feature_CaseDesign/4_Mcap\ Data/output-20260129/0.mcap

# 列出所有通道
mcap list ../QA_Feature_CaseDesign/4_Mcap\ Data/output-20260129/0.mcap

# 查看消息详情
mcap cat ../QA_Feature_CaseDesign/4_Mcap\ Data/output-20260129/0.mcap

# 查看特定通道
mcap cat ../QA_Feature_CaseDesign/4_Mcap\ Data/output-20260129/0.mcap --topics /robot/env_camera/color/image_raw

# 导出为 JSON
mcap cat ../QA_Feature_CaseDesign/4_Mcap\ Data/output-20260129/0.mcap --format json > output.json
```

## 📝 Python API 使用示例

### 基本读取

```python
from mcap.reader import make_reader

with open("路径/到/文件.mcap", "rb") as f:
    reader = make_reader(f)
    
    for schema, channel, message in reader.iter_messages():
        print(f"Topic: {channel.topic}")
        print(f"Timestamp: {message.log_time}")
        print(f"Data size: {len(message.data)} bytes")
```

### 获取文件摘要

```python
from mcap.reader import make_reader

with open("路径/到/文件.mcap", "rb") as f:
    reader = make_reader(f)
    summary = reader.get_summary()
    
    print(f"消息数: {summary.statistics.message_count}")
    print(f"通道数: {summary.statistics.channel_count}")
    
    for channel_id, channel in summary.channels.items():
        print(f"通道: {channel.topic}")
```

### 提取图像帧

```python
from mcap.reader import make_reader
import cv2
import numpy as np

with open("路径/到/文件.mcap", "rb") as f:
    reader = make_reader(f)
    
    for schema, channel, message in reader.iter_messages():
        if 'camera' in channel.topic:
            # 假设是压缩的 JPEG 图像
            img_data = np.frombuffer(message.data, dtype=np.uint8)
            img = cv2.imdecode(img_data, cv2.IMREAD_COLOR)
            
            if img is not None:
                # 保存或显示图像
                cv2.imwrite(f"frame_{message.log_time}.jpg", img)
```

### 按时间范围筛选

```python
from mcap.reader import make_reader

with open("路径/到/文件.mcap", "rb") as f:
    reader = make_reader(f)
    
    start_time = None
    for schema, channel, message in reader.iter_messages():
        if start_time is None:
            start_time = message.log_time
        
        # 只读取前5秒的数据
        if message.log_time - start_time > 5e9:  # 5秒（纳秒）
            break
        
        # 处理消息...
```

## 📖 数据集说明

三组测试数据：

- **0.mcap**: 第一组测试数据
- **50.mcap**: 第二组测试数据
- **100.mcap**: 第三组测试数据

每个 MCAP 文件包含三个摄像头的同步数据：
- 🎥 环境摄像头（env_camera）
- 🎥 左摄像头（left_camera）
- 🎥 右摄像头（right_camera）

对应的文件夹中已包含提取好的视频文件，可以直接播放查看。

## ❓ 常见问题

### Q: MCAP 文件和视频文件有什么区别？

- **MCAP 文件**: 原始传感器数据，包含时间戳、元数据等完整信息，适合精确分析
- **视频文件**: 已编码压缩的视频，方便直接播放查看，但丢失了精确时间戳等信息

### Q: 如何只提取某一个摄像头的数据？

使用 `topic_filter` 参数：

```python
extract_messages_by_topic(
    "0.mcap",
    topic_filter=["/robot/left_camera/color/image_raw"]
)
```

### Q: 提取图像帧失败怎么办？

1. 确保安装了 opencv-python: `pip install opencv-python`
2. 检查消息格式是否是压缩图像（JPEG/PNG）
3. 可能需要根据实际的消息格式调整解析代码

### Q: 如何可视化 MCAP 数据？

推荐使用 [Foxglove Studio](https://foxglove.dev/)，这是一个专业的机器人数据可视化工具，支持直接打开 MCAP 文件并实时播放。

## 🔗 参考资料

- [MCAP 官方文档](https://mcap.dev/)
- [mcap Python 库](https://github.com/foxglove/mcap/tree/main/python)
- [Foxglove Studio](https://foxglove.dev/) - 可视化工具

## 📧 支持

如有问题，请联系 QA 团队。
