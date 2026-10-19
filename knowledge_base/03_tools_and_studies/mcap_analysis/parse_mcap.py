#!/usr/bin/env python3
"""
MCAP 数据解析工具
用于解析机器人三摄像头数据
"""

from mcap.reader import make_reader
import os
import json
from datetime import datetime
from pathlib import Path


def analyze_mcap_structure(mcap_path):
    """
    分析 MCAP 文件的结构，列出所有通道和消息类型
    """
    print(f"\n{'='*60}")
    print(f"分析文件: {mcap_path}")
    print(f"{'='*60}")
    
    if not os.path.exists(mcap_path):
        print(f"错误：文件不存在 - {mcap_path}")
        return None
    
    file_size = os.path.getsize(mcap_path) / (1024 * 1024)  # MB
    print(f"文件大小: {file_size:.2f} MB")
    
    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        
        try:
            summary = reader.get_summary()
            
            # 打印统计信息
            if summary and summary.statistics:
                stats = summary.statistics
                print(f"\n基本信息:")
                print(f"  消息总数: {stats.message_count}")
                print(f"  通道数量: {stats.channel_count}")
                print(f"  Schema 数量: {stats.schema_count}")
                
                if stats.message_start_time and stats.message_end_time:
                    start_time = stats.message_start_time / 1e9  # 转换为秒
                    end_time = stats.message_end_time / 1e9
                    duration = end_time - start_time
                    print(f"  记录时长: {duration:.2f} 秒")
                    print(f"  开始时间: {datetime.fromtimestamp(start_time)}")
                    print(f"  结束时间: {datetime.fromtimestamp(end_time)}")
            
            # 打印通道信息
            if summary and summary.channels:
                print(f"\n通道列表:")
                channel_info = {}
                for channel_id, channel in summary.channels.items():
                    print(f"  [{channel_id}] {channel.topic}")
                    print(f"      消息类型: {channel.message_encoding}")
                    print(f"      Schema ID: {channel.schema_id}")
                    channel_info[channel_id] = {
                        'topic': channel.topic,
                        'encoding': channel.message_encoding,
                        'schema_id': channel.schema_id
                    }
                
                return channel_info
            
            # 如果没有 summary，手动遍历消息
            print("\n正在遍历消息...")
            channels_seen = set()
            message_count = 0
            
            for schema, channel, message in reader.iter_messages():
                if channel.id not in channels_seen:
                    channels_seen.add(channel.id)
                    print(f"  发现通道: {channel.topic}")
                message_count += 1
                
                if message_count >= 100:  # 只遍历前100条消息作为样本
                    print(f"  (已遍历 {message_count} 条消息...)")
                    break
            
            print(f"\n总共发现 {len(channels_seen)} 个通道")
            
        except Exception as e:
            print(f"错误: {e}")
            return None


def extract_messages_by_topic(mcap_path, topic_filter=None, max_messages=None):
    """
    提取指定 topic 的消息
    
    Args:
        mcap_path: MCAP 文件路径
        topic_filter: 要提取的 topic 列表，None 表示提取所有
        max_messages: 最大提取消息数，None 表示提取所有
    """
    print(f"\n{'='*60}")
    print(f"提取消息: {mcap_path}")
    print(f"{'='*60}")
    
    messages_by_topic = {}
    
    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        
        count = 0
        for schema, channel, message in reader.iter_messages():
            topic = channel.topic
            
            # 过滤 topic
            if topic_filter and topic not in topic_filter:
                continue
            
            if topic not in messages_by_topic:
                messages_by_topic[topic] = []
            
            # 保存消息信息
            msg_info = {
                'timestamp': message.log_time,
                'sequence': message.sequence,
                'data_size': len(message.data),
                'publish_time': message.publish_time,
            }
            messages_by_topic[topic].append(msg_info)
            
            count += 1
            if max_messages and count >= max_messages:
                break
    
    # 打印统计
    print(f"\n提取的消息统计:")
    for topic, messages in messages_by_topic.items():
        print(f"  {topic}: {len(messages)} 条消息")
        if messages:
            first_time = messages[0]['timestamp'] / 1e9
            last_time = messages[-1]['timestamp'] / 1e9
            duration = last_time - first_time
            fps = len(messages) / duration if duration > 0 else 0
            print(f"    时长: {duration:.2f}s, 平均帧率: {fps:.2f} fps")
            print(f"    平均数据大小: {sum(m['data_size'] for m in messages) / len(messages) / 1024:.2f} KB")
    
    return messages_by_topic


def extract_camera_frames(mcap_path, output_dir, topic_filter=None, frame_interval=1):
    """
    从 MCAP 中提取摄像头帧并保存为图像
    
    Args:
        mcap_path: MCAP 文件路径
        output_dir: 输出目录
        topic_filter: 要提取的摄像头 topic 列表
        frame_interval: 帧间隔（每隔 N 帧保存一次）
    """
    print(f"\n{'='*60}")
    print(f"提取摄像头帧: {mcap_path}")
    print(f"{'='*60}")
    
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("错误: 需要安装 opencv-python")
        print("请运行: pip install opencv-python")
        return
    
    os.makedirs(output_dir, exist_ok=True)
    
    frame_counts = {}
    
    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        
        for schema, channel, message in reader.iter_messages():
            topic = channel.topic
            
            # 只处理摄像头数据
            if topic_filter and topic not in topic_filter:
                continue
            
            if 'camera' not in topic.lower() and 'image' not in topic.lower():
                continue
            
            if topic not in frame_counts:
                frame_counts[topic] = 0
            
            frame_counts[topic] += 1
            
            # 按间隔保存帧
            if frame_counts[topic] % frame_interval != 0:
                continue
            
            try:
                # 尝试解析图像数据
                # 假设是压缩图像数据
                img_data = np.frombuffer(message.data, dtype=np.uint8)
                img = cv2.imdecode(img_data, cv2.IMREAD_COLOR)
                
                if img is not None:
                    # 创建 topic 对应的子目录
                    topic_dir = os.path.join(output_dir, topic.replace('/', '_').replace('.', '_'))
                    os.makedirs(topic_dir, exist_ok=True)
                    
                    # 保存图像
                    timestamp = message.log_time
                    filename = f"{topic_dir}/frame_{timestamp}_{frame_counts[topic]:06d}.jpg"
                    cv2.imwrite(filename, img)
                    
                    if frame_counts[topic] == 1:
                        print(f"  {topic}: 开始提取帧...")
                    
            except Exception as e:
                if frame_counts[topic] == 1:
                    print(f"  {topic}: 解析失败 - {e}")
    
    print(f"\n提取结果:")
    for topic, count in frame_counts.items():
        saved_count = (count + frame_interval - 1) // frame_interval
        print(f"  {topic}: 处理 {count} 帧, 保存 {saved_count} 帧")


def compare_mcap_files(mcap_paths):
    """
    比较多个 MCAP 文件的结构
    """
    print(f"\n{'='*60}")
    print(f"比较 {len(mcap_paths)} 个 MCAP 文件")
    print(f"{'='*60}\n")
    
    all_info = {}
    for path in mcap_paths:
        name = os.path.basename(path)
        print(f"处理: {name}")
        all_info[name] = analyze_mcap_structure(path)
    
    # 打印比较结果
    print(f"\n{'='*60}")
    print("比较总结")
    print(f"{'='*60}")
    
    all_topics = set()
    for info in all_info.values():
        if info:
            for channel_info in info.values():
                all_topics.add(channel_info['topic'])
    
    print(f"\n所有发现的 topics:")
    for topic in sorted(all_topics):
        print(f"  - {topic}")


def main():
    """
    主函数 - 演示如何使用
    """
    # 设置数据路径 - 更新为相对于当前脚本的路径
    base_dir = Path(__file__).parent.parent / "QA_Feature_CaseDesign/3_Mcap Data/output-20260129"
    
    # 如果路径不存在，尝试其他可能的路径
    if not base_dir.exists():
        # 尝试直接在当前目录下查找
        base_dir = Path("output-20260129")
        if not base_dir.exists():
            print("❌ 错误: 找不到数据目录 'output-20260129'")
            print(f"请确保数据目录在以下位置之一:")
            print(f"  1. {Path(__file__).parent.parent / 'QA_Feature_CaseDesign/3_Mcap Data/output-20260129'}")
            print(f"  2. {Path(__file__).parent / 'output-20260129'}")
            print(f"\n或者直接指定 MCAP 文件路径运行单个文件分析:")
            print(f"  analyze_mcap_structure('路径/到/文件.mcap')")
            return
    
    print(f"✅ 找到数据目录: {base_dir}")
    
    # 1. 分析单个 MCAP 文件
    mcap_file = base_dir / "0.mcap"
    if mcap_file.exists():
        print("\n【步骤 1】分析 MCAP 文件结构")
        channel_info = analyze_mcap_structure(str(mcap_file))
        
        # 2. 提取消息统计
        print("\n【步骤 2】提取消息统计")
        messages = extract_messages_by_topic(
            str(mcap_file),
            topic_filter=None,  # 提取所有 topic
            max_messages=1000   # 限制最多1000条消息用于分析
        )
        
        # 3. 提取摄像头帧（可选，需要安装 opencv-python）
        # 取消下面的注释来提取图像帧
        # print("\n【步骤 3】提取摄像头帧")
        # extract_camera_frames(
        #     str(mcap_file),
        #     output_dir=str(base_dir / "0_extracted_frames"),
        #     topic_filter=None,  # 自动检测摄像头 topic
        #     frame_interval=30   # 每30帧保存一次
        # )
    else:
        print(f"❌ 文件不存在: {mcap_file}")
    
    # 4. 比较所有 MCAP 文件
    print("\n【步骤 4】比较所有 MCAP 文件")
    mcap_files = [
        str(base_dir / "0.mcap"),
        str(base_dir / "50.mcap"),
        str(base_dir / "100.mcap")
    ]
    mcap_files = [f for f in mcap_files if os.path.exists(f)]
    if mcap_files:
        compare_mcap_files(mcap_files)
    else:
        print("❌ 未找到 MCAP 文件")


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║           MCAP 数据解析工具 v1.0                             ║
║           三摄像头机器人数据分析                             ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
