#!/bin/bash
# MCAP 数据解析演示脚本

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           MCAP 数据解析工具 - 快速开始                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# 检查是否安装了依赖
echo "📦 检查 Python 依赖..."
if ! python3 -c "import mcap" 2>/dev/null; then
    echo "❌ 未安装 mcap 库"
    echo "正在安装依赖..."
    pip3 install -r requirements.txt
    echo ""
fi

# 检查数据文件是否存在
DATA_DIR="../Feature_CaseDesign/4_Mcap Data/output-20260129"
if [ ! -d "$DATA_DIR" ]; then
    echo "❌ 错误: 数据目录不存在: $DATA_DIR"
    echo "请确保数据文件在正确的位置"
    exit 1
fi

echo "✅ 数据目录存在"
echo ""

# 菜单选择
echo "请选择要执行的操作:"
echo "  1) 快速查看 0.mcap 文件信息"
echo "  2) 快速查看 50.mcap 文件信息"
echo "  3) 快速查看 100.mcap 文件信息"
echo "  4) 完整分析所有文件并比较"
echo "  5) 退出"
echo ""
read -p "请输入选项 (1-5): " choice

case $choice in
    1)
        echo ""
        echo "正在分析 0.mcap..."
        python3 quick_view.py "$DATA_DIR/0.mcap"
        ;;
    2)
        echo ""
        echo "正在分析 50.mcap..."
        python3 quick_view.py "$DATA_DIR/50.mcap"
        ;;
    3)
        echo ""
        echo "正在分析 100.mcap..."
        python3 quick_view.py "$DATA_DIR/100.mcap"
        ;;
    4)
        echo ""
        echo "正在进行完整分析..."
        python3 parse_mcap.py
        ;;
    5)
        echo "退出"
        exit 0
        ;;
    *)
        echo "无效的选项"
        exit 1
        ;;
esac

echo ""
echo "完成！"
