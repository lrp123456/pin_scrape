"""Pinterest Cookie 管理 CLI

用法:
    python cookie_cli.py list              列出所有Cookie账号
    python cookie_cli.py check             检查所有Cookie是否有效
    python cookie_cli.py check --id 1      检查指定ID的Cookie
    python cookie_cli.py delete --id 1     删除指定ID的Cookie
    python cookie_cli.py add --label xxx   添加一个待登录账号
    python cookie_cli.py ensure --n 3      确保至少有3个Cookie账号
    python cookie_cli.py release --worker worker-1  释放Worker绑定
"""

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from shared.cookie_manager import CookieManager

STATUS_MAP = {1: "✅ 有效", 0: "❌ 失效", -1: "⏳ 待登录"}


def cmd_list(args):
    cm = CookieManager()
    accounts = cm.get_all_accounts()

    if not accounts:
        print("\n📭 数据库中没有Cookie账号")
        print("   使用 python cookie_cli.py add --label <标签>  添加账号")
        print("   使用 python cookie_login.py                  登录并保存Cookie\n")
        return

    print(f"\n{'='*80}")
    print(f"  Pinterest Cookie 账号列表  (共 {len(accounts)} 个)")
    print(f"{'='*80}")

    valid = sum(1 for a in accounts if a["status"] == 1)
    invalid = sum(1 for a in accounts if a["status"] == 0)
    pending = sum(1 for a in accounts if a["status"] == -1)
    print(f"  有效: {valid}  |  失效: {invalid}  |  待登录: {pending}")
    print(f"{'-'*80}")
    print(f"  {'ID':<5} {'标签':<18} {'状态':<12} {'Worker':<12} {'最后检查':<20}")
    print(f"{'-'*80}")

    for acc in accounts:
        status_label = STATUS_MAP.get(acc["status"], "未知")
        worker = acc.get("worker_id") or "-"
        last_check = acc.get("last_check") or "-"
        label = acc.get("label") or "-"
        print(f"  {acc['id']:<5} {label:<18} {status_label:<12} {worker:<12} {last_check:<20}")

    print(f"{'='*80}\n")


def _cookie_auth_pinterest(pw, storage_state) -> bool:
    """参考 social-auto-upload-main 的 cookie_auth 模式：
    1. 加载 storage_state 创建浏览器上下文
    2. 访问必须登录才能看到的页面（settings）
    3. 检测是否出现登录元素 → 出现则失效
    4. 超时5秒未到达目标页也视为失效
    """
    browser = None
    try:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(storage_state=storage_state)
        page = context.new_page()

        page.goto("https://www.pinterest.com/settings/", timeout=15000)

        try:
            page.wait_for_url("**/settings/**", timeout=5000)
        except Exception:
            pass

        current_url = page.url

        if "/login" in current_url or "/signup" in current_url:
            return False

        login_text_found = False
        for text in ["登录", "Log in", "Sign up", "注册"]:
            try:
                count = page.get_by_text(text, exact=True).count()
                if count > 0:
                    login_text_found = True
                    break
            except Exception:
                pass

        if login_text_found:
            return False

        try:
            login_btn = page.locator('[data-test-id="login-button"]')
            signup_btn = page.locator('[data-test-id="signup-button"]')
            if login_btn.count() > 0 or signup_btn.count() > 0:
                return False
        except Exception:
            pass

        return True

    except Exception:
        return False
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass


def cmd_check(args):
    cm = CookieManager()
    accounts = cm.get_all_accounts()

    if args.id:
        accounts = [a for a in accounts if a["id"] == args.id]
        if not accounts:
            print(f"\n❌ 未找到 ID={args.id} 的账号\n")
            return

    if not accounts:
        print("\n📭 数据库中没有Cookie账号\n")
        return

    print(f"\n{'='*80}")
    print(f"  Pinterest Cookie 有效性检查  (参考 social-auto-upload 校验模式)")
    print(f"{'='*80}\n")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ 需要安装 playwright: pip install playwright && playwright install chromium\n")
        return

    with sync_playwright() as pw:
        for acc in accounts:
            account_id = acc["id"]
            label = acc.get("label") or "-"
            status_before = STATUS_MAP.get(acc["status"], "未知")

            print(f"  检查账号 #{account_id} ({label})  当前状态: {status_before}")

            storage_state = cm.load_storage_state(account_id)
            if not storage_state:
                print(f"    → ⏳ 无 storage_state 文件，标记为待登录\n")
                cm.set_status(account_id, -1)
                continue

            cookie_count = len(storage_state.get("cookies", []))
            has_sess = any(c.get("name") == "_pinterest_sess" for c in storage_state.get("cookies", []))
            print(f"    → Cookie文件: {cookie_count} 个 cookie, _pinterest_sess: {'✓' if has_sess else '✗'}")
            print(f"    → 正在启动浏览器访问 /settings/ 验证...")

            is_valid = _cookie_auth_pinterest(pw, storage_state)

            if is_valid:
                cm.set_status(account_id, 1)
                print(f"    → ✅ Cookie 有效\n")
            else:
                cm.set_status(account_id, 0)
                print(f"    → ❌ Cookie 已失效（访问 /settings/ 被重定向到登录页）\n")

    print(f"{'='*80}")
    print(f"  检查完成。使用 python cookie_cli.py list 查看最新状态")
    print(f"{'='*80}\n")


def cmd_delete(args):
    if not args.id:
        print("\n❌ 请指定要删除的账号ID: python cookie_cli.py delete --id <ID>\n")
        return

    cm = CookieManager()
    success = cm.delete_account(args.id)
    if success:
        print(f"\n✅ 已删除账号 #{args.id}\n")
    else:
        print(f"\n❌ 未找到账号 #{args.id}\n")


def cmd_add(args):
    cm = CookieManager()
    account_id = cm.add_account(label=args.label or "")
    print(f"\n✅ 已创建待登录账号 #{account_id}")
    print(f"   使用 python cookie_login.py --id {account_id} 登录并保存Cookie\n")


def cmd_ensure(args):
    cm = CookieManager()
    accounts = cm.ensure_accounts_for_workers(args.n)
    valid = sum(1 for a in accounts if a["status"] == 1)
    pending = sum(1 for a in accounts if a["status"] == -1)
    print(f"\n✅ 当前共有 {len(accounts)} 个账号 (有效: {valid}, 待登录: {pending})")
    if pending > 0:
        print(f"   有 {pending} 个待登录账号，请使用 python cookie_login.py 登录\n")
    else:
        print()


def cmd_release(args):
    cm = CookieManager()
    if args.worker:
        cm.release_worker(args.worker)
        print(f"\n✅ 已释放 {args.worker} 的Cookie绑定\n")
    else:
        print("\n❌ 请指定Worker ID: python cookie_cli.py release --worker worker-1\n")


def main():
    parser = argparse.ArgumentParser(
        description="Pinterest Cookie 管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cookie_cli.py list                          列出所有Cookie
  python cookie_cli.py check                         检查所有Cookie有效性
  python cookie_cli.py check --id 1                  检查指定Cookie
  python cookie_cli.py add --label "我的账号"         添加待登录账号
  python cookie_cli.py delete --id 1                 删除指定账号
  python cookie_cli.py ensure --n 3                  确保至少3个Cookie
  python cookie_cli.py release --worker worker-1     释放Worker绑定
""",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    list_parser = subparsers.add_parser("list", help="列出所有Cookie账号")
    list_parser.set_defaults(func=cmd_list)

    check_parser = subparsers.add_parser("check", help="检查Cookie有效性")
    check_parser.add_argument("--id", type=int, help="指定账号ID")
    check_parser.set_defaults(func=cmd_check)

    delete_parser = subparsers.add_parser("delete", help="删除Cookie账号")
    delete_parser.add_argument("--id", type=int, required=True, help="账号ID")
    delete_parser.set_defaults(func=cmd_delete)

    add_parser = subparsers.add_parser("add", help="添加待登录账号")
    add_parser.add_argument("--label", type=str, default="", help="账号标签")
    add_parser.set_defaults(func=cmd_add)

    ensure_parser = subparsers.add_parser("ensure", help="确保Cookie数量足够")
    ensure_parser.add_argument("--n", type=int, default=1, help="Worker数量")
    ensure_parser.set_defaults(func=cmd_ensure)

    release_parser = subparsers.add_parser("release", help="释放Worker绑定")
    release_parser.add_argument("--worker", type=str, required=True, help="Worker ID")
    release_parser.set_defaults(func=cmd_release)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
