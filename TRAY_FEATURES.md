# 托盘应用状态更新功能说明

## ✅ 已修复：状态自动更新

### 问题
之前服务状态显示需要手动刷新或访问网页才能更新。

### 解决方案
添加了自动状态更新机制：

1. **后台更新线程**：每2秒自动刷新状态
2. **动态图标颜色**：根据服务状态改变图标颜色
3. **实时菜单更新**：状态文本自动更新

### 功能特性

#### 1. 动态图标颜色

托盘图标会根据服务状态自动变色：

| 状态 | 图标颜色 | 说明 |
|------|---------|------|
| 服务运行中 | 🟢 绿色 | API服务正常工作 |
| 服务已停止 | ⚪ 灰色 | API服务未运行 |

**使用效果**：
- 用户可以一眼看出服务状态
- 不需要点开菜单查看
- 状态变化时图标自动变色

#### 2. 实时状态显示

**菜单状态文本**：
```
服务状态: 运行中 - idle 0%      ← 服务运行中，空闲状态
服务状态: 运行中 - collecting 45%  ← 正在爬取，45%进度
服务状态: 已停止                ← 服务未运行
```

**更新频率**：每2秒自动刷新

#### 3. 状态检测内容

托盘应用会定期查询API服务：

```python
# 查询端点
GET http://localhost:8000/api/progress

# 返回数据
{
  "running": true,
  "stage": "collecting",
  "percentage": 45,
  "current": 45,
  "total": 100,
  "query": "简约风格",
  "message": "已收集 45/100 个Pin"
}
```

## 使用体验改进

### 改进前
1. 启动服务后需要手动刷新
2. 不知道服务是否真的在运行
3. 必须访问网页才能看到进度

### 改进后
1. ✅ 图标颜色直接指示状态
2. ✅ 状态文本实时更新
3. ✅ 进度百分比直接显示
4. ✅ 无需任何手动操作

## 工作原理

### 状态更新流程

```
托盘应用启动
    ↓
创建更新线程（后台运行）
    ↓
每2秒执行：
    ├─ 查询 API /progress 接口
    ├─ 更新菜单状态文本
    └─ 根据状态更新图标颜色
    ↓
循环执行直到退出
```

### 线程安全

- 使用独立后台线程，不阻塞UI
- 线程设置为daemon，应用退出时自动结束
- 异常捕获，不会导致程序崩溃

## 性能影响

**资源占用**：
- CPU：几乎为0（每2秒一次轻量级HTTP请求）
- 内存：线程栈约1MB
- 网络：每2秒约1KB流量

**结论**：性能影响极小，可忽略不计。

## 故障排查

### 问题1：状态不更新

**可能原因**：
- API服务未启动
- 网络请求超时
- 防火墙阻止

**解决方法**：
```bash
# 检查API服务
访问 http://localhost:8000/health

# 查看日志
右键托盘 → 查看日志
```

### 问题2：图标颜色不变

**可能原因**：
- 图标文件被锁定
- PIL库问题

**解决方法**：
- 重启托盘应用
- 检查是否使用了自定义图标

## 技术实现

### 核心代码

```python
def _start_status_update(self):
    """启动状态更新线程"""
    def update_loop():
        while self._running:
            try:
                if self.icon:
                    # 更新菜单
                    self.icon.update_menu()

                    # 更新图标
                    new_icon = self._create_status_icon()
                    self.icon.icon = new_icon
            except Exception as e:
                print(f"状态更新出错: {e}")
            time.sleep(2)

    self._update_thread = threading.Thread(
        target=update_loop,
        daemon=True
    )
    self._update_thread.start()
```

### 动态图标生成

```python
def _create_status_icon(self, size=64):
    # 创建图像
    image = Image.new('RGB', (size, size), 'white')
    dc = ImageDraw.Draw(image)

    # 根据状态选择颜色
    if self.process_manager.is_running():
        bg_color = '#4CAF50'  # 绿色 - 运行中
    else:
        bg_color = '#9E9E9E'  # 灰色 - 已停止

    # 绘制图标
    dc.ellipse([8, 8, size-8, size-8], fill=bg_color)
    dc.text((20, 15), 'P', fill='white')

    return image
```

## 未来优化方向

1. **更多状态颜色**
   - 红色：错误状态
   - 黄色：警告状态
   - 蓝色：处理中

2. **动画效果**
   - 任务执行时图标闪烁
   - 进度变化动画

3. **通知提醒**
   - 任务完成时弹出通知
   - 错误时桌面提醒

---

**更新日期**: 2026-04-17
**版本**: 2.1.0
