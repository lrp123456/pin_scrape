"""天津住宅户型图爬虫插件

实现 PipelinePlugin 接口，三阶段管道:
  1. 住建委 → 提取住宅项目备案名
  2. 房天下 → 备案名转宣传名
  3. 多源户型图 → 用宣传名搜索并下载户型图
"""

from plugins.tianjin.plugin import TianjinPlugin


def register():
    from core.engine import register_plugin
    register_plugin("tianjin", TianjinPlugin)
