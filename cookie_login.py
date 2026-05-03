"""Pinterest Cookie 登录工具

用法:
    python cookie_login.py                     登录并保存为新账号
    python cookie_login.py --id 1              验证/刷新指定ID账号的Cookie
    python cookie_login.py --label "我的账号"   登录并设置标签

流程:
  - 有已有Cookie: 先验证是否仍有效 → 有效则直接更新保存 → 失效则打开登录页
  - 无已有Cookie: 直接打开登录页等待手动登录
"""

import argparse
import json
import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shared.cookie_manager import CookieManager

DEBUG_DIR = Path(__file__).parent / "logs" / "debug" / "cookie_login"
COOKIES_DIR = Path(__file__).parent / "cookiesFile"


def _save_page_snapshot(page, label: str):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%H%M%S")

    try:
        html = page.content()
        out_path = DEBUG_DIR / f"{ts}_{label}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"  [快照] 已保存 {label} 页面: {out_path}")
    except Exception as e:
        print(f"  [快照] 保存 {label} 页面失败: {e}")

    try:
        page.screenshot(path=str(DEBUG_DIR / f"{ts}_{label}.png"))
    except Exception:
        pass


def _check_logged_in(page) -> bool:
    try:
        current_url = page.url
        if "/login" in current_url or "/signup" in current_url:
            return False

        result = page.evaluate("""
            () => {
                const loginSels = [
                    '[data-test-id="login-modal"]',
                    '[data-test-id="signup-button"]',
                    '[data-test-id="login-button"]',
                    '[data-test-id="unauth-bottom-login-button"]',
                ];
                for (const s of loginSels) {
                    if (document.querySelector(s)) return false;
                }

                const loggedInSels = [
                    '[data-test-id="pin"]',
                    'div[data-grid-item]',
                    '[data-test-id="homefeed-feed"]',
                    '[data-test-id="header-profile"]',
                    '[data-test-id="user-avatar"]',
                    '[data-test-id="nav-profile"]',
                    'a[href*="/settings/"]',
                    'a[href*="/_saved/"]',
                ];
                for (const s of loggedInSels) {
                    if (document.querySelector(s)) return true;
                }
                return false;
            }
        """)
        return bool(result)
    except Exception:
        return False


def _do_manual_login(page, context, cm, account_id):
    print("\n" + "=" * 60)
    print("  需要手动登录")
    print("=" * 60)
    print("\n请在浏览器中登录 Pinterest，完成后在终端按 Enter...\n")

    _save_page_snapshot(page, "before_login")

    manual_confirm = threading.Event()

    def _wait_for_enter():
        try:
            input()
            manual_confirm.set()
        except Exception:
            pass

    enter_thread = threading.Thread(target=_wait_for_enter, daemon=True)
    enter_thread.start()

    while not manual_confirm.is_set():
        time.sleep(1)

    print("\n👉 收到确认，正在保存...")

    _save_page_snapshot(page, "after_login")

    time.sleep(2)

    return _save_and_close(page, context, cm, account_id)


def _save_and_close(page, context, cm, account_id):
    try:
        storage_state = context.storage_state()
        cookie_count = len(storage_state.get("cookies", []))
        origin_count = len(storage_state.get("origins", []))
        pinterest_cookies = [c for c in storage_state.get("cookies", []) if "pinterest" in c.get("domain", "")]
    except Exception as e:
        print(f"\n❌ 保存 Cookie 失败: {e}")
        return False

    cm.update_storage_state(account_id, storage_state)

    print(f"\n{'='*60}")
    print(f"  Cookie 已保存到数据库")
    print(f"{'='*60}")
    print(f"  账号 ID:         #{account_id}")
    print(f"  总 Cookie 数:     {cookie_count}")
    print(f"  Pinterest Cookie:  {len(pinterest_cookies)}")
    print(f"  LocalStorage 源:  {origin_count}")
    print(f"  当前页面:         {page.url}")
    print(f"  状态:            ✅ 有效")
    print(f"{'='*60}\n")

    return True


def do_login(account_id: int = None, label: str = "", headless: bool = False):
    cm = CookieManager()

    existing_state = None
    if account_id:
        existing_state = cm.load_storage_state(account_id)
        if not existing_state:
            print(f"\n⚠️  账号 #{account_id} 无有效 storage_state，需要手动登录\n")
        else:
            cookie_count = len(existing_state.get("cookies", []))
            print(f"\n✅ 账号 #{account_id} 已有 {cookie_count} 个 cookie\n")
    else:
        account_id = cm.add_account(label=label)
        print(f"\n✅ 已创建新账号 #{account_id}\n")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ 需要安装 playwright: pip install playwright && playwright install chromium\n")
        return False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--lang=zh-CN",
                "--start-maximized",
            ],
        )

        context_kwargs = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "viewport": {"width": 1280, "height": 900},
        }

        if existing_state and existing_state.get("cookies"):
            state_file = COOKIES_DIR / f"_temp_{account_id}_state.json"
            state_file.write_text(json.dumps(existing_state, ensure_ascii=False), encoding="utf-8")
            context_kwargs["storage_state"] = str(state_file)
            print("[Cookie] 已加载已有Cookie，正在验证登录状态...\n")

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        # 有已有Cookie → 先访问首页验证是否仍有效
        if existing_state and existing_state.get("cookies"):
            page.goto("https://www.pinterest.com/", timeout=60000)
            time.sleep(3)

            logged_in = _check_logged_in(page)
            current_url = page.url

            if logged_in:
                print(f"✅ Cookie 仍然有效！当前页面: {current_url}")
                print("   正在更新 Cookie 到数据库...\n")
                result = _save_and_close(page, context, cm, account_id)
                browser.close()
                return result
            else:
                print(f"❌ Cookie 已失效（页面: {current_url}），需要重新登录")
                page.goto("https://www.pinterest.com/login/", timeout=60000)
                result = _do_manual_login(page, context, cm, account_id)
                browser.close()
                return result

        # 无已有Cookie → 直接打开登录页
        else:
            page.goto("https://www.pinterest.com/login/", timeout=60000)
            print(f"  已打开登录页: {page.url}")
            result = _do_manual_login(page, context, cm, account_id)
            browser.close()
            return result


def main():
    parser = argparse.ArgumentParser(
        description="Pinterest Cookie 登录工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cookie_login.py                     登录并保存为新账号
  python cookie_login.py --id 1              验证/刷新指定账号的Cookie
  python cookie_login.py --label "主号"       登录并设置标签
""",
    )
    parser.add_argument("--id", type=int, help="指定账号ID（验证/刷新Cookie）")
    parser.add_argument("--label", type=str, default="", help="账号标签")
    parser.add_argument("--headless", action="store_true", help="无头模式（不推荐）")

    args = parser.parse_args()

    do_login(account_id=args.id, label=args.label, headless=args.headless)


if __name__ == "__main__":
    main()
