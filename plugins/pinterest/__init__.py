"""Pinterest 插件注册"""

from plugins.pinterest.plugin import PinterestPlugin


def register():
    from core.engine import register_plugin
    register_plugin("pinterest", PinterestPlugin)
