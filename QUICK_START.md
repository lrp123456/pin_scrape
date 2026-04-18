# Pinterest Scraper - 快速使用指南

## ✅ 配置状态

**Chrome 配置已成功设置：**
- ✅ Cookies 文件已挂载（480KB）
- ✅ 登录数据已复制
- ✅ Docker volume 已配置

**配置路径：**
- 宿主机：`C:\Users\王\AppData\Local\Google\Chrome\User Data\Default\`
- Docker：`/home/node/.chrome-profile/`

---

## 🚀 快速开始

### 方法 1：使用便捷脚本（推荐）

```bash
cd C:\Users\王\Desktop\pinterest-scraper

# 运行测试（3个 pin，快速验证）
./quick_test.sh

# 正式爬取
./run_in_docker.sh "现代简约" 100 50
# 参数：关键词 数量 最小saves
```

### 方法 2：直接运行命令

**测试运行（3个 pin）：**
```bash
docker exec -it n8n-python-runner python /home/node/scripts/pinterest-scraper/main.py \
  -q "test" \
  -n 3 \
  --connect \
  --auto-launch \
  --chrome-profile /home/node/.chrome-profile \
  --debug
```

**正式爬取：**
```bash
docker exec -it n8n-python-runner python /home/node/scripts/pinterest-scraper/main.py \
  -q "现代简约" \
  -n 100 \
  --connect \
  --auto-launch \
  --chrome-profile /home/node/.chrome-profile \
  --min-saves 50 \
  -o /tmp/results/pinterest
```

### 方法 3：在 n8n 工作流中调用

**HTTP Request 节点：**
```json
{
  "method": "POST",
  "url": "http://python-runner:5000/execute",
  "body": {
    "script": "pinterest-scraper/n8n_integration_example.py",
    "args": {
      "query": "现代简约",
      "max_pins": 100,
      "chrome_profile": "/home/node/.chrome-profile",
      "min_saves": 50
    }
  }
}
```

---

## 📊 查看结果

```bash
# 列出输出文件
docker exec n8n-python-runner ls -lh /tmp/results/pinterest/

# 查看 JSON 内容
docker exec n8n-python-runner cat /tmp/results/pinterest/data.json

# 复制到宿主机
docker cp n8n-python-runner:/tmp/results/pinterest ./output
```

---

## ⚙️ 参数说明

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `-q` | 搜索关键词 | 必需 | `"现代简约"` |
| `-n` | 最大爬取数量 | 100 | `100` |
| `--chrome-profile` | Chrome 配置路径 | 临时目录 | `/home/node/.chrome-profile` |
| `--min-saves` | 最小 save 数筛选 | 0 | `50` |
| `--min-likes` | 最小点赞数筛选 | 0 | `10` |
| `--min-comments` | 最小评论数筛选 | 0 | `5` |
| `-o` | 输出目录 | `./output` | `/tmp/results/pinterest` |
| `--debug` | 调试模式 | 关闭 | - |

---

## 🔄 更新登录状态

如果爬虫提示需要登录，重新复制配置：

```bash
# 1. 关闭 Chrome（宿主机）
taskkill /F /IM chrome.exe

# 2. 确认已在 Chrome 中登录 Pinterest

# 3. 重新复制配置
cd C:\Users\王\Desktop\scripts

cp -r "/c/Users/王/AppData/Local/Google/Chrome/User Data/Default/Login Data" ./data/chrome-profile/Default/
cp -r "/c/Users/王/AppData/Local/Google/Chrome/User Data/Default/Login Data-journal" ./data/chrome-profile/Default/
cp -r "/c/Users/王/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies" ./data/chrome-profile/Default/Network/
cp -r "/c/Users/王/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies-journal" ./data/chrome-profile/Default/Network/

chmod -R 777 ./data/chrome-profile

# 4. 重启容器
docker-compose restart python-runner
```

---

## 📝 常见问题

### Q1: 提示"需要 Pinterest 登录"

**原因：** 登录状态过期或配置文件损坏

**解决：** 按照上面的"更新登录状态"步骤重新复制配置

### Q2: 爬取速度很慢

**正常情况：** 脚本采用拟人化浏览模式，模拟真实用户：
- 每个操作间隔 2-8 秒
- 每 20 个 pin 休息 15-30 秒
- 随机点击查看 pin 详情

**100 个 pin 大约需要 15-30 分钟**

### Q3: 爬取结果少于预期

**可能原因：**
- Pinterest 没有足够的相关内容
- 筛选条件过严（`--min-saves` 太高）
- 被反爬限制

**建议：** 降低筛选条件或分批爬取

### Q4: 想要批量爬取多个关键词

**方案 A：手动循环**
```bash
for keyword in "现代简约" "北欧风格" "中式装修"; do
  ./run_in_docker.sh "$keyword" 50 30
  sleep 1800  # 休息 30 分钟
done
```

**方案 B：使用 n8n 工作流**

参考 `N8N_WORKFLOW_EXAMPLES.md` 的批量爬取示例

---

## 📚 相关文档

- `README.md` - 项目概述和基础使用
- `DOCKER_DEPLOYMENT.md` - Docker 部署详细指南
- `N8N_WORKFLOW_EXAMPLES.md` - n8n 工作流集成示例
- `CHROME_PROFILE_SETUP.md` - Chrome 配置详细说明

---

## ✨ 特色功能

1. **拟人化浏览** - 模拟真实用户，降低封禁风险
2. **相似推荐探索** - 自动扩展相关内容
3. **持久化登录** - 配置一次，长期使用
4. **智能去重** - 自动去除重复 pin
5. **灵活筛选** - 按多种条件过滤结果

---

## 🎯 使用建议

1. **首次使用**：运行 `./quick_test.sh` 验证配置
2. **日常使用**：使用 `./run_in_docker.sh` 快速启动
3. **定时任务**：在 n8n 中创建定时工作流
4. **定期更新**：每月更新 Chrome 配置保持登录状态
5. **合理频率**：避免短时间内大量爬取，建议间隔 30 分钟以上

---

## 🆘 获取帮助

遇到问题时：

1. 查看本文档的"常见问题"部分
2. 运行 `./quick_test.sh` 获取诊断信息
3. 查看 Docker 日志：`docker logs n8n-python-runner`
4. 参考详细文档：`DOCKER_DEPLOYMENT.md` 和 `CHROME_PROFILE_SETUP.md`

---

**祝使用愉快！🎉**
