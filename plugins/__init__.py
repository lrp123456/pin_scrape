"""Pinterest 插件包

将原 scraper.py (3573行) 拆分为:
  - plugin.py    : 插件主类，实现 ScraperPlugin 接口
  - navigator.py : 页面导航、滚动、模态框操作
  - collector.py : Pin 收集、批量处理、AI 筛选
  - extractor.py : 数据提取（DOM/JSON/模态框）
  - auth.py      : 登录、Cookie 管理
"""

from plugins.pinterest.plugin import PinterestPlugin


def register():
    from core.engine import register_plugin
    register_plugin("pinterest", PinterestPlugin)
