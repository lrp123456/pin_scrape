# Pinterest Scraper - 错误排查指南

## 404 Not Found 错误

### 可能的原因

#### 1. 脚本路径问题

**症状：** 运行命令时提示 "The resource you are requesting could not be found"

**原因：** Docker volume 映射不正确，脚本文件不在容器中

**诊断：**
```bash
# 检查脚本是否存在
docker exec n8n-python-runner ls -la /home/node/scripts/pinterest-scraper/

# 如果显示 "No such file or directory"，说明路径有问题
```

**解决方案：**

**步骤 1：检查 docker-compose.yml**

确保 `python-runner` 服务有正确的 volume 映射：

```yaml
services:
  python-runner:
    volumes:
      - ./docker/scripts:/home/node/scripts
      # 确保这一行存在
```

**步骤 2：检查本地脚本位置**

脚本应该在以下位置之一：

```
选项 A (推荐):
C:\Users\王\Desktop\scripts\docker\scripts\pinterest-scraper\main.py

选项 B:
C:\Users\王\Desktop\pinterest-scraper\main.py
```

**步骤 3：复制脚本到正确位置**

如果脚本在 `C:\Users\王\Desktop\pinterest-scraper\`：

```bash
# 创建目录
mkdir -p /mnt/c/Users/王/Desktop/scripts/docker/scripts

# 复制整个项目
cp -r /mnt/c/Users/王/Desktop/pinterest-scraper /mnt/c/Users/王/Desktop/scripts/docker/scripts/

# 重启容器
cd /mnt/c/Users/王/Desktop/scripts
docker-compose restart python-runner
```

**步骤 4：验证路径**

```bash
# 在容器内检查
docker exec n8n-python-runner ls -la /home/node/scripts/pinterest-scraper/

# 应该看到 main.py, scraper.py 等文件
```

---

#### 2. Pinterest URL 访问问题

**症状：** Chrome 启动后显示 404 错误

**原因：**
- Pinterest URL 被重定向
- 网络问题
- 地区限制（kr.pinterest.com）

**解决方案：**

修改 `scraper.py` 中的 BASE_URL：

```python
# 从
BASE_URL = "https://kr.pinterest.com/search/pins/"

# 改为
BASE_URL = "https://www.pinterest.com/search/pins/"
```

或：

```python
# 根据你的地区选择
BASE_URL = "https://pinterest.com/search/pins/"  # 美国
BASE_URL = "https://in.pinterest.com/search/pins/"  # 印度
BASE_URL = "https://www.pinterest.jp/search/pins/"  # 日本
```

---

#### 3. Chromium 未正确安装

**症状：** Chrome 启动失败

**诊断：**
```bash
docker exec n8n-python-runner which chromium
# 应该返回路径，如 /usr/bin/chromium
```

**解决方案：**
```bash
# 重新构建镜像
cd /mnt/c/Users/王/Desktop/scripts
docker-compose build python-runner --no-cache
docker-compose up -d python-runner
```

---

#### 4. Chrome 配置损坏

**症状：** Chrome 启动但无法加载页面

**解决方案：**

```bash
# 1. 清除旧的 Chrome 配置
docker exec n8n-python-runner rm -rf /home/node/.chrome-profile/Default

# 2. 重新复制配置
cd /mnt/c/Users/王/Desktop/scripts
cp -r "/mnt/c/Users/王/AppData/Local/Google/Chrome/User Data/Default" ./data/chrome-profile/
chmod -R 777 ./data/chrome-profile

# 3. 重启容器
docker-compose restart python-runner
```

---

## 运行诊断

### 步骤 1：运行诊断脚本

```bash
cd /mnt/c/Users/王/Desktop/pinterest-scraper
./diagnose.sh
```

这会检查：
- ✅ 容器状态
- ✅ 脚本路径
- ✅ Chrome 配置
- ✅ Chromium 安装
- ✅ 网络连接
- ✅ 输出目录
- ✅ Python 依赖

### 步骤 2：查看详细日志

```bash
# 查看容器日志
docker logs n8n-python-runner --tail 100

# 实时查看日志
docker logs -f n8n-python-runner
```

### 步骤 3：手动测试

进入容器手动测试：

```bash
# 进入容器
docker exec -it n8n-python-runner bash

# 检查环境
ls -la /home/node/scripts/
ls -la /home/node/.chrome-profile/

# 手动运行脚本
cd /home/node/scripts/pinterest-scraper
python main.py -q "test" -n 3 --connect --auto-launch --chrome-profile /home/node/.chrome-profile --debug
```

---

## 常见错误及解决

### 错误 1: "No such file or directory: '/home/node/scripts/pinterest-scraper/main.py'"

**原因：** 脚本不在容器中

**解决：**
```bash
# 检查本地路径
ls -la /mnt/c/Users/王/Desktop/scripts/docker/scripts/

# 如果为空，复制脚本
cp -r /mnt/c/Users/王/Desktop/pinterest-scraper /mnt/c/Users/王/Desktop/scripts/docker/scripts/

# 重启容器
cd /mnt/c/Users/王/Desktop/scripts
docker-compose restart python-runner
```

### 错误 2: "Permission denied"

**原因：** 权限不足

**解决：**
```bash
# 设置权限
chmod -R 777 /mnt/c/Users/王/Desktop/scripts/docker/scripts/pinterest-scraper
chmod -R 777 /mnt/c/Users/王/Desktop/scripts/data/chrome-profile

# 在容器内也设置
docker exec n8n-python-runner chmod -R 777 /home/node/.chrome-profile
```

### 错误 3: "Chromium failed to launch"

**原因：** Chromium 未安装或依赖缺失

**解决：**
```bash
# 检查 Chromium
docker exec n8n-python-runner which chromium

# 如果未安装，重新构建镜像
cd /mnt/c/Users/王/Desktop/scripts
docker-compose build python-runner --no-cache
```

### 错误 4: "需要 Pinterest 登录"

**原因：** Cookies 过期或配置文件损坏

**解决：**

按照 `CHROME_PROFILE_SETUP.md` 重新复制 Chrome 配置：

```bash
# 1. 关闭 Chrome（Windows）
taskkill /F /IM chrome.exe

# 2. 重新复制配置
cd /mnt/c/Users/王/Desktop/scripts
cp -r "/mnt/c/Users/王/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies" ./data/chrome-profile/Default/Network/
cp -r "/mnt/c/Users/王/AppData/Local/Google/Chrome/User Data/Default/Login Data" ./data/chrome-profile/Default/

# 3. 设置权限
chmod -R 777 ./data/chrome-profile

# 4. 重启容器
docker-compose restart python-runner
```

---

## 获取详细错误信息

### 方法 1: 使用 --debug 标志

```bash
docker exec -it n8n-python-runner python /home/node/scripts/pinterest-scraper/main.py \
  -q "test" \
  -n 3 \
  --connect \
  --auto-launch \
  --chrome-profile /home/node/.chrome-profile \
  --no-headless \
  --debug
```

这会：
- 保存截图到 `debug_screenshot.png`
- 保存 HTML 到 `debug_data.json`
- 显示详细的执行日志

### 方法 2: 检查输出文件

```bash
# 查看调试截图
docker cp n8n-python-runner:/tmp/debug_screenshot.png ./

# 查看调试 JSON
docker cp n8n-python-runner:/tmp/debug_data.json ./
cat debug_data.json | head -100
```

### 方法 3: 查看 Chrome 日志

```bash
# 查看 Chrome 的标准输出
docker exec n8n-python-runner cat /tmp/chrome.log 2>/dev/null || echo "No Chrome log found"
```

---

## 快速修复清单

按照以下顺序检查：

```bash
# 1. 运行诊断
cd /mnt/c/Users/王/Desktop/pinterest-scraper
./diagnose.sh

# 2. 检查脚本路径
docker exec n8n-python-runner ls -la /home/node/scripts/pinterest-scraper/

# 3. 检查 Chrome 配置
docker exec n8n-python-runner ls -la /home/node/.chrome-profile/Default/Network/

# 4. 测试网络
docker exec n8n-python-runner curl -I https://pinterest.com

# 5. 如果都正常，运行测试
docker exec -it n8n-python-runner python /home/node/scripts/pinterest-scraper/main.py \
  -q "test" -n 3 --connect --auto-launch \
  --chrome-profile /home/node/.chrome-profile --debug
```

---

## 联系支持

如果以上方法都无法解决问题，请提供：

1. **诊断脚本输出**：`./diagnose.sh` 的完整输出
2. **完整错误信息**：包含错误堆栈
3. **日志文件**：`docker logs n8n-python-runner --tail 100`
4. **环境信息**：
   ```bash
   docker --version
   docker-compose --version
   docker exec n8n-python-runner python --version
   ```

这将帮助我们更快地定位问题。

---

## 预防措施

为避免 404 错误：

1. ✅ 确保 volume 映射正确
2. ✅ 定期更新 Chrome 配置
3. ✅ 检查网络连接
4. ✅ 使用 `--debug` 标志查看详细信息
5. ✅ 定期重启容器保持环境清洁
