# PrismaX Knowledge Base

本目录按主题组织 PrismaX 的系统说明、数据规范、分析工具、发布流程和专项研究。

## 目录导航

| 目录 | 内容 |
| --- | --- |
| [`01_system/`](./01_system/) | 系统架构、前后端逻辑、用户与 QA、上传下载、Tele-Op、积分等 |
| [`02_data_and_mcap/`](./02_data_and_mcap/) | 数据采集、MCAP 规范、QA 标准、配置、场景表和样例数据 |
| [`03_tools_and_studies/`](./03_tools_and_studies/) | MCAP 解析工具、分析报告、样例媒体和图像识别流程 |
| [`04_release_management/`](./04_release_management/) | 发布管理要求、流程优化方案及中英文交付文档 |

## 使用约定

- 新文档优先放入对应主题目录，避免直接堆放在本目录根层。
- 同一专题的文档、脚本、配置和样例数据放在同一子目录中。
- 工具生成物（如 `.DS_Store`、`__pycache__`、`*.pyc`）不作为知识库内容保存。
- 移动专题目录时保持其内部相对结构，避免破坏脚本和文档引用。

## 主要入口

- 系统知识：[`01_system/system_knowledge/`](./01_system/system_knowledge/)
- 数据与 MCAP 规范：[`02_data_and_mcap/standards_and_specs/`](./02_data_and_mcap/standards_and_specs/)
- 数据采集系统说明：[`02_data_and_mcap/datacollection.md`](./02_data_and_mcap/datacollection.md)
- MCAP 分析工具：[`03_tools_and_studies/mcap_analysis/README.md`](./03_tools_and_studies/mcap_analysis/README.md)
- 图像识别流程：[`03_tools_and_studies/image_recognition/image_recognitions_flow.md`](./03_tools_and_studies/image_recognition/image_recognitions_flow.md)
- 发布管理：[`04_release_management/`](./04_release_management/)
