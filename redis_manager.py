#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Redis 配置管理工具"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shared.redis_config import get_redis_config, reload_redis_config


def show_config():
    config = get_redis_config()
    print("\n当前 Redis 配置:")
    print("=" * 50)
    print(f"配置文件位置: {config.get_config_file_path()}")
    print(f"启用状态: {'✓ 已启用' if config.enabled else '✗ 未启用'}")
    print(f"服务器地址: {config.host}:{config.port}")
    print(f"数据库编号: {config.db}")
    print(f"密码: {'已设置' if config.password else '未设置'}")
    print("=" * 50)


def test_connection():
    config = get_redis_config()
    print("\n测试 Redis 连接...")
    print("=" * 50)
    if config.test_connection():
        print("✓ 连接成功！")
    else:
        print("✗ 连接失败")
    print("=" * 50)


def enable_redis():
    config = get_redis_config()
    config.config["enabled"] = True
    config.save_config()
    print("\n✓ Redis 已启用")
    show_config()


def disable_redis():
    config = get_redis_config()
    config.config["enabled"] = False
    config.save_config()
    print("\n✓ Redis 已禁用")
    show_config()


def set_host():
    config = get_redis_config()
    host = input("请输入 Redis 服务器地址 (默认: localhost): ").strip() or "localhost"
    config.config["host"] = host
    config.save_config()
    print(f"\n✓ 服务器地址已设置为: {host}")


def set_port():
    config = get_redis_config()
    port_str = input("请输入 Redis 端口 (默认: 6379): ").strip() or "6379"
    try:
        port = int(port_str)
        config.config["port"] = port
        config.save_config()
        print(f"\n✓ 端口已设置为: {port}")
    except ValueError:
        print("\n✗ 无效的端口号")


def set_db():
    config = get_redis_config()
    db_str = input("请输入数据库编号 (0-15, 默认: 0): ").strip() or "0"
    try:
        db = int(db_str)
        if 0 <= db <= 15:
            config.config["db"] = db
            config.save_config()
            print(f"\n✓ 数据库编号已设置为: {db}")
        else:
            print("\n✗ 数据库编号必须在 0-15 之间")
    except ValueError:
        print("\n✗ 无效的数据库编号")


def set_password():
    config = get_redis_config()
    password = input("请输入 Redis 密码 (留空表示无密码): ").strip()
    config.config["password"] = password if password else None
    config.save_config()
    print(f"\n✓ 密码已{'设置' if password else '清除'}")


def clear_collected_ids():
    from shared.models import Pin
    confirm = input("\n⚠️  确认清除所有已收集的 Pin ID？(yes/no): ").strip().lower()
    if confirm == "yes":
        Pin.clear_collected()
        print("\n✓ 已清除所有已收集的 Pin ID")
    else:
        print("\n✗ 操作已取消")


def show_stats():
    from shared.models import Pin, get_redis_client
    
    print("\n统计信息:")
    print("=" * 50)
    print(f"内存中已收集 Pin 数: {Pin.get_collected_count()}")
    
    config = get_redis_config()
    if config.enabled:
        client = get_redis_client()
        if client:
            try:
                redis_count = client.scard("pinterest:collected_pin_ids")
                print(f"Redis 中已收集 Pin 数: {redis_count}")
            except Exception as e:
                print(f"Redis 查询失败: {e}")
    print("=" * 50)


def main_menu():
    while True:
        print("\n" + "=" * 50)
        print("Redis 配置管理工具")
        print("=" * 50)
        print("1. 查看当前配置")
        print("2. 测试连接")
        print("3. 启用 Redis")
        print("4. 禁用 Redis")
        print("5. 设置服务器地址")
        print("6. 设置端口")
        print("7. 设置数据库编号")
        print("8. 设置密码")
        print("9. 查看统计信息")
        print("10. 清除已收集 Pin ID")
        print("0. 退出")
        print("=" * 50)
        
        choice = input("请选择操作 (0-10): ").strip()
        
        if choice == "1":
            show_config()
        elif choice == "2":
            test_connection()
        elif choice == "3":
            enable_redis()
        elif choice == "4":
            disable_redis()
        elif choice == "5":
            set_host()
        elif choice == "6":
            set_port()
        elif choice == "7":
            set_db()
        elif choice == "8":
            set_password()
        elif choice == "9":
            show_stats()
        elif choice == "10":
            clear_collected_ids()
        elif choice == "0":
            print("\n再见！")
            break
        else:
            print("\n✗ 无效的选择")


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n操作已取消")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
