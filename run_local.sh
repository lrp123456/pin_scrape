#!/bin/bash
# Pinterest Scraper - 宿主机完整运行脚本
# 用法: ./run_local.sh [关键词] [数量] [最小saves]

set -e

# 参数
QUERY="${1:-现代简约}"
MAX_PINS="${2:-50}"
MIN_SAVES="${3:-10}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OUTPUT_DIR="$SCRIPT_DIR/output/$(date +%Y%m%d_%H%M%S)_${QUERY}"

echo "=========================================="
echo "Pinterest Scraper - 完整爬取"
echo "=========================================="
echo ""
echo "搜索关键词: $QUERY"
echo "爬取数量: $MAX_PINS"
echo "最小 Saves: $MIN_SAVES"
echo "输出目录: $OUTPUT_DIR"
echo ""

# 检查 Chrome 配置
CHROME_PROFILE="$SCRIPT_DIR/data/chrome-profile"
if [ -d "$CHROME_PROFILE/Default" ]; then
    echo "✅ 使用 Chrome 配置: $CHROME_PROFILE"
    USE_PROFILE=true
else
    echo "⚠️  未找到 Chrome 配置，将使用临时配置"
    echo "   如需登录 Pinterest，请参考 CHROME_PROFILE_SETUP.md"
    USE_PROFILE=false
fi
echo ""

# 运行爬取
echo "📋 开始爬取..."
echo "----------------------------------------"

if [ "$USE_PROFILE" = true ]; then
    python3 main.py \
      -q "$QUERY" \
      -n "$MAX_PINS" \
      --min-saves "$MIN_SAVES" \
      -o "$OUTPUT_DIR" \
      --chrome-profile "$CHROME_PROFILE" \
      --connect \
      --auto-launch
else
    python3 main.py \
      -q "$QUERY" \
      -n "$MAX_PINS" \
      --min-saves "$MIN_SAVES" \
      -o "$OUTPUT_DIR"
fi

RESULT=$?

echo ""
echo "=========================================="
if [ $RESULT -eq 0 ]; then
    echo "✅ 爬取完成！"
    echo ""
    echo "结果文件:"
    ls -lh "$OUTPUT_DIR/"
    echo ""
    echo "数据摘要:"
    if [ -f "$OUTPUT_DIR/data.json" ]; then
        python3 -c "
import json
with open('$OUTPUT_DIR/data.json') as f:
    data = json.load(f)
    print(f\"总 Pins: {data.get('total_pins', 0)}\")
    print(f\"主 Pins: {data.get('main_pins', 0)}\")
    print(f\"相似 Pins: {data.get('similar_pins', 0)}\")
    print(f\"筛选后: {data.get('filtered_pins', 0)}\")
"
    fi
    echo ""
    echo "图片目录: $OUTPUT_DIR/images/"
else
    echo "❌ 爬取失败"
fi
echo "=========================================="
