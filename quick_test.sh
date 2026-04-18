#!/bin/bash
# Pinterest Scraper - 快速测试脚本

echo "=========================================="
echo "Pinterest Scraper - 配置测试"
echo "=========================================="
echo ""

# 测试 1: 检查 Chrome 配置
echo "📋 测试 1: 检查 Chrome 配置"
echo "----------------------------------------"
docker exec n8n-python-runner ls -lh /home/node/.chrome-profile/Default/Network/
if [ $? -eq 0 ]; then
  echo "✅ Chrome 配置存在"
else
  echo "❌ Chrome 配置不存在"
  exit 1
fi
echo ""

# 测试 2: 运行小型爬取
echo "📋 测试 2: 测试爬取（3个 pin）"
echo "----------------------------------------"
echo "命令: python main.py -q 'test' -n 3 --connect --auto-launch --chrome-profile /home/node/.chrome-profile --debug"
echo ""

docker exec -it n8n-python-runner python /home/node/scripts/pinterest-scraper/main.py \
  -q "test" \
  -n 3 \
  --connect \
  --auto-launch \
  --chrome-profile /home/node/.chrome-profile \
  --debug

TEST_RESULT=$?

echo ""
echo "=========================================="
if [ $TEST_RESULT -eq 0 ]; then
  echo "✅ 所有测试通过！"
  echo ""
  echo "配置已验证，可以正常使用。"
  echo ""
  echo "运行正式爬取："
  echo "  ./run_in_docker.sh \"现代简约\" 100 50"
  echo ""
  echo "或直接运行："
  echo "  docker exec -it n8n-python-runner python /home/node/scripts/pinterest-scraper/main.py \\"
  echo "    -q \"现代简约\" -n 100 --connect --auto-launch \\"
  echo "    --chrome-profile /home/node/.chrome-profile"
else
  echo "❌ 测试失败"
  echo ""
  echo "可能的原因："
  echo "1. Pinterest 登录状态已过期"
  echo "   - 解决：重新复制 Chrome 配置文件"
  echo "   - 参考：CHROME_PROFILE_SETUP.md"
  echo ""
  echo "2. Chrome 进程启动失败"
  echo "   - 检查：docker logs n8n-python-runner"
  echo ""
  echo "3. 网络问题"
  echo "   - 检查：容器是否可以访问互联网"
fi
echo "=========================================="
