#!/bin/bash
# Pinterest Scraper - Docker 快速启动脚本

# 默认参数
QUERY="${1:-现代简约}"
MAX_PINS="${2:-100}"
MIN_SAVES="${3:-50}"

echo "=========================================="
echo "Pinterest Scraper - Docker 运行"
echo "=========================================="
echo ""
echo "搜索关键词: $QUERY"
echo "爬取数量: $MAX_PINS"
echo "最小 saves: $MIN_SAVES"
echo ""
echo "使用 Chrome 配置: /home/node/.chrome-profile"
echo ""

# 运行爬虫
docker exec -it n8n-python-runner python /home/node/scripts/pinterest-scraper/main.py \
  -q "$QUERY" \
  -n "$MAX_PINS" \
  --connect \
  --auto-launch \
  --chrome-profile /home/node/.chrome-profile \
  --min-saves "$MIN_SAVES" \
  -o /tmp/results/pinterest

# 检查结果
if [ $? -eq 0 ]; then
  echo ""
  echo "=========================================="
  echo "✅ 爬取成功！"
  echo "=========================================="
  echo ""
  echo "结果文件:"
  docker exec n8n-python-runner ls -lh /tmp/results/pinterest/
  echo ""
  echo "查看 JSON:"
  echo "  docker exec n8n-python-runner cat /tmp/results/pinterest/data.json"
  echo ""
else
  echo ""
  echo "=========================================="
  echo "❌ 爬取失败"
  echo "=========================================="
  echo ""
  echo "请检查错误信息并参考故障排查文档"
fi
