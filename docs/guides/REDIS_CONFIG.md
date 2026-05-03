# Redis 配置使用指南

## 概述

项目现在支持通过外部配置文件 `redis_config.json` 来管理 Redis 连接，无需修改代码即可控制 Redis 的启用/禁用和连接参数。

---

## 配置文件位置

### 开发环境
```
项目根目录/redis_config.json
例如: C:\outputs\pinterest-scraper\redis_config.json
```

### 打包后（exe）
```
exe文件所在目录/redis_config.json
例如: C:\MyApp\redis_config.json
```

**重要**：配置文件会自动保存在程序所在目录，打包后依然有效！

---

## 配置文件格式

```json
{
  "enabled": false,
  "host": "localhost",
  "port": 6379,
  "db": 0,
  "password": null
}
```

### 配置项说明

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `enabled` | boolean | 是否启用 Redis | `false` |
| `host` | string | Redis 服务器地址 | `"localhost"` |
| `port` | number | Redis 服务器端口 | `6379` |
| `db` | number | Redis 数据库编号 (0-15) | `0` |
| `password` | string/null | Redis 密码（无密码填 `null`） | `null` |

---

## 使用方法

### 方法 1: 图形化配置工具（推荐）

运行配置管理工具：

```powershell
python redis_manager.py
```

**首次运行会显示配置文件位置**，例如：
```
配置文件位置: C:\outputs\pinterest-scraper\redis_config.json
```

菜单选项：
1. 查看当前配置
2. 测试连接
3. 启用 Redis
4. 禁用 Redis
5. 设置服务器地址
6. 设置端口
7. 设置数据库编号
8. 设置密码
9. 查看统计信息
10. 清除已收集 Pin ID

### 方法 2: 手动编辑配置文件

直接编辑 `redis_config.json`：

```json
{
  "enabled": true,
  "host": "192.168.1.100",
  "port": 6379,
  "db": 1,
  "password": "your_password"
}
```

保存后，下次运行爬虫时自动生效。

---

## 使用场景

### 场景 1: 禁用 Redis（默认）

```json
{
  "enabled": false
}
```

- 使用内存去重
- 程序重启后去重记录清空
- 适合临时测试

### 场景 2: 本地 Redis（无密码）

```json
{
  "enabled": true,
  "host": "localhost",
  "port": 6379,
  "db": 0,
  "password": null
}
```

- 连接本地 Redis
- 去重记录持久化
- 程序重启后保留

### 场景 3: 远程 Redis（有密码）

```json
{
  "enabled": true,
  "host": "192.168.1.100",
  "port": 6379,
  "db": 1,
  "password": "your_password"
}
```

- 连接远程 Redis
- 多台机器共享去重数据
- 适合分布式爬取

---

## 命令行使用

### 启动爬虫（自动读取配置）

```powershell
# 滚动模式
python main.py -q "设计" -n 100 --connect --auto-launch

# 探索模式
python main.py -q "设计" -n 50 --min-saves 100 --connect --auto-launch
```

爬虫会自动：
1. 读取 `redis_config.json`
2. 如果 `enabled=true`，连接 Redis
3. 如果连接失败，自动降级到内存模式

### 测试 Redis 连接

```powershell
python redis_manager.py
# 选择 2. 测试连接
```

---

## 托盘应用使用

托盘应用也会自动读取 `redis_config.json`：

1. 双击 `tray_app.exe`
2. 右键托盘图标 → 启动服务
3. 服务会自动使用配置文件中的 Redis 设置

---

## 常见问题

### Q: 修改配置后需要重启吗？

A: 是的，修改配置后需要重启爬虫或服务才能生效。

### Q: Redis 连接失败会怎样？

A: 自动降级到内存去重模式，不影响爬虫运行，但重启后去重记录会清空。

### Q: 如何清除已收集的 Pin ID？

A: 运行 `python redis_manager.py`，选择 "10. 清除已收集 Pin ID"。

### Q: 多台机器如何共享去重数据？

A: 配置所有机器连接到同一个 Redis 服务器，使用相同的 `db` 编号。

---

## 配置示例

### 示例 1: 开发环境（本地 Redis）

```json
{
  "enabled": true,
  "host": "localhost",
  "port": 6379,
  "db": 0,
  "password": null
}
```

### 示例 2: 生产环境（远程 Redis）

```json
{
  "enabled": true,
  "host": "redis.example.com",
  "port": 6379,
  "db": 1,
  "password": "prod_password_123"
}
```

### 示例 3: 测试环境（禁用 Redis）

```json
{
  "enabled": false
}
```

---

## 技术细节

### 去重机制

- **内存去重**：使用 Python `set()` 存储已收集的 Pin ID
- **Redis 去重**：使用 Redis `SET` 数据结构存储
- **混合模式**：启动时从 Redis 加载到内存，后续只查内存（极快）

### 性能

- 内存查询：O(1)，微秒级
- Redis 写入：异步，不阻塞主流程
- 启动加载：一次性，后续不再访问 Redis

---

## 故障排查

### 连接失败

```
⚠️  Redis 连接失败：Connection refused
   将使用内存去重模式（重启后会重置）
```

**解决方法**：
1. 检查 Redis 是否启动：`redis-cli ping`
2. 检查配置文件中的 host 和 port
3. 检查防火墙设置

### 密码错误

```
⚠️  Redis 连接失败：NOAUTH Authentication required
```

**解决方法**：
在配置文件中设置正确的密码。

---

## 总结

✅ **配置文件**：`redis_config.json`  
✅ **管理工具**：`python redis_manager.py`  
✅ **自动降级**：Redis 失败时使用内存模式  
✅ **无需重启**：修改配置后重启爬虫即可生效
