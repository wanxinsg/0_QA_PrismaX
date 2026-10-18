#!/usr/bin/env python3
"""
交互式 MCAP 关节数据查看器
"""

import sys
from pathlib import Path
from mcap.reader import make_reader
import struct


def parse_cdr_joint_state(data):
    """解析 CDR 编码的 JointState 消息"""
    try:
        offset = 0
        offset += 4  # CDR header
        
        # Header
        if len(data) < offset + 8:
            return None
        sec = struct.unpack_from('<i', data, offset)[0]
        offset += 4
        nanosec = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        timestamp = sec + nanosec / 1e9
        
        # Skip frame_id
        if len(data) < offset + 4:
            return None
        string_len = struct.unpack_from('<I', data, offset)[0]
        offset += 4 + string_len
        if offset % 4 != 0:
            offset += 4 - (offset % 4)
        
        # Parse names
        if len(data) < offset + 4:
            return None
        name_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        
        names = []
        for _ in range(name_count):
            if len(data) < offset + 4:
                break
            name_len = struct.unpack_from('<I', data, offset)[0]
            offset += 4
            if len(data) < offset + name_len:
                break
            name = data[offset:offset + name_len].decode('utf-8').rstrip('\x00')
            names.append(name)
            offset += name_len
            if offset % 4 != 0:
                offset += 4 - (offset % 4)
        
        # Parse positions
        if len(data) < offset + 4:
            return {"timestamp": timestamp, "names": names, "positions": [], "velocities": [], "efforts": []}
        pos_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        
        positions = []
        for _ in range(pos_count):
            if len(data) < offset + 8:
                break
            pos = struct.unpack_from('<d', data, offset)[0]
            positions.append(pos)
            offset += 8
        
        # Parse velocities
        velocities = []
        if len(data) >= offset + 4:
            vel_count = struct.unpack_from('<I', data, offset)[0]
            offset += 4
            for _ in range(vel_count):
                if len(data) < offset + 8:
                    break
                vel = struct.unpack_from('<d', data, offset)[0]
                velocities.append(vel)
                offset += 8
        
        # Parse efforts
        efforts = []
        if len(data) >= offset + 4:
            eff_count = struct.unpack_from('<I', data, offset)[0]
            offset += 4
            for _ in range(eff_count):
                if len(data) < offset + 8:
                    break
                eff = struct.unpack_from('<d', data, offset)[0]
                efforts.append(eff)
                offset += 8
        
        return {
            "timestamp": timestamp,
            "names": names,
            "positions": positions,
            "velocities": velocities,
            "efforts": efforts
        }
    except:
        return None


def get_topics(mcap_path):
    """获取所有关节状态 topics"""
    topics = []
    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        summary = reader.get_summary()
        
        if summary and summary.channels:
            for channel_id, channel in summary.channels.items():
                if 'joint_states' in channel.topic:
                    topics.append(channel.topic)
    
    return sorted(topics)


def view_joint_data(mcap_path, topic, num_messages=5):
    """查看关节数据"""
    print(f"\n{'='*100}")
    print(f"📊 通道: {topic}")
    print(f"{'='*100}\n")
    
    message_count = 0
    first_time = None
    
    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        
        for schema, channel, message in reader.iter_messages():
            if channel.topic != topic:
                continue
            
            message_count += 1
            
            if first_time is None:
                first_time = message.log_time
            
            relative_time = (message.log_time - first_time) / 1e9
            
            joint_state = parse_cdr_joint_state(message.data)
            
            if joint_state and message_count == 1:
                # 只在第一条消息显示关节名称
                print(f"🔧 关节列表: {', '.join(joint_state['names'])}")
                print(f"🔢 关节数量: {len(joint_state['names'])}")
                print()
            
            if joint_state:
                print(f"⏱️  消息 #{message_count} | 时间: {relative_time:.3f}s")
                print(f"   位置 (rad/°): ", end="")
                for i, pos in enumerate(joint_state['positions']):
                    print(f"[{i}]{pos:7.3f}({pos*180/3.14159:6.1f}°) ", end="")
                print()
                
                if joint_state['velocities']:
                    print(f"   速度 (rad/s): ", end="")
                    for i, vel in enumerate(joint_state['velocities']):
                        print(f"[{i}]{vel:7.3f} ", end="")
                    print()
                
                if joint_state['efforts']:
                    print(f"   力矩 (Nm):    ", end="")
                    for i, eff in enumerate(joint_state['efforts']):
                        print(f"[{i}]{eff:7.3f} ", end="")
                    print()
                
                print()
            
            if message_count >= num_messages:
                break
    
    if message_count == 0:
        print(f"❌ 未找到数据")
    else:
        print(f"✅ 显示了 {message_count} 条消息")


def interactive_menu():
    """交互式菜单"""
    # 查找 MCAP 文件
    data_dir = Path("../QA_Feature_CaseDesign/3_Mcap Data/output-20260129")
    
    if not data_dir.exists():
        print("❌ 数据目录不存在")
        return
    
    mcap_files = sorted(data_dir.glob("*.mcap"))
    
    if not mcap_files:
        print("❌ 未找到 MCAP 文件")
        return
    
    print("\n" + "="*100)
    print("🤖 MCAP 关节数据交互式查看器")
    print("="*100)
    
    # 选择文件
    print("\n📁 可用的 MCAP 文件:")
    for i, f in enumerate(mcap_files, 1):
        size = f.stat().st_size / (1024 * 1024)
        print(f"  {i}. {f.name} ({size:.2f} MB)")
    
    try:
        choice = input(f"\n选择文件 (1-{len(mcap_files)}) [默认: 1]: ").strip()
        file_idx = int(choice) - 1 if choice else 0
        
        if file_idx < 0 or file_idx >= len(mcap_files):
            file_idx = 0
        
        mcap_file = mcap_files[file_idx]
        print(f"\n✅ 已选择: {mcap_file.name}")
        
        # 获取所有关节状态通道
        topics = get_topics(str(mcap_file))
        
        if not topics:
            print("❌ 未找到关节状态通道")
            return
        
        while True:
            print("\n" + "-"*100)
            print("📡 可用的关节状态通道:")
            for i, topic in enumerate(topics, 1):
                topic_name = topic.split('/')[-2]  # 提取简短名称
                print(f"  {i}. {topic_name:30s} ({topic})")
            
            print(f"  0. 退出")
            
            choice = input(f"\n选择通道 (0-{len(topics)}): ").strip()
            
            if not choice or choice == '0':
                print("\n👋 退出程序")
                break
            
            try:
                topic_idx = int(choice) - 1
                
                if topic_idx < 0 or topic_idx >= len(topics):
                    print("❌ 无效的选择")
                    continue
                
                topic = topics[topic_idx]
                
                # 询问显示数量
                num_str = input("显示多少条消息? [默认: 5]: ").strip()
                num_messages = int(num_str) if num_str else 5
                
                # 显示数据
                view_joint_data(str(mcap_file), topic, num_messages)
                
                # 继续查看其他通道
                continue_choice = input("\n是否继续查看其他通道? (y/n) [默认: y]: ").strip().lower()
                if continue_choice == 'n':
                    print("\n👋 退出程序")
                    break
            
            except ValueError:
                print("❌ 请输入有效的数字")
                continue
    
    except KeyboardInterrupt:
        print("\n\n👋 程序被中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")


if __name__ == "__main__":
    try:
        interactive_menu()
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
