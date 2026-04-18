# Pinterest Scraper - Chrome 配置设置完成

## ✅ 已完成的步骤

### 1. Chrome 配置文件已复制
源路径: `C:\Users\王\AppData\Local\Google\Chrome\User Data\Default\`
目标路径:
- `C:\Users\王\Desktop\pinterest-scraper\data\chrome-profile\`
- `C:\Users\王\Desktop\scripts\data\chrome-profile\`

已复制的文件:
```
✓ Login Data (40K) - 登录信息
✓ Web Data (192K) - 表单数据和偏好
✓ Preferences (64K) - 浏览器偏好设置
✓ Secure Preferences (18K) - 安全偏好
✓ Network/Cookies (480K) - Cookie（包含 Pinterest 登录状态）
```

### 2. 权限已设置
- `chmod -R 777 ./data/chrome-profile` ✅

---

## 🔧 还需要完成的步骤

### 步骤 1: 修改 docker-compose.yml

在 `C:\Users\王\Desktop\scripts\docker-compose.yml` 的 `python-runner` 服务中添加 volume：

```yaml
services:
  python-runner:
    volumes:
      # ... 现有 volumes ...
      # ⭐ 添加这一行
      - ./data/chrome-profile:/home/node/.chrome-profile
```

### 步骤 2: 重启 Docker 容器

```bash
cd C:\Users\王\Desktop\scripts
docker-compose restart python-runner
```

### 步骤 3: 验证配置

```bash
# 检查 volume 是否正确挂载
docker exec n8n-python-runner ls -la /home/node/.chrome-profile/Default/Network/

# 应该看到:
# -rw-r--r-- 1 node node 480K Apr 16 09:48 Cookies
```

### 步骤 4: 运行测试

**方法 A: 使用测试脚本（推荐）**

```bash
cd C:\Users\王\Desktop\pinterest-scraper
./test_chrome_profile.sh
```

**方法 B: 手动测试**

```bash
# 进入容器
docker exec -it n8n-python-runner bash

# 在容器内运行
python /home/node/scripts/pinterest-scraper/main.py \
  -q "test" \
  -n 5 \
  --connect \
  --auto-launch \
  --chrome-profile /home/node/.chrome-profile \
  --no-headless \
  --debug
```

---

## 📝 使用方法

### 在宿主机上运行

```bash
cd C:\Users\王\Desktop\pinterest-scraper
python main.py -q "现代简约" -n 100 --connect --auto-launch \
  --chrome-profile ./data/chrome-profile
```

### 在 Docker 容器中运行

```bash
docker exec n8n-python-runner python /home/node/scripts/pinterest-scraper/main.py \
  -q "现代简约" \
  -n 100 \
  --connect \
  --auto-launch \
  --chrome-profile /home/node/.chrome-profile
```

### 在 n8n 工作流中调用

**HTTP Request 节点配置：**

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

## ⚠️ 重要注意事项

### 1. Chrome 必须关闭才能复制文件

如果需要重新复制配置：
```bash
# 关闭 Chrome
taskkill /F /IM chrome.exe

# 重新复制
cp -r "/c/Users/王/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies" \
  ./data/chrome-profile/Default/Network/
```

### 2. 登录状态有效期

- Pinterest 的登录状态通常持续 30-90 天
- 如果爬虫提示需要登录，重复上述步骤重新复制配置
- 建议定期（每月）更新 Chrome 配置

### 3. 隐私和安全

- `Cookies` 文件包含敏感信息，请妥善保管
- 不要将 `./data/chrome-profile` 提交到 Git 仓库
- 添加到 `.gitignore`:
  ```
  data/chrome-profile/
  ```

---

## 🔍 故障排查

### 问题 1: "Chrome 启动失败"

**检查：**
```bash
docker exec n8n-python-runner which chromium
```

**解决：**
```bash
cd C:\Users\王\Desktop\scripts
docker-compose build python-runner
docker-compose up -d python-runner
```

### 问题 2: "Permission denied"

**检查：**
```bash
docker exec n8n-python-runner ls -la /home/node/.chrome-profile/Default/Network/
```

**解决：**
```bash
chmod -R 777 C:\Users\王\Desktop\scripts\data\chrome-profile
docker-compose restart python-runner
```

### 问题 3: "需要 Pinterest 登录"

**原因：** Cookies 过期或损坏

**解决：**
1. 在宿主机上打开 Chrome 并访问 pinterest.com
2. 确认已登录 Pinterest
3. 关闭 Chrome
4. 重新复制配置文件（见上文）

---

## 📚 相关文档

- [Docker 部署指南](DOCKER_DEPLOYMENT.md) - 完整的 Docker 部署文档
- [n8n 工作流示例](N8N_WORKFLOW_EXAMPLES.md) - n8n 集成示例
- [主文档](README.md) - 项目概述和基础使用

---

## ✨ 下一步

1. ✅ 完成上述剩余步骤（修改 docker-compose.yml、重启容器）
2. ✅ 运行测试脚本验证配置
3. ✅ 开始在 n8n 中创建工作流
4. ✅ 定期更新 Chrome 配置以保持登录状态

如有问题，请参考故障排查部分或查看详细文档。
