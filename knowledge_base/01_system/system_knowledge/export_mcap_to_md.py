#!/usr/bin/env python3
"""
MCAP 数据导出到 Markdown 工具
解析 MCAP 文件并将每个通道的消息样本写入 MD 文件
"""

from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory
import os
import json
from datetime import datetime
from pathlib import Path


def parse_message_data(message_data, encoding):
    """
    解析消息数据
    """
    try:
        if encoding == "cdr":
            # CDR 编码的数据，尝试转换为可读格式
            # 返回原始数据的摘要信息
            return f"二进制数据 (大小: {len(message_data)} 字节)"
        elif encoding == "json":
            return json.loads(message_data.decode('utf-8'))
        else:
            # 尝试解码为字符串
            try:
                return message_data.decode('utf-8')
            except:
                return f"二进制数据 (大小: {len(message_data)} 字节)"
    except Exception as e:
        return f"解析失败: {str(e)}"


def format_message_for_md(msg_data, schema_name="Unknown"):
    """
    格式化消息数据为 Markdown 友好格式
    """
    if isinstance(msg_data, dict):
        lines = []
        for key, value in msg_data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"  - **{key}**: `{json.dumps(value, ensure_ascii=False)}`")
            else:
                lines.append(f"  - **{key}**: `{value}`")
        return "\n".join(lines)
    elif isinstance(msg_data, str):
        return f"  - {msg_data}"
    else:
        return f"  - `{msg_data}`"


def export_mcap_to_markdown(mcap_path, output_md_path, samples_per_channel=3):
    """
    解析 MCAP 文件并导出到 Markdown
    
    Args:
        mcap_path: MCAP 文件路径
        output_md_path: 输出的 MD 文件路径
        samples_per_channel: 每个通道显示的消息样本数量
    """
    print(f"正在解析 MCAP 文件: {mcap_path}")
    
    if not os.path.exists(mcap_path):
        print(f"错误：文件不存在 - {mcap_path}")
        return
    
    # 收集数据
    file_size = os.path.getsize(mcap_path) / (1024 * 1024)  # MB
    channels_data = {}
    file_stats = {
        'size': file_size,
        'message_count': 0,
        'channel_count': 0,
        'start_time': None,
        'end_time': None,
        'duration': 0
    }
    
    decoder_factory = DecoderFactory()
    
    with open(mcap_path, "rb") as f:
        reader = make_reader(f, decoder_factories=[decoder_factory])
        
        # 获取摘要信息
        try:
            summary = reader.get_summary()
            if summary and summary.statistics:
                stats = summary.statistics
                file_stats['message_count'] = stats.message_count
                file_stats['channel_count'] = stats.channel_count
                
                if stats.message_start_time and stats.message_end_time:
                    file_stats['start_time'] = datetime.fromtimestamp(stats.message_start_time / 1e9)
                    file_stats['end_time'] = datetime.fromtimestamp(stats.message_end_time / 1e9)
                    file_stats['duration'] = (stats.message_end_time - stats.message_start_time) / 1e9
        except Exception as e:
            print(f"警告: 无法读取文件摘要 - {e}")
        
        # 遍历消息
        print("正在读取消息...")
        for schema, channel, message in reader.iter_messages():
            topic = channel.topic
            
            # 初始化通道数据
            if topic not in channels_data:
                channels_data[topic] = {
                    'channel_id': channel.id,
                    'schema': schema.name if schema else "Unknown",
                    'encoding': channel.message_encoding,
                    'message_count': 0,
                    'samples': []
                }
            
            channels_data[topic]['message_count'] += 1
            
            # 收集样本消息
            if len(channels_data[topic]['samples']) < samples_per_channel:
                msg_info = {
                    'sequence': message.sequence,
                    'timestamp': datetime.fromtimestamp(message.log_time / 1e9),
                    'log_time_ns': message.log_time,
                    'data_size': len(message.data)
                }
                
                # 尝试解析消息内容
                try:
                    # 使用 ROS2 解码器
                    if schema and channel.message_encoding == "cdr":
                        decoder = decoder_factory.decoder_for(
                            message_encoding=channel.message_encoding,
                            schema=schema
                        )
                        decoded_msg = decoder(message.data)
                        msg_info['content'] = decoded_msg
                    else:
                        msg_info['content'] = parse_message_data(message.data, channel.message_encoding)
                except Exception as e:
                    msg_info['content'] = f"解析失败: {str(e)}"
                
                channels_data[topic]['samples'].append(msg_info)
    
    # 生成 Markdown 文件
    print(f"正在生成 Markdown 文件: {output_md_path}")
    
    with open(output_md_path, 'w', encoding='utf-8') as f:
        # 写入标题和文件信息
        f.write(f"# MCAP 数据分析报告\n\n")
        f.write(f"**文件**: `{os.path.basename(mcap_path)}`  \n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n\n")
        
        f.write(f"## 文件概览\n\n")
        f.write(f"- **文件大小**: {file_stats['size']:.2f} MB\n")
        f.write(f"- **消息总数**: {file_stats['message_count']:,}\n")
        f.write(f"- **通道数量**: {len(channels_data)}\n")
        
        if file_stats['start_time'] and file_stats['end_time']:
            f.write(f"- **记录时长**: {file_stats['duration']:.2f} 秒\n")
            f.write(f"- **开始时间**: {file_stats['start_time'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
            f.write(f"- **结束时间**: {file_stats['end_time'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
        
        f.write(f"\n---\n\n")
        
        # 写入通道列表
        f.write(f"## 通道列表\n\n")
        f.write(f"| 序号 | 通道名称 | 消息类型 | 消息数量 | 编码格式 |\n")
        f.write(f"|------|----------|----------|----------|----------|\n")
        
        for idx, (topic, data) in enumerate(sorted(channels_data.items()), 1):
            f.write(f"| {idx} | `{topic}` | `{data['schema']}` | {data['message_count']:,} | {data['encoding']} |\n")
        
        f.write(f"\n---\n\n")
        
        # 写入每个通道的详细信息和消息样本
        f.write(f"## 通道详细信息\n\n")
        
        for idx, (topic, data) in enumerate(sorted(channels_data.items()), 1):
            f.write(f"### {idx}. {topic}\n\n")
            f.write(f"**基本信息**:\n")
            f.write(f"- **通道 ID**: {data['channel_id']}\n")
            f.write(f"- **消息类型**: `{data['schema']}`\n")
            f.write(f"- **编码格式**: {data['encoding']}\n")
            f.write(f"- **消息总数**: {data['message_count']:,}\n")
            
            if data['message_count'] > 0 and file_stats['duration'] > 0:
                fps = data['message_count'] / file_stats['duration']
                f.write(f"- **平均频率**: {fps:.2f} Hz\n")
            
            f.write(f"\n**消息样本** (显示 {len(data['samples'])} / {data['message_count']} 条):\n\n")
            
            # 写入消息样本
            for msg_idx, sample in enumerate(data['samples'], 1):
                f.write(f"#### 样本 {msg_idx}\n\n")
                f.write(f"```yaml\n")
                f.write(f"序列号: {sample['sequence']}\n")
                f.write(f"时间戳: {sample['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
                f.write(f"数据大小: {sample['data_size']:,} 字节\n")
                f.write(f"```\n\n")
                
                # 写入消息内容
                content = sample['content']
                if hasattr(content, '__dict__'):
                    # ROS2 消息对象
                    f.write(f"**消息内容**:\n\n")
                    f.write(f"```python\n")
                    for attr in dir(content):
                        if not attr.startswith('_'):
                            try:
                                value = getattr(content, attr)
                                if not callable(value):
                                    f.write(f"{attr}: {value}\n")
                            except:
                                pass
                    f.write(f"```\n\n")
                elif isinstance(content, dict):
                    f.write(f"**消息内容**:\n\n")
                    f.write(f"```json\n")
                    f.write(json.dumps(content, indent=2, ensure_ascii=False))
                    f.write(f"\n```\n\n")
                elif isinstance(content, str):
                    f.write(f"**消息内容**: {content}\n\n")
                else:
                    f.write(f"**消息内容**: `{content}`\n\n")
            
            f.write(f"---\n\n")
    
    print(f"✅ 导出完成！")
    print(f"   输出文件: {output_md_path}")
    print(f"   总通道数: {len(channels_data)}")
    print(f"   总消息数: {sum(d['message_count'] for d in channels_data.values())}")


def main():
    """
    主函数
    """
    # MCAP 文件路径
    mcap_path = "/Users/wanxin/PycharmProjects/WORK/Prismax/_local_data/qa_prismax/mcap_output/output-20260129/0.mcap"
    
    # 输出 MD 文件路径
    output_md_path = "/Users/wanxin/PycharmProjects/WORK/Prismax/0_QA_PrismaX/knowledge_base/03_tools_and_studies/mcap_analysis/0_mcap_分析.md"
    
    # 每个通道显示的消息样本数量
    samples_per_channel = 3
    
    # 执行导出
    export_mcap_to_markdown(mcap_path, output_md_path, samples_per_channel)


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║           MCAP to Markdown 导出工具                          ║
║           将 MCAP 数据导出为可读的 Markdown 文档             ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
