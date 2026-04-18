#!/bin/bash
# Pinterest Scraper - Chrome 配置测试脚本

echo "=========================================="
echo "Pinterest Scraper - 配置验证测试"
echo "=========================================="
echo ""

# 测试 1: 检查容器内的 Chrome 配置
echo "📋 测试 1: 检查 Docker volume 挂载"
echo "----------------------------------------"
if docker exec n8n-python-runner test -d /home/node/.chrome-profile; then
    echo "✅ Chrome 配置目录存在"
    echo ""
    echo "文件列表:"
    docker exec n8n-python-runner ls -lh /home/node/.chrome-profile/Default/Network/
    echo ""
else
    echo "❌ Chrome 配置目录不存在"
    echo "请检查 docker-compose.yml 的 volume 配置"
    exit 1
fi

# 测试 2: 检查 Cookies 文件
echo "📋 测试 2: 检查 Cookies 文件"
echo "----------------------------------------"
if docker exec n8n-python-runner test -f /home/node/.chrome-profile/Default/Network/Cookies; then
    SIZE=$(docker exec n8n-python-runner stat -c%s /home/node/.chrome-profile/Default/Network/Cookies)
    echo "✅ Cookies 文件存在 (${SIZE} bytes)"
    echo ""
else
    echo "❌ Cookies 文件不存在"
    exit 1
fi

# 测试 3: 运行简单爬取测试
echo "📋 测试 3: 测试爬虫运行（5个 pin）"
echo "----------------------------------------"
echo "正在运行: python main.py -q 'test' -n 5 --connect --auto-launch --chrome-profile /home/node/.chrome-profile --no-headless"
echo ""

docker exec -it n8n-python-runner python /home/node/scripts/pinterest-scraper/main.py \
    -q "test" \
    -n 5 \
    --connect \
    --auto-launch \
    --chrome-profile /home/node/.chrome-profile \
    --no-headless \
    --debug

TEST_RESULT=$?

echo ""
echo "=========================================="
if [ $TEST_RESULT -eq 0 ]; then
    echo "✅ 所有测试通过！"
    echo ""
    echo "Chrome 配置已成功加载，可以正常使用。"
    echo ""
    echo "下一步："
    echo "1. 在 n8n 工作流中配置参数:"
    echo "   --chrome-profile /home/node/.chrome-profile"
    echo "2. 开始正常爬取任务"
else
    echo "❌ 测试失败"
    echo ""
    echo "可能的原因："
    echo "1. Chrome 配置文件损坏或不完整"
    echo "2. Pinterest 需要重新登录"
    echo "3. Chrome 进程启动失败"
    echo ""
    echo "请查看上面的错误信息进行排查。"
fi
echo "=========================================="
